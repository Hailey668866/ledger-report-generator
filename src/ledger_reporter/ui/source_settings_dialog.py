from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ledger_reporter.io.source_settings import (
    DEFAULT_SOURCE_SETTINGS,
    XLSX_MAX_ROW,
    SourceSettings,
)


class SourceSettingsDialog(QDialog):
    def __init__(self, current: SourceSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected_settings: SourceSettings | None = None
        self.setWindowTitle("字段设置")
        self.resize(560, 520)
        self.setMinimumSize(500, 460)

        self.funds_sheet = QLineEdit()
        self.funds_header_row = QSpinBox()
        self.funds_channel = QLineEdit()
        self.funds_payment_date = QLineEdit()
        self.funds_amount = QLineEdit()
        self.funds_operation_fee = QLineEdit()
        self.operations_sheet = QLineEdit()
        self.operations_header_row = QSpinBox()
        self.operations_bill_no = QLineEdit()
        self.operations_project_type = QLineEdit()
        self.operations_destination = QLineEdit()
        self.operations_departure = QLineEdit()
        self.operations_supplier = QLineEdit()
        self.operations_receivable = QLineEdit()
        self.operations_gross_profit = QLineEdit()
        for control in (self.funds_header_row, self.operations_header_row):
            control.setRange(1, XLSX_MAX_ROW)
        self._populate(current)

        self.tabs = QTabWidget()
        funds_page = QWidget()
        funds_form = QFormLayout(funds_page)
        funds_form.addRow("工作表名称", self.funds_sheet)
        funds_form.addRow("表头行", self.funds_header_row)
        funds_form.addRow("渠道名称", self.funds_channel)
        funds_form.addRow("付款日期", self.funds_payment_date)
        funds_form.addRow("付款金额", self.funds_amount)
        funds_form.addRow("应收操作费", self.funds_operation_fee)
        self.tabs.addTab(funds_page, "资金台账")

        operations_page = QWidget()
        operations_form = QFormLayout(operations_page)
        operations_form.addRow("工作表名称", self.operations_sheet)
        operations_form.addRow("表头行", self.operations_header_row)
        operations_form.addRow("提单号", self.operations_bill_no)
        operations_form.addRow("项目类型", self.operations_project_type)
        operations_form.addRow("目的口岸", self.operations_destination)
        operations_form.addRow("预计起飞时间", self.operations_departure)
        operations_form.addRow("B1 供应商", self.operations_supplier)
        operations_form.addRow("预估总应收", self.operations_receivable)
        operations_form.addRow("预估毛利润", self.operations_gross_profit)
        self.tabs.addTab(operations_page, "运营台账")

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Reset
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        self.restore_button = self.buttons.button(QDialogButtonBox.StandardButton.Reset)
        self.cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.restore_button.setText("恢复默认")
        self.restore_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.cancel_button.setText("取消")
        self.save_button.setText("保存")
        self.restore_button.clicked.connect(self.restore_defaults)
        self.buttons.rejected.connect(self.reject)
        self.buttons.accepted.connect(self.accept_settings)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(16)
        layout.addWidget(self.tabs)
        layout.addWidget(self.buttons)

    def _populate(self, settings: SourceSettings) -> None:
        self.funds_sheet.setText(settings.funds_sheet)
        self.funds_header_row.setValue(settings.funds_header_row)
        self.funds_channel.setText(settings.funds_channel)
        self.funds_payment_date.setText(settings.funds_payment_date)
        self.funds_amount.setText(settings.funds_amount)
        self.funds_operation_fee.setText(settings.funds_operation_fee)
        self.operations_sheet.setText(settings.operations_sheet)
        self.operations_header_row.setValue(settings.operations_header_row)
        self.operations_bill_no.setText(settings.operations_bill_no)
        self.operations_project_type.setText(settings.operations_project_type)
        self.operations_destination.setText(settings.operations_destination)
        self.operations_departure.setText(settings.operations_departure)
        self.operations_supplier.setText(settings.operations_supplier)
        self.operations_receivable.setText(settings.operations_receivable)
        self.operations_gross_profit.setText(settings.operations_gross_profit)

    def restore_defaults(self) -> None:
        self._populate(DEFAULT_SOURCE_SETTINGS)

    def values(self) -> SourceSettings:
        settings = SourceSettings(
            funds_sheet=self.funds_sheet.text(),
            funds_header_row=self.funds_header_row.value(),
            funds_channel=self.funds_channel.text(),
            funds_payment_date=self.funds_payment_date.text(),
            funds_amount=self.funds_amount.text(),
            funds_operation_fee=self.funds_operation_fee.text(),
            operations_sheet=self.operations_sheet.text(),
            operations_header_row=self.operations_header_row.value(),
            operations_bill_no=self.operations_bill_no.text(),
            operations_project_type=self.operations_project_type.text(),
            operations_destination=self.operations_destination.text(),
            operations_departure=self.operations_departure.text(),
            operations_supplier=self.operations_supplier.text(),
            operations_receivable=self.operations_receivable.text(),
            operations_gross_profit=self.operations_gross_profit.text(),
        )
        settings.validate()
        return settings

    def accept_settings(self) -> None:
        self.selected_settings = None
        try:
            settings = self.values()
        except ValueError as error:
            QMessageBox.warning(self, "无法保存字段设置", str(error))
            return
        self.selected_settings = settings
        self.accept()
