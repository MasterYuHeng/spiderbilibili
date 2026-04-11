from datetime import timezone

from app.crawler.hot_spider import BilibiliHotSpider


def test_parse_popular_page_data_normalizes_hot_video_candidates() -> None:
    payload = {
        "code": 0,
        "data": {
            "no_more": False,
            "list": [
                {
                    "bvid": "BV1hot12345",
                    "aid": 123,
                    "title": "<em class=\"keyword\">Hot</em> video",
                    "desc": "Current hot item",
                    "owner": {"name": "Hot UP", "mid": 999},
                    "pic": "//i0.hdslb.com/hot.jpg",
                    "pubdate": 1_700_000_000,
                    "duration": 125,
                    "tname": "Tech",
                    "tnamev2": "Digital",
                    "stat": {
                        "view": 50000,
                        "like": 2300,
                        "favorite": 800,
                        "reply": 120,
                        "danmaku": 90,
                    },
                }
            ],
        },
    }

    page_data = BilibiliHotSpider.parse_popular_page_data(
        payload,
        page=2,
        page_size=20,
    )

    assert page_data.page == 2
    assert page_data.total_pages == 3
    candidate = page_data.candidates[0]
    assert candidate.keyword == ""
    assert candidate.bvid == "BV1hot12345"
    assert candidate.title == "Hot video"
    assert candidate.cover_url == "https://i0.hdslb.com/hot.jpg"
    assert candidate.search_rank == 21
    assert candidate.play_count == 50000
    assert candidate.like_count == 2300
    assert candidate.favorite_count == 800
    assert candidate.comment_count == 120
    assert candidate.danmaku_count == 90
    assert sorted(candidate.tag_names) == ["Digital", "Tech"]
    assert candidate.published_at is not None
    assert candidate.published_at.tzinfo == timezone.utc


def test_parse_partition_ranking_data_builds_single_page_candidates() -> None:
    payload = {
        "code": 0,
        "data": {
            "list": [
                {
                    "bvid": "BV1rank12345",
                    "aid": 456,
                    "title": "Partition ranking video",
                    "desc": "Ranking item",
                    "owner": {"name": "Ranking UP", "mid": 1001},
                    "pic": "https://i0.hdslb.com/rank.jpg",
                    "pubdate": 1_700_000_100,
                    "duration": "01:30",
                    "tname": "Science",
                    "stat": {
                        "view": "12.5万",
                        "like": 3400,
                        "favorite": 1200,
                        "reply": 88,
                        "danmaku": 66,
                    },
                }
            ]
        },
    }

    page_data = BilibiliHotSpider.parse_partition_ranking_data(
        payload,
        partition_tid=188,
    )

    assert page_data.page == 1
    assert page_data.total_pages == 1
    assert page_data.total_results == 1
    candidate = page_data.candidates[0]
    assert candidate.search_rank == 1
    assert candidate.play_count == 125000
    assert candidate.duration_seconds == 90
    assert candidate.tag_names == ["Science"]
