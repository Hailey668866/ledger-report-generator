import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger_reporter.app_paths import resource_path


@dataclass(frozen=True, slots=True)
class Baseline:
    version: str
    fiscal_year: int
    frozen_through: date
    rows: tuple[dict[str, object], ...]


def load_fy2026_baseline() -> Baseline:
    payload = json.loads(
        resource_path("fy2026_baseline.json").read_text(encoding="utf-8"),
        parse_float=Decimal,
    )
    return Baseline(
        version=payload["version"],
        fiscal_year=int(payload["fiscal_year"]),
        frozen_through=date.fromisoformat(payload["frozen_through"]),
        rows=tuple(payload["rows"]),
    )
