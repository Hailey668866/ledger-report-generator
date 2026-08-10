from datetime import date, timedelta

from ledger_reporter.domain.models import ReportingPeriod, UpdatePlan
from ledger_reporter.domain.periods import latest_completed_week, month_weeks, previous_week


def _periods_after(day: date, through: ReportingPeriod) -> tuple[ReportingPeriod, ...]:
    periods: list[ReportingPeriod] = []
    cursor = day.replace(day=1)

    while cursor <= through.end:
        periods.extend(
            period
            for period in month_weeks(cursor.year, cursor.month)
            if period.start > day and period.end <= through.end
        )
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    return tuple(periods)


def plan_updates(
    today: date, existing: set[ReportingPeriod], frozen_through: date
) -> UpdatePlan:
    latest = latest_completed_week(today)
    expected = _periods_after(frozen_through, latest)
    new_periods = tuple(period for period in expected if period not in existing)
    refresh_periods = tuple(
        sorted(
            {
                period
                for period in (previous_week(latest), latest)
                if period.start > frozen_through and period in existing
            },
            key=lambda period: period.start,
        )
    )
    return UpdatePlan(latest, new_periods, refresh_periods)
