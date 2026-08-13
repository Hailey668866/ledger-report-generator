from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QStyle, QWidget


class SourcePicker(QWidget):
    path_changed = Signal(object)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._path: Path | None = None
        self.title_label = QLabel(title)
        self.title_label.setObjectName("sourceTitle")
        self.title_label.setFixedWidth(92)
        self.label = QLabel("未选择")
        self.label.setObjectName("sourcePath")
        self.button = QPushButton("选择")
        self.button.setObjectName("secondaryButton")
        self.button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.button.clicked.connect(self.choose_file)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.title_label)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.button)

    @property
    def path(self) -> Path | None:
        return self._path

    def set_path(self, path: Path) -> None:
        self._path = Path(path)
        self.label.setText(self._path.name)
        self.label.setToolTip(str(self._path))
        self.path_changed.emit(self._path)

    def choose_file(self) -> None:
        value, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "选择 XLSX",
            "",
            "Excel 工作簿 (*.xlsx)",
        )
        if value:
            self.set_path(Path(value))

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".xlsx"):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1:
            self.set_path(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()
