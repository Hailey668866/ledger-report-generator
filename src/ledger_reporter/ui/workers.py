from datetime import date
from pathlib import Path

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
