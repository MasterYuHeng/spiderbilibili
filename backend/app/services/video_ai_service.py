from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

import jieba.analyse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.analysis import AiSummary
from app.models.enums import LogLevel, TaskStage
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video, VideoTextContent
from app.schemas.analysis import VideoAiSummaryDraft
from app.services.ai_client import (
    AiPromptBundle,
    AiStructuredResponse,
    AiSummaryClient,
    OpenAICompatibleAiClient,
)
from app.services.system_config_service import (
    get_ai_batch_defaults,
    get_ai_quality_control_defaults,
    get_ai_summary_defaults,
)
from app.services.task_log_service import create_task_log
from app.services.task_service import assert_task_execution_allowed

TEXT_SECTION_LABEL_PATTERN = re.compile(
    r"^Video (Description|Search Summary|Subtitle|Title):\s*$"
)
TEXT_WHITESPACE_PATTERN = re.compile(r"\s+")
TOPIC_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")
TOPIC_CLEANUP_PATTERN = re.compile(r"[^\w\u4e00-\u9fff]+")
TITLE_SPLIT_PATTERN = re.compile(r"[-_/｜丨:：·,，【】()\[\]]+")
MAX_ALLOWED_TOPIC_COUNT = 10
GENERIC_TOPIC_KEYS = {
    "unclassified",
    "unknown",
    "misc",
    "other",
    "others",
    "general",
    "topic",
    "topics",
    "视频",
    "内容",
    "总结",
    "主题",
    "话题",
    "相关内容",
    "视频主题",
    "其他",
    "其它",
    "未知",
    "未分类",
    "杂项",
}


@dataclass(slots=True)
class TaskAiAnalysisResult:
    total_count: int
    success_count: int
    failure_count: int
    fallback_count: int
    batch_count: int
    cached_count: int
    clipped_count: int


@dataclass(slots=True)
class _AiTarget:
    task_video: TaskVideo
    video: Video
    text_content: VideoTextContent
    ai_summary: AiSummary | None = None


@dataclass(slots=True)
class _AiExecutionOutcome:
    used_fallback: bool
    input_clipped: bool


