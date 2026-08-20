import hashlib
from datetime import date, datetime
from pathlib import Path

from ledger_reporter.domain.models import (
    FundRecord,
    OperationalRecord,
    ReportBundle,
    SourceInspection,
    UpdatePlan,
    WeekSnapshot,
)
from ledger_reporter.domain.periods import fiscal_year_for
from ledger_reporter.io.source_settings import DEFAULT_SOURCE_SETTINGS, SourceSettings
from ledger_reporter.io.workbooks import read_funds, read_operations
from ledger_reporter.services.baseline import Baseline, load_fy2026_baseline
from ledger_reporter.services.calculations import (
    calculate_business_table,
    calculate_period,
)
from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.update_planner import plan_updates

IN_MEMORY_SUMMARY: dict[str, object] = {
    "name": "in-memory",
    "size": 0,
    "sha256": "",
}


class ReportService:
    def __init__(
        self,
        history: HistoryRepository,
        source_settings: SourceSettings = DEFAULT_SOURCE_SETTINGS,
    ) -> None:
        source_settings.validate()
        self.history = history
        self.source_settings = source_settings

    def set_source_settings(self, settings: SourceSettings) -> None:
        settings.validate()
        self.source_settings = settings

    def _plan(self, today: date) -> tuple[int, Baseline, UpdatePlan]:
        fiscal_year = fiscal_year_for(today)
        baseline = load_fy2026_baseline()
        frozen_through = (
            baseline.frozen_through
            if fiscal_year == baseline.fiscal_year
            else date(fiscal_year, 3, 31)
        )
        existing = self.history.load_weeks(fiscal_year)
        update_plan = plan_updates(
            today,
            {snapshot.period for snapshot in existing},
            frozen_through,
        )
        return fiscal_year, baseline, update_plan

    def inspect_sources(
        self,
        funds_path: Path,
        operations_path: Path,
        today: date,
    ) -> SourceInspection:
        settings = self.source_settings
        fiscal_year, _baseline, update_plan = self._plan(today)
        operations = read_operations(operations_path, settings)
        funds = read_funds(
            funds_path,
            {fiscal_year, fiscal_year + 1},
            settings,
        )

        for period in update_plan.periods:
            calculate_period(period, operations, funds, settings)
        calculate_business_table(update_plan.latest, operations, settings)

        return SourceInspection(fiscal_year, update_plan)

    def generate_from_records(
        self,
        today: date,
        operations: list[OperationalRecord],
        funds: list[FundRecord],
        *,
        generated_at: datetime | None = None,
        funds_summary: dict[str, object] | None = None,
        operations_summary: dict[str, object] | None = None,
    ) -> ReportBundle:
        fiscal_year, baseline, update_plan = self._plan(today)
        calculated = tuple(
            WeekSnapshot(
                fiscal_year,
                period,
                calculate_period(period, operations, funds, self.source_settings),
            )
            for period in update_plan.periods
        )
        business = calculate_business_table(update_plan.latest, operations, self.source_settings)

        actual_generated_at = generated_at or datetime.now().astimezone()
        actual_funds_summary = IN_MEMORY_SUMMARY.copy() if funds_summary is None else funds_summary
        actual_operations_summary = (
            IN_MEMORY_SUMMARY.copy() if operations_summary is None else operations_summary
        )

        with self.history.transaction() as connection:
            self.history.save_weeks(calculated, connection)
            self.history.save_generation(
                fiscal_year,
                actual_generated_at,
                baseline.version if fiscal_year == baseline.fiscal_year else "none",
                actual_funds_summary,
                actual_operations_summary,
                connection,
            )

        baseline_rows = baseline.rows if fiscal_year == baseline.fiscal_year else ()
        return ReportBundle(
            fiscal_year=fiscal_year,
            latest_period=update_plan.latest,
            baseline_rows=baseline_rows,
            weeks=tuple(self.history.load_weeks(fiscal_year)),
            business=business,
        )

    @staticmethod
    def _source_summary(path: Path) -> dict[str, object]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
        return {"name": path.name, "size": size, "sha256": digest.hexdigest()}

    def generate(
        self,
        funds_path: Path,
        operations_path: Path,
        today: date,
    ) -> ReportBundle:
        settings = self.source_settings
        fiscal_year = fiscal_year_for(today)
        operations = read_operations(operations_path, settings)
        funds = read_funds(
            funds_path,
            {fiscal_year, fiscal_year + 1},
            settings,
        )
        return self.generate_from_records(
            today,
            operations,
            funds,
            funds_summary=self._source_summary(funds_path),
            operations_summary=self._source_summary(operations_path),
        )
