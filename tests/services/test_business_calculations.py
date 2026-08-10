from datetime import date
from decimal import Decimal

import pytest

from ledger_reporter.domain.models import OperationalRecord, ReportingPeriod
from ledger_reporter.services.calculations import calculate_business_table

PERIOD = ReportingPeriod(date(2026, 8, 1), date(2026, 8, 7), "W1（8.1-8.7）")
EXPECTED_ROW_NAMES = (
    "WWP",
    "欧展-固定位（LAX）",
    "欧展-差价",
    "金开宇",
    "厦门伦升",
    "印华固定位OSL",
    "印华固定位ORD",
    "印华固定位LGG",
    "美鑫通GRU",
    "迅達航空",
    "散采",
)


def operation(
    *,
    bill_no: str | None = "001",
    project_type: str | None = None,
    destination: str | None = None,
    departure: date = date(2026, 8, 4),
    supplier: str | None = None,
    receivable: str = "100",
    profit: str = "10",
) -> OperationalRecord:
    return OperationalRecord(
        bill_no=bill_no,
        project_type=project_type,
        destination=destination,
        departure=departure,
        supplier=supplier,
        receivable=Decimal(receivable),
        gross_profit=Decimal(profit),
    )


@pytest.mark.parametrize(
    ("name", "fields"),
    [
        ("WWP", {"supplier": "Worldwide Partner Logistics Company Limited"}),
        (
            "欧展-固定位（LAX）",
            {
                "supplier": "欧展国际货运（上海）有限公司北京货运代理分公司",
                "project_type": "BSA-欧展",
            },
        ),
        (
            "欧展-差价",
            {
                "supplier": "欧展国际货运（上海）有限公司北京货运代理分公司",
                "project_type": "差价-欧展",
            },
        ),
        ("金开宇", {"supplier": "北京金开宇国际货运代理有限公司"}),
        ("厦门伦升", {"supplier": "厦门伦升国际物流有限公司"}),
        (
            "印华固定位OSL",
            {
                "supplier": "上海印华国际货运代理有限公司深圳分公司",
                "destination": "OSL",
            },
        ),
        (
            "印华固定位ORD",
            {
                "supplier": "上海印华国际货运代理有限公司深圳分公司",
                "destination": "ORD",
            },
        ),
        (
            "印华固定位LGG",
            {
                "supplier": "上海印华国际货运代理有限公司深圳分公司",
                "destination": "LGG",
            },
        ),
        ("美鑫通GRU", {"supplier": "广州美鑫通国际供应链有限公司"}),
        ("迅達航空", {"supplier": "迅達航空貨運（香港）有限公司"}),
        ("散采", {"project_type": "散采"}),
    ],
)
def test_each_business_rule_selects_its_matching_operation(
    name: str, fields: dict[str, str]
) -> None:
    table = calculate_business_table(PERIOD, [operation(**fields)])

    metric = next(row for row in table.rows if row.name == name)
    assert (metric.count, metric.profit, metric.receivable) == (
        1,
        Decimal(10),
        Decimal(100),
    )


def test_rows_follow_the_fixed_business_rule_order() -> None:
    table = calculate_business_table(PERIOD, [])

    assert tuple(row.name for row in table.rows) == EXPECTED_ROW_NAMES


def test_uses_inclusive_departure_dates_and_excludes_operations_outside_period() -> None:
    supplier = "Worldwide Partner Logistics Company Limited"
    operations = [
        operation(bill_no="start", departure=PERIOD.start, supplier=supplier, profit="2"),
        operation(bill_no="end", departure=PERIOD.end, supplier=supplier, profit="3"),
        operation(
            bill_no="before", departure=date(2026, 7, 31), supplier=supplier, profit="100"
        ),
        operation(
            bill_no="after", departure=date(2026, 8, 8), supplier=supplier, profit="200"
        ),
    ]

    table = calculate_business_table(PERIOD, operations)

    assert (table.rows[0].count, table.rows[0].profit) == (2, Decimal(5))
    assert (table.total.count, table.total.profit) == (2, Decimal(5))


def test_missing_bill_number_does_not_count_but_financial_values_are_included() -> None:
    record = operation(
        bill_no=None,
        supplier="Worldwide Partner Logistics Company Limited",
        receivable="250.50",
        profit="25.05",
    )

    table = calculate_business_table(PERIOD, [record])

    assert (table.rows[0].count, table.rows[0].profit, table.rows[0].receivable) == (
        0,
        Decimal("25.05"),
        Decimal("250.50"),
    )
    assert (table.total.count, table.total.profit, table.total.receivable) == (
        0,
        Decimal("25.05"),
        Decimal("250.50"),
    )


def test_total_uses_all_period_operations_once_instead_of_summing_business_rows() -> None:
    overlapping = operation(
        bill_no="overlap",
        project_type="散采",
        destination="OSL",
        supplier="上海印华国际货运代理有限公司深圳分公司",
        receivable="300",
        profit="30",
    )
    unmatched = operation(
        bill_no="unmatched",
        project_type="普通项目",
        supplier="未配置供应商",
        receivable="700",
        profit="70",
    )

    table = calculate_business_table(PERIOD, [overlapping, unmatched])

    assert table.rows[5].count == 1
    assert table.rows[10].count == 1
    assert table.total.name == "销售额合计"
    assert (table.total.count, table.total.profit, table.total.receivable) == (
        2,
        Decimal(100),
        Decimal(1000),
    )


def test_margin_is_none_when_receivable_is_zero() -> None:
    table = calculate_business_table(
        PERIOD,
        [
            operation(
                supplier="Worldwide Partner Logistics Company Limited",
                receivable="0",
                profit="12",
            )
        ],
    )

    assert table.rows[0].margin is None
    assert table.total.margin is None


def test_margin_is_decimal_ratio_when_receivable_is_nonzero() -> None:
    table = calculate_business_table(
        PERIOD,
        [
            operation(
                supplier="Worldwide Partner Logistics Company Limited",
                receivable="80",
                profit="20",
            )
        ],
    )

    assert table.rows[0].margin == Decimal("0.25")
    assert table.total.margin == Decimal("0.25")
