from datetime import date
from decimal import Decimal

from ledger_reporter.services.baseline import load_fy2026_baseline


def test_loads_fy2026_frozen_baseline() -> None:
    baseline = load_fy2026_baseline()

    assert baseline.version == "fy2026-requirement-2026-08-10-v1"
    assert baseline.fiscal_year == 2026
    assert baseline.frozen_through == date(2026, 7, 31)
    assert len(baseline.rows) == 26
    assert baseline.rows[0]["label"] == "Q1(26.4-26.6)"
    assert baseline.rows[-1]["label"] == "W5（24-31）"
    assert baseline.rows[-1]["values"][:6] == [
        168,
        Decimal("-729734.851957015"),
        9,
        Decimal("14016.4289426375"),
        Decimal("85644.23"),
        Decimal("729.266484493151"),
    ]
    assert isinstance(baseline.rows[-1]["values"][1], Decimal)


def test_baseline_loading_does_not_depend_on_current_working_directory(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)

    baseline = load_fy2026_baseline()

    assert baseline.frozen_through == date(2026, 7, 31)
