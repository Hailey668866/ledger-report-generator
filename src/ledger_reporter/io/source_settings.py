import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation
from pathlib import Path

XLSX_MAX_ROW = 1_048_576
SCHEMA_VERSION = 2


def _required(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}必须是非空字符串。")


@dataclass(frozen=True, slots=True)
class FilterRule:
    field: str
    value: str
    exclude: bool = False

    def validate(self, label: str) -> None:
        if not isinstance(self.field, str) or not isinstance(self.value, str):
            raise ValueError(f"{label}的筛选字段和值必须是字符串。")
        if bool(self.field.strip()) != bool(self.value.strip()):
            raise ValueError(f"{label}的筛选字段和值必须同时填写或同时留空。")
        if type(self.exclude) is not bool:
            raise ValueError(f"{label}的排除选项无效。")

    @property
    def enabled(self) -> bool:
        return bool(self.field.strip())


@dataclass(frozen=True, slots=True)
class AggregateRule:
    date_field: str
    value_field: str
    filters: tuple[FilterRule, ...] = ()

    def validate(self, label: str) -> None:
        _required(self.date_field, f"{label}的日期字段")
        _required(self.value_field, f"{label}的计算字段")
        if len(self.filters) > 3:
            raise ValueError(f"{label}最多允许三个筛选条件。")
        for index, rule in enumerate(self.filters, 1):
            rule.validate(f"{label}筛选条件 {index}")


@dataclass(frozen=True, slots=True)
class RatioRule:
    date_field: str
    numerator_field: str
    denominator_field: str
    filters: tuple[FilterRule, ...] = ()

    def validate(self, label: str) -> None:
        _required(self.date_field, f"{label}的日期字段")
        _required(self.numerator_field, f"{label}的分子字段")
        _required(self.denominator_field, f"{label}的分母字段")
        if len(self.filters) > 3:
            raise ValueError(f"{label}最多允许三个筛选条件。")
        for index, rule in enumerate(self.filters, 1):
            rule.validate(f"{label}筛选条件 {index}")


@dataclass(frozen=True, slots=True)
class ChannelRate:
    name: str
    rate: Decimal

    def validate(self, label: str) -> None:
        _required(self.name, f"{label}名称")
        if not isinstance(self.rate, Decimal) or not Decimal(0) <= self.rate <= Decimal(1):
            raise ValueError(f"{label}利率必须在 0% 至 100% 之间。")


@dataclass(frozen=True, slots=True)
class FundProfitRule:
    date_field: str
    channel_field: str
    amount_field: str
    operation_fee_field: str
    channels: tuple[ChannelRate, ...]
    capital_cost: Decimal
    term_days: int

    def validate(self) -> None:
        for value, label in (
            (self.date_field, "资金预估利润的日期字段"),
            (self.channel_field, "资金预估利润的渠道字段"),
            (self.amount_field, "资金预估利润的金额字段"),
            (self.operation_fee_field, "资金预估利润的操作费字段"),
        ):
            _required(value, label)
        if not self.channels:
            raise ValueError("资金预估利润至少需要一个资金渠道。")
        for index, channel in enumerate(self.channels, 1):
            channel.validate(f"资金渠道 {index}")
        names = [channel.name.strip() for channel in self.channels]
        if len(names) != len(set(names)):
            raise ValueError("资金渠道名称不可重复。")
        if not isinstance(self.capital_cost, Decimal) or not Decimal(
            0
        ) <= self.capital_cost <= Decimal(1):
            raise ValueError("资金成本率必须在 0% 至 100% 之间。")
        if type(self.term_days) is not int or self.term_days < 0:
            raise ValueError("计息天数必须是非负整数。")


@dataclass(frozen=True, slots=True)
class BusinessRowRule:
    name: str
    cycle: str
    measured_rate: str
    count: AggregateRule
    profit: AggregateRule
    margin: RatioRule

    def validate(self, index: int) -> None:
        _required(self.name, f"自营项目第 {index} 行业务名称")
        if not isinstance(self.cycle, str) or not isinstance(self.measured_rate, str):
            raise ValueError(f"自营项目「{self.name}」的显示内容必须是字符串。")
        self.count.validate(f"自营项目「{self.name}」完成数量")
        self.profit.validate(f"自营项目「{self.name}」预估利润")
        self.margin.validate(f"自营项目「{self.name}」预估利润率")


