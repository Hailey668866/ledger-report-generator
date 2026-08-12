from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
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
        self.setWindowTitle("报表预览")
        self.resize(1120, 720)
        self.setMinimumSize(760, 520)
        self.tabs = QTabWidget()

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
                font = item.font()
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

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)
