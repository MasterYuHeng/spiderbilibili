from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.crawler.browser_client import BilibiliBrowserClient
from app.crawler.client import BilibiliHttpClient
from app.crawler.detail_spider import BilibiliDetailSpider
from app.crawler.uploader_spider import BilibiliUploaderSpider
from app.models.base import utc_now
from app.models.task import CrawlTask
from app.schemas.task import (
    TaskAnalysisAuthorRepresentativeVideoRead,
    TaskAnalysisAuthorVideoRead,
    TaskAnalysisPopularAuthorRead,
    TaskAnalysisTopicHotAuthorRead,
    TaskAnalysisTopicInsightRead,
    TaskAnalysisVideoInsightRead,
)
from app.services.ai_client import AiPromptBundle, OpenAICompatibleAiClient
from app.services.system_config_service import build_bilibili_runtime_settings


@dataclass(slots=True)
class PopularAuthorAnalysisResult:
    popular_authors: list[TaskAnalysisPopularAuthorRead] = field(default_factory=list)
    topic_hot_authors: list[TaskAnalysisTopicHotAuthorRead] = field(
        default_factory=list
    )
    author_analysis_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class _SourceAuthorAggregate:
    author_name: str
    author_mid: str | None
    source_videos: list[TaskAnalysisVideoInsightRead] = field(default_factory=list)
    topic_names: Counter[str] = field(default_factory=Counter)
    selection_reasons: set[str] = field(default_factory=set)
    popularity_score: float = 0.0


class _AuthorVideoAiDraft(BaseModel):
    bvid: str
    summary: str | None = None
    focus: list[str] = Field(default_factory=list)


class _AuthorAiEnvelope(BaseModel):
    creator_profile: str | None = None
    recent_content_summary: str | None = None
    content_strategy: list[str] = Field(default_factory=list)
    content_keywords: list[str] = Field(default_factory=list)
    videos: list[_AuthorVideoAiDraft] = Field(default_factory=list)


