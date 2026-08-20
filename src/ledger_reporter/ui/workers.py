from datetime import date
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot


class GenerationWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: object, funds: Path, operations: Path, today: date) -> None:
        super().__init__()
        self.service = service
        self.funds = funds
        self.operations = operations
        self.today = today

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.generate(self.funds, self.operations, self.today)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports service failures.
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


class ValidationWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service: object, funds: Path, operations: Path, today: date) -> None:
        super().__init__()
        self.service = service
        self.funds = funds
        self.operations = operations
        self.today = today

    @Slot()
    def run(self) -> None:
        try:
            result = self.service.inspect_sources(self.funds, self.operations, self.today)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports service failures.
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(result)
        finally:
            self.finished.emit()


class UpdateCheckWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, checker: object, current_version: str) -> None:
        super().__init__()
        self.checker = checker
        self.current_version = current_version

    @Slot()
    def run(self) -> None:
        try:
            update = self.checker(self.current_version)
        except Exception as exc:  # noqa: BLE001 - worker boundary reports update failures.
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(update)
        finally:
            self.finished.emit()


class UpdateDownloadWorker(QObject):
    progress = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, downloader: object, update: object, cache_dir: Path) -> None:
        super().__init__()
        self.downloader = downloader
        self.update = update
        self.cache_dir = cache_dir
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @Slot()
    def run(self) -> None:
        try:
            path = self.downloader(
                self.update,
                self.cache_dir,
                progress=self.progress.emit,
                cancelled=self._cancelled.is_set,
            )
        except Exception as exc:  # noqa: BLE001 - worker boundary reports update failures.
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.succeeded.emit(path)
        finally:
            self.finished.emit()