@dataclass(frozen=True, slots=True)
class BusinessTotalRule:
    label: str
    sales: AggregateRule
    count: AggregateRule
    profit: AggregateRule
    margin: RatioRule

    def validate(self) -> None:
        _required(self.label, "自营项目合计行名称")
        self.sales.validate("自营项目销售额合计")
        self.count.validate("自营项目合计完成数量")
        self.profit.validate("自营项目合计预估利润")
        self.margin.validate("自营项目合计预估利润率")


@dataclass(frozen=True, slots=True)
class SourceSettings:
    schema_version: int
    funds_sheet: str
    funds_header_row: int
    operations_sheet: str
    operations_header_row: int
    project_count: AggregateRule
    project_profit: AggregateRule
    scatter_count: AggregateRule
    scatter_profit: AggregateRule
    fund_amount: AggregateRule
    fund_profit: FundProfitRule
    business_rows: tuple[BusinessRowRule, ...]
    business_total: BusinessTotalRule

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"不支持的设置版本：{self.schema_version}。")
        _required(self.funds_sheet, "资金台账工作表名称")
        _required(self.operations_sheet, "运营台账工作表名称")
        for value in (self.funds_header_row, self.operations_header_row):
            if type(value) is not int or not 1 <= value <= XLSX_MAX_ROW:
                raise ValueError(f"表头行必须是 1 至 {XLSX_MAX_ROW} 之间的正整数。")
        for label, rule in (
            ("项目订单数量", self.project_count),
            ("项目预估利润", self.project_profit),
            ("散采订单数量", self.scatter_count),
            ("散采预估利润", self.scatter_profit),
            ("资金放款金额", self.fund_amount),
        ):
            rule.validate(label)
        self.fund_profit.validate()
        if not self.business_rows:
            raise ValueError("自营项目周报至少需要一个业务行。")
        for index, row in enumerate(self.business_rows, 1):
            row.validate(index)
        names = [row.name.strip() for row in self.business_rows]
        if len(names) != len(set(names)):
            raise ValueError("自营项目业务名称不可重复。")
        self.business_total.validate()

    @staticmethod
    def _aggregate_fields(rule: AggregateRule) -> set[str]:
        return {
            rule.date_field,
            rule.value_field,
            *(item.field for item in rule.filters if item.enabled),
        }

    @staticmethod
    def _ratio_fields(rule: RatioRule) -> set[str]:
        return {
            rule.date_field,
            rule.numerator_field,
            rule.denominator_field,
            *(item.field for item in rule.filters if item.enabled),
        }

    def operation_fields(self) -> set[str]:
        result = set()
        for rule in (
            self.project_count,
            self.project_profit,
            self.scatter_count,
            self.scatter_profit,
            self.business_total.sales,
            self.business_total.count,
            self.business_total.profit,
        ):
            result.update(self._aggregate_fields(rule))
        result.update(self._ratio_fields(self.business_total.margin))
        for row in self.business_rows:
            result.update(self._aggregate_fields(row.count))
            result.update(self._aggregate_fields(row.profit))
            result.update(self._ratio_fields(row.margin))
        return result

    def operation_date_fields(self) -> set[str]:
        result = {
            self.project_count.date_field,
            self.project_profit.date_field,
            self.scatter_count.date_field,
            self.scatter_profit.date_field,
            self.business_total.sales.date_field,
            self.business_total.count.date_field,
            self.business_total.profit.date_field,
            self.business_total.margin.date_field,
        }
        for row in self.business_rows:
            result.update((row.count.date_field, row.profit.date_field, row.margin.date_field))
        return result

    def operation_numeric_fields(self) -> set[str]:
        result = {
            self.project_profit.value_field,
            self.scatter_profit.value_field,
            self.business_total.sales.value_field,
            self.business_total.profit.value_field,
            self.business_total.margin.numerator_field,
            self.business_total.margin.denominator_field,
        }
        for row in self.business_rows:
            result.update(
                (
                    row.profit.value_field,
                    row.margin.numerator_field,
                    row.margin.denominator_field,
                )
            )
        return result

    def fund_fields(self) -> set[str]:
        return {
            *self._aggregate_fields(self.fund_amount),
            self.fund_profit.date_field,
            self.fund_profit.channel_field,
            self.fund_profit.amount_field,
            self.fund_profit.operation_fee_field,
        }

    def fund_date_fields(self) -> set[str]:
        return {self.fund_amount.date_field, self.fund_profit.date_field}

    def fund_numeric_fields(self) -> set[str]:
        return {
            self.fund_amount.value_field,
            self.fund_profit.amount_field,
            self.fund_profit.operation_fee_field,
        }


