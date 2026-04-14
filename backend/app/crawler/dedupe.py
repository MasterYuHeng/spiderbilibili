from __future__ import annotations

from app.crawler.models import SearchVideoCandidate


def dedupe_search_candidates(
    candidates: list[SearchVideoCandidate],
    *,
    source_keyword: str | None = None,
) -> list[SearchVideoCandidate]:
    deduped: dict[str, SearchVideoCandidate] = {}
    for candidate in candidates:
        current = deduped.get(candidate.bvid)
        if current is None:
            deduped[candidate.bvid] = candidate
            continue

        deduped[candidate.bvid] = _merge_candidates(
            current,
            candidate,
            source_keyword=source_keyword,
        )

    return sorted(deduped.values(), key=lambda item: item.search_rank)


def _merge_candidates(
    left: SearchVideoCandidate,
    right: SearchVideoCandidate,
    *,
    source_keyword: str | None = None,
) -> SearchVideoCandidate:
    primary = left if left.search_rank <= right.search_rank else right
    secondary = right if primary is left else left

    merged_matched_keywords = _merge_matched_keywords(
        left.matched_keywords,
        right.matched_keywords,
    )
    primary.matched_keywords = merged_matched_keywords
    primary.primary_matched_keyword = _resolve_primary_matched_keyword(
        left,
        right,
        source_keyword=source_keyword,
        merged_matched_keywords=merged_matched_keywords,
    )
    if primary.primary_matched_keyword:
        primary.keyword = primary.primary_matched_keyword
    primary.search_rank = min(left.search_rank, right.search_rank)
    primary.hit_columns = sorted(set(primary.hit_columns) | set(secondary.hit_columns))
    primary.tag_names = sorted(set(primary.tag_names) | set(secondary.tag_names))
    primary.play_count = max(primary.play_count, secondary.play_count)
    primary.like_count = max(primary.like_count, secondary.like_count)
    primary.favorite_count = max(primary.favorite_count, secondary.favorite_count)
    primary.comment_count = max(primary.comment_count, secondary.comment_count)
    primary.danmaku_count = max(primary.danmaku_count, secondary.danmaku_count)
    if len(primary.description) < len(secondary.description):
        primary.description = secondary.description
    return primary


def _merge_matched_keywords(
    left: list[str],
    right: list[str],
) -> list[str]:
    merged_values: list[str] = []
    seen: set[str] = set()
    for item in [*left, *right]:
        normalized_item = str(item or "").strip()
        if not normalized_item or normalized_item in seen:
            continue
        merged_values.append(normalized_item)
        seen.add(normalized_item)
    return merged_values


def _resolve_primary_matched_keyword(
    left: SearchVideoCandidate,
    right: SearchVideoCandidate,
    *,
    source_keyword: str | None,
    merged_matched_keywords: list[str],
) -> str | None:
    normalized_source_keyword = str(source_keyword or "").strip()
    if normalized_source_keyword and normalized_source_keyword in merged_matched_keywords:
        return normalized_source_keyword

    left_primary = left.primary_matched_keyword or left.keyword or None
    right_primary = right.primary_matched_keyword or right.keyword or None
    if left.search_rank <= right.search_rank:
        return left_primary or right_primary
    return right_primary or left_primary
