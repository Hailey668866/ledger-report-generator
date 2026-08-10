from datetime import date
from decimal import Decimal

import pytest

from ledger_reporter.domain.models import FundRecord, OperationalRecord, ReportingPeriod
from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.services.calculations import calculate_period

PERIOD = ReportingPeriod(date(2026, 8, 1), date(2026, 8, 6), "W1（8.1-8.6）")


def op(kind: str, profit: str) -> OperationalRecord:
    return OperationalRecord(
        "001", kind, "OSL", date(2026, 8, 3), "供应商", Decimal(1000), Decimal(profit)
    )


def test_calculates_summary_columns() -> None:
    funds = [
        FundRecord(
            "广州美鑫通国际供应链有限公司", date(2026, 8, 4), Decimal(10000), Decimal(20)
        )
    ]

    metrics = calculate_period(PERIOD, [op("BSA", "100"), op("散采", "30")], funds)

    assert metrics.project_count == 1
    assert metrics.project_profit == Decimal(100)
    assert metrics.scatter_count == 1
    assert metrics.scatter_profit == Decimal(30)
    assert metrics.fund_amount == Decimal(10000)
    assert metrics.fund_profit == (
        Decimal(10000) * Decimal("0.0552") * Decimal(60) / Decimal(365) + Decimal(20)
    )


def test_rejects_unknown_fund_channel() -> None:
    funds = [FundRecord("未知渠道", date(2026, 8, 4), Decimal(100), Decimal(0))]

    with pytest.raises(WorkbookDataError, match="未知渠道"):
        calculate_period(PERIOD, [], funds)


def test_identifies_blank_fund_channel() -> None:
    funds = [FundRecord("", date(2026, 8, 4), Decimal(100), Decimal(0))]

    with pytest.raises(WorkbookDataError, match="<空白>"):
        calculate_period(PERIOD, [], funds)


def test_empty_inputs_return_zero_core_metrics() -> None:
    metrics = calculate_period(PERIOD, [], [])

    assert metrics.project_count == 0
    assert metrics.project_profit == Decimal(0)
    assert metrics.scatter_count == 0
    assert metrics.scatter_profit == Decimal(0)
    assert metrics.fund_amount == Decimal(0)
    assert metrics.fund_profit == Decimal(0)
    assert isinstance(metrics.project_count, int)
    assert isinstance(metrics.scatter_count, int)
    assert all(
        isinstance(value, Decimal)
        for value in (
            metrics.project_profit,
            metrics.scatter_profit,
            metrics.fund_amount,
            metrics.fund_profit,
        )
    )


def test_accepts_single_use_iterators() -> None:
    funds = [
        FundRecord(
            "广州美鑫通国际供应链有限公司", date(2026, 8, 4), Decimal(100), Decimal(20)
        )
    ]

    metrics = calculate_period(PERIOD, iter([op("BSA", "10")]), iter(funds))

    assert metrics.project_count == 1
    assert metrics.project_profit == Decimal(10)
    assert metrics.fund_amount == Decimal(100)
    assert metrics.fund_profit == (
        Decimal(100) * Decimal("0.0552") * Decimal(60) / Decimal(365) + Decimal(20)
    )


def test_uses_inclusive_dates_and_both_configured_fund_rates() -> None:
    operations = [
        OperationalRecord("start", "项目", "OSL", date(2026, 8, 1), "供应商", Decimal(1), Decimal(2)),
        OperationalRecord("end", "散采", "OSL", date(2026, 8, 6), "供应商", Decimal(1), Decimal(3)),
        OperationalRecord("after", "项目", "OSL", date(2026, 8, 7), "供应商", Decimal(1), Decimal(99)),
        OperationalRecord(None, "项目", "OSL", date(2026, 8, 3), "供应商", Decimal(1), Decimal(4)),
    ]
    funds = [
        FundRecord("广州美鑫通国际供应链有限公司", date(2026, 8, 1), Decimal(100), Decimal(1)),
        FundRecord("浙江飞速供应链管理有限公司", date(2026, 8, 6), Decimal(200), Decimal(2)),
        FundRecord("未知渠道", date(2026, 8, 7), Decimal(300), Decimal(3)),
    ]

    metrics = calculate_period(PERIOD, operations, funds)

    assert (metrics.project_count, metrics.project_profit) == (1, Decimal(6))
    assert (metrics.scatter_count, metrics.scatter_profit) == (1, Decimal(3))
    assert metrics.fund_amount == Decimal(300)
    assert metrics.fund_profit == (
        Decimal(100) * Decimal("0.0552") * Decimal(60) / Decimal(365)
        + Decimal(1)
        + Decimal(200) * Decimal("0.0752") * Decimal(60) / Decimal(365)
        + Decimal(2)
    )
