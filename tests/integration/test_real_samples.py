import hashlib
import os
from datetime import date
from pathlib import Path

import pytest

from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService

SAMPLE_DIR = os.getenv("LEDGER_REPORTER_SAMPLE_DIR")
pytestmark = pytest.mark.skipif(not SAMPLE_DIR, reason="需要本地真实样例路径")

SOURCE_NAMES = (
    "AB台账-线上版(1).xlsx",
    "台账交接(1).xlsx",
    "需求(1).xlsx",
)


def _fingerprint(path: Path) -> tuple[int, int, str]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return stat.st_size, stat.st_mtime_ns, digest.hexdigest()


def test_real_samples_generate_latest_complete_period_without_source_changes(
    tmp_path: Path,
) -> None:
    root = Path(SAMPLE_DIR or "")
    paths = {name: root / name for name in SOURCE_NAMES}
    before = {name: _fingerprint(path) for name, path in paths.items()}

    service = ReportService(HistoryRepository(tmp_path / "history.sqlite3"))
    bundle = service.generate(
        paths["AB台账-线上版(1).xlsx"],
        paths["台账交接(1).xlsx"],
        date(2026, 8, 10),
    )

    assert (bundle.latest_period.start, bundle.latest_period.end) == (
        date(2026, 8, 1),
        date(2026, 8, 6),
    )
    assert bundle.baseline_rows[-1]["label"] == "W5（24-31）"
    assert {name: _fingerprint(path) for name, path in paths.items()} == before
