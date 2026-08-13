from functools import lru_cache

from PySide6.QtGui import QFont, QFontDatabase

from ledger_reporter.app_paths import resource_path

BUNDLED_FONT_FAMILY = "Noto Sans SC"
_SYSTEM_FALLBACKS = ("PingFang SC", "Microsoft YaHei", "Microsoft YaHei UI")


@lru_cache(maxsize=1)
def ui_font_family() -> str | None:
    font_id = QFontDatabase.addApplicationFont(str(resource_path("NotoSansSC-Variable.ttf")))
    if font_id >= 0:
        families = QFontDatabase.applicationFontFamilies(font_id)
        if BUNDLED_FONT_FAMILY in families:
            return BUNDLED_FONT_FAMILY
        if families:
            return families[0]

    available = set(QFontDatabase.families())
    return next((family for family in _SYSTEM_FALLBACKS if family in available), None)


def ui_font(point_size: int = 10) -> QFont:
    family = ui_font_family()
    return QFont(family, point_size) if family else QFont()
