from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")  # noqa: FURB157


@dataclass(frozen=True, slots=True)
class ReportingPeriod:
    start: date
    end: date
    label: str


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    latest: ReportingPeriod
    new_periods: tuple[ReportingPeriod, ...]
    refresh_periods: tuple[ReportingPeriod, ...]

    @property
    def periods(self) -> tuple[ReportingPeriod, ...]:
        return tuple(
            sorted(set(self.new_periods + self.refresh_periods), key=lambda item: item.start)
        )


@dataclass(frozen=True, slots=True)
class OperationalRecord:
    bill_no: str | None
    project_type: str | None
    destination: str | None
    departure: date
    supplier: str | None
    receivable: Decimal
    gross_profit: Decimal


@dataclass(frozen=True, slots=True)
class FundRecord:
    channel: str
    payment_date: date
    amount: Decimal
    operation_fee: Decimal


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    project_count: int = 0
    project_profit: Decimal = ZERO
    scatter_count: int = 0
    scatter_profit: Decimal = ZERO
    fund_amount: Decimal = ZERO
    fund_profit: Decimal = ZERO
    card_count: int = 0
    card_profit: Decimal = ZERO

    @property
    def total_profit(self) -> Decimal:
        return self.project_profit + self.scatter_profit + self.fund_profit + self.card_profit


@dataclass(frozen=True, slots=True)
class WeekSnapshot:
    fiscal_year: int
    period: ReportingPeriod
    metrics: PeriodMetrics


@dataclass(frozen=True, slots=True)
class BusinessMetric:
    name: str
    count: int
    profit: Decimal
    receivable: Decimal

    @property
    def margin(self) -> Decimal | None:
        return None if self.receivable == ZERO else self.profit / self.receivable


@dataclass(frozen=True, slots=True)
class BusinessTable:
    period: ReportingPeriod
    rows: tuple[BusinessMetric, ...]
    total: BusinessMetric


@dataclass(frozen=True, slots=True)
class ReportBundle:
    fiscal_year: int
    latest_period: ReportingPeriod
    baseline_rows: tuple[dict[str, object], ...]
    weeks: tuple[WeekSnapshot, ...]
    business: BusinessTable


@dataclass(frozen=True, slots=True)
class SourceInspection:
    fiscal_year: int
    update_plan: UpdatePlan
