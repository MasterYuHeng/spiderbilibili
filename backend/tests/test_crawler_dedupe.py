from app.crawler.dedupe import dedupe_search_candidates
from app.testsupport import build_search_candidate


def test_dedupe_search_candidates_prioritizes_source_keyword() -> None:
    original_candidate = build_search_candidate(
        "BV1dup",
        "和平精英",
        search_rank=8,
    )
    synonym_candidate = build_search_candidate(
        "BV1dup",
        "吃鸡",
        search_rank=2,
    )

    deduped = dedupe_search_candidates(
        [original_candidate, synonym_candidate],
        source_keyword="和平精英",
    )

    assert len(deduped) == 1
    assert deduped[0].search_rank == 2
    assert deduped[0].matched_keywords == ["和平精英", "吃鸡"]
    assert deduped[0].primary_matched_keyword == "和平精英"
    assert deduped[0].keyword_match_count == 2


def test_dedupe_search_candidates_uses_best_rank_without_source_keyword() -> None:
    first_synonym_candidate = build_search_candidate(
        "BV1dup",
        "吃鸡",
        search_rank=9,
    )
    better_rank_synonym_candidate = build_search_candidate(
        "BV1dup",
        "大逃杀",
        search_rank=3,
    )

    deduped = dedupe_search_candidates(
        [first_synonym_candidate, better_rank_synonym_candidate],
        source_keyword="和平精英",
    )

    assert len(deduped) == 1
    assert deduped[0].search_rank == 3
    assert deduped[0].matched_keywords == ["吃鸡", "大逃杀"]
    assert deduped[0].primary_matched_keyword == "大逃杀"
    assert deduped[0].keyword_match_count == 2
