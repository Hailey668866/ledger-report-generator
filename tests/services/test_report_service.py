import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from ledger_reporter.domain.models import (
    FundRecord,
    OperationalRecord,
    PeriodMetrics,
    ReportBundle,
    ReportingPeriod,
    WeekSnapshot,
)
from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.rules import BUSINESS_RULES
from ledger_reporter.services.baseline import load_fy2026_baseline
from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService


def _operation(
    bill_no: str,
    departure: date,
    profit: str,
    *,
    project_type: str = "普通项目",
    supplier: str = "Worldwide Partner Logistics Company Limited",
) -> OperationalRecord:
    return OperationalRecord(
        bill_no=bill_no,
        project_type=project_type,
        destination="OSL",
        departure=departure,
        supplier=supplier,
        receivable=Decimal(1000),
        gross_profit=Decimal(profit),
    )


def _fund(payment_date: date, amount: str = "1000") -> FundRecord:
    return FundRecord(
        channel="广州美鑫通国际供应链有限公司",
        payment_date=payment_date,
        amount=Decimal(amount),
        operation_fee=Decimal(10),
    )


def _snapshot(profit: str = "10") -> WeekSnapshot:
    return WeekSnapshot(
        fiscal_year=2026,
        period=ReportingPeriod(date(2026, 8, 1), date(2026, 8, 6), "old"),
        metrics=PeriodMetrics(project_count=1, project_profit=Decimal(profit)),
    )


