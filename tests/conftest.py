from datetime import date
from decimal import Decimal

import pytest

from ledger_reporter.domain.models import (
    BusinessMetric,
    BusinessTable,
    PeriodMetrics,
    ReportBundle,
    ReportingPeriod,
    WeekSnapshot,
)
from ledger_reporter.rules import BUSINESS_RULES


@pytest.fixture
def report_bundle() -> ReportBundle:
    period = ReportingPeriod(date(2026, 8, 1), date(2026, 8, 6), "W1（8.1-8.6）")
    metrics = PeriodMetrics(
        project_count=2,
        project_profit=Decimal(100),
        scatter_count=1,
        scatter_profit=Decimal(20),
        fund_amount=Decimal(900),
        fund_profit=Decimal(5),
    )
    business_rows = tuple(
        BusinessMetric(name, 1, Decimal(100), Decimal(1000)) for name, _criteria in BUSINESS_RULES
    )
    business = BusinessTable(
        period,
        business_rows,
        BusinessMetric("销售额合计", 12, Decimal(1200), Decimal(12000)),
    )
    baseline = (
        {
            "label": "W5（24-31）",
            "values": [
                Decimal(168),
                Decimal("-729734.85"),
                Decimal(9),
                Decimal("14016.43"),
                Decimal("85644.23"),
                Decimal("729.27"),
                Decimal(0),
                Decimal(0),
                Decimal("-714989.15"),
                Decimal(0),
            ],
        },
    )
    return ReportBundle(
        2026,
        period,
        baseline,
        (WeekSnapshot(2026, period, metrics),),
        business,
    )
