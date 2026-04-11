from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.base import utc_now
from app.models.enums import TaskStage
from app.schemas.task import (
    TaskAnalysisPayload,
    TaskAnalysisRecommendationRead,
    TaskAnalysisTopicInsightRead,
    TaskAnalysisTopicTrendRead,
    TaskAnalysisVideoInsightRead,
    TaskReportAiOutputRead,
    TaskReportPayload,
    TaskReportSectionRead,
)
from app.services.task_log_service import create_task_log
from app.services.ai_client import AiPromptBundle, OpenAICompatibleAiClient
from app.services.task_result_service import (
    get_task_analysis,
    load_cached_analysis_snapshot,
)
from app.services.task_service import get_task_or_raise


@dataclass(slots=True)
class _PromptSpec:
    key: str
    title: str
    audience: str
    system_prompt: str
    task_goal: str


class _AiOutputDraft(BaseModel):
    key: str
    content: str = Field(min_length=20)


class _AiOutputsEnvelope(BaseModel):
    outputs: list[_AiOutputDraft] = Field(default_factory=list)


class TaskReportService:
    def __init__(
        self,
        session: Session,
        *,
        ai_client: OpenAICompatibleAiClient | Any | None = None,
    ) -> None:
        self.session = session
        self.ai_client = ai_client or OpenAICompatibleAiClient.from_settings()

    def build_report(self, task_id: str) -> TaskReportPayload:
        task = get_task_or_raise(self.session, task_id)
        cached_report = self._load_cached_report_snapshot(task.extra_params)
        if cached_report is not None:
            return cached_report

        analysis = self._resolve_analysis_payload(task)
        return self._build_report_payload(task, analysis)

    def generate_and_persist(
        self,
        task,
        *,
        status_override: str | None = None,
    ) -> TaskReportPayload:
        report = self._build_report_payload(
            task,
            self._resolve_analysis_payload(task, prefer_cached=True),
            status_override=status_override,
        )
        task.extra_params = self._merge_report_payload(
            task.extra_params,
            {"report_snapshot": report.model_dump(mode="json")},
        )
        self.session.commit()
        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.REPORT,
            message="Generated task report snapshot.",
            payload={
                "section_count": len(report.sections),
                "ai_output_count": len(report.ai_outputs),
                "featured_video_count": len(report.featured_videos),
                "popular_author_count": len(report.popular_authors),
            },
        )
        self.session.commit()
        return report

    def _build_report_payload(
        self,
        task,
        analysis: TaskAnalysisPayload,
        *,
        status_override: str | None = None,
    ) -> TaskReportPayload:
        extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
        scope_label = self._build_scope_label(extra_params)
        latest_hot_topic = analysis.advanced.latest_hot_topic.topic
        momentum_topic = analysis.advanced.momentum_topics[0] if analysis.advanced.momentum_topics else None
        depth_topic = analysis.advanced.depth_topics[0] if analysis.advanced.depth_topics else None
        community_topic = analysis.advanced.community_topics[0] if analysis.advanced.community_topics else None
        trend_topic = self._resolve_trend_topic(analysis.advanced.topic_evolution, latest_hot_topic)
        top_explosive_video = analysis.advanced.explosive_videos[0] if analysis.advanced.explosive_videos else None
        top_deep_video = analysis.advanced.deep_videos[0] if analysis.advanced.deep_videos else None
        top_community_video = analysis.advanced.community_videos[0] if analysis.advanced.community_videos else None

        title = f"{task.keyword or 'B站热点'} 热点内容分析报告"
        subtitle = (
            f"当前最值得关注的热点主题是“{latest_hot_topic.topic_name}”，本次任务覆盖 {analysis.summary.total_videos} 条视频。"
            if latest_hot_topic is not None
            else f"本次任务覆盖 {analysis.summary.total_videos} 条视频，已生成结构化热点分析报告。"
        )
        executive_summary = self._build_executive_summary(
            keyword=task.keyword,
            scope_label=scope_label,
            total_videos=analysis.summary.total_videos,
            latest_hot_topic=latest_hot_topic,
            top_explosive_video=top_explosive_video,
            top_deep_video=top_deep_video,
            top_community_video=top_community_video,
        )
        sections = [
            self._build_overview_section(
                keyword=task.keyword,
                scope_label=scope_label,
                generated_at=analysis.generated_at,
                total_videos=analysis.summary.total_videos,
                latest_hot_topic=latest_hot_topic,
                recommendations=analysis.advanced.recommendations,
            ),
            self._build_hotspot_section(
                latest_hot_topic=latest_hot_topic,
                reason=analysis.advanced.latest_hot_topic.reason,
                supporting_points=analysis.advanced.latest_hot_topic.supporting_points,
                momentum_topic=momentum_topic,
                community_topic=community_topic,
            ),
            self._build_burst_section(momentum_topic, top_explosive_video),
            self._build_depth_section(depth_topic, top_deep_video),
            self._build_community_section(community_topic, top_community_video),
            self._build_evolution_section(trend_topic),
            self._build_recommendation_section(analysis.advanced.recommendations),
            self._build_author_section(
                analysis.advanced.popular_authors,
                analysis.advanced.author_analysis_notes,
            ),
            self._build_methodology_section(analysis.advanced.data_notes),
        ]
        sections = [section for section in sections if section is not None]

        ai_outputs = self._build_ai_outputs(
            keyword=task.keyword,
            scope_label=scope_label,
            generated_at=analysis.generated_at or utc_now(),
            executive_summary=executive_summary,
            sections=sections,
            recommendations=analysis.advanced.recommendations,
            latest_hot_topic=latest_hot_topic,
            top_videos=[
                video
                for video in [top_explosive_video, top_deep_video, top_community_video]
                if video is not None
            ],
            data_notes=analysis.advanced.data_notes,
        )
        report_markdown = self._build_markdown(
            title=title,
            subtitle=subtitle,
            executive_summary=executive_summary,
            sections=sections,
            ai_outputs=ai_outputs,
        )

        return TaskReportPayload(
            task_id=task.id,
            status=status_override or task.status.value,
            generated_at=analysis.generated_at or utc_now(),
            title=title,
            subtitle=subtitle,
            executive_summary=executive_summary,
            latest_hot_topic_name=latest_hot_topic.topic_name if latest_hot_topic is not None else None,
            featured_videos=self._build_featured_videos(
                analysis.advanced.recommendations,
                fallback_videos=[top_explosive_video, top_deep_video, top_community_video],
            ),
            recommendations=analysis.advanced.recommendations,
            popular_authors=analysis.advanced.popular_authors,
            topic_hot_authors=analysis.advanced.topic_hot_authors,
            sections=sections,
            ai_outputs=ai_outputs,
            report_markdown=report_markdown,
        )

    def _resolve_analysis_payload(
        self,
        task,
        *,
        prefer_cached: bool = False,
    ) -> TaskAnalysisPayload:
        if prefer_cached:
            cached_snapshot = load_cached_analysis_snapshot(task.extra_params)
            if cached_snapshot is not None:
                return TaskAnalysisPayload(
                    task_id=task.id,
                    status=task.status.value,
                    generated_at=cached_snapshot.generated_at or utc_now(),
                    summary=cached_snapshot.statistics.summary,
                    topics=cached_snapshot.statistics.topics,
                    top_videos=cached_snapshot.top_videos or [],
                    advanced=cached_snapshot.statistics.advanced,
                    has_ai_summaries=bool(cached_snapshot.has_ai_summaries),
                    has_topics=bool(cached_snapshot.statistics.topics),
                )

        return get_task_analysis(self.session, task.id)

    def _load_cached_report_snapshot(
        self,
        extra_params: dict[str, Any] | None,
    ) -> TaskReportPayload | None:
        if not isinstance(extra_params, dict):
            return None

        snapshot = extra_params.get("report_snapshot")
        if not isinstance(snapshot, dict):
            return None

        try:
            return TaskReportPayload.model_validate(snapshot)
        except Exception:
            return None

    @staticmethod
    def _merge_report_payload(
        extra_params: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(extra_params or {})
        merged.update(payload)
        return merged

    def _build_ai_outputs(
        self,
        *,
        keyword: str,
        scope_label: str,
        generated_at: datetime,
        executive_summary: str,
        sections: list[TaskReportSectionRead],
        recommendations: list[TaskAnalysisRecommendationRead],
        latest_hot_topic: TaskAnalysisTopicInsightRead | None,
        top_videos: list[TaskAnalysisVideoInsightRead],
        data_notes: list[str],
    ) -> list[TaskReportAiOutputRead]:
        specs = self._prompt_specs()
        context = self._build_ai_context(
            keyword=keyword,
            scope_label=scope_label,
            generated_at=generated_at,
            executive_summary=executive_summary,
            sections=sections,
            recommendations=recommendations,
            latest_hot_topic=latest_hot_topic,
            top_videos=top_videos,
            data_notes=data_notes,
        )
        prompt = AiPromptBundle(
            system_prompt=(
                "你是一名负责解读 B 站热点任务的中文分析助手。"
                "请基于给定任务数据，同时按照不同受众视角输出结果。"
                "只输出 JSON 对象，不要输出额外解释。"
                'JSON 结构必须为 {"outputs":[{"key":"...","content":"..."}]}。'
                "每条 content 都必须是可直接展示给用户的完整中文结果，"
                "不要再提“以下是模板”或“建议输入给 AI”。"
            ),
            user_prompt=(
                "请根据下面的任务分析上下文，分别生成三类最终成品内容："
                "1. 吃瓜群众速览版；2. 专业分析版；3. 运营选题版。\n"
                f"角色要求：{json.dumps([asdict(spec) for spec in specs], ensure_ascii=False)}\n"
                f"任务上下文：{json.dumps(context, ensure_ascii=False)}"
            ),
            model=self.ai_client.default_model if hasattr(self.ai_client, "default_model") else "",
            fallback_model=self.ai_client.fallback_model if hasattr(self.ai_client, "fallback_model") else None,
            temperature=0.5,
        )

        if hasattr(self.ai_client, "is_available") and self.ai_client.is_available():
            try:
                response = self.ai_client.generate_json(prompt)
                payload = _AiOutputsEnvelope.model_validate(response.payload)
                outputs_by_key = {item.key: item.content.strip() for item in payload.outputs if item.content.strip()}
                return [
                    TaskReportAiOutputRead(
                        key=spec.key,
                        title=spec.title,
                        audience=spec.audience,
                        content=outputs_by_key.get(spec.key) or self._build_fallback_ai_output(spec, context),
                        generation_mode="ai" if spec.key in outputs_by_key else "fallback",
                        model_name=response.model_name if spec.key in outputs_by_key else None,
                    )
                    for spec in specs
                ]
            except Exception:
                pass

        return [
            TaskReportAiOutputRead(
                key=spec.key,
                title=spec.title,
                audience=spec.audience,
                content=self._build_fallback_ai_output(spec, context),
                generation_mode="fallback",
                model_name=None,
            )
            for spec in specs
        ]

    def _build_ai_context(
        self,
        *,
        keyword: str,
        scope_label: str,
        generated_at: datetime,
        executive_summary: str,
        sections: list[TaskReportSectionRead],
        recommendations: list[TaskAnalysisRecommendationRead],
        latest_hot_topic: TaskAnalysisTopicInsightRead | None,
        top_videos: list[TaskAnalysisVideoInsightRead],
        data_notes: list[str],
    ) -> dict[str, Any]:
        return {
            "task_keyword": keyword,
            "scope_label": scope_label,
            "generated_at": generated_at.isoformat(),
            "executive_summary": executive_summary,
            "latest_hot_topic": latest_hot_topic.topic_name if latest_hot_topic is not None else None,
            "sections": [
                {
                    "key": section.key,
                    "title": section.title,
                    "summary": section.summary,
                    "bullets": section.bullets[:6],
                    "evidence": section.evidence[:4],
                }
                for section in sections
            ],
            "recommendations": [
                {
                    "title": item.title,
                    "description": item.description,
                    "topic_name": item.topic_name,
                    "videos": [
                        {
                            "title": video.title,
                            "topic_name": video.topic_name,
                            "composite_score": video.composite_score,
                            "burst_score": video.burst_score,
                            "depth_score": video.depth_score,
                            "community_score": video.community_score,
                        }
                        for video in item.videos[:3]
                    ],
                }
                for item in recommendations[:4]
            ],
            "top_videos": [
                {
                    "title": video.title,
                    "topic_name": video.topic_name,
                    "burst_score": video.burst_score,
                    "depth_score": video.depth_score,
                    "community_score": video.community_score,
                    "composite_score": video.composite_score,
                }
                for video in top_videos[:5]
            ],
            "data_notes": data_notes[:8],
        }

    def _build_scope_label(self, extra_params: dict[str, Any]) -> str:
        task_options = extra_params.get("task_options")
        if not isinstance(task_options, dict):
            return "B站全站"
        if str(task_options.get("search_scope") or "site") == "partition":
            partition_name = task_options.get("partition_name") or task_options.get("partition_tid")
            return f"固定分区：{partition_name}"
        return "B站全站"

    def _build_executive_summary(
        self,
        *,
        keyword: str,
        scope_label: str,
        total_videos: int,
        latest_hot_topic: TaskAnalysisTopicInsightRead | None,
        top_explosive_video: TaskAnalysisVideoInsightRead | None,
        top_deep_video: TaskAnalysisVideoInsightRead | None,
        top_community_video: TaskAnalysisVideoInsightRead | None,
    ) -> str:
        topic_clause = (
            f"当前最热主题为“{latest_hot_topic.topic_name}”。"
            if latest_hot_topic is not None
            else "当前任务尚未形成单一绝对领先的热点主题。"
        )
        explosive_clause = (
            f"最值得追新的爆发视频是《{top_explosive_video.title}》。"
            if top_explosive_video is not None
            else "当前未识别出足够强势的爆发视频样本。"
        )
        depth_clause = (
            f"内容深度表现最强的视频是《{top_deep_video.title}》。"
            if top_deep_video is not None
            else "内容深度榜样本仍然有限。"
        )
        community_clause = (
            f"社区扩散最强的视频是《{top_community_video.title}》。"
            if top_community_video is not None
            else "社区扩散信号仍需继续积累。"
        )
        return (
            f"本报告基于“{keyword}”在“{scope_label}”下抓取的 {total_videos} 条视频生成。"
            f"{topic_clause}{explosive_clause}{depth_clause}{community_clause}"
        )

    def _build_overview_section(
        self,
        *,
        keyword: str,
        scope_label: str,
        generated_at: datetime,
        total_videos: int,
        latest_hot_topic: TaskAnalysisTopicInsightRead | None,
        recommendations: list[TaskAnalysisRecommendationRead],
    ) -> TaskReportSectionRead:
        return TaskReportSectionRead(
            key="overview",
            title="任务总览",
            summary="先回答这次任务到底看到了什么、热点集中在哪里、结果值不值得继续追。",
            bullets=[
                f"分析关键词：{keyword}",
                f"抓取范围：{scope_label}",
                f"纳入分析的视频数：{total_videos}",
                f"报告生成时间：{generated_at.isoformat()}",
                f"当前最新热点主题：{latest_hot_topic.topic_name if latest_hot_topic is not None else '暂无'}",
                f"已生成推荐分组：{len(recommendations)} 组",
            ],
        )

    def _build_hotspot_section(
        self,
        latest_hot_topic: TaskAnalysisTopicInsightRead | None,
        reason: str | None,
        supporting_points: list[str],
        momentum_topic: TaskAnalysisTopicInsightRead | None,
        community_topic: TaskAnalysisTopicInsightRead | None,
    ) -> TaskReportSectionRead:
        bullets = list(supporting_points[:6])
        if momentum_topic is not None:
            bullets.append(
                f"爆发力领先主题是“{momentum_topic.topic_name}”，均值 {momentum_topic.average_burst_score or 0:.2f}。"
            )
        if community_topic is not None:
            bullets.append(
                f"社区扩散领先主题是“{community_topic.topic_name}”，均值 {community_topic.average_community_score or 0:.2f}。"
            )
        return TaskReportSectionRead(
            key="hotspot",
            title="热点主题判断",
            summary=reason or f"当前任务中最值得优先关注的主题是“{latest_hot_topic.topic_name if latest_hot_topic else '暂无明确热点主题'}”。",
            bullets=bullets,
        )

    def _build_burst_section(
        self,
        topic: TaskAnalysisTopicInsightRead | None,
        video: TaskAnalysisVideoInsightRead | None,
    ) -> TaskReportSectionRead | None:
        if topic is None and video is None:
            return None
        bullets: list[str] = []
        if topic is not None:
            bullets.append(
                f"爆发力最强主题：{topic.topic_name}，平均爆发力 {topic.average_burst_score or 0:.2f}，平均播放 {topic.average_view_count:.0f}。"
            )
        if video is not None:
            bullets.append(
                f"爆发视频样本：《{video.title}》，爆发力 {video.burst_score or 0:.2f}，搜索到当前播放增长率 {((video.search_to_current_view_growth_ratio or 0) * 100):.2f}%。"
            )
            bullets.append(
                f"发布以来小时均播放 {video.views_per_hour_since_publish or 0:.2f}，历史快照数 {video.historical_snapshot_count}。"
            )
        return TaskReportSectionRead(
            key="burst",
            title="爆发力分析",
            summary="这部分用来判断哪些内容正在快速升温，适合吃瓜、追新和判断热点后劲。",
            bullets=bullets,
        )

    def _build_depth_section(
        self,
        topic: TaskAnalysisTopicInsightRead | None,
        video: TaskAnalysisVideoInsightRead | None,
    ) -> TaskReportSectionRead | None:
        if topic is None and video is None:
            return None
        bullets: list[str] = []
        if topic is not None:
            bullets.append(
                f"内容深度最强主题：{topic.topic_name}，平均深度 {topic.average_depth_score or 0:.2f}，平均点赞率 {(topic.average_like_view_ratio or 0) * 100:.2f}%。"
            )
        if video is not None:
            bullets.append(
                f"高深度视频样本：《{video.title}》，深度 {video.depth_score or 0:.2f}，完播代理分 {video.completion_proxy_score or 0:.4f}。"
            )
            bullets.append(
                f"点赞率 {(video.like_view_ratio or 0) * 100:.2f}%，投币率 {(video.coin_view_ratio or 0) * 100:.2f}%，收藏率 {(video.favorite_view_ratio or 0) * 100:.2f}%。"
            )
        return TaskReportSectionRead(
            key="depth",
            title="内容深度分析",
            summary="这部分用来判断视频不只是被看到，而是真的让观众愿意认真看、认真互动。",
            bullets=bullets,
        )

    def _build_community_section(
        self,
        topic: TaskAnalysisTopicInsightRead | None,
        video: TaskAnalysisVideoInsightRead | None,
    ) -> TaskReportSectionRead | None:
        if topic is None and video is None:
            return None
        bullets: list[str] = []
        if topic is not None:
            bullets.append(
                f"社区扩散最强主题：{topic.topic_name}，平均扩散分 {topic.average_community_score or 0:.2f}，平均分享率 {(topic.average_share_rate or 0) * 100:.2f}%。"
            )
        if video is not None:
            bullets.append(
                f"高扩散视频样本：《{video.title}》，社区扩散 {video.community_score or 0:.2f}。"
            )
            bullets.append(
                f"分享率 {(video.share_view_ratio or 0) * 100:.2f}%，评论率 {(video.reply_view_ratio or 0) * 100:.2f}%，弹幕率 {(video.danmaku_view_ratio or 0) * 100:.2f}%。"
            )
        return TaskReportSectionRead(
            key="community",
            title="社区扩散分析",
            summary="这部分用来判断热点是不是会在社区里持续发酵，而不是只停留在短时曝光。",
            bullets=bullets,
        )

    def _build_evolution_section(
        self,
        trend: TaskAnalysisTopicTrendRead | None,
    ) -> TaskReportSectionRead | None:
        if trend is None:
            return None
        return TaskReportSectionRead(
            key="evolution",
            title="热点演化判断",
            summary=(
                f"主题“{trend.topic_name}”当前走势为“{self._trend_label(trend.trend_direction)}”，"
                "适合结合发布时间窗口继续观察热度变化。"
            ),
            bullets=[
                f"最新热度时间桶：{trend.latest_bucket or '暂无'}，热度指数 {trend.latest_topic_heat_index or 0:.2f}。",
                f"峰值时间桶：{trend.peak_bucket or '暂无'}，峰值热度指数 {trend.peak_topic_heat_index or 0:.2f}。",
                f"总演化点数：{len(trend.points)}。",
            ],
        )

    def _build_recommendation_section(
        self,
        recommendations: list[TaskAnalysisRecommendationRead],
    ) -> TaskReportSectionRead:
        bullets: list[str] = []
        evidence: list[str] = []
        for recommendation in recommendations[:4]:
            bullets.append(f"{recommendation.title}：{recommendation.description or '面向当前任务的推荐分组。'}")
            if recommendation.videos:
                top_video = recommendation.videos[0]
                evidence.append(
                    f"建议优先看《{top_video.title}》，主题 {top_video.topic_name or '未归类'}，综合分 {top_video.composite_score:.2f}。"
                )
        return TaskReportSectionRead(
            key="recommendation",
            title="推荐与行动建议",
            summary="如果只想快速看重点，建议从这里列出的推荐组和代表视频开始。",
            bullets=bullets,
            evidence=evidence,
        )

    def _build_author_section(
        self,
        authors,
        notes: list[str],
    ) -> TaskReportSectionRead | None:
        if not authors:
            return None

        bullets = [
            (
                f"{author.author_name}：热点样本 {author.source_video_count} 条，"
                f"热点贡献分 {author.source_total_heat_score:.2f}，"
                f"二次抓取 {author.fetched_video_count} 条视频。"
            )
            for author in authors[:5]
        ]
        evidence = list(notes[:3])
        return TaskReportSectionRead(
            key="authors",
            title="热门 UP 主画像",
            summary="从热点视频中先汇总出高频且高热度的 up 主，再补抓其投稿视频，形成更稳定的创作者画像。",
            bullets=bullets,
            evidence=evidence,
        )

    def _build_methodology_section(self, data_notes: list[str]) -> TaskReportSectionRead:
        return TaskReportSectionRead(
            key="methodology",
            title="口径说明与边界",
            summary="这里说明当前报告里的指标口径和数据边界，避免误读分析结论。",
            bullets=data_notes,
        )

    def _prompt_specs(self) -> list[_PromptSpec]:
        return [
            _PromptSpec(
                key="melon_reader",
                title="吃瓜速览版",
                audience="普通网友 / 吃瓜群众",
                system_prompt="用网友能快速看懂的中文写作，少术语，多结论。",
                task_goal="用轻松但准确的方式总结当前最热主题、最值得追的视频、可能继续发酵的方向，以及普通用户先看什么。",
            ),
            _PromptSpec(
                key="pro_analyst",
                title="专业分析版",
                audience="研究员 / 专业分析人员",
                system_prompt="强调结论、证据、方法口径和限制，避免把代理指标写成官方指标。",
                task_goal="输出一份更专业的热点分析判断，重点写主题结构、爆发力、深度、社区扩散、时间演化和局限性。",
            ),
            _PromptSpec(
                key="ops_planning",
                title="运营选题版",
                audience="内容运营 / 选题策划",
                system_prompt="把分析结论转成可执行建议，关注选题、表达角度、跟进策略。",
                task_goal="告诉运营人员该追哪条热点、该做什么类型的视频、哪些样本适合借势，以及优先级如何排。",
            ),
        ]

    def _build_fallback_ai_output(self, spec: _PromptSpec, context: dict[str, Any]) -> str:
        latest_hot_topic = context.get("latest_hot_topic") or "暂无明确热点主题"
        top_videos = context.get("top_videos") or []
        video_names = [item.get("title") for item in top_videos if item.get("title")]
        top_video_text = "、".join(video_names[:3]) if video_names else "暂无强代表样本"
        recommendation_titles = [
            item.get("title")
            for item in context.get("recommendations") or []
            if item.get("title")
        ]
        recommendation_text = "；".join(recommendation_titles[:3]) if recommendation_titles else "暂无推荐分组"
        section_summaries = [
            f"{item.get('title')}：{item.get('summary')}"
            for item in context.get("sections") or []
            if item.get("title") and item.get("summary")
        ]
        section_text = "\n".join(section_summaries[:5])
        return (
            f"面向“{spec.audience}”的最终结果如下。\n"
            f"本次任务范围为 {context.get('scope_label')}，核心热点主题是“{latest_hot_topic}”。\n"
            f"当前最值得优先关注的视频包括：{top_video_text}。\n"
            f"建议重点查看这些推荐分组：{recommendation_text}。\n"
            f"从报告角度看，你最需要先抓住的是：{context.get('executive_summary')}\n"
            f"进一步展开时，可以按以下模块理解：\n{section_text}\n"
            f"写作目标：{spec.task_goal}"
        ).strip()

    def _build_markdown(
        self,
        *,
        title: str,
        subtitle: str | None,
        executive_summary: str,
        sections: list[TaskReportSectionRead],
        ai_outputs: list[TaskReportAiOutputRead],
    ) -> str:
        lines = [f"# {title}"]
        if subtitle:
            lines.append(subtitle)
        lines.append("")
        lines.append("## 执行摘要")
        lines.append(executive_summary)
        for section in sections:
            lines.append("")
            lines.append(f"## {section.title}")
            lines.append(section.summary)
            for bullet in section.bullets:
                lines.append(f"- {bullet}")
            for evidence in section.evidence:
                lines.append(f"- 证据：{evidence}")
        for output in ai_outputs:
            lines.append("")
            lines.append(f"## {output.title}")
            lines.append(f"受众：{output.audience}")
            lines.append(f"生成方式：{output.generation_mode}")
            lines.append(output.content)
        return "\n".join(lines).strip()

    def _build_featured_videos(
        self,
        recommendations: list[TaskAnalysisRecommendationRead],
        fallback_videos: list[TaskAnalysisVideoInsightRead | None],
    ) -> list[TaskAnalysisVideoInsightRead]:
        ordered: list[TaskAnalysisVideoInsightRead] = []
        seen: set[str] = set()
        for recommendation in recommendations:
            for video in recommendation.videos[:2]:
                if video.video_id in seen:
                    continue
                ordered.append(video)
                seen.add(video.video_id)
        for video in fallback_videos:
            if video is None or video.video_id in seen:
                continue
            ordered.append(video)
            seen.add(video.video_id)
        return ordered[:6]

    def _resolve_trend_topic(
        self,
        trends: list[TaskAnalysisTopicTrendRead],
        latest_hot_topic: TaskAnalysisTopicInsightRead | None,
    ) -> TaskAnalysisTopicTrendRead | None:
        if latest_hot_topic is not None:
            for item in trends:
                if item.topic_id == latest_hot_topic.topic_id:
                    return item
        return trends[0] if trends else None

    def _trend_label(self, direction: str) -> str:
        return {
            "rising": "持续升温",
            "cooling": "热度回落",
            "stable": "走势稳定",
        }.get(direction, direction or "走势稳定")
