from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.analysis import AiSummary, TopicCluster, TopicVideoRelation
from app.models.enums import TaskStage
from app.models.task import CrawlTask, TaskVideo
from app.models.video import Video
from app.services.system_config_service import get_topic_clustering_defaults
from app.services.task_log_service import create_task_log
from app.services.task_service import assert_task_execution_allowed

NON_WORD_PATTERN = re.compile(r"[^\w\u4e00-\u9fff]+")
TRAILING_INDEX_PATTERN = re.compile(r"(相关)?\d+$")
TITLE_SPLIT_PATTERN = re.compile(r"[-_/｜丨:：·,，【】()\[\]]+")
RESERVED_TOPIC_NAMES = {
    "unclassified",
    "unknown",
    "misc",
    "other",
    "others",
    "general",
    "topic",
    "topics",
    "其他",
    "其它",
    "未知",
    "未分类",
    "杂项",
    "视频主题",
}


@dataclass(slots=True)
class TopicClusterResult:
    cluster_count: int
    relation_count: int
    primary_cluster_count: int


@dataclass(slots=True)
class _TopicVideoTarget:
    task_video: TaskVideo
    video: Video
    ai_summary: AiSummary


@dataclass(slots=True)
class _ClusterAggregation:
    display_name: str
    normalized_name: str
    keywords: Counter[str] = field(default_factory=Counter)
    topic_frequency: Counter[str] = field(default_factory=Counter)
    summaries: list[str] = field(default_factory=list)
    relations: list[dict[str, object]] = field(default_factory=list)


