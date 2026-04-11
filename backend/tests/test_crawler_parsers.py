from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.crawler.detail_spider import BilibiliDetailSpider
from app.crawler.exceptions import BilibiliParseError
from app.crawler.subtitle_spider import BilibiliSubtitleSpider
from app.crawler.uploader_spider import BilibiliUploaderSpider

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "crawler"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_video_detail_fixture_extracts_core_fields() -> None:
    payload = load_fixture("detail_payload.json")

    detail = BilibiliDetailSpider.parse_video_detail(payload)

    assert detail.bvid == "BV1parser001"
    assert detail.aid == 778899
    assert detail.title == "AI 实战拆解：从检索到主题聚类"
    assert detail.description.startswith("这是一条用于解析测试的视频简介")
    assert detail.author_name == "测试解析 UP"
    assert detail.author_mid == "424242"
    assert detail.cover_url == "https://i0.hdslb.com/detail-cover.jpg"
    assert detail.duration_seconds == 754
    assert detail.metrics.view_count == 12800
    assert detail.metrics.like_count == 2300
    assert detail.metrics.danmaku_count == 321
    assert detail.tags == ["AI", "内容分析", "工作流"]
    assert len(detail.pages) == 2
    assert detail.pages[0].cid == 90001
    assert detail.pages[1].duration_seconds == 394


def test_parse_video_detail_raises_when_view_data_is_missing() -> None:
    with pytest.raises(BilibiliParseError, match="missing View data"):
        BilibiliDetailSpider.parse_video_detail({"data": {}})


def test_pick_best_subtitle_meta_prefers_expected_languages() -> None:
    payload = load_fixture("subtitle_meta_payload.json")
    spider = BilibiliSubtitleSpider(http_client=None)  # type: ignore[arg-type]

    subtitle_meta = spider._pick_best_subtitle_meta(payload)

    assert subtitle_meta is not None
    assert subtitle_meta["lan"] == "zh-CN"


def test_parse_subtitle_payload_filters_empty_segments_and_normalizes_text() -> None:
    subtitle_meta = {
        "lan": "zh-CN",
        "lan_doc": "中文（自动生成）",
        "subtitle_url": "//i0.hdslb.com/subtitle-body.json",
    }
    subtitle_payload = load_fixture("subtitle_body_payload.json")

    subtitle = BilibiliSubtitleSpider.parse_subtitle_payload(
        subtitle_meta=subtitle_meta,
        subtitle_payload=subtitle_payload,
    )

    assert subtitle.subtitle_url == "https://i0.hdslb.com/subtitle-body.json"
    assert subtitle.language_code == "zh-CN"
    assert subtitle.language_name == "中文（自动生成）"
    assert [segment.content for segment in subtitle.segments] == [
        "大家好，欢迎来到解析测试。",
        "这一段字幕会保留。",
        "这里会把 HTML 标签去掉。",
    ]
    assert subtitle.segments[0].start_seconds == 0.5
    assert subtitle.segments[-1].end_seconds == 7.8


def test_parse_subtitle_payload_requires_body_segments() -> None:
    with pytest.raises(BilibiliParseError, match="missing body segments"):
        BilibiliSubtitleSpider.parse_subtitle_payload(
            subtitle_meta={
                "lan": "zh-CN",
                "lan_doc": "中文",
                "subtitle_url": "//x.json",
            },
            subtitle_payload={},
        )


def test_parse_uploader_page_data_extracts_author_video_candidates() -> None:
    payload = {
        "data": {
            "page": {"count": 2, "pn": 1, "ps": 2},
            "list": {
                "vlist": [
                    {
                        "aid": 1001,
                        "bvid": "BV1author1",
                        "title": "作者热门视频 1",
                        "description": "作者视频简介",
                        "author": "测试 UP",
                        "mid": "8899",
                        "pic": "//i0.hdslb.com/author-cover.jpg",
                        "created": 1775779200,
                        "length": "10:05",
                        "play": "12.3万",
                        "comment": "345",
                    }
                ]
            },
        }
    }

    page = BilibiliUploaderSpider.parse_uploader_page_data(
        payload,
        author_mid="8899",
        page=1,
        page_size=2,
    )

    assert page.total_results == 2
    assert page.total_pages == 1
    assert len(page.candidates) == 1
    candidate = page.candidates[0]
    assert candidate.bvid == "BV1author1"
    assert candidate.author_mid == "8899"
    assert candidate.author_name == "测试 UP"
    assert candidate.duration_seconds == 605
    assert candidate.play_count == 123000
    assert candidate.comment_count == 345
    assert candidate.cover_url == "https://i0.hdslb.com/author-cover.jpg"
