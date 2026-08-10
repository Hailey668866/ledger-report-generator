import calendar
from datetime import date, timedelta

from .models import ReportingPeriod


def fiscal_year_for(day: date) -> int:
    return day.year if day.month >= 4 else day.year - 1


def _label(index: int, start: date, end: date) -> str:
    return f"W{index}（{start.month}.{start.day}-{end.month}.{end.day}）"


def month_weeks(year: int, month: int) -> list[ReportingPeriod]:
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    cursor = date(year, month, 1)
    first_end = cursor + timedelta(days=(3 - cursor.weekday()) % 7)
    periods = [ReportingPeriod(cursor, first_end, "")]
    cursor = first_end + timedelta(days=1)

    while cursor <= month_end:
        nominal_end = cursor + timedelta(days=6)
        if nominal_end <= month_end:
            periods.append(ReportingPeriod(cursor, nominal_end, ""))
            cursor = nominal_end + timedelta(days=1)
            continue

        tail_days = (month_end - cursor).days + 1
        if tail_days == 1:
            previous = periods[-1]
            periods[-1] = ReportingPeriod(previous.start, month_end, "")
        else:
            periods.append(ReportingPeriod(cursor, month_end, ""))
        break

    return [
        ReportingPeriod(period.start, period.end, _label(i, period.start, period.end))
        for i, period in enumerate(periods, 1)
    ]


def latest_completed_week(today: date) -> ReportingPeriod:
    candidates = [period for period in month_weeks(today.year, today.month) if period.end < today]
    if candidates:
        return candidates[-1]

    previous_month_end = today.replace(day=1) - timedelta(days=1)
    return month_weeks(previous_month_end.year, previous_month_end.month)[-1]


def previous_week(period: ReportingPeriod) -> ReportingPeriod:
    month = month_weeks(period.start.year, period.start.month)
    index = next(i for i, candidate in enumerate(month) if candidate.start == period.start)
    if index:
        return month[index - 1]

    previous_month_end = period.start - timedelta(days=1)
    return month_weeks(previous_month_end.year, previous_month_end.month)[-1]
