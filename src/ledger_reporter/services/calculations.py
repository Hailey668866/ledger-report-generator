from collections.abc import Iterable
from decimal import Decimal

from ledger_reporter.domain.models import (
    BusinessMetric,
    BusinessTable,
    FundRecord,
    OperationalRecord,
    PeriodMetrics,
    ReportingPeriod,
)
from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.rules import BUSINESS_RULES, CAPITAL_COST, FUND_RATES, SCATTER

ZERO = Decimal("0")  # noqa: FURB157
DAYS_PER_YEAR = Decimal(365)
FUND_TERM_DAYS = Decimal(60)


def _summarize_operations(name: str, operations: Iterable[OperationalRecord]) -> BusinessMetric:
    records = tuple(operations)
    return BusinessMetric(
        name=name,
        count=sum(bool(record.bill_no) for record in records),
        profit=sum((record.gross_profit for record in records), ZERO),
        receivable=sum((record.receivable for record in records), ZERO),
    )


def calculate_business_table(
    period: ReportingPeriod,
    operations: Iterable[OperationalRecord],
) -> BusinessTable:
    selected_operations = tuple(
        record for record in operations if period.start <= record.departure <= period.end
    )
    rows = tuple(
        _summarize_operations(
            name,
            (
                record
                for record in selected_operations
                if all(getattr(record, field) == value for field, value in criteria.items())
            ),
        )
        for name, criteria in BUSINESS_RULES
    )
    return BusinessTable(
        period=period,
        rows=rows,
        total=_summarize_operations("销售额合计", selected_operations),
    )


def calculate_period(
    period: ReportingPeriod,
    operations: Iterable[OperationalRecord],
    funds: Iterable[FundRecord],
) -> PeriodMetrics:
    selected_operations = [
        record for record in operations if period.start <= record.departure <= period.end
    ]
    selected_funds = [
        record for record in funds if period.start <= record.payment_date <= period.end
    ]

    unknown_channels = sorted(
        {
            record.channel or "<空白>"
            for record in selected_funds
            if record.channel not in FUND_RATES
        }
    )
    if unknown_channels:
        raise WorkbookDataError(f"未知资金渠道：{', '.join(unknown_channels)}")

    project_operations = [
        record for record in selected_operations if record.project_type != SCATTER
    ]
    scatter_operations = [
        record for record in selected_operations if record.project_type == SCATTER
    ]

    return PeriodMetrics(
        project_count=sum(bool(record.bill_no) for record in project_operations),
        project_profit=sum((record.gross_profit for record in project_operations), ZERO),
        scatter_count=sum(bool(record.bill_no) for record in scatter_operations),
        scatter_profit=sum((record.gross_profit for record in scatter_operations), ZERO),
        fund_amount=sum((record.amount for record in selected_funds), ZERO),
        fund_profit=sum(
            (
                record.amount
                * (FUND_RATES[record.channel] - CAPITAL_COST)
                * FUND_TERM_DAYS
                / DAYS_PER_YEAR
                + record.operation_fee
                for record in selected_funds
            ),
            ZERO,
        ),
    )