BUSINESS_DEFAULTS = (
    ("WWP", "dl :26.9.31", "1.02%", (("supplier", "Worldwide Partner Logistics Company Limited"),)),
    (
        "欧展-固定位（LAX）",
        "26.1.1--27.1.31",
        "2.41%",
        (
            ("supplier", "欧展国际货运（上海）有限公司北京货运代理分公司"),
            ("project_type", "BSA-欧展"),
        ),
    ),
    (
        "欧展-差价",
        "长期",
        "",
        (
            ("supplier", "欧展国际货运（上海）有限公司北京货运代理分公司"),
            ("project_type", "差价-欧展"),
        ),
    ),
    ("金开宇", "长期", "固定差价2%", (("supplier", "北京金开宇国际货运代理有限公司"),)),
    ("厦门伦升", "长期", "1.52%", (("supplier", "厦门伦升国际物流有限公司"),)),
    (
        "印华固定位OSL",
        "dl :26.12.31",
        "0.08%",
        (("supplier", "上海印华国际货运代理有限公司深圳分公司"), ("destination", "OSL")),
    ),
    (
        "印华固定位ORD",
        "26.1.17--27.1.14",
        "",
        (("supplier", "上海印华国际货运代理有限公司深圳分公司"), ("destination", "ORD")),
    ),
    (
        "印华固定位LGG",
        "26.1.1--26.12.29",
        "",
        (("supplier", "上海印华国际货运代理有限公司深圳分公司"), ("destination", "LGG")),
    ),
    ("美鑫通GRU", "26.6.8--26.12.31", "合计260W", (("supplier", "广州美鑫通国际供应链有限公司"),)),
    ("迅達航空", "26.6.1--26.12.31", "6.92%", (("supplier", "迅達航空貨運（香港）有限公司"),)),
    ("散采", "", "", (("project_type", "散采"),)),
)


def _defaults(legacy: dict[str, object] | None = None) -> SourceSettings:
    legacy = legacy or {}
    departure = str(legacy.get("operations_departure", "预计起飞时间"))
    bill = str(legacy.get("operations_bill_no", "提单号"))
    project_type = str(legacy.get("operations_project_type", "项目类型"))
    destination = str(legacy.get("operations_destination", "目的口岸"))
    supplier = str(legacy.get("operations_supplier", "B1供应商"))
    receivable = str(legacy.get("operations_receivable", "预估总应收"))
    profit = str(legacy.get("operations_gross_profit", "预估毛利润"))
    semantic_fields = {
        "supplier": supplier,
        "project_type": project_type,
        "destination": destination,
    }
    rows = []
    for name, cycle, measured_rate, criteria in BUSINESS_DEFAULTS:
        filters = tuple(FilterRule(semantic_fields[field], value) for field, value in criteria)
        rows.append(
            BusinessRowRule(
                name,
                cycle,
                measured_rate,
                AggregateRule(departure, bill, filters),
                AggregateRule(departure, profit, filters),
                RatioRule(departure, profit, receivable, filters),
            )
        )
    payment_date = str(legacy.get("funds_payment_date", "信容付款日期"))
    amount = str(legacy.get("funds_amount", "付款金额合计（90%）"))
    return SourceSettings(
        SCHEMA_VERSION,
        str(legacy.get("funds_sheet", "资金散板汇总{年份}")),
        int(legacy.get("funds_header_row", 1)),
        str(legacy.get("operations_sheet", "台账明细")),
        int(legacy.get("operations_header_row", 1)),
        AggregateRule(departure, bill, (FilterRule(project_type, "散采", True),)),
        AggregateRule(departure, profit, (FilterRule(project_type, "散采", True),)),
        AggregateRule(departure, bill, (FilterRule(project_type, "散采"),)),
        AggregateRule(departure, profit, (FilterRule(project_type, "散采"),)),
        AggregateRule(payment_date, amount),
        FundProfitRule(
            payment_date,
            str(legacy.get("funds_channel", "渠道名称")),
            amount,
            str(legacy.get("funds_operation_fee", "应收操作费")),
            (
                ChannelRate("广州美鑫通国际供应链有限公司", Decimal("0.10")),
                ChannelRate("浙江飞速供应链管理有限公司", Decimal("0.12")),
            ),
            Decimal("0.0448"),
            60,
        ),
        tuple(rows),
        BusinessTotalRule(
            "销售额合计",
            AggregateRule(departure, receivable),
            AggregateRule(departure, bill),
            AggregateRule(departure, profit),
            RatioRule(departure, profit, receivable),
        ),
    )


