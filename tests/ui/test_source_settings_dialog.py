from dataclasses import replace

from PySide6.QtWidgets import QDialogButtonBox

from ledger_reporter.io.source_settings import DEFAULT_SOURCE_SETTINGS
from ledger_reporter.ui.source_settings_dialog import SourceSettingsDialog


def test_dialog_has_three_plain_navigation_pages(qtbot) -> None:
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)

    assert [dialog.navigation.item(index).text() for index in range(3)] == [
        "数据源设置",
        "经营汇总",
        "自营项目周报",
    ]
    assert dialog.pages.count() == 3
    assert dialog.windowTitle() == "字段与计算设置"


def test_data_source_controls_are_initialized(qtbot) -> None:
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)

    assert dialog.funds_sheet.text() == "资金散板汇总{年份}"
    assert dialog.funds_header_row.value() == 1
    assert dialog.operations_sheet.text() == "台账明细"
    assert dialog.operations_header_row.value() == 1


def test_summary_selector_covers_every_output(qtbot) -> None:
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)

    assert [
        dialog.summary_selector.itemText(index) for index in range(dialog.summary_selector.count())
    ] == [
        "项目订单数量",
        "项目预估利润",
        "散采订单数量",
        "散采预估利润",
        "资金放款金额",
        "资金预估利润",
        "卡转订单 / 利润",
        "合计利润",
    ]


def test_summary_output_fields_are_saved_independently(qtbot) -> None:
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)

    dialog.summary_editors["project_count"].date_field.setText("数量日期")
    dialog.summary_editors["project_profit"].date_field.setText("利润日期")

    settings = dialog.values()

    assert settings.project_count.date_field == "数量日期"
    assert settings.project_profit.date_field == "利润日期"


def test_weekly_page_includes_all_rows_and_independent_metrics(qtbot) -> None:
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)

    assert dialog.business_selector.count() == 12
    assert dialog.business_selector.itemText(0) == "WWP"
    assert dialog.business_selector.itemText(10) == "散采"
    assert dialog.business_selector.itemText(11) == "销售额合计"
    first = dialog.business_editors[0]
    first.count.date_field.setText("数量日期")
    first.profit.date_field.setText("利润日期")
    first.margin.date_field.setText("利润率日期")

    settings = dialog.values()

    assert settings.business_rows[0].count.date_field == "数量日期"
    assert settings.business_rows[0].profit.date_field == "利润日期"
    assert settings.business_rows[0].margin.date_field == "利润率日期"


def test_restore_defaults_repopulates_all_sections(qtbot) -> None:
    dialog = SourceSettingsDialog(replace(DEFAULT_SOURCE_SETTINGS, funds_sheet="其他资金表"))
    qtbot.addWidget(dialog)
    dialog.summary_editors["project_count"].date_field.setText("其他日期")

    dialog.restore_defaults()

    assert dialog.funds_sheet.text() == DEFAULT_SOURCE_SETTINGS.funds_sheet
    assert dialog.summary_editors["project_count"].date_field.text() == "预计起飞时间"


def test_save_accepts_and_cancel_rejects(qtbot) -> None:
    accepted = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(accepted)
    accepted.save_button.click()
    assert accepted.result() == accepted.DialogCode.Accepted
    assert accepted.selected_settings == DEFAULT_SOURCE_SETTINGS

    cancelled = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(cancelled)
    cancelled.cancel_button.click()
    assert cancelled.result() == cancelled.DialogCode.Rejected
    assert cancelled.selected_settings is None


def test_buttons_use_chinese_text(qtbot) -> None:
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)

    assert dialog.restore_button.text() == "恢复默认"
    assert dialog.cancel_button.text() == "取消"
    assert dialog.save_button.text() == "保存设置"
    assert dialog.buttons.standardButtons() & QDialogButtonBox.StandardButton.Save
