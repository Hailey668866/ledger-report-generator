from PySide6.QtWidgets import QTableWidget

from ledger_reporter.ui.fonts import BUNDLED_FONT_FAMILY
from ledger_reporter.ui.preview_dialog import PreviewDialog


def test_preview_dialog_matches_approved_collapsed_preview(qtbot, report_bundle) -> None:
    dialog = PreviewDialog(report_bundle)
    qtbot.addWidget(dialog)

    assert dialog.objectName() == "previewDialog"
    assert dialog.font().family() == BUNDLED_FONT_FAMILY
    assert dialog.title_label.text() == "报表预览"
    assert dialog.close_button.text() == ""
    assert dialog.close_button.toolTip() == "关闭"
    assert [dialog.tabs.tabText(index) for index in range(dialog.tabs.count())] == [
        "经营汇总",
        "自营项目周报",
    ]
    assert dialog.findChildren(QTableWidget)


def test_preview_close_button_rejects_dialog(qtbot, report_bundle) -> None:
    dialog = PreviewDialog(report_bundle)
    qtbot.addWidget(dialog)

    with qtbot.waitSignal(dialog.rejected):
        dialog.close_button.click()