DEFAULT_SOURCE_SETTINGS = _defaults()
LEGACY_KEYS = {
    "funds_sheet",
    "funds_header_row",
    "funds_channel",
    "funds_payment_date",
    "funds_amount",
    "funds_operation_fee",
    "operations_sheet",
    "operations_header_row",
    "operations_bill_no",
    "operations_project_type",
    "operations_destination",
    "operations_departure",
    "operations_supplier",
    "operations_receivable",
    "operations_gross_profit",
}


def _filters(data: list[dict[str, object]]) -> tuple[FilterRule, ...]:
    return tuple(FilterRule(**item) for item in data)


def _aggregate(data: dict[str, object]) -> AggregateRule:
    return AggregateRule(
        str(data["date_field"]), str(data["value_field"]), _filters(data.get("filters", []))
    )  # type: ignore[arg-type]


def _ratio(data: dict[str, object]) -> RatioRule:
    return RatioRule(
        str(data["date_field"]),
        str(data["numerator_field"]),
        str(data["denominator_field"]),
        _filters(data.get("filters", [])),
    )  # type: ignore[arg-type]


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"无法识别数值：{value!r}。") from None


def _load_v2(data: dict[str, object]) -> SourceSettings:
    expected = {field.name for field in fields(SourceSettings)}
    if set(data) != expected:
        raise ValueError("字段设置包含未知项或缺少必填项。")
    fund = data["fund_profit"]
    total = data["business_total"]
    if not isinstance(fund, dict) or not isinstance(total, dict):
        raise ValueError("字段设置结构无效。")
    channels = tuple(
        ChannelRate(str(item["name"]), _decimal(item["rate"])) for item in fund["channels"]
    )  # type: ignore[index]
    fund_profit = FundProfitRule(
        str(fund["date_field"]),
        str(fund["channel_field"]),
        str(fund["amount_field"]),
        str(fund["operation_fee_field"]),
        channels,
        _decimal(fund["capital_cost"]),
        int(fund["term_days"]),
    )
    rows = tuple(
        BusinessRowRule(
            str(item["name"]),
            str(item["cycle"]),
            str(item["measured_rate"]),
            _aggregate(item["count"]),
            _aggregate(item["profit"]),
            _ratio(item["margin"]),  # type: ignore[arg-type]
        )
        for item in data["business_rows"]  # type: ignore[union-attr]
    )
    settings = SourceSettings(
        int(data["schema_version"]),
        str(data["funds_sheet"]),
        int(data["funds_header_row"]),
        str(data["operations_sheet"]),
        int(data["operations_header_row"]),
        _aggregate(data["project_count"]),
        _aggregate(data["project_profit"]),  # type: ignore[arg-type]
        _aggregate(data["scatter_count"]),
        _aggregate(data["scatter_profit"]),  # type: ignore[arg-type]
        _aggregate(data["fund_amount"]),
        fund_profit,
        rows,  # type: ignore[arg-type]
        BusinessTotalRule(
            str(total["label"]),
            _aggregate(total["sales"]),
            _aggregate(total["count"]),
            _aggregate(total["profit"]),
            _ratio(total["margin"]),
        ),  # type: ignore[arg-type]
    )
    settings.validate()
    return settings


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def load_source_settings(path: Path) -> SourceSettings:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("设置内容必须是对象。")
        if "schema_version" in data:
            if data["schema_version"] != SCHEMA_VERSION:
                raise ValueError(f"不支持的设置版本：{data['schema_version']}。")
            return _load_v2(data)
        if set(data) != LEGACY_KEYS:
            raise ValueError("旧版字段设置包含未知项或缺少必填项。")
        settings = _defaults(data)
        settings.validate()
        return settings
    except FileNotFoundError:
        return DEFAULT_SOURCE_SETTINGS
    except (OSError, UnicodeError, TypeError, ValueError, KeyError) as error:
        raise ValueError(f"字段设置文件无法读取：{error}") from None


def save_source_settings(path: Path, settings: SourceSettings) -> None:
    settings.validate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(_jsonable(asdict(settings)), temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
