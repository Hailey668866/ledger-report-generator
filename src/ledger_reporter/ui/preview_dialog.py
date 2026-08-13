from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ledger_reporter.domain.models import ReportBundle
from ledger_reporter.exporters.png import _format
from ledger_reporter.presentation.builders import build_tables
from ledger_reporter.presentation.theme import STYLES
from ledger_reporter.ui.fonts import ui_font

PREVIEW_STYLESHEET = """
QDialog#previewDialog {
    background: #f6f8f6;
    color: #26372e;
}
QFrame#previewHeader {
    background: #ffffff;
    border-bottom: 1px solid #dfe5e1;
}
QLabel#previewTitle {
    color: #23362c;
    font-size: 15px;
    font-weight: 700;
}
QPushButton#previewCloseButton {
    width: 30px;
    height: 30px;
    border: 1px solid #ced8d2;
    border-radius: 5px;
    background: #ffffff;
}
QPushButton#previewCloseButton:hover {
    background: #f0f5f2;
    border-color: #9eb2a7;
}
QTabWidget#previewTabs::pane {
    border: 1px solid #d5ddd8;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    min-height: 30px;
    padding: 0 14px;
    margin-right: 4px;
    border: 0;
    border-radius: 4px;
    background: #edf1ef;
    color: #637168;
}
QTabBar::tab:selected {
    background: #dff0e5;
    color: #176b40;
    font-weight: 700;
}
QTableWidget#previewTable {
    background: #ffffff;
    border: 0;
    gridline-color: #d5ddd8;
    color: #3f5047;
    selection-background-color: transparent;
}
QTableWidget#previewTable QTableCornerButton::section {
    border: 0;
}
"""


def _alignment(name: str) -> Qt.AlignmentFlag:
    horizontal = {
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
        "left": Qt.AlignmentFlag.AlignLeft,
    }[name]
    return horizontal | Qt.AlignmentFlag.AlignVCenter


class PreviewDialog(QDialog):
    def __init__(self, bundle: ReportBundle, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewDialog")
        self.setWindowTitle("报表预览")
        self.resize(1120, 720)
        self.setMinimumSize(760, 520)
        self.setFont(ui_font(10))
        self.setStyleSheet(PREVIEW_STYLESHEET)

        header = QFrame()
        header.setObjectName("previewHeader")
        header.setFixedHeight(58)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 0, 18, 0)
        self.title_label = QLabel("报表预览")
        self.title_label.setObjectName("previewTitle")
        self.close_button = QPushButton()
        self.close_button.setObjectName("previewCloseButton")
        self.close_button.setToolTip("关闭")
        self.close_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton)
        )
        self.close_button.clicked.connect(self.reject)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.close_button)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("previewTabs")

        for table in build_tables(bundle):
            rows = max(cell.row for cell in table.cells)
            columns = max(cell.column for cell in table.cells)
            widget = QTableWidget(rows, columns)
            widget.setObjectName("previewTable")
            widget.horizontalHeader().hide()
            widget.verticalHeader().hide()
            widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            widget.setAlternatingRowColors(False)
            for cell in table.cells:
                item = QTableWidgetItem(_format(cell.value, cell.number_format))
                style = STYLES[cell.style]
                item.setBackground(QColor("#" + style["fill"]))
                item.setForeground(QColor("#" + style.get("font", "000000")))
                font = ui_font(9)
                font.setBold(bool(style["bold"]))
                item.setFont(font)
                item.setTextAlignment(_alignment(str(style["align"])))
                widget.setItem(cell.row - 1, cell.column - 1, item)
            for merge in table.merges:
                widget.setSpan(
                    merge.start_row - 1,
                    merge.start_column - 1,
                    merge.end_row - merge.start_row + 1,
                    merge.end_column - merge.start_column + 1,
                )
            for index, width in enumerate(table.column_widths):
                widget.setColumnWidth(index, max(72, int(width * 8)))
            for index, height in enumerate(table.row_heights):
                widget.setRowHeight(index, max(28, int(height * 1.35)))
            self.tabs.addTab(widget, table.name)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 16, 18, 18)
        body_layout.addWidget(self.tabs, 1)
        layout.addWidget(body, 1)
