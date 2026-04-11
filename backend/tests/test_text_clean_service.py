from app.crawler.models import SubtitleData, SubtitleSegmentData
from app.services.text_clean_service import TextCleanService


def test_text_clean_service_combines_and_normalizes_description_and_subtitle() -> None:
    service = TextCleanService(max_combined_length=500)
    subtitle = SubtitleData(
        subtitle_url="https://example.com/subtitle.json",
        language_code="zh-CN",
        language_name="Chinese",
        segments=[
            SubtitleSegmentData(
                segment_index=0,
                start_seconds=0.0,
                end_seconds=1.5,
                content="  First   line  ",
            ),
            SubtitleSegmentData(
                segment_index=1,
                start_seconds=1.5,
                end_seconds=3.0,
                content="Second line",
            ),
        ],
        raw_payload={},
    )

    cleaned = service.build_cleaned_text(
        title="AI Demo",
        description="  Intro line \n\n\nAnother line ",
        subtitle=subtitle,
    )

    assert cleaned.has_description is True
    assert cleaned.has_subtitle is True
    assert cleaned.description_text == "Intro line\n\nAnother line"
    assert cleaned.subtitle_text == "First line\nSecond line"
    assert cleaned.combined_text.startswith("Video Description:")
    assert "Video Subtitle:" in cleaned.combined_text
    assert cleaned.combined_text_hash
    assert len(cleaned.subtitle_segments) == 2


def test_text_clean_service_uses_search_summary_when_description_is_empty() -> None:
    service = TextCleanService(max_combined_length=500)

    cleaned = service.build_cleaned_text(
        title="Fallback Title",
        description=" \n ",
        search_summary=" Search summary from results ",
        subtitle=None,
    )

    assert cleaned.has_description is True
    assert cleaned.has_subtitle is False
    assert cleaned.description_text == "Search summary from results"
    assert cleaned.subtitle_text is None
    assert cleaned.combined_text == (
        "Video Search Summary:\nSearch summary from results"
    )


def test_text_clean_service_uses_title_fallback_when_text_sources_are_empty() -> None:
    service = TextCleanService(max_combined_length=500)

    cleaned = service.build_cleaned_text(
        title="Fallback Title",
        description=" \n ",
        subtitle=None,
    )

    assert cleaned.has_description is False
    assert cleaned.has_subtitle is False
    assert cleaned.description_text is None
    assert cleaned.subtitle_text is None
    assert cleaned.combined_text == "Video Title:\nFallback Title"
