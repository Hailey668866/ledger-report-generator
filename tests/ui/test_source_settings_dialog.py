from dataclasses import fields, replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel

from ledger_reporter.io.source_settings import DEFAULT_SOURCE_SETTINGS, SourceSettings
from ledger_reporter.ui.source_settings_dialog import SourceSettingsDialog


CUSTOM_SETTINGS = SourceSettings(
    funds_sheet="资金数据{年份}",
    funds_header_row=3,
    funds_channel="渠道",
    funds_payment_date="付款日",
    funds_amount="实付金额",
    funds_operation_fee="操作费",
    operations_sheet="运营数据",
    operations_header_row=4,
    operations_bill_no="运单号",
    operations_project_type="业务类型",
    operations_destination="到达港",
    operations_departure="起飞日",
    operations_supplier="供应商",
    operations_receivable="总应收",
    operations_gross_profit="毛利润",
)


def _control_value(dialog: SourceSettingsDialog, field_name: str) -> str | int:
    control = getattr(dialog, field_name)
    if field_name.endswith("_header_row"):
        return control.value()
    return control.text()


def test_dialog_has_two_plain_form_tabs(qtbot) -> None:
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "字段设置"
    assert dialog.tabs.count() == 2
    assert [dialog.tabs.tabText(index) for index in range(2)] == ["资金台账", "运营台账"]
    assert isinstance(dialog.tabs.widget(0).layout(), QFormLayout)
    assert isinstance(dialog.tabs.widget(1).layout(), QFormLayout)
    assert [label.text() for label in dialog.tabs.widget(0).findChildren(QLabel)] == [
        "工作表名称",
        "表头行",
        "渠道名称",
        "付款日期",
        "付款金额",
        "应收操作费",
    ]
    assert [label.text() for label in dialog.tabs.widget(1).findChildren(QLabel)] == [
        "工作表名称",
        "表头行",
        "提单号",
        "项目类型",
        "目的口岸",
        "预计起飞时间",
        "B1 供应商",
        "预估总应收",
        "预估毛利润",
    ]
    assert dialog.findChildren(QLabel, "description") == []
    assert dialog.findChildren(QLabel, "help") == []
    assert dialog.width() <= 700
    assert dialog.height() <= 700


def test_all_controls_are_initialized_from_current_settings(qtbot) -> None:
    dialog = SourceSettingsDialog(CUSTOM_SETTINGS)
    qtbot.addWidget(dialog)

    assert {field.name: _control_value(dialog, field.name) for field in fields(SourceSettings)} == {
        field.name: getattr(CUSTOM_SETTINGS, field.name) for field in fields(SourceSettings)
    }


def test_values_round_trips_all_settings(qtbot) -> None:
    dialog = SourceSettingsDialog(CUSTOM_SETTINGS)
    qtbot.addWidget(dialog)

    assert dialog.values() == CUSTOM_SETTINGS


def test_large_valid_header_rows_are_not_truncated(qtbot) -> None:
    current = replace(
        DEFAULT_SOURCE_SETTINGS,
        funds_header_row=10_000,
        operations_header_row=1_048_576,
    )
    dialog = SourceSettingsDialog(current)
    qtbot.addWidget(dialog)

    assert dialog.funds_header_row.value() == 10_000
    assert dialog.operations_header_row.value() == 1_048_576
    assert dialog.values() == current


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("operations_bill_no", "", "非空字符串"),
        ("funds_payment_date", "渠道名称", "同一工作表中的业务字段名称不可重复"),
    ],
)
def test_invalid_settings_warn_and_keep_dialog_open(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    value: str,
    message: str,
) -> None:
    warnings: list[tuple[str, str]] = []
    dialog = SourceSettingsDialog(DEFAULT_SOURCE_SETTINGS)
    qtbot.addWidget(dialog)
    getattr(dialog, field_name).setText(value)
    monkeypatch.setattr(
        "ledger_reporter.ui.source_settings_dialog.QMessageBox.warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )

    dialog.accept_settings()

    assert len(warnings) == 1
    assert warnings[0][0] == "无法保存字段设置"
    assert message in warnings[0][1]
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.selected_settings is None


def test_save_accepts_dialog_and_exposes_selected_settings(qtbot) -> None:
    dialog = SourceSettingsDialog(CUSTOM_SETTINGS)
    qtbot.addWidget(dialog)

    dialog.save_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.selected_settings == CUSTOM_SETTINGS


def test_restore_defaults_repopulates_every_control_without_closing(qtbot) -> None:
    dialog = SourceSettingsDialog(CUSTOM_SETTINGS)
    qtbot.addWidget(dialog)

    dialog.restore_button.click()

    assert {field.name: _control_value(dialog, field.name) for field in fields(SourceSettings)} == {
        field.name: getattr(DEFAULT_SOURCE_SETTINGS, field.name) for field in fields(SourceSettings)
    }
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.selected_settings is None


def test_cancel_rejects_without_selecting_settings(qtbot) -> None:
    dialog = SourceSettingsDialog(CUSTOM_SETTINGS)
    qtbot.addWidget(dialog)
    dialog.show()

    with qtbot.waitSignal(dialog.rejected):
        qtbot.mouseClick(dialog.cancel_button, Qt.MouseButton.LeftButton)

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.selected_settings is None


def test_buttons_use_chinese_text_and_header_rows_start_at_one(qtbot) -> None:
    dialog = SourceSettingsDialog(replace(DEFAULT_SOURCE_SETTINGS, funds_header_row=2))
    qtbot.addWidget(dialog)

    assert dialog.restore_button.text() == "恢复默认"
    assert dialog.cancel_button.text() == "取消"
    assert dialog.save_button.text() == "保存"
    assert not dialog.restore_button.icon().isNull()
    assert dialog.funds_header_row.minimum() == 1
    assert dialog.operations_header_row.minimum() == 1
