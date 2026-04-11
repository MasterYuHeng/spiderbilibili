from __future__ import annotations

from app.crawler.utils import datetime_from_timestamp, parse_count_text


def test_parse_count_text_returns_zero_for_non_finite_numbers() -> None:
    assert parse_count_text(float("nan")) == 0
    assert parse_count_text(float("inf")) == 0


def test_datetime_from_timestamp_returns_none_for_out_of_range_value() -> None:
    assert datetime_from_timestamp("1e309") is None
