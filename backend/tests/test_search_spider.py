from datetime import timezone

from app.crawler.search_spider import BilibiliSearchSpider


def test_parse_search_page_data_normalizes_video_candidates() -> None:
    payload = {
        "code": 0,
        "data": {
            "page": 1,
            "pagesize": 20,
            "numResults": 100,
            "numPages": 5,
            "result": [
                {
                    "bvid": "BV1test12345",
                    "aid": 123,
                    "title": '这是一个<em class="keyword">AI</em>视频',
                    "description": '用于测试的<em class="keyword">描述</em>',
                    "author": "测试UP",
                    "mid": 999,
                    "arcurl": "https://www.bilibili.com/video/BV1test12345",
                    "pic": "//i0.hdslb.com/cover.jpg",
                    "pubdate": 1_700_000_000,
                    "duration": "01:02:03",
                    "play": "3.5万",
                    "like": 1200,
                    "favorites": "678",
                    "review": "45",
                    "video_review": "321",
                    "tag": "AI,人工智能",
                    "hit_columns": ["title", "description"],
                    "rank_index": 3,
                }
            ],
        },
    }

    page_data = BilibiliSearchSpider.parse_search_page_data(
        payload,
        keyword="AI",
        page=1,
    )

    assert page_data.total_results == 100
    assert page_data.total_pages == 5
    candidate = page_data.candidates[0]
    assert candidate.bvid == "BV1test12345"
    assert candidate.title == "这是一个AI视频"
    assert candidate.description == "用于测试的描述"
    assert candidate.cover_url == "https://i0.hdslb.com/cover.jpg"
    assert candidate.duration_seconds == 3723
    assert candidate.play_count == 35000
    assert candidate.danmaku_count == 321
    assert candidate.tag_names == ["AI", "人工智能"]
    assert candidate.hit_columns == ["title", "description"]
    assert candidate.search_rank == 3
    assert candidate.published_at is not None
    assert candidate.published_at.tzinfo == timezone.utc
