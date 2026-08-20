from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
import re

from ledger_reporter.domain.models import PeriodMetrics, ReportBundle, WeekSnapshot
from ledger_reporter.presentation.models import CellSpec, MergeSpec, TableSpec
from ledger_reporter.rules import MONTH_TARGET, QUARTER_TARGET

ZERO = Decimal("0")  # noqa: FURB157
TEN_THOUSAND = Decimal(10000)
BUSINESS_META: tuple[tuple[str, str, Decimal | str | None], ...] = (
    ("WWP", "dl :26.9.31", Decimal("0.0102")),
    ("欧展-固定位（LAX）", "26.1.1--27.1.31", Decimal("0.0241")),
    ("欧展-差价", "长期", None),
    ("金开宇", "长期", "固定差价2%"),
    ("厦门伦升", "长期", Decimal("0.0152")),
    ("印华固定位OSL", "dl :26.12.31", Decimal("0.0008")),
    ("印华固定位ORD", "26.1.17--27.1.14", None),
    ("印华固定位LGG", "26.1.1--26.12.29", None),
    ("美鑫通GRU", "26.6.8--26.12.31", "合计260W"),
    ("迅達航空", "26.6.1--26.12.31", Decimal("0.0692")),
    ("散采", "", None),
)
BUSINESS_META_BY_NAME = {name: (cycle, measured) for name, cycle, measured in BUSINESS_META}


@dataclass(frozen=True, slots=True)
class _SummaryRow:
    kind: str
    label: str
    metrics: PeriodMetrics
    total_profit: Decimal
    target: Decimal | None


def _decimal(value: object) -> Decimal:
    return ZERO if value in (None, "", "-") else Decimal(str(value).replace(",", ""))


def _metrics_from_baseline(values: Sequence[object]) -> PeriodMetrics:
    return PeriodMetrics(
        project_count=int(values[0] or 0),
        project_profit=_decimal(values[1]),
        scatter_count=int(values[2] or 0),
        scatter_profit=_decimal(values[3]),
        fund_amount=_decimal(values[4]),
        fund_profit=_decimal(values[5]),
        card_count=int(values[6] or 0),
        card_profit=_decimal(values[7]),
    )


def _add(left: PeriodMetrics, right: PeriodMetrics) -> PeriodMetrics:
    return PeriodMetrics(
        project_count=left.project_count + right.project_count,
        project_profit=left.project_profit + right.project_profit,
        scatter_count=left.scatter_count + right.scatter_count,
        scatter_profit=left.scatter_profit + right.scatter_profit,
        fund_amount=left.fund_amount + right.fund_amount,
        fund_profit=left.fund_profit + right.fund_profit,
        card_count=left.card_count + right.card_count,
        card_profit=left.card_profit + right.card_profit,
    )


def _sum_metrics(items: Iterable[WeekSnapshot]) -> PeriodMetrics:
    result = PeriodMetrics()
    for item in items:
        result = _add(result, item.metrics)
    return result


def _quarter_number(month: int) -> int:
    return ((month - 4) % 12) // 3 + 1


def _quarter_label(fiscal_year: int, number: int) -> str:
    start_month = 4 + (number - 1) * 3
    start_year = fiscal_year
    while start_month > 12:
        start_month -= 12
        start_year += 1
    end_month = start_month + 2
    end_year = start_year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    return f"Q{number}({str(start_year)[-2:]}.{start_month}-{str(end_year)[-2:]}.{end_month})"


def _summary_rows(bundle: ReportBundle) -> list[_SummaryRow]:
    rows: list[_SummaryRow] = []
    quarter_indexes: dict[int, int] = {}
    for raw in bundle.baseline_rows:
        label = str(raw["label"])
        values = list(raw["values"])
        kind = "quarter" if label.startswith("Q") else "month" if "年" in label else "week"
        target = _decimal(values[9]) if values[9] not in (None, "") else None
        rows.append(
            _SummaryRow(
                kind,
                label,
                _metrics_from_baseline(values),
                _decimal(values[8]),
                target,
            )
        )
        if kind == "quarter":
            quarter_indexes[int(label[1])] = len(rows) - 1

    by_month: dict[tuple[int, int], list[WeekSnapshot]] = defaultdict(list)
    for week in bundle.weeks:
        by_month[(week.period.start.year, week.period.start.month)].append(week)

    for (year, month), weeks in sorted(by_month.items()):
        number = _quarter_number(month)
        month_metrics = _sum_metrics(weeks)
        if number in quarter_indexes:
            index = quarter_indexes[number]
            existing = rows[index]
            rows[index] = _SummaryRow(
                existing.kind,
                existing.label,
                _add(existing.metrics, month_metrics),
                existing.total_profit + month_metrics.total_profit,
                existing.target,
            )
        else:
            quarter_indexes[number] = len(rows)
            rows.append(
                _SummaryRow(
                    "quarter",
                    _quarter_label(bundle.fiscal_year, number),
                    month_metrics,
                    month_metrics.total_profit,
                    QUARTER_TARGET,
                )
            )
        rows.append(
            _SummaryRow(
                "month",
                f"{year}年{month}月",
                month_metrics,
                month_metrics.total_profit,
                MONTH_TARGET,
            )
        )
        rows.extend(
            _SummaryRow(
                "week",
                week.period.label,
                week.metrics,
                week.metrics.total_profit,
                None,
            )
            for week in weeks
        )
    return rows


