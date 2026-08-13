from pathlib import Path

from PySide6.QtGui import QFont

from ledger_reporter.app_paths import resource_path
from ledger_reporter.ui.fonts import BUNDLED_FONT_FAMILY, ui_font, ui_font_family


def test_bundled_chinese_font_and_license_are_packaged_resources() -> None:
    font_path = resource_path("NotoSansSC-Variable.ttf")
    license_path = resource_path("NotoSansSC-OFL.txt")

    assert font_path.is_file()
    assert font_path.stat().st_size > 10_000_000
    assert license_path.is_file()
    assert "SIL OPEN FONT LICENSE" in license_path.read_text(encoding="utf-8")


def test_ui_font_prefers_the_bundled_noto_family(qapp) -> None:
    ui_font_family.cache_clear()

    assert ui_font_family() == BUNDLED_FONT_FAMILY == "Noto Sans SC"
    font = ui_font(10)
    assert isinstance(font, QFont)
    assert font.family() == BUNDLED_FONT_FAMILY


def test_font_resource_path_cannot_escape_resources() -> None:
    assert Path(resource_path("NotoSansSC-Variable.ttf")).parent.name == "resources"
