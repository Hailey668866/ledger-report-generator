from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from ledger_reporter.domain.models import PeriodMetrics, ReportingPeriod, WeekSnapshot
from ledger_reporter.services.history import HistoryRepository


def _snapshot(
    fiscal_year: int,
    start: date,
    end: date,
    label: str,
    metrics: PeriodMetrics | None = None,
) -> WeekSnapshot:
    return WeekSnapshot(
        fiscal_year,
        ReportingPeriod(start, end, label),
        metrics or PeriodMetrics(),
    )


def _generation(
    repository: HistoryRepository,
    fiscal_year: int,
    generated_at: datetime,
    version: str,
    marker: str,
    connection=None,
) -> None:
    repository.save_generation(
        fiscal_year,
        generated_at,
        version,
        {"name": "资金.xlsx", "marker": marker, "nested": {"rows": [1, 2]}},
        {"name": "operations.xlsx", "marker": marker, "rows": 34},
        connection,
    )


def test_upsert_replaces_label_and_every_metric_without_duplicate(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    period_start = date(2026, 8, 1)
    period_end = date(2026, 8, 6)
    original = _snapshot(
        2026,
        period_start,
        period_end,
        "old label",
        PeriodMetrics(
            project_count=1,
            project_profit=Decimal("2.10"),
            scatter_count=3,
            scatter_profit=Decimal("4.20"),
            fund_amount=Decimal("5.30"),
            fund_profit=Decimal("6.40"),
            card_count=7,
            card_profit=Decimal("8.50"),
        ),
    )
    replacement = _snapshot(
        2026,
        period_start,
        period_end,
        "recalculated label",
        PeriodMetrics(
            project_count=11,
            project_profit=Decimal("-12.3400"),
            scatter_count=13,
            scatter_profit=Decimal("14.500"),
            fund_amount=Decimal("15.6000"),
            fund_profit=Decimal("-16.700"),
            card_count=17,
            card_profit=Decimal("18.9000"),
        ),
    )

    repository.save_weeks([original])
    repository.save_weeks([replacement])

    assert repository.load_weeks(2026) == [replacement]


def test_same_dates_are_isolated_by_fiscal_year(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    shared_start = date(2026, 8, 1)
    shared_end = date(2026, 8, 6)
    fy2026 = _snapshot(
        2026,
        shared_start,
        shared_end,
        "FY2026",
        PeriodMetrics(project_profit=Decimal("26.00")),
    )
    fy2027 = _snapshot(
        2027,
        shared_start,
        shared_end,
        "FY2027",
        PeriodMetrics(project_profit=Decimal("27.00")),
    )

    repository.save_weeks([fy2026, fy2027])

    assert repository.load_weeks(2026) == [fy2026]
    assert repository.load_weeks(2027) == [fy2027]


def test_round_trips_all_metrics_and_decimal_text_precision(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    snapshot = _snapshot(
        2026,
        date(2026, 8, 1),
        date(2026, 8, 6),
        "W1",
        PeriodMetrics(
            project_count=101,
            project_profit=Decimal("-12.3400"),
            scatter_count=202,
            scatter_profit=Decimal("0.5000"),
            fund_amount=Decimal("1000000.000100"),
            fund_profit=Decimal("-0.00700"),
            card_count=303,
            card_profit=Decimal("42.000"),
        ),
    )

    repository.save_weeks([snapshot])
    loaded = repository.load_weeks(2026)[0]

    assert loaded.period == snapshot.period
    assert loaded.metrics.project_count == 101
    assert loaded.metrics.scatter_count == 202
    assert loaded.metrics.card_count == 303
    assert str(loaded.metrics.project_profit) == "-12.3400"
    assert str(loaded.metrics.scatter_profit) == "0.5000"
    assert str(loaded.metrics.fund_amount) == "1000000.000100"
    assert str(loaded.metrics.fund_profit) == "-0.00700"
    assert str(loaded.metrics.card_profit) == "42.000"


def test_load_weeks_sorts_by_start_date_and_empty_year_returns_empty_list(
    tmp_path: Path,
) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    weeks = [
        _snapshot(2026, date(2026, 8, 15), date(2026, 8, 21), "W3"),
        _snapshot(2026, date(2026, 8, 1), date(2026, 8, 7), "W1"),
        _snapshot(2026, date(2026, 8, 8), date(2026, 8, 14), "W2"),
    ]

    repository.save_weeks(weeks)

    assert [item.period.label for item in repository.load_weeks(2026)] == ["W1", "W2", "W3"]
    assert repository.load_weeks(2099) == []


def test_transaction_rollback_restores_old_values_and_removes_new_rows(
    tmp_path: Path,
) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    period_start = date(2026, 8, 1)
    period_end = date(2026, 8, 6)
    old_week = _snapshot(
        2026,
        period_start,
        period_end,
        "old",
        PeriodMetrics(project_profit=Decimal("10.00")),
    )
    repository.save_weeks([old_week])
    old_generated_at = datetime(2026, 8, 7, 9, 0, tzinfo=UTC)
    _generation(repository, 2026, old_generated_at, "baseline-old", "old")

    with pytest.raises(RuntimeError, match="stop"), repository.transaction() as connection:
        replacement = _snapshot(
            2026,
            period_start,
            period_end,
            "replacement",
            PeriodMetrics(project_profit=Decimal("99.00")),
        )
        new_week = _snapshot(
            2026,
            date(2026, 8, 7),
            date(2026, 8, 13),
            "new",
            PeriodMetrics(project_profit=Decimal("88.00")),
        )
        repository.save_weeks([replacement, new_week], connection)
        _generation(
            repository,
            2026,
            datetime(2026, 8, 14, 9, 0, tzinfo=UTC),
            "baseline-new",
            "new",
            connection,
        )
        assert connection.execute("SELECT 1").fetchone() == (1,)
        raise RuntimeError("stop")

    assert repository.load_weeks(2026) == [old_week]
    assert repository.latest_generation(2026) == {
        "generated_at": old_generated_at.isoformat(),
        "baseline_version": "baseline-old",
        "funds": {"marker": "old", "name": "资金.xlsx", "nested": {"rows": [1, 2]}},
        "operations": {"marker": "old", "name": "operations.xlsx", "rows": 34},
    }


def test_transaction_commits_week_and_generation_together(tmp_path: Path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    week = _snapshot(
        2026,
        date(2026, 8, 1),
        date(2026, 8, 6),
        "committed",
        PeriodMetrics(project_profit=Decimal("25.00")),
    )
    generated_at = datetime(2026, 8, 7, 10, 30, tzinfo=UTC)

    with repository.transaction() as connection:
        repository.save_weeks([week], connection)
        _generation(repository, 2026, generated_at, "baseline-committed", "committed", connection)
        assert connection.execute("SELECT COUNT(*) FROM generation_runs").fetchone() == (1,)

    assert repository.load_weeks(2026) == [week]
    assert repository.latest_generation(2026)["generated_at"] == generated_at.isoformat()


def test_latest_generation_uses_insert_order_and_isolates_fiscal_years(
    tmp_path: Path,
) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    first_time = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    latest_insert_time = datetime(2026, 8, 7, 10, 30, tzinfo=UTC)
    other_year_time = datetime(2027, 8, 7, 10, 30, tzinfo=UTC)
    _generation(repository, 2026, first_time, "baseline-first", "first")
    _generation(repository, 2027, other_year_time, "baseline-2027", "other-year")
    _generation(repository, 2026, latest_insert_time, "baseline-latest", "latest")

    assert repository.latest_generation(2026) == {
        "generated_at": latest_insert_time.isoformat(),
        "baseline_version": "baseline-latest",
        "funds": {"marker": "latest", "name": "资金.xlsx", "nested": {"rows": [1, 2]}},
        "operations": {"marker": "latest", "name": "operations.xlsx", "rows": 34},
    }
    assert repository.latest_generation(2027) == {
        "generated_at": other_year_time.isoformat(),
        "baseline_version": "baseline-2027",
        "funds": {
            "marker": "other-year",
            "name": "资金.xlsx",
            "nested": {"rows": [1, 2]},
        },
        "operations": {"marker": "other-year", "name": "operations.xlsx", "rows": 34},
    }
    assert repository.latest_generation(2099) is None


def test_parent_directory_is_created_and_reinitialization_preserves_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "data" / "history.sqlite3"
    first_repository = HistoryRepository(database_path)
    week = _snapshot(2026, date(2026, 8, 1), date(2026, 8, 6), "persisted")
    first_repository.save_weeks([week])

    second_repository = HistoryRepository(database_path)

    assert database_path.is_file()
    assert second_repository.load_weeks(2026) == [week]
