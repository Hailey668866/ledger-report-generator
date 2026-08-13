from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)


class SourcePicker(QWidget):
    path_changed = Signal(object)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("sourcePicker")
        self.setMinimumHeight(64)
        self._path: Path | None = None
        self.icon_label = QLabel(title[:1])
        self.icon_label.setObjectName("sourceIcon")
        self.icon_label.setFixedSize(38, 38)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("sourceTitle")
        self.label = QLabel("尚未选择 XLSX 文件")
        self.label.setObjectName("sourcePath")
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.button = QPushButton("选择文件")
        self.button.setObjectName("secondaryButton")
        self.button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.button.clicked.connect(self.choose_file)

        copy_layout = QVBoxLayout()
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(3)
        copy_layout.addWidget(self.title_label)
        copy_layout.addWidget(self.label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(11)
        layout.addWidget(self.icon_label)
        layout.addLayout(copy_layout, 1)
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