def test_first_fy2026_generation_combines_baseline_week_and_generation_history(
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    service = ReportService(history)

    bundle = service.generate_from_records(
        date(2026, 8, 7),
        [_operation("first", date(2026, 8, 3), "25")],
        [_fund(date(2026, 8, 4))],
    )

    assert bundle.fiscal_year == 2026
    assert (bundle.latest_period.start, bundle.latest_period.end) == (
        date(2026, 8, 1),
        date(2026, 8, 6),
    )
    assert bundle.baseline_rows[-1]["label"] == "W5（24-31）"
    assert len(bundle.weeks) == 1
    assert bundle.weeks[0].period == bundle.latest_period
    assert history.load_weeks(2026) == list(bundle.weeks)
    assert history.latest_generation(2026)["baseline_version"] == (load_fy2026_baseline().version)


def test_second_generation_refreshes_previous_week_and_adds_latest_without_duplicates(
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    service = ReportService(history)
    service.generate_from_records(
        date(2026, 8, 7),
        [_operation("old", date(2026, 8, 3), "10")],
        [],
    )

    bundle = service.generate_from_records(
        date(2026, 8, 14),
        [
            _operation("updated", date(2026, 8, 3), "111"),
            _operation("latest", date(2026, 8, 8), "222"),
        ],
        [],
    )

    assert [(week.period.start, week.metrics.project_profit) for week in bundle.weeks] == [
        (date(2026, 8, 1), Decimal(111)),
        (date(2026, 8, 7), Decimal(222)),
    ]
    assert history.load_weeks(2026) == list(bundle.weeks)
    assert bundle.business.period == bundle.latest_period
    assert bundle.business.total.count == 1
    assert bundle.business.total.profit == Decimal(222)


def test_nonbaseline_fiscal_year_is_isolated_and_records_none_baseline_version(
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    old_week = _snapshot("70")
    history.save_weeks([old_week])
    service = ReportService(history)

    bundle = service.generate_from_records(
        date(2027, 4, 9),
        [_operation("fy2027", date(2027, 4, 2), "27")],
        [],
    )

    assert bundle.fiscal_year == 2027
    assert bundle.baseline_rows == ()
    assert [week.period.start for week in bundle.weeks] == [
        date(2027, 4, 1),
        date(2027, 4, 2),
    ]
    assert all(week.fiscal_year == 2027 for week in bundle.weeks)
    assert history.latest_generation(2027)["baseline_version"] == "none"
    assert history.load_weeks(2026) == [old_week]


def test_inspection_validates_records_and_never_changes_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    old_week = _snapshot()
    history.save_weeks([old_week])
    service = ReportService(history)
    operations = [_operation("latest", date(2026, 8, 8), "15")]
    funds = [_fund(date(2026, 8, 8))]
    monkeypatch.setattr(
        "ledger_reporter.services.report_service.read_operations", lambda _path: operations
    )
    monkeypatch.setattr(
        "ledger_reporter.services.report_service.read_funds",
        lambda _path, _years: funds,
    )
    before_weeks = history.load_weeks(2026)
    before_generation = history.latest_generation(2026)

    inspection = service.inspect_sources(
        tmp_path / "funds.xlsx",
        tmp_path / "operations.xlsx",
        date(2026, 8, 14),
    )

    assert inspection.fiscal_year == 2026
    assert inspection.update_plan.latest.start == date(2026, 8, 7)
    assert history.load_weeks(2026) == before_weeks
    assert history.latest_generation(2026) == before_generation


def test_inspection_propagates_validation_error_without_changing_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    old_week = _snapshot()
    history.save_weeks([old_week])
    service = ReportService(history)
    invalid_funds = [FundRecord("未知渠道", date(2026, 8, 8), Decimal(1), Decimal(0))]
    monkeypatch.setattr("ledger_reporter.services.report_service.read_operations", lambda _path: [])
    monkeypatch.setattr(
        "ledger_reporter.services.report_service.read_funds",
        lambda _path, _years: invalid_funds,
    )
    before_weeks = history.load_weeks(2026)

    with pytest.raises(WorkbookDataError, match="未知资金渠道"):
        service.inspect_sources(
            tmp_path / "funds.xlsx",
            tmp_path / "operations.xlsx",
            date(2026, 8, 14),
        )

    assert history.load_weeks(2026) == before_weeks
    assert history.latest_generation(2026) is None


def test_record_validation_failure_occurs_before_transaction_and_preserves_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    old_week = _snapshot()
    history.save_weeks([old_week])
    service = ReportService(history)
    transaction_entered = False
    original_transaction = history.transaction

    def tracked_transaction():
        nonlocal transaction_entered
        transaction_entered = True
        return original_transaction()

    monkeypatch.setattr(history, "transaction", tracked_transaction)
    invalid_funds = [FundRecord("未知渠道", date(2026, 8, 8), Decimal(1), Decimal(0))]

    with pytest.raises(WorkbookDataError, match="未知资金渠道"):
        service.generate_from_records(date(2026, 8, 14), [], invalid_funds)

    assert transaction_entered is False
    assert history.load_weeks(2026) == [old_week]
    assert history.latest_generation(2026) is None


def test_business_calculation_failure_occurs_before_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    old_week = _snapshot()
    history.save_weeks([old_week])
    service = ReportService(history)
    transaction_entered = False
    original_transaction = history.transaction

    def tracked_transaction():
        nonlocal transaction_entered
        transaction_entered = True
        return original_transaction()

    def fail_business(*_args: object) -> None:
        raise RuntimeError("simulated business calculation failure")

    monkeypatch.setattr(history, "transaction", tracked_transaction)
    monkeypatch.setattr(
        "ledger_reporter.services.report_service.calculate_business_table",
        fail_business,
    )

    with pytest.raises(RuntimeError, match="simulated business calculation failure"):
        service.generate_from_records(date(2026, 8, 14), [], [])

    assert transaction_entered is False
    assert history.load_weeks(2026) == [old_week]
    assert history.latest_generation(2026) is None


def test_generation_failure_rolls_back_refreshed_and_new_weeks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    old_week = _snapshot()
    old_generated_at = datetime(2026, 8, 7, 9, tzinfo=UTC)
    history.save_weeks([old_week])
    history.save_generation(2026, old_generated_at, "old", {"old": 1}, {"old": 2})
    service = ReportService(history)

    def fail_generation(*_args, **_kwargs) -> None:
        raise sqlite3.OperationalError("simulated generation failure")

    monkeypatch.setattr(history, "save_generation", fail_generation)

    with pytest.raises(sqlite3.OperationalError, match="simulated generation failure"):
        service.generate_from_records(
            date(2026, 8, 14),
            [
                _operation("updated", date(2026, 8, 3), "111"),
                _operation("new", date(2026, 8, 8), "222"),
            ],
            [],
        )

    assert history.load_weeks(2026) == [old_week]
    assert history.latest_generation(2026) == {
        "generated_at": old_generated_at.isoformat(),
        "baseline_version": "old",
        "funds": {"old": 1},
        "operations": {"old": 2},
    }


def test_generated_at_and_explicit_source_summaries_are_persisted_verbatim(
    tmp_path: Path,
) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")
    service = ReportService(history)
    generated_at = datetime(2026, 8, 7, 10, 30, tzinfo=UTC)
    operations_summary = {"name": "operations.xlsx", "size": 12, "sha256": "abc"}

    service.generate_from_records(
        date(2026, 8, 7),
        [],
        [],
        generated_at=generated_at,
        funds_summary={},
        operations_summary=operations_summary,
    )

    generation = history.latest_generation(2026)
    assert generation["generated_at"] == generated_at.isoformat()
    assert generation["funds"] == {}
    assert generation["operations"] == operations_summary


def test_default_source_summaries_describe_in_memory_records(tmp_path: Path) -> None:
    history = HistoryRepository(tmp_path / "history.sqlite3")

    ReportService(history).generate_from_records(date(2026, 8, 7), [], [])

    generation = history.latest_generation(2026)
    expected = {"name": "in-memory", "size": 0, "sha256": ""}
    assert generation["funds"] == expected
    assert generation["operations"] == expected
    assert datetime.fromisoformat(generation["generated_at"]).tzinfo is not None


def test_source_summary_hashes_stream_bytes_without_changing_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    content = bytes(range(256)) * 9000
    source.write_bytes(content)
    before_bytes = source.read_bytes()
    before_mtime = source.stat().st_mtime_ns
    service = ReportService(HistoryRepository(tmp_path / "history.sqlite3"))

    def reject_later_stat(_path: Path) -> None:
        raise AssertionError("summary size must come from the bytes that were hashed")

    with monkeypatch.context() as context:
        context.setattr(Path, "stat", reject_later_stat)
        summary = service._source_summary(source)

    assert summary == {
        "name": "source.bin",
        "size": len(content),
        "sha256": sha256(content).hexdigest(),
    }
    assert source.read_bytes() == before_bytes
    assert source.stat().st_mtime_ns == before_mtime


def test_generate_reads_expected_years_and_passes_real_summaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    funds_path = tmp_path / "funds.xlsx"
    operations_path = tmp_path / "operations.xlsx"
    funds_bytes = b"fund records"
    operations_bytes = b"operation records"
    funds_path.write_bytes(funds_bytes)
    operations_path.write_bytes(operations_bytes)
    operations = [_operation("one", date(2027, 4, 2), "1")]
    funds = [_fund(date(2027, 4, 2))]
    captured: dict[str, object] = {}
    marker = object()
    service = ReportService(HistoryRepository(tmp_path / "history.sqlite3"))

    def fake_read_operations(path: Path) -> list[OperationalRecord]:
        captured["operations_path"] = path
        return operations

    def fake_read_funds(path: Path, allowed_years: set[int]) -> list[FundRecord]:
        captured["funds_path"] = path
        captured["allowed_years"] = allowed_years
        return funds

    def fake_generate_from_records(
        today: date,
        received_operations: list[OperationalRecord],
        received_funds: list[FundRecord],
        **kwargs: object,
    ) -> object:
        captured["today"] = today
        captured["operations"] = received_operations
        captured["funds"] = received_funds
        captured.update(kwargs)
        return marker

    monkeypatch.setattr(
        "ledger_reporter.services.report_service.read_operations", fake_read_operations
    )
    monkeypatch.setattr("ledger_reporter.services.report_service.read_funds", fake_read_funds)
    monkeypatch.setattr(service, "generate_from_records", fake_generate_from_records)

    result = service.generate(funds_path, operations_path, date(2027, 4, 9))

    assert result is marker
    assert captured["operations_path"] == operations_path
    assert captured["funds_path"] == funds_path
    assert captured["allowed_years"] == {2027, 2028}
    assert captured["today"] == date(2027, 4, 9)
    assert captured["operations"] is operations
    assert captured["funds"] is funds
    assert captured["funds_summary"] == {
        "name": funds_path.name,
        "size": len(funds_bytes),
        "sha256": sha256(funds_bytes).hexdigest(),
    }
    assert captured["operations_summary"] == {
        "name": operations_path.name,
        "size": len(operations_bytes),
        "sha256": sha256(operations_bytes).hexdigest(),
    }


def test_shared_report_bundle_fixture_has_export_ready_structure(
    report_bundle: ReportBundle,
) -> None:
    assert report_bundle.fiscal_year == 2026
    assert (report_bundle.latest_period.start, report_bundle.latest_period.end) == (
        date(2026, 8, 1),
        date(2026, 8, 6),
    )
    assert len(report_bundle.weeks) == 1
    assert tuple(row.name for row in report_bundle.business.rows) == tuple(
        name for name, _criteria in BUSINESS_RULES
    )
    assert report_bundle.business.total.name == "销售额合计"
    week_five = next(row for row in report_bundle.baseline_rows if row["label"] == "W5（24-31）")
    assert len(week_five["values"]) == 10
    assert all(isinstance(value, Decimal) for value in week_five["values"])
