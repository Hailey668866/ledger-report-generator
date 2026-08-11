import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ledger_reporter.domain.models import PeriodMetrics, ReportingPeriod, WeekSnapshot


class HistoryRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS week_snapshots (
                    fiscal_year INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    label TEXT NOT NULL,
                    project_count INTEGER NOT NULL,
                    project_profit TEXT NOT NULL,
                    scatter_count INTEGER NOT NULL,
                    scatter_profit TEXT NOT NULL,
                    fund_amount TEXT NOT NULL,
                    fund_profit TEXT NOT NULL,
                    card_count INTEGER NOT NULL,
                    card_profit TEXT NOT NULL,
                    PRIMARY KEY (fiscal_year, start_date, end_date)
                );

                CREATE TABLE IF NOT EXISTS generation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fiscal_year INTEGER NOT NULL,
                    generated_at TEXT NOT NULL,
                    baseline_version TEXT NOT NULL,
                    funds_summary TEXT NOT NULL,
                    operations_summary TEXT NOT NULL
                );
                """
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_weeks(
        self,
        weeks: Iterable[WeekSnapshot],
        connection: sqlite3.Connection | None = None,
    ) -> None:
        owns_connection = connection is None
        active_connection = self._connect() if owns_connection else connection
        assert active_connection is not None
        try:
            active_connection.executemany(
                """
                INSERT INTO week_snapshots (
                    fiscal_year,
                    start_date,
                    end_date,
                    label,
                    project_count,
                    project_profit,
                    scatter_count,
                    scatter_profit,
                    fund_amount,
                    fund_profit,
                    card_count,
                    card_profit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (fiscal_year, start_date, end_date) DO UPDATE SET
                    label = excluded.label,
                    project_count = excluded.project_count,
                    project_profit = excluded.project_profit,
                    scatter_count = excluded.scatter_count,
                    scatter_profit = excluded.scatter_profit,
                    fund_amount = excluded.fund_amount,
                    fund_profit = excluded.fund_profit,
                    card_count = excluded.card_count,
                    card_profit = excluded.card_profit
                """,
                (
                    (
                        week.fiscal_year,
                        week.period.start.isoformat(),
                        week.period.end.isoformat(),
                        week.period.label,
                        week.metrics.project_count,
                        str(week.metrics.project_profit),
                        week.metrics.scatter_count,
                        str(week.metrics.scatter_profit),
                        str(week.metrics.fund_amount),
                        str(week.metrics.fund_profit),
                        week.metrics.card_count,
                        str(week.metrics.card_profit),
                    )
                    for week in weeks
                ),
            )
            if owns_connection:
                active_connection.commit()
        except Exception:
            if owns_connection:
                active_connection.rollback()
            raise
        finally:
            if owns_connection:
                active_connection.close()

    def load_weeks(self, fiscal_year: int) -> list[WeekSnapshot]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    fiscal_year,
                    start_date,
                    end_date,
                    label,
                    project_count,
                    project_profit,
                    scatter_count,
                    scatter_profit,
                    fund_amount,
                    fund_profit,
                    card_count,
                    card_profit
                FROM week_snapshots
                WHERE fiscal_year = ?
                ORDER BY start_date ASC
                """,
                (fiscal_year,),
            ).fetchall()
        finally:
            connection.close()

        return [
            WeekSnapshot(
                fiscal_year=row[0],
                period=ReportingPeriod(
                    start=date.fromisoformat(row[1]),
                    end=date.fromisoformat(row[2]),
                    label=row[3],
                ),
                metrics=PeriodMetrics(
                    project_count=row[4],
                    project_profit=Decimal(row[5]),
                    scatter_count=row[6],
                    scatter_profit=Decimal(row[7]),
                    fund_amount=Decimal(row[8]),
                    fund_profit=Decimal(row[9]),
                    card_count=row[10],
                    card_profit=Decimal(row[11]),
                ),
            )
            for row in rows
        ]

    def save_generation(
        self,
        fiscal_year: int,
        generated_at: datetime,
        baseline_version: str,
        funds: dict[str, object],
        operations: dict[str, object],
        connection: sqlite3.Connection | None = None,
    ) -> None:
        funds_summary = json.dumps(funds, ensure_ascii=False, sort_keys=True)
        operations_summary = json.dumps(operations, ensure_ascii=False, sort_keys=True)
        owns_connection = connection is None
        active_connection = self._connect() if owns_connection else connection
        assert active_connection is not None
        try:
            active_connection.execute(
                """
                INSERT INTO generation_runs (
                    fiscal_year,
                    generated_at,
                    baseline_version,
                    funds_summary,
                    operations_summary
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    fiscal_year,
                    generated_at.isoformat(),
                    baseline_version,
                    funds_summary,
                    operations_summary,
                ),
            )
            if owns_connection:
                active_connection.commit()
        except Exception:
            if owns_connection:
                active_connection.rollback()
            raise
        finally:
            if owns_connection:
                active_connection.close()

    def latest_generation(self, fiscal_year: int) -> dict[str, object] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT generated_at, baseline_version, funds_summary, operations_summary
                FROM generation_runs
                WHERE fiscal_year = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (fiscal_year,),
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None
        return {
            "generated_at": row[0],
            "baseline_version": row[1],
            "funds": json.loads(row[2]),
            "operations": json.loads(row[3]),
        }
