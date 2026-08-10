from datetime import date

from ledger_reporter.domain.periods import fiscal_year_for, latest_completed_week, month_weeks


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