def _summary_table(bundle: ReportBundle) -> TableSpec:
    cells = [
        CellSpec(1, 1, "日期", "header"),
        CellSpec(1, 2, "项目订单", "header"),
        CellSpec(1, 4, "散采订单", "header"),
        CellSpec(1, 6, "资金订单", "header"),
        CellSpec(1, 8, "卡转订单", "header"),
        CellSpec(1, 10, "合计利润", "header"),
        CellSpec(1, 11, "目标", "header"),
        CellSpec(1, 12, "完成度", "header"),
        CellSpec(2, 2, "板位数", "header"),
        CellSpec(2, 3, "预估利润", "header"),
        CellSpec(2, 4, "板位数", "header"),
        CellSpec(2, 5, "预估利润", "header"),
        CellSpec(2, 6, "放款金额", "header"),
        CellSpec(2, 7, "预估利润", "header"),
        CellSpec(2, 8, "车次", "header"),
        CellSpec(2, 9, "预估利润", "header"),
    ]
    rows = _summary_rows(bundle)
    for row_number, item in enumerate(rows, 3):
        metrics = item.metrics
        completion = None if item.target in (None, ZERO) else item.total_profit / item.target
        style = item.kind if item.kind in {"quarter", "month"} else "body"
        values = (
            item.label,
            metrics.project_count,
            metrics.project_profit,
            metrics.scatter_count,
            metrics.scatter_profit,
            metrics.fund_amount,
            metrics.fund_profit,
            metrics.card_count,
            metrics.card_profit,
            item.total_profit,
            item.target,
            completion,
        )
        formats = (
            None,
            "#,##0",
            "#,##0.00",
            "#,##0",
            "#,##0.00",
            "#,##0.00",
            "#,##0.00",
            "#,##0",
            "#,##0.00",
            "#,##0.00",
            "#,##0.00",
            "0%",
        )
        cells.extend(
            CellSpec(row_number, column, value, style, formats[column - 1])
            for column, value in enumerate(values, 1)
        )
    merges = (
        MergeSpec(1, 1, 2, 1),
        MergeSpec(1, 2, 1, 3),
        MergeSpec(1, 4, 1, 5),
        MergeSpec(1, 6, 1, 7),
        MergeSpec(1, 8, 1, 9),
        MergeSpec(1, 10, 2, 10),
        MergeSpec(1, 11, 2, 11),
        MergeSpec(1, 12, 2, 12),
    )
    return TableSpec(
        "经营汇总",
        tuple(cells),
        merges,
        (18, 12, 16, 12, 16, 18, 16, 10, 14, 18, 16, 14),
        (28, 24) + (22,) * len(rows),
    )


def _business_table(bundle: ReportBundle) -> TableSpec:
    title = (
        f"{bundle.latest_period.start.year}年{bundle.latest_period.start.month}月"
        f"{bundle.latest_period.label}自营项目数据情况，单位：万元"
    )
    cells = [CellSpec(1, 1, title, "total")]
    headers = ("业务名称", "项目周期", "利润率测算", "完成数量", "预估利润", "预估利润率")
    cells.extend(CellSpec(2, column, value, "header") for column, value in enumerate(headers, 1))
    for row_number, metric in enumerate(bundle.business.rows, 3):
        fallback_cycle, fallback_rate = BUSINESS_META_BY_NAME.get(metric.name, ("", None))
        cycle = fallback_cycle if metric.cycle is None else metric.cycle
        measured_rate: Decimal | str | None = fallback_rate
        if metric.measured_rate is not None:
            text = metric.measured_rate.strip()
            match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)%", text)
            measured_rate = Decimal(match.group(1)) / 100 if match else text or None
        values = (
            metric.name,
            cycle,
            measured_rate,
            metric.count,
            metric.profit / TEN_THOUSAND,
            metric.margin,
        )
        formats = (
            None,
            None,
            "0.00%" if isinstance(measured_rate, Decimal) else None,
            "#,##0",
            "#,##0.00",
            "0.00%",
        )
        cells.extend(
            CellSpec(row_number, column, value, "body", formats[column - 1])
            for column, value in enumerate(values, 1)
        )
    total_row = 3 + len(bundle.business.rows)
    total = bundle.business.total
    total_values = (
        f"销售额合计：{total.receivable / TEN_THOUSAND:.0f}",
        "",
        "",
        total.count,
        total.profit / TEN_THOUSAND,
        total.margin,
    )
    total_formats = (None, None, None, "#,##0", "#,##0.00", "0.00%")
    cells.extend(
        CellSpec(total_row, column, value, "total", total_formats[column - 1])
        for column, value in enumerate(total_values, 1)
    )
    return TableSpec(
        "自营项目周报",
        tuple(cells),
        (MergeSpec(1, 1, 1, 6),),
        (27, 24, 18, 14, 16, 16),
        (34, 26) + (23,) * (total_row - 2),
    )


def build_tables(bundle: ReportBundle) -> tuple[TableSpec, TableSpec]:
    return _summary_table(bundle), _business_table(bundle)
