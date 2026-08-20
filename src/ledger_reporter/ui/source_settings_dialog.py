from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ledger_reporter.io.source_settings import (
    DEFAULT_SOURCE_SETTINGS,
    SCHEMA_VERSION,
    XLSX_MAX_ROW,
    AggregateRule,
    BusinessRowRule,
    BusinessTotalRule,
    ChannelRate,
    FilterRule,
    FundProfitRule,
    RatioRule,
    SourceSettings,
)


class _FilterEditor:
    def __init__(self, layout: QFormLayout, index: int) -> None:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        self.field = QLineEdit()
        self.field.setPlaceholderText("字段名称")
        self.value = QLineEdit()
        self.value.setPlaceholderText("筛选值")
        row_layout.addWidget(self.field)
        row_layout.addWidget(self.value)
        layout.addRow(f"筛选条件 {index}", row)
        self.exclude = False

    def populate(self, rule: FilterRule | None) -> None:
        self.field.setText(rule.field if rule else "")
        self.value.setText(rule.value if rule else "")
        self.exclude = rule.exclude if rule else False

    def rule(self) -> FilterRule:
        return FilterRule(self.field.text(), self.value.text(), self.exclude)


class AggregateEditor(QWidget):
    def __init__(self, value_label: str) -> None:
        super().__init__()
        layout = QFormLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(12)
        self.date_field = QLineEdit()
        self.value_field = QLineEdit()
        layout.addRow("周期日期字段", self.date_field)
        self.filters = [_FilterEditor(layout, index) for index in range(1, 4)]
        layout.addRow(value_label, self.value_field)

    def populate(self, rule: AggregateRule) -> None:
        self.date_field.setText(rule.date_field)
        self.value_field.setText(rule.value_field)
        for index, editor in enumerate(self.filters):
            editor.populate(rule.filters[index] if index < len(rule.filters) else None)

    def rule(self) -> AggregateRule:
        filters = tuple(editor.rule() for editor in self.filters)
        return AggregateRule(
            self.date_field.text(),
            self.value_field.text(),
            tuple(rule for rule in filters if rule.field.strip() or rule.value.strip()),
        )


