import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from ledger_reporter import __version__
from ledger_reporter.app_paths import app_cache_dir, app_data_dir
from ledger_reporter.io.source_settings import load_source_settings
from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService
from ledger_reporter.ui.main_window import MainWindow


def _startup_error_message(history_path: Path | None, error: Exception) -> str:
    location = str(history_path) if history_path is not None else "应用数据目录"
    detail = str(error) or error.__class__.__name__
    return (
        "无法打开应用内部历史数据。\n\n"
        f"历史文件：{location}\n\n"
        "请在 Finder 中使用“前往文件夹”定位该文件，将 history.sqlite3 "
        "改名为 history.sqlite3.backup，然后重新打开应用。\n"
        "程序不会自动删除原历史文件；已导出的 Excel/PNG 不受影响。\n\n"
        f"错误详情：{detail}"
    )


def _show_startup_error(history_path: Path | None, error: Exception) -> None:
    QMessageBox.critical(
        None,
        "台账报表生成器无法启动",
        _startup_error_message(history_path, error),
    )


def _source_settings_error_message(settings_path: Path, error: Exception) -> str:
    detail = str(error) or error.__class__.__name__
    return (
        "无法读取数据源字段设置。\n\n"
        f"设置文件：{settings_path}\n\n"
        "请在 Finder 中使用“前往文件夹”定位该文件，将 source-fields.json "
        "改名为 source-fields.json.backup，然后重新启动应用以恢复默认字段设置。\n"
        "程序不会自动删除原设置文件；历史数据和已导出的 Excel/PNG 均不受影响。\n\n"
        f"错误详情：{detail}"
    )


def _show_source_settings_error(settings_path: Path, error: Exception) -> None:
    QMessageBox.critical(
        None,
        "台账报表生成器无法启动",
        _source_settings_error_message(settings_path, error),
    )


def _application_startup_error_message(error: Exception) -> str:
    detail = str(error) or error.__class__.__name__
    return (
        "应用界面初始化失败。\n\n"
        "请先重新启动 Mac 后再试；如果问题仍然存在，请重新安装应用。\n"
        "不要移动或删除历史文件；已导出的 Excel/PNG 不受影响。\n\n"
        f"错误详情：{detail}"
    )


def _show_application_startup_error(error: Exception) -> None:
    QMessageBox.critical(
        None,
        "台账报表生成器无法启动",
        _application_startup_error_message(error),
    )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("台账报表生成器")
    app.setOrganizationName("Ledger Reporter")
    history_path: Path | None = None
    try:
        data_dir = app_data_dir()
        history_path = data_dir / "history.sqlite3"
        repository = HistoryRepository(history_path)
    except Exception as exc:  # noqa: BLE001 - packaged app must surface startup failures.
        _show_startup_error(history_path, exc)
        return 1
    settings_path = data_dir / "source-fields.json"
    try:
        settings = load_source_settings(settings_path)
    except Exception as exc:  # noqa: BLE001 - packaged app must surface startup failures.
        _show_source_settings_error(settings_path, exc)
        return 1
    try:
        service = ReportService(repository, settings)
        window = MainWindow(
            service,
            settings_path,
            current_version=__version__,
            update_cache_dir=app_cache_dir() / "updates",
            auto_check_updates=sys.platform == "darwin",
        )
        window.resize(820, 520)
        window.show()
        smoke_ready_file = os.getenv("LEDGER_REPORTER_SMOKE_READY_FILE")
        if smoke_ready_file:
            app.processEvents()
            marker = Path(smoke_ready_file)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("ready\n", encoding="ascii")
    except Exception as exc:  # noqa: BLE001 - packaged app must surface startup failures.
        _show_application_startup_error(exc)
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
