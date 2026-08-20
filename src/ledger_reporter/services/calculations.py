from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ledger_reporter.domain.models import (
    BusinessMetric,
    BusinessTable,
    FundRecord,
    OperationalRecord,
    PeriodMetrics,
    ReportingPeriod,
)
from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.io.source_settings import (
    DEFAULT_SOURCE_SETTINGS,
    AggregateRule,
    FilterRule,
    RatioRule,
    SourceSettings,
)

ZERO = Decimal("0")
DAYS_PER_YEAR = Decimal(365)
OPERATION_DEFAULTS = {
    "提单号": "bill_no",
    "项目类型": "project_type",
    "目的口岸": "destination",
    "预计起飞时间": "departure",
    "B1供应商": "supplier",
    "预估总应收": "receivable",
    "预估毛利润": "gross_profit",
}
FUND_DEFAULTS = {
    "渠道名称": "channel",
    "信容付款日期": "payment_date",
    "付款金额合计（90%）": "amount",
    "应收操作费": "operation_fee",
}


def _value(record: object, field: str, defaults: Mapping[str, str]) -> object:
    values = getattr(record, "values", {})
    if field in values:
        return values[field]
    attribute = defaults.get(field)
    return getattr(record, attribute) if attribute is not None else None


def _date_value(value: object, label: str) -> date | None:
    if value in (None, "", "未放款"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
        except ValueError:
            pass
    raise WorkbookDataError(f"{label}包含无法识别的日期：{value!r}。")


def _decimal_value(value: object, label: str) -> Decimal:
    if value in (None, ""):
        return ZERO
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise WorkbookDataError(f"{label}包含无法识别的金额：{value!r}。") from None
    if not result.is_finite():
        raise WorkbookDataError(f"{label}包含无法识别的金额：{value!r}。")
    return result


def _matches(record: object, filters: tuple[FilterRule, ...], defaults: Mapping[str, str]) -> bool:
    for rule in filters:
        if not rule.enabled:
            continue
        equal = str(_value(record, rule.field, defaults) or "").strip() == rule.value.strip()
        if equal == rule.exclude:
            return False
    return True


def _selected(
    records: Iterable[object],
    period: ReportingPeriod,
    date_field: str,
    filters: tuple[FilterRule, ...],
    defaults: Mapping[str, str],
    label: str,
) -> tuple[object, ...]:
    selected = []
    for record in records:
        record_date = _date_value(
            _value(record, date_field, defaults), f"{label}字段「{date_field}」"
        )
        if record_date is not None and period.start <= record_date <= period.end:
            if _matches(record, filters, defaults):
                selected.append(record)
    return tuple(selected)


def _count(
    records: Iterable[object],
    period: ReportingPeriod,
    rule: AggregateRule,
    defaults: Mapping[str, str],
    label: str,
) -> int:
    return sum(
        bool(_value(record, rule.value_field, defaults))
        for record in _selected(records, period, rule.date_field, rule.filters, defaults, label)
    )


def _sum(
    records: Iterable[object],
    period: ReportingPeriod,
    rule: AggregateRule,
    defaults: Mapping[str, str],
    label: str,
) -> Decimal:
    return sum(
        (
            _decimal_value(
                _value(record, rule.value_field, defaults),
                f"{label}字段「{rule.value_field}」",
            )
            for record in _selected(records, period, rule.date_field, rule.filters, defaults, label)
        ),
        ZERO,
    )


def _ratio(
    records: Iterable[object],
    period: ReportingPeriod,
    rule: RatioRule,
    defaults: Mapping[str, str],
    label: str,
) -> tuple[Decimal, Decimal, Decimal | None]:
    selected = _selected(records, period, rule.date_field, rule.filters, defaults, label)
    numerator = sum(
        (
            _decimal_value(
                _value(record, rule.numerator_field, defaults),
                f"{label}字段「{rule.numerator_field}」",
            )
            for record in selected
        ),
        ZERO,
    )
    denominator = sum(
        (
            _decimal_value(
                _value(record, rule.denominator_field, defaults),
                f"{label}字段「{rule.denominator_field}」",
            )
            for record in selected
        ),
        ZERO,
    )
    return numerator, denominator, None if denominator == ZERO else numerator / denominator


def calculate_business_table(
    period: ReportingPeriod,
    operations: Iterable[OperationalRecord],
    settings: SourceSettings = DEFAULT_SOURCE_SETTINGS,
) -> BusinessTable:
    records = tuple(operations)
    rows = []
    for row in settings.business_rows:
        count = _count(records, period, row.count, OPERATION_DEFAULTS, f"{row.name}完成数量")
        profit = _sum(records, period, row.profit, OPERATION_DEFAULTS, f"{row.name}预估利润")
        _numerator, denominator, margin = _ratio(
            records, period, row.margin, OPERATION_DEFAULTS, f"{row.name}预估利润率"
        )
        rows.append(
            BusinessMetric(
                row.name, count, profit, denominator, margin, row.cycle, row.measured_rate
            )
        )

    total_rule = settings.business_total
    sales = _sum(records, period, total_rule.sales, OPERATION_DEFAULTS, "销售额合计")
    count = _count(records, period, total_rule.count, OPERATION_DEFAULTS, "合计完成数量")
    profit = _sum(records, period, total_rule.profit, OPERATION_DEFAULTS, "合计预估利润")
    _numerator, _denominator, margin = _ratio(
        records, period, total_rule.margin, OPERATION_DEFAULTS, "合计预估利润率"
    )
    return BusinessTable(
        period=period,
        rows=tuple(rows),
        total=BusinessMetric(total_rule.label, count, profit, sales, margin),
    )


def calculate_period(
    period: ReportingPeriod,
    operations: Iterable[OperationalRecord],
    funds: Iterable[FundRecord],
    settings: SourceSettings = DEFAULT_SOURCE_SETTINGS,
) -> PeriodMetrics:
    operation_records = tuple(operations)
    fund_records = tuple(funds)
    fund_rule = settings.fund_profit
    selected_funds = _selected(
        fund_records,
        period,
        fund_rule.date_field,
        (),
        FUND_DEFAULTS,
        "资金预估利润",
    )
    rates = {channel.name: channel.rate for channel in fund_rule.channels}
    unknown_channels = sorted(
        {
            str(_value(record, fund_rule.channel_field, FUND_DEFAULTS) or "<空白>")
            for record in selected_funds
            if str(_value(record, fund_rule.channel_field, FUND_DEFAULTS) or "") not in rates
        }
    )
    if unknown_channels:
        raise WorkbookDataError(f"未知资金渠道：{', '.join(unknown_channels)}")
    fund_profit = sum(
        (
            _decimal_value(
                _value(record, fund_rule.amount_field, FUND_DEFAULTS),
                f"资金预估利润字段「{fund_rule.amount_field}」",
            )
            * (
                rates[str(_value(record, fund_rule.channel_field, FUND_DEFAULTS))]
                - fund_rule.capital_cost
            )
            * Decimal(fund_rule.term_days)
            / DAYS_PER_YEAR
            + _decimal_value(
                _value(record, fund_rule.operation_fee_field, FUND_DEFAULTS),
                f"资金预估利润字段「{fund_rule.operation_fee_field}」",
            )
            for record in selected_funds
        ),
        ZERO,
    )
    return PeriodMetrics(
        project_count=_count(
            operation_records, period, settings.project_count, OPERATION_DEFAULTS, "项目订单数量"
        ),
        project_profit=_sum(
            operation_records, period, settings.project_profit, OPERATION_DEFAULTS, "项目预估利润"
        ),
        scatter_count=_count(
            operation_records, period, settings.scatter_count, OPERATION_DEFAULTS, "散采订单数量"
        ),
        scatter_profit=_sum(
            operation_records, period, settings.scatter_profit, OPERATION_DEFAULTS, "散采预估利润"
        ),
        fund_amount=_sum(fund_records, period, settings.fund_amount, FUND_DEFAULTS, "资金放款金额"),
        fund_profit=fund_profit,
    )