class RatioEditor(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QFormLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(12)
        self.date_field = QLineEdit()
        self.numerator_field = QLineEdit()
        self.denominator_field = QLineEdit()
        layout.addRow("周期日期字段", self.date_field)
        self.filters = [_FilterEditor(layout, index) for index in range(1, 4)]
        layout.addRow("分子字段", self.numerator_field)
        layout.addRow("分母字段", self.denominator_field)

    def populate(self, rule: RatioRule) -> None:
        self.date_field.setText(rule.date_field)
        self.numerator_field.setText(rule.numerator_field)
        self.denominator_field.setText(rule.denominator_field)
        for index, editor in enumerate(self.filters):
            editor.populate(rule.filters[index] if index < len(rule.filters) else None)

    def rule(self) -> RatioRule:
        filters = tuple(editor.rule() for editor in self.filters)
        return RatioRule(
            self.date_field.text(),
            self.numerator_field.text(),
            self.denominator_field.text(),
            tuple(rule for rule in filters if rule.field.strip() or rule.value.strip()),
        )


class FundProfitEditor(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QFormLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setHorizontalSpacing(18)
        layout.setVerticalSpacing(12)
        self.date_field = QLineEdit()
        self.channel_field = QLineEdit()
        self.amount_field = QLineEdit()
        self.operation_fee_field = QLineEdit()
        layout.addRow("周期日期字段", self.date_field)
        layout.addRow("渠道字段", self.channel_field)
        layout.addRow("付款金额字段", self.amount_field)
        layout.addRow("操作费字段", self.operation_fee_field)
        self.channel_names = [QLineEdit(), QLineEdit()]
        self.channel_rates = [self._percent_box(), self._percent_box()]
        for index in range(2):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(self.channel_names[index], 2)
            row_layout.addWidget(self.channel_rates[index], 1)
            layout.addRow(f"资金渠道 {index + 1}", row)
        self.capital_cost = self._percent_box()
        self.term_days = QSpinBox()
        self.term_days.setRange(0, 36500)
        layout.addRow("资金成本率", self.capital_cost)
        layout.addRow("计息天数", self.term_days)

    @staticmethod
    def _percent_box() -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setRange(0, 100)
        control.setDecimals(4)
        control.setSuffix("%")
        return control

    def populate(self, rule: FundProfitRule) -> None:
        self.date_field.setText(rule.date_field)
        self.channel_field.setText(rule.channel_field)
        self.amount_field.setText(rule.amount_field)
        self.operation_fee_field.setText(rule.operation_fee_field)
        for index in range(2):
            channel = (
                rule.channels[index] if index < len(rule.channels) else ChannelRate("", Decimal(0))
            )
            self.channel_names[index].setText(channel.name)
            self.channel_rates[index].setValue(float(channel.rate * 100))
        self.capital_cost.setValue(float(rule.capital_cost * 100))
        self.term_days.setValue(rule.term_days)

    def rule(self) -> FundProfitRule:
        channels = tuple(
            ChannelRate(name.text(), Decimal(str(rate.value())) / 100)
            for name, rate in zip(self.channel_names, self.channel_rates, strict=True)
        )
        return FundProfitRule(
            self.date_field.text(),
            self.channel_field.text(),
            self.amount_field.text(),
            self.operation_fee_field.text(),
            channels,
            Decimal(str(self.capital_cost.value())) / 100,
            self.term_days.value(),
        )


class BusinessEditor(QWidget):
    def __init__(self, rule: BusinessRowRule) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        display = QWidget()
        display_form = QFormLayout(display)
        display_form.setContentsMargins(18, 18, 18, 18)
        self.name = QLineEdit()
        self.cycle = QLineEdit()
        self.measured_rate = QLineEdit()
        display_form.addRow("业务名称", self.name)
        display_form.addRow("项目周期", self.cycle)
        display_form.addRow("利润率测算", self.measured_rate)
        self.count = AggregateEditor("计数字段")
        self.profit = AggregateEditor("求和字段")
        self.margin = RatioEditor()
        tabs = QTabWidget()
        tabs.addTab(display, "显示内容")
        tabs.addTab(self.count, "完成数量")
        tabs.addTab(self.profit, "预估利润")
        tabs.addTab(self.margin, "预估利润率")
        layout.addWidget(tabs)
        self.populate(rule)

    def populate(self, rule: BusinessRowRule) -> None:
        self.name.setText(rule.name)
        self.cycle.setText(rule.cycle)
        self.measured_rate.setText(rule.measured_rate)
        self.count.populate(rule.count)
        self.profit.populate(rule.profit)
        self.margin.populate(rule.margin)

    def rule(self) -> BusinessRowRule:
        return BusinessRowRule(
            self.name.text(),
            self.cycle.text(),
            self.measured_rate.text(),
            self.count.rule(),
            self.profit.rule(),
            self.margin.rule(),
        )


class BusinessTotalEditor(QWidget):
    def __init__(self, rule: BusinessTotalRule) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label_page = QWidget()
        label_form = QFormLayout(label_page)
        label_form.setContentsMargins(18, 18, 18, 18)
        self.label = QLineEdit()
        label_form.addRow("显示名称", self.label)
        self.sales = AggregateEditor("销售额字段")
        self.count = AggregateEditor("计数字段")
        self.profit = AggregateEditor("求和字段")
        self.margin = RatioEditor()
        tabs = QTabWidget()
        tabs.addTab(label_page, "显示内容")
        tabs.addTab(self.sales, "销售额合计")
        tabs.addTab(self.count, "完成数量")
        tabs.addTab(self.profit, "预估利润")
        tabs.addTab(self.margin, "预估利润率")
        layout.addWidget(tabs)
        self.populate(rule)

    def populate(self, rule: BusinessTotalRule) -> None:
        self.label.setText(rule.label)
        self.sales.populate(rule.sales)
        self.count.populate(rule.count)
        self.profit.populate(rule.profit)
        self.margin.populate(rule.margin)

    def rule(self) -> BusinessTotalRule:
        return BusinessTotalRule(
            self.label.text(),
            self.sales.rule(),
            self.count.rule(),
            self.profit.rule(),
            self.margin.rule(),
        )


class SourceSettingsDialog(QDialog):
    def __init__(self, current: SourceSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected_settings: SourceSettings | None = None
        self.setWindowTitle("字段与计算设置")
        self.resize(980, 700)
        self.setMinimumSize(820, 620)
        self.setStyleSheet(
            "QListWidget{background:#eef2f0;border:0;border-right:1px solid #d7ddda;padding:12px;}"
            "QListWidget::item{height:46px;padding:0 12px;border-radius:5px;}"
            "QListWidget::item:selected{background:#fff;color:#176b41;}"
            "QLineEdit,QSpinBox,QDoubleSpinBox,QComboBox{min-height:34px;border:1px solid #b9c5be;"
            "border-radius:4px;padding:0 8px;background:#fff;}"
            "QTabWidget::pane{border:1px solid #d7ddda;background:#fff;}"
        )

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(220)
        self.navigation.addItems(("数据源设置", "经营汇总", "自营项目周报"))
        self.pages = QStackedWidget()
        self.pages.addWidget(self._data_page())
        self.pages.addWidget(self._summary_page())
        self.pages.addWidget(self._business_page(current))
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Reset
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save
        )
        self.restore_button = self.buttons.button(QDialogButtonBox.StandardButton.Reset)
        self.cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.restore_button.setText("恢复默认")
        self.cancel_button.setText("取消")
        self.save_button.setText("保存设置")
        self.restore_button.clicked.connect(self.restore_defaults)
        self.buttons.rejected.connect(self.reject)
        self.buttons.accepted.connect(self.accept_settings)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self.navigation)
        content.addWidget(self.pages, 1)
        footer = QFrame()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 12, 18, 12)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self.buttons)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(content, 1)
        layout.addWidget(footer)
        self._populate(current)

    def _page(self, title: str, body: QWidget) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        heading = QLabel(title)
        heading.setStyleSheet("font-size:21px;font-weight:700;color:#1d2a24;")
        layout.addWidget(heading)
        layout.addWidget(body, 1)
        return page

    def _data_page(self) -> QWidget:
        body = QWidget()
        form = QFormLayout(body)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        self.funds_sheet = QLineEdit()
        self.funds_header_row = QSpinBox()
        self.operations_sheet = QLineEdit()
        self.operations_header_row = QSpinBox()
        for control in (self.funds_header_row, self.operations_header_row):
            control.setRange(1, XLSX_MAX_ROW)
        form.addRow("资金台账工作表", self.funds_sheet)
        form.addRow("资金台账表头行", self.funds_header_row)
        form.addRow("运营台账工作表", self.operations_sheet)
        form.addRow("运营台账表头行", self.operations_header_row)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        return self._page("数据源设置", body)

    def _summary_page(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.summary_selector = QComboBox()
        self.summary_stack = QStackedWidget()
        items = (
            ("项目订单数量", "project_count", AggregateEditor("计数字段")),
            ("项目预估利润", "project_profit", AggregateEditor("求和字段")),
            ("散采订单数量", "scatter_count", AggregateEditor("计数字段")),
            ("散采预估利润", "scatter_profit", AggregateEditor("求和字段")),
            ("资金放款金额", "fund_amount", AggregateEditor("求和字段")),
            ("资金预估利润", "fund_profit", FundProfitEditor()),
        )
        self.summary_editors = {}
        for label, key, editor in items:
            self.summary_selector.addItem(label)
            self.summary_editors[key] = editor
            self.summary_stack.addWidget(editor)
        for label, text in (
            ("卡转订单 / 利润", "固定为 0"),
            ("合计利润", "项目预估利润 + 散采预估利润 + 资金预估利润"),
        ):
            self.summary_selector.addItem(label)
            fixed = QLabel(text)
            fixed.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fixed.setStyleSheet("color:#5f6e66;font-size:14px;")
            self.summary_stack.addWidget(fixed)
        self.summary_selector.currentIndexChanged.connect(self.summary_stack.setCurrentIndex)
        layout.addWidget(self.summary_selector)
        layout.addWidget(self.summary_stack, 1)
        return self._page("经营汇总", body)

    def _business_page(self, settings: SourceSettings) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.business_selector = QComboBox()
        self.business_stack = QStackedWidget()
        layout.addWidget(self.business_selector)
        layout.addWidget(self.business_stack, 1)
        self.business_selector.currentIndexChanged.connect(self.business_stack.setCurrentIndex)
        self.business_editors: list[BusinessEditor] = []
        self.total_editor: BusinessTotalEditor | None = None
        self._populate_business(settings)
        return self._page("自营项目周报", body)

    def _populate_business(self, settings: SourceSettings) -> None:
        while self.business_stack.count():
            widget = self.business_stack.widget(0)
            self.business_stack.removeWidget(widget)
            widget.deleteLater()
        self.business_selector.clear()
        self.business_editors = []
        for rule in settings.business_rows:
            editor = BusinessEditor(rule)
            self.business_editors.append(editor)
            self.business_selector.addItem(rule.name)
            self.business_stack.addWidget(editor)
        self.total_editor = BusinessTotalEditor(settings.business_total)
        self.business_selector.addItem(settings.business_total.label)
        self.business_stack.addWidget(self.total_editor)

    def _populate(self, settings: SourceSettings) -> None:
        self.funds_sheet.setText(settings.funds_sheet)
        self.funds_header_row.setValue(settings.funds_header_row)
        self.operations_sheet.setText(settings.operations_sheet)
        self.operations_header_row.setValue(settings.operations_header_row)
        for key in (
            "project_count",
            "project_profit",
            "scatter_count",
            "scatter_profit",
            "fund_amount",
            "fund_profit",
        ):
            self.summary_editors[key].populate(getattr(settings, key))
        self._populate_business(settings)

    def restore_defaults(self) -> None:
        self._populate(DEFAULT_SOURCE_SETTINGS)

    def values(self) -> SourceSettings:
        assert self.total_editor is not None
        settings = SourceSettings(
            SCHEMA_VERSION,
            self.funds_sheet.text(),
            self.funds_header_row.value(),
            self.operations_sheet.text(),
            self.operations_header_row.value(),
            self.summary_editors["project_count"].rule(),
            self.summary_editors["project_profit"].rule(),
            self.summary_editors["scatter_count"].rule(),
            self.summary_editors["scatter_profit"].rule(),
            self.summary_editors["fund_amount"].rule(),
            self.summary_editors["fund_profit"].rule(),
            tuple(editor.rule() for editor in self.business_editors),
            self.total_editor.rule(),
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
