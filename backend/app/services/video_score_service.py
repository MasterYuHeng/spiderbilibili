from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from app.crawler.models import CrawledVideoBundle, ScoredVideo

DEFAULT_RELEVANCE_WEIGHT = 0.4
DEFAULT_HEAT_WEIGHT = 0.6
DEFAULT_HEAT_DIMENSIONS = [
    "view_count",
    "like_count",
    "coin_count",
    "favorite_count",
    "reply_count",
    "danmaku_count",
]


class VideoScoreService:
    def score_video(
        self,
        keyword: str,
        bundle: CrawledVideoBundle,
        *,
        scoring_weights: dict[str, Any] | None = None,
    ) -> ScoredVideo:
        keyword_normalized = keyword.casefold().strip()
        title_text = bundle.detail.title.casefold()
        description_text = (
            f"{bundle.candidate.description}\n{bundle.detail.description}".casefold()
        )
        tag_texts = [
            tag.casefold()
            for tag in (bundle.detail.tags or bundle.candidate.tag_names)
        ]

        keyword_hit_title = (
            keyword_normalized in title_text if keyword_normalized else False
        )
        keyword_hit_description = (
            keyword_normalized in description_text if keyword_normalized else False
        )
        keyword_hit_tags = any(
            keyword_normalized in tag for tag in tag_texts if keyword_normalized
        )

        title_score = 1.0 if keyword_hit_title else 0.0
        description_score = 0.75 if keyword_hit_description else 0.0
        tag_score = 0.6 if keyword_hit_tags else 0.0
        hit_column_score = min(len(bundle.candidate.hit_columns) * 0.1, 0.3)
        relevance_score = min(
            (title_score * 0.5)
            + (description_score * 0.25)
            + (tag_score * 0.15)
            + hit_column_score,
            1.0,
        )

        metrics = bundle.detail.metrics
        heat_dimensions = self._normalize_heat_dimensions(
            scoring_weights.get("heat_dimensions") if scoring_weights else None
        )
        heat_score = self._calculate_heat_score(metrics, heat_dimensions)

        relevance_weight = (
            float(scoring_weights.get("relevance_weight", DEFAULT_RELEVANCE_WEIGHT))
            if scoring_weights
            else DEFAULT_RELEVANCE_WEIGHT
        )
        heat_weight = (
            float(scoring_weights.get("heat_weight", DEFAULT_HEAT_WEIGHT))
            if scoring_weights
            else DEFAULT_HEAT_WEIGHT
        )
        composite_score = (relevance_score * relevance_weight) + (
            heat_score * heat_weight
        )

        return ScoredVideo(
            bundle=bundle,
            keyword_hit_title=keyword_hit_title,
            keyword_hit_description=keyword_hit_description,
            keyword_hit_tags=keyword_hit_tags,
            relevance_score=round(relevance_score, 4),
            heat_score=round(heat_score, 4),
            composite_score=round(composite_score, 4),
        )

    @staticmethod
    def _calculate_heat_score(metrics, dimensions: list[str]) -> float:
        weighted_values = []
        metric_weights = {
            "view_count": 1.0,
            "like_count": 1.1,
            "coin_count": 1.3,
            "favorite_count": 1.2,
            "share_count": 1.0,
            "reply_count": 0.9,
            "danmaku_count": 0.8,
        }
        for dimension in dimensions:
            raw_value = getattr(metrics, dimension, 0) or 0
            normalized = math.log1p(raw_value)
            weighted_values.append(normalized * metric_weights.get(dimension, 1.0))

        if not weighted_values:
            return 0.0
        return min(sum(weighted_values) / (len(weighted_values) * 10), 1.0)

    @staticmethod
    def _normalize_heat_dimensions(value: object) -> list[str]:
        if not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            return list(DEFAULT_HEAT_DIMENSIONS)
        normalized = [item for item in value if isinstance(item, str) and item]
        return normalized or list(DEFAULT_HEAT_DIMENSIONS)