class VideoAiService:
    def __init__(
        self,
        session: Session,
        *,
        ai_client: AiSummaryClient | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.ai_client = ai_client or OpenAICompatibleAiClient.from_settings()
        self.logger = get_logger(__name__)

    def analyze_task(
        self,
        task: CrawlTask,
        *,
        batch_size: int | None = None,
        expected_dispatch_generation: int | None = None,
    ) -> TaskAiAnalysisResult:
        all_targets = self._load_targets(task.id)
        batch_defaults = get_ai_batch_defaults(self.session)
        summary_defaults = get_ai_summary_defaults(self.session, self.settings)
        quality_defaults = get_ai_quality_control_defaults(self.session)
        resolved_batch_size = max(1, batch_size or batch_defaults["batch_size"])
        reusable_targets: list[_AiTarget] = []
        targets: list[_AiTarget] = []
        for target in all_targets:
            if self._should_reuse_existing_result(target, batch_defaults):
                reusable_targets.append(target)
            else:
                targets.append(target)
        batches = [
            targets[index : index + resolved_batch_size]
            for index in range(0, len(targets), resolved_batch_size)
        ]

        success_count = 0
        failure_count = 0
        fallback_count = 0
        cached_count = len(reusable_targets)
        clipped_count = 0

        if not all_targets:
            task.analyzed_videos = 0
            self.session.commit()
            return TaskAiAnalysisResult(
                total_count=0,
                success_count=0,
                failure_count=0,
                fallback_count=0,
                batch_count=0,
                cached_count=0,
                clipped_count=0,
            )

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.AI,
            message="Starting AI summary analysis for persisted videos.",
            payload={
                "target_video_count": len(all_targets),
                "pending_video_count": len(targets),
                "cached_video_count": cached_count,
                "batch_count": len(batches),
                "batch_size": resolved_batch_size,
            },
        )
        self.session.commit()

        task.analyzed_videos = cached_count
        self.session.commit()

        if cached_count > 0:
            create_task_log(
                self.session,
                task=task,
                stage=TaskStage.AI,
                message="Reused cached AI summaries for unchanged videos.",
                payload={"cached_video_count": cached_count},
            )
            self.session.commit()

        for batch_index, batch in enumerate(batches, start=1):
            batch_success = 0
            batch_failure = 0
            batch_fallback = 0
            batch_clipped = 0

            for target in batch:
                task = assert_task_execution_allowed(
                    self.session,
                    task.id,
                    expected_dispatch_generation=expected_dispatch_generation,
                )
                try:
                    outcome = self._analyze_single_video(
                        task,
                        target,
                        summary_defaults=summary_defaults,
                        quality_defaults=quality_defaults,
                    )
                    batch_success += 1
                    success_count += 1
                    if outcome.used_fallback:
                        batch_fallback += 1
                        fallback_count += 1
                    if outcome.input_clipped:
                        batch_clipped += 1
                        clipped_count += 1
                except Exception as exc:
                    batch_failure += 1
                    failure_count += 1
                    self.logger.warning(
                        "AI analysis failed for task {} video {}: {}",
                        task.id,
                        target.video.bvid,
                        exc,
                    )
                    create_task_log(
                        self.session,
                        task=task,
                        level=LogLevel.WARNING,
                        stage=TaskStage.AI,
                        message="AI analysis failed for a video.",
                        payload={
                            "video_id": target.video.id,
                            "bvid": target.video.bvid,
                            "error": str(exc),
                            "batch_index": batch_index,
                        },
                    )

                task.analyzed_videos = cached_count + success_count

            create_task_log(
                self.session,
                task=task,
                stage=TaskStage.AI,
                message="Finished an AI analysis batch.",
                payload={
                    "batch_index": batch_index,
                    "batch_size": len(batch),
                    "success_count": batch_success,
                    "failure_count": batch_failure,
                    "fallback_count": batch_fallback,
                    "clipped_count": batch_clipped,
                    "analyzed_videos": task.analyzed_videos,
                },
            )
            self.session.commit()

        task.extra_params = self._merge_ai_payload(
            task.extra_params,
            {
                "ai_stats": {
                    "target_video_count": len(all_targets),
                    "pending_video_count": len(targets),
                    "cached_count": cached_count,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "fallback_count": fallback_count,
                    "clipped_count": clipped_count,
                    "batch_count": len(batches),
                }
            },
        )
        self.session.commit()

        return TaskAiAnalysisResult(
            total_count=len(all_targets),
            success_count=success_count,
            failure_count=failure_count,
            fallback_count=fallback_count,
            batch_count=len(batches),
            cached_count=cached_count,
            clipped_count=clipped_count,
        )

    def _analyze_single_video(
        self,
        task: CrawlTask,
        target: _AiTarget,
        *,
        summary_defaults: dict[str, int | float | str | None],
        quality_defaults: dict[str, int | str],
    ) -> _AiExecutionOutcome:
        prompt, input_clipped = self._build_prompt(
            task,
            target,
            summary_defaults,
            quality_defaults,
        )

        used_fallback = False
        fallback_reason: str | None = None
        response: AiStructuredResponse | None = None

        if self.ai_client.is_available():
            try:
                response = self.ai_client.generate_summary(prompt)
                draft = self._apply_quality_control(
                    response.payload,
                    target=target,
                    quality_defaults=quality_defaults,
                    topic_count=summary_defaults["topic_count"],
                    summary_max_length=summary_defaults["summary_max_length"],
                )
            except Exception as exc:
                used_fallback = True
                fallback_reason = str(exc)
                draft = self._build_fallback_summary(
                    target,
                    quality_defaults=quality_defaults,
                    topic_count=summary_defaults["topic_count"],
                    summary_max_length=summary_defaults["summary_max_length"],
                )
        else:
            used_fallback = True
            fallback_reason = "AI API key is not configured."
            draft = self._build_fallback_summary(
                target,
                quality_defaults=quality_defaults,
                topic_count=summary_defaults["topic_count"],
                summary_max_length=summary_defaults["summary_max_length"],
            )

        self._upsert_ai_summary(
            task=task,
            target=target,
            draft=draft,
            prompt_version=summary_defaults["prompt_version"],
            model_name=(
                response.model_name
                if response is not None and not used_fallback
                else "heuristic-fallback"
            ),
            raw_response={
                "raw_content": response.raw_content if response is not None else None,
                "used_fallback": used_fallback,
                "fallback_reason": fallback_reason,
                "input_clipped": input_clipped,
                "topic_count": len(draft.topics),
            },
        )
        return _AiExecutionOutcome(
            used_fallback=used_fallback,
            input_clipped=input_clipped,
        )

    def _load_targets(self, task_id: str) -> list[_AiTarget]:
        statement = (
            select(TaskVideo, Video, VideoTextContent, AiSummary)
            .join(Video, Video.id == TaskVideo.video_id)
            .join(
                VideoTextContent,
                (VideoTextContent.task_id == TaskVideo.task_id)
                & (VideoTextContent.video_id == TaskVideo.video_id),
            )
            .outerjoin(
                AiSummary,
                (AiSummary.task_id == TaskVideo.task_id)
                & (AiSummary.video_id == TaskVideo.video_id),
            )
            .where(TaskVideo.task_id == task_id)
            .order_by(
                TaskVideo.composite_score.desc(),
                TaskVideo.search_rank.asc().nulls_last(),
                Video.created_at.desc(),
            )
        )
        rows = self.session.execute(statement).all()
        return [
            _AiTarget(
                task_video=task_video,
                video=video,
                text_content=text_content,
                ai_summary=ai_summary,
            )
            for task_video, video, text_content, ai_summary in rows
        ]

    def _build_prompt(
        self,
        task: CrawlTask,
        target: _AiTarget,
        summary_defaults: dict[str, int | float | str],
        quality_defaults: dict[str, int | str],
    ) -> tuple[AiPromptBundle, bool]:
        topic_count = max(
            1, min(int(summary_defaults["topic_count"]), MAX_ALLOWED_TOPIC_COUNT)
        )
        min_topic_count = max(
            1,
            min(int(quality_defaults["min_topic_count"]), topic_count),
        )
        max_summary_length = int(summary_defaults["summary_max_length"])
        clipped_text, input_clipped = self._clip_input_text(
            target.text_content.combined_text
        )

        system_prompt = (
            "你是一个负责总结 B 站视频文本的分析助手。"
            "只输出 JSON 对象，不要输出额外解释。"
            "JSON 必须包含 summary、topics、primary_topic、tone、confidence 字段。"
            f"summary 使用中文，长度控制在 {quality_defaults['min_summary_length']}"
            f"-{max_summary_length} 个字之间。"
            f"topics 返回 {min_topic_count}-{topic_count} 个主题词，"
            "primary_topic 必须包含在 topics 中。"
            "主题必须使用简洁、可解释、可复用的标签。"
            "相近主题请合并成更稳定的上位主题，不要拆得过细。"
            "不要输出 unclassified、unknown、misc、other 以及其他兜底标签。"
            "不要输出纯章节词、纯情绪词或偶发细节词，除非它们就是视频的核心主题。"
            "confidence 返回 0 到 1 的数字。"
        )
        user_prompt = (
            f"任务关键词：{task.keyword}\n"
            f"视频标题：{target.video.title}\n"
            f"视频标签：{', '.join(target.video.tags or []) or '无'}\n"
            f"语言：{target.text_content.language_code}\n"
            "请基于下面的清洗后文本生成摘要和主题：\n"
            f"{clipped_text}"
        )

        return (
            AiPromptBundle(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=str(summary_defaults["model"]),
                fallback_model=(
                    str(summary_defaults["fallback_model"])
                    if summary_defaults.get("fallback_model")
                    else None
                ),
                temperature=float(summary_defaults["temperature"]),
            ),
            input_clipped,
        )

    def _apply_quality_control(
        self,
        draft: VideoAiSummaryDraft,
        *,
        target: _AiTarget,
        quality_defaults: dict[str, int | str],
        topic_count: int,
        summary_max_length: int,
    ) -> VideoAiSummaryDraft:
        summary = self._normalize_summary(draft.summary, max_length=summary_max_length)
        max_topic_count = min(
            int(quality_defaults["max_topic_count"]),
            int(topic_count),
            MAX_ALLOWED_TOPIC_COUNT,
        )
        min_topic_count = min(
            int(quality_defaults["min_topic_count"]),
            max_topic_count,
        )
        topics = self._normalize_topics(
            draft.topics,
            primary_topic=draft.primary_topic,
            target=target,
            min_topic_count=min_topic_count,
            max_topic_count=max_topic_count,
            fallback_primary_topic=str(quality_defaults["fallback_primary_topic"]),
        )
        primary_topic = (
            topics[0]
            if topics
            else self._derive_fallback_topic(
                target,
                fallback_primary_topic=str(quality_defaults["fallback_primary_topic"]),
            )
        )

        confidence = draft.confidence
        if confidence is None:
            confidence = 0.65

        if len(summary) < int(quality_defaults["min_summary_length"]):
            raise ValueError("AI summary was too short after normalization.")

        return VideoAiSummaryDraft(
            summary=summary,
            topics=topics,
            primary_topic=primary_topic,
            tone=draft.tone or str(quality_defaults["fallback_tone"]),
            confidence=max(0.0, min(float(confidence), 1.0)),
        )

    def _build_fallback_summary(
        self,
        target: _AiTarget,
        *,
        quality_defaults: dict[str, int | str],
        topic_count: int,
        summary_max_length: int,
    ) -> VideoAiSummaryDraft:
        max_topic_count = min(
            int(quality_defaults["max_topic_count"]),
            int(topic_count),
            MAX_ALLOWED_TOPIC_COUNT,
        )
        min_topic_count = min(
            int(quality_defaults["min_topic_count"]),
            max_topic_count,
        )
        fallback_topics = self._normalize_topics(
            [],
            primary_topic=None,
            target=target,
            min_topic_count=min_topic_count,
            max_topic_count=max_topic_count,
            fallback_primary_topic=str(quality_defaults["fallback_primary_topic"]),
        )
        primary_topic = (
            fallback_topics[0]
            if fallback_topics
            else self._derive_fallback_topic(
                target,
                fallback_primary_topic=str(quality_defaults["fallback_primary_topic"]),
            )
        )
        plain_text = self._plain_text(target.text_content.combined_text)
        summary_body = plain_text[: max(40, summary_max_length - 18)].strip()
        if not summary_body:
            summary_body = target.video.title
        summary = (
            f"视频《{target.video.title}》主要围绕{primary_topic}展开，"
            f"{summary_body}"
        )
        summary = self._normalize_summary(summary, max_length=summary_max_length)

        return VideoAiSummaryDraft(
            summary=summary,
            topics=fallback_topics,
            primary_topic=primary_topic,
            tone=str(quality_defaults["fallback_tone"]),
            confidence=0.35,
        )

    def _upsert_ai_summary(
        self,
        *,
        task: CrawlTask,
        target: _AiTarget,
        draft: VideoAiSummaryDraft,
        prompt_version: str,
        model_name: str,
        raw_response: dict[str, object | None],
    ) -> None:
        ai_summary = self.session.scalar(
            select(AiSummary).where(
                AiSummary.task_id == task.id,
                AiSummary.video_id == target.video.id,
            )
        )
        if ai_summary is None:
            ai_summary = AiSummary(
                task_id=task.id,
                video_id=target.video.id,
                text_content_id=target.text_content.id,
                summary=draft.summary,
                topics=draft.topics,
            )
            self.session.add(ai_summary)

        ai_summary.text_content_id = target.text_content.id
        ai_summary.summary = draft.summary
        ai_summary.topics = draft.topics
        ai_summary.primary_topic = draft.primary_topic
        ai_summary.tone = draft.tone
        ai_summary.confidence = (
            Decimal(str(draft.confidence)) if draft.confidence is not None else None
        )
        ai_summary.model_name = model_name
        ai_summary.prompt_version = prompt_version
        ai_summary.raw_response = raw_response

    @staticmethod
    def _merge_ai_payload(
        extra_params: dict | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        merged = dict(extra_params or {})
        merged.update(payload)
        return merged

    @staticmethod
    def _normalize_summary(summary: str, *, max_length: int) -> str:
        normalized = TEXT_WHITESPACE_PATTERN.sub(" ", summary).strip()
        if len(normalized) <= max_length:
            return normalized
        return normalized[:max_length].rstrip(" ,，。；;")

    def _normalize_topics(
        self,
        topics: list[str],
        *,
        primary_topic: str | None,
        target: _AiTarget,
        min_topic_count: int,
        max_topic_count: int,
        fallback_primary_topic: str,
    ) -> list[str]:
        resolved_max_topic_count = max(
            1,
            min(max_topic_count, MAX_ALLOWED_TOPIC_COUNT),
        )
        resolved_min_topic_count = max(
            1, min(min_topic_count, resolved_max_topic_count)
        )
        normalized: list[str] = []

        def append_topic(value: str | None) -> None:
            topic = self._sanitize_topic_label(value)
            if topic is None or self._is_generic_topic(topic):
                return

            existing_index = self._find_similar_topic_index(normalized, topic)
            if existing_index is not None:
                normalized[existing_index] = self._prefer_topic_label(
                    normalized[existing_index],
                    topic,
                )
                return

            if len(normalized) < resolved_max_topic_count:
                normalized.append(topic)

        append_topic(primary_topic)
        for topic in topics:
            append_topic(topic)

        for tag in target.video.tags or []:
            if len(normalized) >= resolved_max_topic_count:
                break
            append_topic(tag)

        plain_text = self._plain_text(target.text_content.combined_text)
        if len(normalized) < resolved_min_topic_count:
            extracted_keywords = jieba.analyse.extract_tags(
                f"{target.video.title} {plain_text}",
                topK=resolved_max_topic_count * 3,
            )
            for keyword in extracted_keywords:
                if len(normalized) >= resolved_max_topic_count:
                    break
                append_topic(keyword)

        if not normalized:
            normalized.append(
                self._derive_fallback_topic(
                    target,
                    fallback_primary_topic=fallback_primary_topic,
                )
            )

        return normalized[:resolved_max_topic_count]

    def _sanitize_topic_label(self, value: str | None) -> str | None:
        if value is None:
            return None
        topic = TEXT_WHITESPACE_PATTERN.sub(" ", str(value)).strip(" ,，。；;、")
        if len(topic) < 2:
            return None
        return topic

    def _is_generic_topic(self, value: str) -> bool:
        topic_key = self._normalize_topic_key(value)
        if not topic_key:
            return True
        if topic_key in GENERIC_TOPIC_KEYS:
            return True
        return topic_key.startswith("unclassified")

    def _normalize_topic_key(self, value: str) -> str:
        return TOPIC_CLEANUP_PATTERN.sub(" ", value).strip().casefold()

    def _find_similar_topic_index(
        self,
        normalized_topics: list[str],
        candidate: str,
    ) -> int | None:
        candidate_key = self._normalize_topic_key(candidate)
        candidate_tokens = self._topic_tokens(candidate)

        for index, existing in enumerate(normalized_topics):
            existing_key = self._normalize_topic_key(existing)
            if candidate_key == existing_key:
                return index
            if candidate_key in existing_key or existing_key in candidate_key:
                return index

            existing_tokens = self._topic_tokens(existing)
            if candidate_tokens and existing_tokens:
                overlap = len(candidate_tokens & existing_tokens)
                token_union = len(candidate_tokens | existing_tokens)
                if overlap >= 2 and token_union > 0 and overlap / token_union >= 0.6:
                    return index

        return None

    def _prefer_topic_label(self, left: str, right: str) -> str:
        left_key = self._normalize_topic_key(left)
        right_key = self._normalize_topic_key(right)
        if right_key in left_key and len(right) <= len(left):
            return right
        if left_key in right_key and len(left) <= len(right):
            return left
        if len(right) < len(left):
            return right
        return left

    def _topic_tokens(self, value: str) -> set[str]:
        tokens = {
            token.casefold()
            for token in TOPIC_SEGMENT_PATTERN.findall(value)
            if len(token.strip()) >= 2
        }
        if tokens:
            return tokens

        compact = self._normalize_topic_key(value).replace(" ", "")
        if len(compact) < 2:
            return set()
        return {
            compact[index : index + 2]
            for index in range(len(compact) - 1)
            if len(compact[index : index + 2]) == 2
        }

    def _derive_fallback_topic(
        self,
        target: _AiTarget,
        *,
        fallback_primary_topic: str,
    ) -> str:
        plain_text = self._plain_text(target.text_content.combined_text)
        extracted_keywords = jieba.analyse.extract_tags(
            f"{target.video.title} {plain_text}",
            topK=8,
        )
        candidate_sources = [
            *(target.video.tags or []),
            *extracted_keywords,
            self._topic_from_title(target.video.title),
            fallback_primary_topic,
        ]

        for candidate in candidate_sources:
            normalized = self._sanitize_topic_label(candidate)
            if normalized is None or self._is_generic_topic(normalized):
                continue
            return normalized

        return self._topic_from_title(target.video.title) or "视频主题"

    def _topic_from_title(self, title: str) -> str | None:
        for part in TITLE_SPLIT_PATTERN.split(title):
            candidate = self._sanitize_topic_label(part)
            if candidate is None or self._is_generic_topic(candidate):
                continue
            if len(candidate) > 16:
                continue
            return candidate

        shortened = self._sanitize_topic_label(title[:16])
        if shortened is None or self._is_generic_topic(shortened):
            return None
        return shortened

    @staticmethod
    def _plain_text(value: str) -> str:
        plain_lines = []
        for line in value.splitlines():
            if TEXT_SECTION_LABEL_PATTERN.match(line.strip()):
                continue
            plain_lines.append(line)
        return TEXT_WHITESPACE_PATTERN.sub(" ", " ".join(plain_lines)).strip()

    def _should_reuse_existing_result(
        self,
        target: _AiTarget,
        batch_defaults: dict[str, int | bool],
    ) -> bool:
        if not self.settings.ai_reuse_existing_results:
            return False
        if not bool(batch_defaults.get("reuse_existing_results", True)):
            return False
        if target.ai_summary is None:
            return False
        if target.ai_summary.text_content_id != target.text_content.id:
            return False
        return bool(target.ai_summary.summary and target.ai_summary.topics)

    def _clip_input_text(self, combined_text: str) -> tuple[str, bool]:
        limit = max(400, int(self.settings.ai_input_char_limit))
        normalized_text = combined_text.strip()
        if len(normalized_text) <= limit:
            return normalized_text, False

        section_limits = {
            "Video Title": 180,
            "Video Description": 520,
            "Video Search Summary": 520,
            "Video Subtitle": 1180,
        }
        sections = self._split_text_sections(normalized_text)
        if not sections:
            return normalized_text[:limit].rstrip(" ,，。；;"), True

        clipped_sections: list[str] = []
        remaining = limit
        labels = list(section_limits.keys())
        for index, label in enumerate(labels):
            content = sections.get(label)
            if not content or remaining <= len(label) + 4:
                continue
            header = f"{label}:\n"
            reserve_for_remaining = max(0, len(labels) - index - 1) * 24
            content_limit = min(
                section_limits[label],
                max(80, remaining - len(header) - reserve_for_remaining),
            )
            clipped_content = content[:content_limit].rstrip(" ,，。；;")
            if not clipped_content:
                continue
            section_text = f"{header}{clipped_content}"
            clipped_sections.append(section_text)
            remaining -= len(section_text) + 2

        if not clipped_sections:
            return normalized_text[:limit].rstrip(" ,，。；;"), True
        return "\n\n".join(clipped_sections), True

    @staticmethod
    def _split_text_sections(value: str) -> dict[str, str]:
        sections: dict[str, list[str]] = {}
        current_label: str | None = None
        for line in value.splitlines():
            stripped = line.strip()
            if stripped.endswith(":") and TEXT_SECTION_LABEL_PATTERN.match(stripped):
                current_label = stripped.removesuffix(":")
                sections.setdefault(current_label, [])
                continue
            if current_label is not None:
                sections[current_label].append(line)
        return {
            label: TEXT_WHITESPACE_PATTERN.sub(" ", " ".join(lines)).strip()
            for label, lines in sections.items()
            if TEXT_WHITESPACE_PATTERN.sub(" ", " ".join(lines)).strip()
        }
