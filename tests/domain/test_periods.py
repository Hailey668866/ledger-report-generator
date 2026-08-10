import calendar
from datetime import date, timedelta

import pytest

from ledger_reporter.domain.periods import (
    fiscal_year_for,
    latest_completed_week,
    month_weeks,
    previous_week,
)


def test_fiscal_year_starts_on_april_first() -> None:
    assert fiscal_year_for(date(2027, 3, 31)) == 2026
    assert fiscal_year_for(date(2027, 4, 1)) == 2027


def test_august_2026_periods_create_four_day_tail() -> None:
    periods = month_weeks(2026, 8)
    assert [(p.start.day, p.end.day) for p in periods] == [
        (1, 6),
        (7, 13),
        (14, 20),
        (21, 27),
        (28, 31),
    ]


def test_one_day_tail_merges_into_previous_week() -> None:
    periods = month_weeks(2026, 7)
    assert (periods[-1].start.day, periods[-1].end.day) == (24, 31)


def test_latest_period_must_end_before_today() -> None:
    period = latest_completed_week(date(2026, 8, 7))
    assert (period.start, period.end) == (date(2026, 8, 1), date(2026, 8, 6))


def test_latest_period_excludes_week_ending_today() -> None:
    period = latest_completed_week(date(2026, 8, 6))
    assert (period.start, period.end) == (date(2026, 7, 24), date(2026, 7, 31))


def test_latest_period_at_month_start_falls_back_to_previous_month() -> None:
    period = latest_completed_week(date(2026, 8, 1))
    assert (period.start, period.end) == (date(2026, 7, 24), date(2026, 7, 31))


def test_previous_week_returns_prior_period_in_same_month() -> None:
    period = previous_week(month_weeks(2026, 8)[1])
    assert (period.start, period.end) == (date(2026, 8, 1), date(2026, 8, 6))


def test_previous_week_falls_back_to_prior_month() -> None:
    period = previous_week(month_weeks(2026, 8)[0])
    assert (period.start, period.end) == (date(2026, 7, 24), date(2026, 7, 31))


@pytest.mark.parametrize("month", range(1, 13))
def test_month_weeks_cover_each_day_once_without_crossing_month(month: int) -> None:
    periods = month_weeks(2026, month)
    month_end = date(2026, month, calendar.monthrange(2026, month)[1])

    actual_days = [
        period.start + timedelta(days=offset)
        for period in periods
        for offset in range((period.end - period.start).days + 1)
    ]
    expected_days = [
        date(2026, month, day) for day in range(1, calendar.monthrange(2026, month)[1] + 1)
    ]

    assert actual_days == expected_days
    assert all(period.start.month == month and period.end.month == month for period in periods)
    assert periods[0].start == date(2026, month, 1)
    assert periods[-1].end == month_end
