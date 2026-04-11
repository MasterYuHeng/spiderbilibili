from __future__ import annotations

from app.crawler.models import SearchVideoCandidate


def dedupe_search_candidates(
    candidates: list[SearchVideoCandidate],
) -> list[SearchVideoCandidate]:
    deduped: dict[str, SearchVideoCandidate] = {}
    for candidate in candidates:
        current = deduped.get(candidate.bvid)
        if current is None:
            deduped[candidate.bvid] = candidate
            continue

        deduped[candidate.bvid] = _merge_candidates(current, candidate)

    return sorted(deduped.values(), key=lambda item: item.search_rank)


def _merge_candidates(
    left: SearchVideoCandidate,
    right: SearchVideoCandidate,
) -> SearchVideoCandidate:
    primary = left if left.search_rank <= right.search_rank else right
    secondary = right if primary is left else left

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