class TopicClusterService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.logger = get_logger(__name__)

    def cluster_task(
        self,
        task: CrawlTask,
        *,
        expected_dispatch_generation: int | None = None,
    ) -> TopicClusterResult:
        defaults = get_topic_clustering_defaults(self.session)
        targets = self._load_targets(task.id)
        fallback_primary_topic = str(defaults["fallback_primary_topic"])

        self._reset_task_topics(task.id)
        self.session.flush()

        if not targets:
            task.clustered_topics = 0
            self.session.commit()
            return TopicClusterResult(
                cluster_count=0,
                relation_count=0,
                primary_cluster_count=0,
            )

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.TOPIC,
            message="Starting topic clustering for AI summaries.",
            payload={"ai_summary_count": len(targets)},
        )
        self.session.commit()

        clusters_by_name: dict[str, _ClusterAggregation] = {}

        for target in targets:
            task = assert_task_execution_allowed(
                self.session,
                task.id,
                expected_dispatch_generation=expected_dispatch_generation,
            )
            cluster_candidates = self._resolve_cluster_candidates(
                target,
                defaults=defaults,
                fallback_primary_topic=fallback_primary_topic,
            )
            primary_name = cluster_candidates[0]
            seen_names: set[str] = set()

            for index, normalized_name in enumerate(cluster_candidates):
                if normalized_name in seen_names:
                    continue
                seen_names.add(normalized_name)
                is_primary = index == 0

                cluster = clusters_by_name.get(normalized_name)
                if cluster is None:
                    cluster = _ClusterAggregation(
                        display_name=self._display_name_for_cluster(
                            normalized_name,
                            target,
                        ),
                        normalized_name=normalized_name,
                    )
                    clusters_by_name[normalized_name] = cluster

                self._append_relation(
                    cluster,
                    target,
                    is_primary=is_primary,
                    primary_cluster_name=primary_name,
                )

        clusters = self._merge_small_clusters(
            clusters_by_name,
            min_cluster_size=int(defaults["min_cluster_size"]),
        )
        clusters = self._limit_cluster_count(
            clusters,
            max_cluster_count=int(defaults["max_cluster_count"]),
        )
        ordered_clusters = sorted(clusters.values(), key=self._cluster_sort_key)

        relation_count = 0
        primary_cluster_count = 0
        for cluster_order, aggregation in enumerate(ordered_clusters, start=1):
            consolidated_relations = self._consolidate_cluster_relations(aggregation)
            if any(bool(relation["is_primary"]) for relation in consolidated_relations):
                primary_cluster_count += 1

            total_heat_score = sum(
                (
                    Decimal(str(relation["heat_score"]))
                    for relation in consolidated_relations
                ),
                start=Decimal("0"),
            )
            topic_cluster = TopicCluster(
                task_id=task.id,
                name=aggregation.display_name,
                normalized_name=aggregation.normalized_name,
                description=self._build_cluster_description(aggregation),
                keywords=self._rank_keywords(
                    aggregation.keywords,
                    aggregation.topic_frequency,
                    max_keywords=int(defaults["max_topic_keywords"]),
                ),
                video_count=len(consolidated_relations),
                total_heat_score=self._quantize_decimal(total_heat_score),
                average_heat_score=self._quantize_decimal(
                    total_heat_score / max(len(consolidated_relations), 1)
                ),
                cluster_order=cluster_order,
            )
            self.session.add(topic_cluster)
            self.session.flush()

            for relation in consolidated_relations:
                self.session.add(
                    TopicVideoRelation(
                        task_id=task.id,
                        topic_cluster_id=topic_cluster.id,
                        video_id=str(relation["video_id"]),
                        ai_summary_id=relation["ai_summary_id"],
                        relevance_score=self._quantize_decimal(
                            Decimal(str(relation["relevance_score"]))
                        ),
                        is_primary=bool(relation["is_primary"]),
                    )
                )
                relation_count += 1

        task.clustered_topics = len(ordered_clusters)
        task.extra_params = self._merge_topic_payload(
            task.extra_params,
            {
                "topic_stats": {
                    "cluster_count": len(ordered_clusters),
                    "relation_count": relation_count,
                    "primary_cluster_count": primary_cluster_count,
                }
            },
        )
        self.session.commit()

        create_task_log(
            self.session,
            task=task,
            stage=TaskStage.TOPIC,
            message="Finished topic clustering and persisted topic relations.",
            payload={
                "cluster_count": len(ordered_clusters),
                "relation_count": relation_count,
                "primary_cluster_count": primary_cluster_count,
            },
        )
        self.session.commit()

        return TopicClusterResult(
            cluster_count=len(ordered_clusters),
            relation_count=relation_count,
            primary_cluster_count=primary_cluster_count,
        )

    def _load_targets(self, task_id: str) -> list[_TopicVideoTarget]:
        statement = (
            select(TaskVideo, Video, AiSummary)
            .join(Video, Video.id == TaskVideo.video_id)
            .join(
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
        return [
            _TopicVideoTarget(task_video=task_video, video=video, ai_summary=ai_summary)
            for task_video, video, ai_summary in self.session.execute(statement).all()
        ]

    def _reset_task_topics(self, task_id: str) -> None:
        self.session.execute(
            delete(TopicVideoRelation).where(TopicVideoRelation.task_id == task_id)
        )
        self.session.execute(
            delete(TopicCluster).where(TopicCluster.task_id == task_id)
        )

    def _append_relation(
        self,
        aggregation: _ClusterAggregation,
        target: _TopicVideoTarget,
        *,
        is_primary: bool,
        primary_cluster_name: str,
    ) -> None:
        aggregation.summaries.append(target.ai_summary.summary)
        aggregation.topic_frequency.update(
            topic for topic in target.ai_summary.topics if topic
        )
        aggregation.keywords.update(self._extract_cluster_keywords(target))
        aggregation.relations.append(
            {
                "video_id": target.video.id,
                "ai_summary_id": target.ai_summary.id,
                "is_primary": is_primary,
                "relevance_score": self._build_relation_score(
                    target.task_video.relevance_score,
                    target.ai_summary.confidence,
                    is_primary=is_primary,
                ),
                "heat_score": target.task_video.heat_score,
                "primary_cluster_name": primary_cluster_name,
            }
        )

    def _resolve_cluster_candidates(
        self,
        target: _TopicVideoTarget,
        *,
        defaults: dict[str, object],
        fallback_primary_topic: str,
    ) -> list[str]:
        raw_topics = [target.ai_summary.primary_topic, *target.ai_summary.topics]
        normalized_topics: list[str] = []
        seen: set[str] = set()

        for topic in raw_topics:
            normalized = self._normalize_topic_name(topic, defaults)
            if normalized is None or normalized in seen:
                continue
            normalized_topics.append(normalized)
            seen.add(normalized)

        if not normalized_topics:
            fallback_name = self._derive_topic_from_target(
                target,
                defaults=defaults,
                fallback_primary_topic=fallback_primary_topic,
            )
            normalized_topics.append(fallback_name)

        return normalized_topics

    def _normalize_topic_name(
        self,
        value: str | None,
        defaults: dict[str, object],
    ) -> str | None:
        if value is None:
            return None
        normalized = NON_WORD_PATTERN.sub(" ", value).strip().casefold()
        normalized = TRAILING_INDEX_PATTERN.sub("", normalized).strip()
        if not normalized or normalized in RESERVED_TOPIC_NAMES:
            return None

        alias_map = self._build_alias_map(defaults)
        normalized = alias_map.get(normalized, normalized)
        stop_topics = {
            self._normalize_stop_topic(topic)
            for topic in defaults.get("stop_topics", [])
        }
        stop_topics.update(RESERVED_TOPIC_NAMES)
        if normalized in stop_topics:
            return None
        return normalized

    @staticmethod
    def _normalize_stop_topic(value: object) -> str:
        return NON_WORD_PATTERN.sub(" ", str(value)).strip().casefold()

    def _build_alias_map(self, defaults: dict[str, object]) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        raw_aliases = defaults.get("topic_aliases", {})
        if not isinstance(raw_aliases, dict):
            return alias_map

        for canonical, aliases in raw_aliases.items():
            normalized_canonical = (
                NON_WORD_PATTERN.sub(
                    " ",
                    str(canonical),
                )
                .strip()
                .casefold()
            )
            if not normalized_canonical:
                continue
            alias_map[normalized_canonical] = normalized_canonical
            if not isinstance(aliases, list):
                continue
            for alias in aliases:
                normalized_alias = (
                    NON_WORD_PATTERN.sub(
                        " ",
                        str(alias),
                    )
                    .strip()
                    .casefold()
                )
                if normalized_alias:
                    alias_map[normalized_alias] = normalized_canonical
        return alias_map

    def _derive_topic_from_target(
        self,
        target: _TopicVideoTarget,
        *,
        defaults: dict[str, object],
        fallback_primary_topic: str,
    ) -> str:
        candidate_sources = [
            target.ai_summary.primary_topic,
            *target.ai_summary.topics,
            *(target.video.tags or []),
            self._topic_from_title(target.video.title),
            fallback_primary_topic,
        ]
        for candidate in candidate_sources:
            normalized = self._normalize_topic_name(candidate, defaults)
            if normalized is not None:
                return normalized
        return "video topic"

    def _topic_from_title(self, title: str) -> str | None:
        for part in TITLE_SPLIT_PATTERN.split(title):
            candidate = NON_WORD_PATTERN.sub(" ", part).strip()
            if 2 <= len(candidate) <= 16:
                return candidate
        trimmed = NON_WORD_PATTERN.sub(" ", title[:16]).strip()
        return trimmed or None

    def _display_name_for_cluster(
        self,
        normalized_name: str,
        target: _TopicVideoTarget,
    ) -> str:
        topics = [target.ai_summary.primary_topic, *target.ai_summary.topics]
        for topic in topics:
            if topic is None:
                continue
            candidate = NON_WORD_PATTERN.sub(" ", topic).strip()
            if candidate and candidate.casefold() == normalized_name:
                return candidate
        return normalized_name.title() if normalized_name.isascii() else normalized_name

    def _extract_cluster_keywords(self, target: _TopicVideoTarget) -> Iterable[str]:
        keywords: list[str] = []
        keywords.extend(topic for topic in target.ai_summary.topics if topic)
        keywords.extend(tag for tag in target.video.tags or [] if tag)
        if target.ai_summary.primary_topic:
            keywords.append(target.ai_summary.primary_topic)
        return keywords

    @staticmethod
    def _build_relation_score(
        relevance_score: Decimal,
        confidence: Decimal | None,
        *,
        is_primary: bool,
    ) -> Decimal:
        confidence_value = confidence or Decimal("0.5")
        base = relevance_score * Decimal("0.7") + confidence_value * Decimal("0.3")
        if not is_primary:
            base *= Decimal("0.8")
        return base

    def _merge_small_clusters(
        self,
        clusters_by_name: dict[str, _ClusterAggregation],
        *,
        min_cluster_size: int,
    ) -> dict[str, _ClusterAggregation]:
        if min_cluster_size <= 1:
            return clusters_by_name

        candidate_names = [
            name
            for name, cluster in clusters_by_name.items()
            if not self._cluster_has_primary_relation(cluster)
            and len({item["video_id"] for item in cluster.relations}) < min_cluster_size
        ]
        for source_name in candidate_names:
            self._redistribute_cluster_relations(clusters_by_name, source_name)

        return clusters_by_name

    def _limit_cluster_count(
        self,
        clusters_by_name: dict[str, _ClusterAggregation],
        *,
        max_cluster_count: int,
    ) -> dict[str, _ClusterAggregation]:
        if len(clusters_by_name) <= max_cluster_count:
            return clusters_by_name

        ordered_names = [
            aggregation.normalized_name
            for aggregation in sorted(
                clusters_by_name.values(),
                key=self._cluster_sort_key,
            )
        ]
        keep_names = set(ordered_names[:max_cluster_count])
        excess_names = ordered_names[max_cluster_count:]

        for source_name in reversed(excess_names):
            self._redistribute_cluster_relations(
                clusters_by_name,
                source_name,
                allowed_target_names=keep_names,
            )

        return clusters_by_name

    def _redistribute_cluster_relations(
        self,
        clusters_by_name: dict[str, _ClusterAggregation],
        source_name: str,
        *,
        allowed_target_names: set[str] | None = None,
    ) -> None:
        source_cluster = clusters_by_name.get(source_name)
        if source_cluster is None:
            return

        candidate_target_names = set(allowed_target_names or clusters_by_name.keys())
        candidate_target_names.discard(source_name)
        if not candidate_target_names:
            return

        touched_targets: set[str] = set()
        for relation in list(source_cluster.relations):
            target_name = self._select_merge_target(
                source_cluster,
                relation,
                clusters_by_name,
                candidate_target_names,
            )
            target_cluster = clusters_by_name.get(target_name)
            if target_cluster is None:
                continue
            target_cluster.relations.append(dict(relation))
            touched_targets.add(target_name)

        for target_name in touched_targets:
            target_cluster = clusters_by_name[target_name]
            target_cluster.keywords.update(source_cluster.keywords)
            target_cluster.topic_frequency.update(source_cluster.topic_frequency)
            if source_cluster.summaries:
                target_cluster.summaries.append(source_cluster.summaries[0])

        del clusters_by_name[source_name]

    def _select_merge_target(
        self,
        source_cluster: _ClusterAggregation,
        relation: dict[str, object],
        clusters_by_name: dict[str, _ClusterAggregation],
        candidate_target_names: set[str],
    ) -> str:
        primary_cluster_name = relation.get("primary_cluster_name")
        if (
            isinstance(primary_cluster_name, str)
            and primary_cluster_name in candidate_target_names
        ):
            return primary_cluster_name

        best_name: str | None = None
        best_score = float("-inf")
        for candidate_name in candidate_target_names:
            candidate_cluster = clusters_by_name.get(candidate_name)
            if candidate_cluster is None:
                continue
            score = self._cluster_similarity_score(source_cluster, candidate_cluster)
            if score > best_score:
                best_score = score
                best_name = candidate_name

        if best_name is not None:
            return best_name
        return sorted(candidate_target_names)[0]

    def _cluster_similarity_score(
        self,
        source_cluster: _ClusterAggregation,
        target_cluster: _ClusterAggregation,
    ) -> float:
        source_relations = self._consolidate_cluster_relations(source_cluster)
        target_relations = self._consolidate_cluster_relations(target_cluster)
        source_video_ids = {str(item["video_id"]) for item in source_relations}
        target_video_ids = {str(item["video_id"]) for item in target_relations}
        shared_videos = len(source_video_ids & target_video_ids)

        source_signature = self._cluster_signature(source_cluster)
        target_signature = self._cluster_signature(target_cluster)
        signature_overlap = (
            len(source_signature & target_signature)
            / len(source_signature | target_signature)
            if source_signature and target_signature
            else 0.0
        )

        source_keywords = set(
            self._rank_keywords(
                source_cluster.keywords,
                source_cluster.topic_frequency,
                max_keywords=4,
            )
        )
        target_keywords = set(
            self._rank_keywords(
                target_cluster.keywords,
                target_cluster.topic_frequency,
                max_keywords=4,
            )
        )
        keyword_overlap = (
            len(source_keywords & target_keywords)
            / len(source_keywords | target_keywords)
            if source_keywords and target_keywords
            else 0.0
        )

        name_similarity = SequenceMatcher(
            None,
            source_cluster.normalized_name,
            target_cluster.normalized_name,
        ).ratio()

        primary_bonus = (
            0.25 if self._cluster_has_primary_relation(target_cluster) else 0.0
        )
        return (
            shared_videos * 2.0
            + signature_overlap * 1.5
            + keyword_overlap
            + name_similarity * 0.5
            + primary_bonus
        )

    def _cluster_signature(self, aggregation: _ClusterAggregation) -> set[str]:
        signature = set(aggregation.normalized_name.split())
        compact_name = aggregation.normalized_name.replace(" ", "")
        signature.update(
            compact_name[index : index + 2]
            for index in range(max(len(compact_name) - 1, 0))
            if len(compact_name[index : index + 2]) == 2
        )
        for keyword in self._rank_keywords(
            aggregation.keywords,
            aggregation.topic_frequency,
            max_keywords=4,
        ):
            normalized_keyword = NON_WORD_PATTERN.sub(" ", keyword).strip().casefold()
            if normalized_keyword:
                signature.add(normalized_keyword)
        return signature

    @staticmethod
    def _cluster_has_primary_relation(aggregation: _ClusterAggregation) -> bool:
        return any(bool(relation["is_primary"]) for relation in aggregation.relations)

    def _rank_keywords(
        self,
        keyword_counter: Counter[str],
        topic_counter: Counter[str],
        *,
        max_keywords: int,
    ) -> list[str]:
        combined = defaultdict(int)
        for key, value in keyword_counter.items():
            normalized = NON_WORD_PATTERN.sub(" ", key).strip()
            if normalized:
                combined[normalized] += int(value)
        for key, value in topic_counter.items():
            normalized = NON_WORD_PATTERN.sub(" ", key).strip()
            if normalized:
                combined[normalized] += int(value) * 2

        ranked = sorted(combined.items(), key=lambda item: (-item[1], item[0]))
        return [keyword for keyword, _ in ranked[:max_keywords]]

    def _build_cluster_description(self, aggregation: _ClusterAggregation) -> str:
        keywords = self._rank_keywords(
            aggregation.keywords,
            aggregation.topic_frequency,
            max_keywords=3,
        )
        if keywords:
            keyword_text = "、".join(keywords)
            return f"该主题主要围绕 {keyword_text} 展开。"
        if aggregation.summaries:
            return aggregation.summaries[0][:120]
        return f"{aggregation.display_name} 主题聚合结果。"

    def _consolidate_cluster_relations(
        self,
        aggregation: _ClusterAggregation,
    ) -> list[dict[str, object]]:
        merged_relations: dict[str, dict[str, object]] = {}

        for relation in aggregation.relations:
            video_id = str(relation["video_id"])
            current = merged_relations.get(video_id)
            if current is None:
                merged_relations[video_id] = dict(relation)
                continue

            current["is_primary"] = bool(current["is_primary"]) or bool(
                relation["is_primary"]
            )
            current["relevance_score"] = max(
                Decimal(str(current["relevance_score"])),
                Decimal(str(relation["relevance_score"])),
            )
            current["heat_score"] = max(
                Decimal(str(current["heat_score"])),
                Decimal(str(relation["heat_score"])),
            )
            if current.get("ai_summary_id") is None:
                current["ai_summary_id"] = relation.get("ai_summary_id")
            if (
                not current.get("primary_cluster_name")
                and relation.get("primary_cluster_name") is not None
            ):
                current["primary_cluster_name"] = relation.get("primary_cluster_name")

        return sorted(
            merged_relations.values(),
            key=lambda item: (
                not bool(item["is_primary"]),
                -Decimal(str(item["relevance_score"])),
                str(item["video_id"]),
            ),
        )

    def _cluster_sort_key(
        self,
        aggregation: _ClusterAggregation,
    ) -> tuple[int, Decimal, str]:
        consolidated_relations = self._consolidate_cluster_relations(aggregation)
        total_heat_score = sum(
            (
                Decimal(str(relation["heat_score"]))
                for relation in consolidated_relations
            ),
            start=Decimal("0"),
        )
        return (
            -len(consolidated_relations),
            -total_heat_score,
            aggregation.display_name,
        )

    @staticmethod
    def _merge_topic_payload(
        extra_params: dict | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        merged = dict(extra_params or {})
        merged.update(payload)
        return merged

    @staticmethod
    def _quantize_decimal(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.0001"))