class PopularAuthorAnalysisService:
    def __init__(
        self,
        session: Session,
        *,
        http_client: BilibiliHttpClient | None = None,
        browser_client: BilibiliBrowserClient | None = None,
        uploader_spider: BilibiliUploaderSpider | None = None,
        detail_spider: BilibiliDetailSpider | None = None,
        ai_client: OpenAICompatibleAiClient | Any | None = None,
    ) -> None:
        self.session = session
        self._owns_http_client = http_client is None
        self._owns_browser_client = browser_client is None
        self.http_client = http_client
        self.browser_client = browser_client
        self.uploader_spider = uploader_spider
        self.detail_spider = detail_spider
        self.ai_client = ai_client or OpenAICompatibleAiClient.from_runtime(
            session=self.session,
        )

    def close(self) -> None:
        if self._owns_http_client and self.http_client is not None:
            self.http_client.close()
        if self._owns_browser_client and self.browser_client is not None:
            self.browser_client.close()

    def build_for_task(
        self,
        task: CrawlTask,
        *,
        video_insights: list[TaskAnalysisVideoInsightRead],
        topic_insights: list[TaskAnalysisTopicInsightRead],
        fetch_author_videos: bool = True,
    ) -> PopularAuthorAnalysisResult:
        options = self._resolve_task_options(task)
        hot_author_total_count = int(options["hot_author_total_count"])
        topic_hot_author_count = int(options["topic_hot_author_count"])
        hot_author_video_limit = int(options["hot_author_video_limit"])
        summary_basis = str(options["hot_author_summary_basis"])

        if hot_author_total_count <= 0 and topic_hot_author_count <= 0:
            return PopularAuthorAnalysisResult()
        if not video_insights:
            return PopularAuthorAnalysisResult(
                author_analysis_notes=["当前任务还没有可用于汇总热门 up 主的视频样本。"]
            )

        author_map = self._aggregate_authors(video_insights)
        if not author_map:
            return PopularAuthorAnalysisResult(
                author_analysis_notes=[
                    "当前任务视频缺少 up 主信息，暂时无法生成热门 up 主分析。"
                ]
            )

        self._score_authors(author_map)
        ranked_authors = sorted(
            author_map.values(),
            key=lambda item: (
                item.popularity_score,
                self._source_total_heat_score(item),
                self._source_total_composite_score(item),
                len(item.source_videos),
            ),
            reverse=True,
        )

        selected_keys: list[str] = []
        if hot_author_total_count > 0:
            for aggregate in ranked_authors[:hot_author_total_count]:
                aggregate.selection_reasons.add("overall_hot")
                selected_keys.append(
                    self._author_key(aggregate.author_mid, aggregate.author_name)
                )

        topic_hot_authors = self._build_topic_hot_authors(
            topic_insights=topic_insights,
            author_map=author_map,
            per_topic_limit=topic_hot_author_count,
            selected_keys=selected_keys,
        )

        selected_aggregates = [
            author_map[key] for key in dict.fromkeys(selected_keys) if key in author_map
        ]
        selected_aggregates.sort(
            key=lambda item: (
                item.popularity_score,
                self._source_total_heat_score(item),
                len(item.source_videos),
            ),
            reverse=True,
        )

        fetched_view_averages = [
            self._source_average_view_count(item) for item in selected_aggregates
        ]
        baseline_median_view = (
            median(fetched_view_averages) if fetched_view_averages else 0.0
        )

        popular_authors = [
            self._build_author_read(
                aggregate,
                hot_author_video_limit=hot_author_video_limit,
                summary_basis=summary_basis,
                baseline_median_view=baseline_median_view,
                fetch_author_videos=fetch_author_videos,
            )
            for aggregate in selected_aggregates
        ]

        notes = self._build_notes(
            popular_authors=popular_authors,
            summary_basis=summary_basis,
            hot_author_video_limit=hot_author_video_limit,
        )
        return PopularAuthorAnalysisResult(
            popular_authors=popular_authors,
            topic_hot_authors=topic_hot_authors,
            author_analysis_notes=notes,
        )

    def _build_topic_hot_authors(
        self,
        *,
        topic_insights: list[TaskAnalysisTopicInsightRead],
        author_map: dict[str, _SourceAuthorAggregate],
        per_topic_limit: int,
        selected_keys: list[str],
    ) -> list[TaskAnalysisTopicHotAuthorRead]:
        if per_topic_limit <= 0:
            return []

        groups: list[TaskAnalysisTopicHotAuthorRead] = []
        for topic in topic_insights:
            topic_candidates: list[_SourceAuthorAggregate] = []
            for aggregate in author_map.values():
                if topic.topic_name not in aggregate.topic_names:
                    continue
                topic_candidates.append(aggregate)

            topic_candidates.sort(
                key=lambda item: (
                    item.topic_names.get(topic.topic_name, 0),
                    self._topic_heat_score(item, topic.topic_name),
                    item.popularity_score,
                ),
                reverse=True,
            )
            if not topic_candidates:
                continue

            chosen = topic_candidates[:per_topic_limit]
            for aggregate in chosen:
                aggregate.selection_reasons.add(f"topic:{topic.topic_name}")
                selected_keys.append(
                    self._author_key(aggregate.author_mid, aggregate.author_name)
                )
            groups.append(
                TaskAnalysisTopicHotAuthorRead(
                    topic_id=topic.topic_id,
                    topic_name=topic.topic_name,
                    authors=[
                        self._build_author_stub(aggregate, summary_basis="time")
                        for aggregate in chosen
                    ],
                )
            )
        return groups

    def _build_author_read(
        self,
        aggregate: _SourceAuthorAggregate,
        *,
        hot_author_video_limit: int,
        summary_basis: str,
        baseline_median_view: float,
        fetch_author_videos: bool,
    ) -> TaskAnalysisPopularAuthorRead:
        if not fetch_author_videos:
            return self._build_source_only_author_read(
                aggregate,
                summary_basis=summary_basis,
            )

        fetched_videos = self._fetch_author_videos(
            aggregate.author_mid,
            limit=hot_author_video_limit,
            summary_basis=summary_basis,
        )
        dominant_topics = [
            topic_name for topic_name, _count in aggregate.topic_names.most_common(3)
        ]
        ai_insights = self._build_author_ai_insights(
            aggregate=aggregate,
            fetched_videos=fetched_videos,
            dominant_topics=dominant_topics,
            summary_basis=summary_basis,
        )
        video_ai_map = {
            item["bvid"]: item
            for item in ai_insights.get("videos", [])
            if isinstance(item, dict) and item.get("bvid")
        }
        enriched_videos = [
            video.model_copy(
                update={
                    "ai_summary": (
                        str(
                            video_ai_map.get(video.bvid, {}).get("summary") or ""
                        ).strip()
                        or video.summary
                    ),
                    "content_focus": list(
                        video_ai_map.get(video.bvid, {}).get("focus") or []
                    ),
                }
            )
            for video in fetched_videos
        ]
        style_tags = self._build_style_tags(
            aggregate=aggregate,
            fetched_videos=enriched_videos,
            baseline_median_view=baseline_median_view,
            dominant_topics=dominant_topics,
        )
        summary_text = self._build_summary_text(
            aggregate=aggregate,
            fetched_videos=enriched_videos,
            summary_basis=summary_basis,
            dominant_topics=dominant_topics,
        )
        analysis_points = self._build_analysis_points(
            aggregate=aggregate,
            fetched_videos=enriched_videos,
            dominant_topics=dominant_topics,
            summary_basis=summary_basis,
        )
        return TaskAnalysisPopularAuthorRead(
            author_name=aggregate.author_name,
            author_mid=aggregate.author_mid,
            source_video_count=len(aggregate.source_videos),
            source_topic_count=len(aggregate.topic_names),
            source_total_heat_score=self._source_total_heat_score(aggregate),
            source_total_composite_score=self._source_total_composite_score(aggregate),
            source_average_engagement_rate=self._source_average_engagement_rate(
                aggregate
            ),
            source_average_view_count=self._source_average_view_count(aggregate),
            popularity_score=aggregate.popularity_score,
            dominant_topics=dominant_topics,
            style_tags=style_tags,
            selection_reasons=sorted(aggregate.selection_reasons),
            representative_video=self._representative_video(aggregate),
            fetched_video_count=len(enriched_videos),
            fetched_average_view_count=self._average(
                [float(item.view_count) for item in enriched_videos]
            ),
            fetched_average_engagement_rate=self._average_nullable(
                [item.engagement_rate for item in enriched_videos]
            )
            or 0.0,
            recent_publish_count=sum(
                1
                for item in enriched_videos
                if item.published_at is not None
                and self._hours_since(item.published_at) is not None
                and self._hours_since(item.published_at) <= 24 * 30
            ),
            summary_basis=summary_basis,
            summary_text=(
                str(ai_insights.get("recent_content_summary") or "").strip()
                or summary_text
            ),
            ai_creator_profile=str(ai_insights.get("creator_profile") or "").strip()
            or None,
            ai_recent_content_summary=(
                str(ai_insights.get("recent_content_summary") or "").strip()
                or summary_text
            ),
            ai_content_strategy=list(ai_insights.get("content_strategy") or []),
            content_keywords=list(ai_insights.get("content_keywords") or []),
            analysis_points=analysis_points,
            videos=enriched_videos,
        )

    def _build_source_only_author_read(
        self,
        aggregate: _SourceAuthorAggregate,
        *,
        summary_basis: str,
    ) -> TaskAnalysisPopularAuthorRead:
        dominant_topics = [
            topic_name for topic_name, _count in aggregate.topic_names.most_common(3)
        ]
        source_video_count = len(aggregate.source_videos)
        dominant_topic_text = " / ".join(dominant_topics) or "多主题"
        summary_text = (
            f"{aggregate.author_name} 在当前热点样本中共出现 "
            f"{source_video_count} 次，"
            f"主要关联主题为 {dominant_topic_text}。"
        )
        analysis_points = [
            (
                f"热点样本数 {len(aggregate.source_videos)}，"
                f"累计热度 {self._source_total_heat_score(aggregate):.2f}，"
                f"平均播放 {self._source_average_view_count(aggregate):.0f}。"
            ),
            (
                "当前为本地轻量分析结果，未触发创作者主页二次抓取；"
                "结论基于任务内已抓到的热点视频样本。"
            ),
        ]
        return TaskAnalysisPopularAuthorRead(
            author_name=aggregate.author_name,
            author_mid=aggregate.author_mid,
            source_video_count=source_video_count,
            source_topic_count=len(aggregate.topic_names),
            source_total_heat_score=self._source_total_heat_score(aggregate),
            source_total_composite_score=self._source_total_composite_score(aggregate),
            source_average_engagement_rate=self._source_average_engagement_rate(
                aggregate
            ),
            source_average_view_count=self._source_average_view_count(aggregate),
            popularity_score=aggregate.popularity_score,
            dominant_topics=dominant_topics,
            style_tags=[],
            selection_reasons=sorted(aggregate.selection_reasons),
            representative_video=self._representative_video(aggregate),
            fetched_video_count=0,
            fetched_average_view_count=0,
            fetched_average_engagement_rate=0,
            recent_publish_count=0,
            summary_basis=summary_basis,
            summary_text=summary_text,
            ai_recent_content_summary=summary_text,
            analysis_points=analysis_points,
            videos=[],
        )

    def _build_author_stub(
        self,
        aggregate: _SourceAuthorAggregate,
        *,
        summary_basis: str,
    ) -> TaskAnalysisPopularAuthorRead:
        return TaskAnalysisPopularAuthorRead(
            author_name=aggregate.author_name,
            author_mid=aggregate.author_mid,
            source_video_count=len(aggregate.source_videos),
            source_topic_count=len(aggregate.topic_names),
            source_total_heat_score=self._source_total_heat_score(aggregate),
            source_total_composite_score=self._source_total_composite_score(aggregate),
            source_average_engagement_rate=self._source_average_engagement_rate(
                aggregate
            ),
            source_average_view_count=self._source_average_view_count(aggregate),
            popularity_score=aggregate.popularity_score,
            dominant_topics=[
                topic_name
                for topic_name, _count in aggregate.topic_names.most_common(3)
            ],
            style_tags=[],
            selection_reasons=sorted(aggregate.selection_reasons),
            representative_video=self._representative_video(aggregate),
            summary_basis=summary_basis,
        )

    def _fetch_author_videos(
        self,
        author_mid: str | None,
        *,
        limit: int,
        summary_basis: str,
    ) -> list[TaskAnalysisAuthorVideoRead]:
        if not author_mid:
            return []

        if self.http_client is None:
            self.http_client = BilibiliHttpClient(
                settings=build_bilibili_runtime_settings(
                    self.session,
                    get_settings(),
                )
            )
        if self.browser_client is None:
            self.browser_client = BilibiliBrowserClient(
                settings=build_bilibili_runtime_settings(
                    self.session,
                    get_settings(),
                )
            )
        if self.uploader_spider is None:
            self.uploader_spider = BilibiliUploaderSpider(
                self.http_client,
                browser_client=self.browser_client,
            )
        if self.detail_spider is None:
            self.detail_spider = BilibiliDetailSpider(
                self.http_client,
                browser_client=self.browser_client,
            )

        order = "pubdate" if summary_basis == "time" else "click"
        candidates = self.uploader_spider.fetch_uploader_videos(
            author_mid,
            limit=limit,
            order=order,
        )
        videos: list[TaskAnalysisAuthorVideoRead] = []
        for candidate in candidates:
            try:
                detail = self.detail_spider.fetch_video_detail(candidate.bvid)
                like_view_ratio = self._ratio(
                    detail.metrics.like_count,
                    detail.metrics.view_count,
                )
                engagement_rate = self._engagement_rate(
                    detail.metrics.view_count,
                    detail.metrics.like_count,
                    detail.metrics.coin_count,
                    detail.metrics.favorite_count,
                    detail.metrics.share_count,
                    detail.metrics.reply_count,
                    detail.metrics.danmaku_count,
                )
                summary = self._video_summary_from_tags(
                    detail.title,
                    detail.tags,
                    detail.description,
                )
                videos.append(
                    TaskAnalysisAuthorVideoRead(
                        bvid=detail.bvid,
                        title=detail.title,
                        url=detail.url,
                        description=detail.description,
                        published_at=detail.published_at,
                        duration_seconds=detail.duration_seconds,
                        view_count=detail.metrics.view_count,
                        like_count=detail.metrics.like_count,
                        coin_count=detail.metrics.coin_count,
                        favorite_count=detail.metrics.favorite_count,
                        share_count=detail.metrics.share_count,
                        reply_count=detail.metrics.reply_count,
                        danmaku_count=detail.metrics.danmaku_count,
                        like_view_ratio=like_view_ratio,
                        engagement_rate=engagement_rate,
                        tags=list(detail.tags or []),
                        summary=summary,
                    )
                )
            except Exception:
                like_view_ratio = self._ratio(
                    candidate.like_count, candidate.play_count
                )
                engagement_rate = self._engagement_rate(
                    candidate.play_count,
                    candidate.like_count,
                    0,
                    candidate.favorite_count,
                    0,
                    candidate.comment_count,
                    candidate.danmaku_count,
                )
                videos.append(
                    TaskAnalysisAuthorVideoRead(
                        bvid=candidate.bvid,
                        title=candidate.title,
                        url=candidate.url,
                        description=candidate.description,
                        published_at=candidate.published_at,
                        duration_seconds=candidate.duration_seconds,
                        view_count=candidate.play_count,
                        like_count=candidate.like_count,
                        favorite_count=candidate.favorite_count,
                        reply_count=candidate.comment_count,
                        danmaku_count=candidate.danmaku_count,
                        like_view_ratio=like_view_ratio,
                        engagement_rate=engagement_rate,
                        tags=list(candidate.tag_names or []),
                        summary=self._video_summary_from_tags(
                            candidate.title,
                            candidate.tag_names,
                            candidate.description,
                        ),
                    )
                )
        return videos

    def _build_author_ai_insights(
        self,
        *,
        aggregate: _SourceAuthorAggregate,
        fetched_videos: list[TaskAnalysisAuthorVideoRead],
        dominant_topics: list[str],
        summary_basis: str,
    ) -> dict[str, object]:
        fallback = self._build_author_ai_fallback(
            aggregate=aggregate,
            fetched_videos=fetched_videos,
            dominant_topics=dominant_topics,
            summary_basis=summary_basis,
        )
        if not fetched_videos:
            return fallback
        if (
            not hasattr(self.ai_client, "is_available")
            or not self.ai_client.is_available()
        ):
            return fallback

        context = {
            "author_name": aggregate.author_name,
            "author_mid": aggregate.author_mid,
            "dominant_topics": dominant_topics,
            "summary_basis": summary_basis,
            "source_video_count": len(aggregate.source_videos),
            "source_total_heat_score": self._source_total_heat_score(aggregate),
            "source_average_view_count": self._source_average_view_count(aggregate),
            "videos": [
                {
                    "bvid": video.bvid,
                    "title": video.title,
                    "description": video.description,
                    "published_at": (
                        video.published_at.isoformat()
                        if video.published_at is not None
                        else None
                    ),
                    "view_count": video.view_count,
                    "engagement_rate": video.engagement_rate,
                    "tags": list(video.tags or []),
                    "summary": video.summary,
                }
                for video in fetched_videos
            ],
        }
        prompt = AiPromptBundle(
            system_prompt=(
                "你是一名负责分析 B 站创作者内容风格的中文研究助理。"
                "请只输出 JSON 对象，不要输出额外说明。"
                "JSON 必须包含 creator_profile、recent_content_summary、"
                "content_strategy、"
                "content_keywords、videos 五个字段。"
                "content_strategy 返回 3 条以内的可读中文结论。"
                "content_keywords 返回 3 到 8 个关键词。"
                "videos 里的每一项都必须包含 bvid、summary、focus。"
                "summary 需要基于视频标题、描述、标签和数据，"
                "写成 35 到 90 字的中文内容总结。"
                "focus 返回 1 到 3 个内容重点词。"
            ),
            user_prompt=(
                "请基于以下 up 主资料，总结其近期内容方向、"
                "创作侧重和每条视频的具体内容重点：\n"
                f"{json.dumps(context, ensure_ascii=False)}"
            ),
            model=(
                self.ai_client.default_model
                if hasattr(self.ai_client, "default_model")
                else ""
            ),
            fallback_model=(
                self.ai_client.fallback_model
                if hasattr(self.ai_client, "fallback_model")
                else None
            ),
            temperature=0.4,
        )
        try:
            response = self.ai_client.generate_json(prompt)
            payload = _AuthorAiEnvelope.model_validate(response.payload)
            normalized_videos = []
            for item in payload.videos:
                normalized_videos.append(
                    {
                        "bvid": item.bvid,
                        "summary": (item.summary or "").strip(),
                        "focus": [
                            value.strip() for value in item.focus if value.strip()
                        ][:3],
                    }
                )
            return {
                "creator_profile": (payload.creator_profile or "").strip(),
                "recent_content_summary": (
                    payload.recent_content_summary or ""
                ).strip(),
                "content_strategy": [
                    value.strip() for value in payload.content_strategy if value.strip()
                ][:3],
                "content_keywords": [
                    value.strip() for value in payload.content_keywords if value.strip()
                ][:8],
                "videos": normalized_videos,
            }
        except Exception:
            return fallback

    def _build_author_ai_fallback(
        self,
        *,
        aggregate: _SourceAuthorAggregate,
        fetched_videos: list[TaskAnalysisAuthorVideoRead],
        dominant_topics: list[str],
        summary_basis: str,
    ) -> dict[str, object]:
        topic_text = " / ".join(dominant_topics) if dominant_topics else "多主题"
        recent_titles = "、".join(video.title for video in fetched_videos[:3])
        keyword_counter: Counter[str] = Counter()
        video_items: list[dict[str, object]] = []
        for video in fetched_videos:
            focus = [item for item in (video.tags or []) if item][:3]
            keyword_counter.update(focus)
            video_items.append(
                {
                    "bvid": video.bvid,
                    "summary": video.summary,
                    "focus": focus,
                }
            )

        basis_label = "最近发布" if summary_basis == "time" else "热度最高"
        recent_sample_text = recent_titles or "暂无可用样本"
        creator_profile = (
            f"{aggregate.author_name} 在当前热点样本中与 {topic_text} 的关联度较高，"
            f"同时兼具 {len(aggregate.source_videos)} 条热点样本支撑。"
        )
        recent_content_summary = (
            f"按“{basis_label}”补抓后，{aggregate.author_name} "
            f"近期重点围绕 {topic_text} 持续输出，"
            f"代表内容包括 {recent_sample_text}。"
        )
        content_strategy = [
            f"内容主轴集中在 {topic_text}。",
            "选题通常围绕热点延展，而不是只停留在单条事件复述。",
            "近期投稿适合继续观察其系列化更新与话题迭代。",
        ]
        return {
            "creator_profile": creator_profile,
            "recent_content_summary": recent_content_summary,
            "content_strategy": content_strategy,
            "content_keywords": [
                keyword for keyword, _count in keyword_counter.most_common(6)
            ]
            or dominant_topics[:6],
            "videos": video_items,
        }

    def _aggregate_authors(
        self,
        video_insights: list[TaskAnalysisVideoInsightRead],
    ) -> dict[str, _SourceAuthorAggregate]:
        author_map: dict[str, _SourceAuthorAggregate] = {}
        for video in video_insights:
            author_name = (video.author_name or "").strip()
            author_mid = (video.author_mid or "").strip() or None
            if not author_name and not author_mid:
                continue

            resolved_name = author_name or f"UP {author_mid}"
            key = self._author_key(author_mid, resolved_name)
            aggregate = author_map.get(key)
            if aggregate is None:
                aggregate = _SourceAuthorAggregate(
                    author_name=resolved_name,
                    author_mid=author_mid,
                )
                author_map[key] = aggregate
            aggregate.source_videos.append(video)
            if video.topic_name:
                aggregate.topic_names[video.topic_name] += 1
        return author_map

    def _score_authors(self, author_map: dict[str, _SourceAuthorAggregate]) -> None:
        max_heat = max(
            (self._source_total_heat_score(item) for item in author_map.values()),
            default=0.0,
        )
        max_composite = max(
            (self._source_total_composite_score(item) for item in author_map.values()),
            default=0.0,
        )
        max_video_count = max(
            (len(item.source_videos) for item in author_map.values()), default=0
        )
        max_engagement = max(
            (
                self._source_average_engagement_rate(item)
                for item in author_map.values()
            ),
            default=0.0,
        )
        for aggregate in author_map.values():
            aggregate.popularity_score = round(
                0.40
                * self._normalize(self._source_total_heat_score(aggregate), max_heat)
                + 0.30
                * self._normalize(
                    self._source_total_composite_score(aggregate),
                    max_composite,
                )
                + 0.20
                * self._normalize(
                    float(len(aggregate.source_videos)), float(max_video_count)
                )
                + 0.10
                * self._normalize(
                    self._source_average_engagement_rate(aggregate),
                    max_engagement,
                ),
                4,
            )

    def _build_style_tags(
        self,
        *,
        aggregate: _SourceAuthorAggregate,
        fetched_videos: list[TaskAnalysisAuthorVideoRead],
        baseline_median_view: float,
        dominant_topics: list[str],
    ) -> list[str]:
        style_tags: list[str] = []
        if dominant_topics:
            style_tags.append(f"{dominant_topics[0]}持续输出")

        average_duration = self._average(
            [
                float(item.duration_seconds or 0)
                for item in fetched_videos
                if item.duration_seconds
            ]
        )
        if average_duration >= 1200:
            style_tags.append("长视频")
        elif 0 < average_duration <= 360:
            style_tags.append("短平快")

        average_engagement = self._average_nullable(
            [item.engagement_rate for item in fetched_videos]
        ) or self._source_average_engagement_rate(aggregate)
        if average_engagement >= 0.12:
            style_tags.append("互动密集")

        average_view = self._average(
            [float(item.view_count) for item in fetched_videos]
        )
        if average_view > 0 and average_view >= baseline_median_view:
            style_tags.append("播放体量高")

        recent_count = sum(
            1
            for item in fetched_videos
            if item.published_at is not None
            and self._hours_since(item.published_at) is not None
            and self._hours_since(item.published_at) <= 24 * 30
        )
        if fetched_videos and recent_count / len(fetched_videos) >= 0.6:
            style_tags.append("近期更新活跃")

        return style_tags[:4]

    def _build_summary_text(
        self,
        *,
        aggregate: _SourceAuthorAggregate,
        fetched_videos: list[TaskAnalysisAuthorVideoRead],
        summary_basis: str,
        dominant_topics: list[str],
    ) -> str:
        if not fetched_videos:
            if aggregate.author_mid:
                return (
                    f"{aggregate.author_name} 在当前热点样本里表现突出，"
                    "但这次没有成功补抓到用于二次总结的视频。"
                )
            return (
                f"{aggregate.author_name} 在当前热点样本里表现突出，"
                "但当前任务没有拿到可用于二次抓取的 up 主 mid。"
            )

        basis_label = "最近发布" if summary_basis == "time" else "热度最高"
        top_titles = "、".join(item.title for item in fetched_videos[:3])
        average_view = self._average(
            [float(item.view_count) for item in fetched_videos]
        )
        average_engagement = (
            self._average_nullable([item.engagement_rate for item in fetched_videos])
            or 0.0
        )
        topic_text = " / ".join(dominant_topics) if dominant_topics else "多主题"
        return (
            f"{aggregate.author_name} 由当前热点视频样本汇总进入热门 up 主名单。"
            f"进一步按“{basis_label}”补抓 {len(fetched_videos)} 条视频后，"
            f"其近期内容主要围绕 {topic_text} 展开，平均播放约 {average_view:.0f}，"
            f"平均互动率约 {average_engagement * 100:.2f}%，"
            f"代表视频包括 {top_titles}。"
        )

    def _build_analysis_points(
        self,
        *,
        aggregate: _SourceAuthorAggregate,
        fetched_videos: list[TaskAnalysisAuthorVideoRead],
        dominant_topics: list[str],
        summary_basis: str,
    ) -> list[str]:
        source_heat = self._source_total_heat_score(aggregate)
        source_view = self._source_average_view_count(aggregate)
        dominant_topic_text = "、".join(dominant_topics) or "多主题"
        points = [
            (
                f"在当前热点样本中贡献了 {len(aggregate.source_videos)} 条视频，"
                f"累计热度分 {source_heat:.2f}，平均播放 {source_view:.0f}。"
            ),
            (
                f"热点覆盖主题主要集中在 {dominant_topic_text}，"
                f"说明该 up 主与当前任务的热点主题耦合度较高。"
            ),
        ]
        if fetched_videos:
            average_duration = self._average(
                [
                    float(item.duration_seconds or 0)
                    for item in fetched_videos
                    if item.duration_seconds
                ]
            )
            average_like_ratio = (
                self._average_nullable(
                    [item.like_view_ratio for item in fetched_videos]
                )
                or 0.0
            )
            points.append(
                (
                    f"按“{'时间' if summary_basis == 'time' else '热度'}”补抓视频后，"
                    f"平均时长 {average_duration / 60:.1f} 分钟，"
                    f"平均点赞率 {average_like_ratio * 100:.2f}%。"
                )
            )
        else:
            points.append(
                "当前未完成 up 主视频二次抓取，因此画像主要基于热点样本本身。"
            )
        return points[:3]

    def _build_notes(
        self,
        *,
        popular_authors: list[TaskAnalysisPopularAuthorRead],
        summary_basis: str,
        hot_author_video_limit: int,
    ) -> list[str]:
        if not popular_authors:
            return []
        missing_mid_count = sum(1 for item in popular_authors if not item.author_mid)
        basis_label = "时间" if summary_basis == "time" else "热度"
        notes = [
            (
                f"热门 up 主画像基于当前热点视频汇总生成，再按“{basis_label}”"
                f"补抓每位 up 主最多 {hot_author_video_limit} 条视频做二次总结。"
            )
        ]
        if summary_basis == "heat":
            notes.append(
                "“热度”抓取当前使用 up 主投稿列表的播放排序 `click` 作为近似热度依据。"
            )
        if missing_mid_count > 0:
            notes.append(
                f"有 {missing_mid_count} 位热门 up 主缺少稳定 mid，"
                "只能保留热点样本内的作者画像，无法继续抓取其投稿列表。"
            )
        return notes

    def _resolve_task_options(self, task: CrawlTask) -> dict[str, object]:
        extra_params = task.extra_params if isinstance(task.extra_params, dict) else {}
        task_options = extra_params.get("task_options")
        if not isinstance(task_options, dict):
            task_options = {}
        return {
            "hot_author_total_count": task_options.get("hot_author_total_count", 0),
            "topic_hot_author_count": task_options.get("topic_hot_author_count", 0),
            "hot_author_video_limit": task_options.get("hot_author_video_limit", 10),
            "hot_author_summary_basis": task_options.get(
                "hot_author_summary_basis",
                "time",
            ),
        }

    @staticmethod
    def _author_key(author_mid: str | None, author_name: str) -> str:
        if author_mid:
            return f"mid:{author_mid}"
        return f"name:{author_name.casefold()}"

    @staticmethod
    def _source_total_heat_score(aggregate: _SourceAuthorAggregate) -> float:
        return round(sum(item.heat_score for item in aggregate.source_videos), 4)

    @staticmethod
    def _source_total_composite_score(aggregate: _SourceAuthorAggregate) -> float:
        return round(sum(item.composite_score for item in aggregate.source_videos), 4)

    def _source_average_engagement_rate(
        self, aggregate: _SourceAuthorAggregate
    ) -> float:
        return self._average(
            [item.engagement_rate or 0.0 for item in aggregate.source_videos]
        )

    def _source_average_view_count(self, aggregate: _SourceAuthorAggregate) -> float:
        return self._average(
            [float(item.view_count) for item in aggregate.source_videos]
        )

    @staticmethod
    def _topic_heat_score(
        aggregate: _SourceAuthorAggregate,
        topic_name: str,
    ) -> float:
        return round(
            sum(
                item.heat_score
                for item in aggregate.source_videos
                if item.topic_name == topic_name
            ),
            4,
        )

    @staticmethod
    def _representative_video(
        aggregate: _SourceAuthorAggregate,
    ) -> TaskAnalysisAuthorRepresentativeVideoRead | None:
        if not aggregate.source_videos:
            return None
        video = max(
            aggregate.source_videos,
            key=lambda item: (
                item.composite_score,
                item.heat_score,
                item.view_count,
            ),
        )
        return TaskAnalysisAuthorRepresentativeVideoRead(
            bvid=video.bvid,
            title=video.title,
            url=video.url,
            topic_name=video.topic_name,
            composite_score=video.composite_score,
        )

    @staticmethod
    def _video_summary_from_tags(
        title: str,
        tags: list[str] | None,
        description: str | None,
    ) -> str:
        tag_text = " / ".join((tags or [])[:3])
        if tag_text:
            return f"{title}，核心标签：{tag_text}。"
        if description:
            return f"{title}，内容摘要：{description[:70].strip()}。"
        return f"{title}。"

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round(numerator / denominator, 4)

    @classmethod
    def _engagement_rate(
        cls,
        view_count: int,
        like_count: int,
        coin_count: int,
        favorite_count: int,
        share_count: int,
        reply_count: int,
        danmaku_count: int,
    ) -> float | None:
        if view_count <= 0:
            return None
        return round(
            (
                like_count
                + coin_count
                + favorite_count
                + share_count
                + reply_count
                + danmaku_count
            )
            / view_count,
            4,
        )

    @staticmethod
    def _normalize(value: float, maximum: float) -> float:
        if maximum <= 0:
            return 0.0
        return max(min(value, maximum), 0.0) / maximum

    @staticmethod
    def _average(values: list[float]) -> float:
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _average_nullable(values: list[float | None]) -> float | None:
        filtered = [value for value in values if value is not None]
        if not filtered:
            return None
        return round(sum(filtered) / len(filtered), 4)

    @staticmethod
    def _hours_since(value) -> float | None:
        if value is None:
            return None
        return round((utc_now() - value).total_seconds() / 3600, 4)
