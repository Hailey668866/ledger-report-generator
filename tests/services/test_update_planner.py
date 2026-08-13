from datetime import date

from ledger_reporter.domain.models import UpdatePlan
from ledger_reporter.domain.periods import month_weeks
from ledger_reporter.services.update_planner import plan_updates

FROZEN_THROUGH = date(2026, 7, 31)


def test_first_august_run_only_adds_first_completed_august_week() -> None:
    august = month_weeks(2026, 8)

    plan = plan_updates(date(2026, 8, 7), set(), FROZEN_THROUGH)

    assert plan.latest == august[0]
    assert plan.new_periods == (august[0],)
    assert plan.refresh_periods == ()
    assert plan.periods == (august[0],)


def test_new_latest_week_refreshes_existing_previous_week() -> None:
    august = month_weeks(2026, 8)

    plan = plan_updates(date(2026, 8, 14), {august[0]}, FROZEN_THROUGH)

    assert plan.latest == august[1]
    assert plan.new_periods == (august[1],)
    assert plan.refresh_periods == (august[0],)
    assert plan.periods == (august[0], august[1])


def test_existing_latest_and_previous_week_are_both_refreshed() -> None:
    august = month_weeks(2026, 8)

    plan = plan_updates(date(2026, 8, 14), {august[0], august[1]}, FROZEN_THROUGH)

    assert plan.new_periods == ()
    assert plan.refresh_periods == (august[0], august[1])
    assert plan.periods == (august[0], august[1])


def test_empty_existing_backfills_every_completed_august_week() -> None:
    august = month_weeks(2026, 8)

    plan = plan_updates(date(2026, 8, 28), set(), FROZEN_THROUGH)

    assert plan.latest == august[3]
    assert plan.new_periods == tuple(august[:4])
    assert plan.refresh_periods == ()
    assert plan.periods == tuple(august[:4])


def test_cross_month_backfill_includes_month_end_and_next_month_start() -> None:
    august = month_weeks(2026, 8)
    september = month_weeks(2026, 9)

    plan = plan_updates(date(2026, 9, 11), set(), date(2026, 8, 20))

    assert plan.latest == september[1]
    assert plan.new_periods == (*august[3:], *september[:2])
    assert plan.periods == (*august[3:], *september[:2])


def test_update_plan_periods_deduplicates_and_sorts() -> None:
    august = month_weeks(2026, 8)
    plan = UpdatePlan(
        latest=august[2],
        new_periods=(august[2], august[0]),
        refresh_periods=(august[1], august[0]),
    )

    assert plan.periods == tuple(august[:3])
