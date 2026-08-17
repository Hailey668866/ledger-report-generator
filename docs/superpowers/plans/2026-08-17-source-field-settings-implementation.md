# 数据源字段设置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加一个可持久保存的字段设置窗口，让用户直接修改两份数据源的工作表名称、表头行和关键字段名称。

**Architecture:** 新增一个不可变的 `SourceSettings` 配置对象和 JSON 读写函数；工作簿读取器只接收配置，不自行访问磁盘。`ReportService` 持有当前配置，主窗口负责打开设置窗口、保存配置并在保存成功后重新校验已选择的数据源。

**Tech Stack:** Python 3.12、标准库 `dataclasses/json/os/tempfile`、openpyxl、PySide6、pytest/pytest-qt、Ruff

---

## 文件结构

- Create: `src/ledger_reporter/io/source_settings.py` — 默认值、校验及 JSON 持久化。
- Create: `src/ledger_reporter/ui/source_settings_dialog.py` — 两个标签页的纯输入设置窗口。
- Create: `tests/io/test_source_settings.py` — 配置校验、保存、加载和恢复默认测试。
- Create: `tests/ui/test_source_settings_dialog.py` — 输入框、保存校验和恢复默认测试。
- Modify: `src/ledger_reporter/io/workbooks.py` — 按配置定位工作表、表头行和字段。
- Modify: `src/ledger_reporter/services/report_service.py` — 将当前配置传入两类工作簿读取器。
- Modify: `src/ledger_reporter/ui/main_window.py` — 增加按钮、保存设置并触发重新校验。
- Modify: `src/ledger_reporter/__main__.py` — 从应用数据目录加载配置。
- Modify: `tests/io/test_workbooks.py`、`tests/services/test_report_service.py`、`tests/ui/test_main_window.py`、`tests/ui/test_app_entry.py` — 回归与接线测试。

按用户要求，本计划只在全部功能和验证完成后创建一个 Git 提交，不按任务拆分提交。

### Task 1: 配置对象与本地保存

**Files:**
- Create: `src/ledger_reporter/io/source_settings.py`
- Create: `tests/io/test_source_settings.py`

- [ ] **Step 1: 写配置默认值、校验和持久化的失败测试**

```python
def test_defaults_match_current_workbooks() -> None:
    settings = SourceSettings()
    assert settings.funds_sheet == "资金散板汇总{年份}"
    assert settings.operations_sheet == "台账明细"
    assert settings.funds_header_row == settings.operations_header_row == 1


def test_round_trip_preserves_user_values(tmp_path: Path) -> None:
    path = tmp_path / "source-fields.json"
    settings = replace(
        SourceSettings(),
        funds_sheet="资金数据{年份}",
        operations_gross_profit="预计利润",
    )
    save_source_settings(path, settings)
    assert load_source_settings(path) == settings


@pytest.mark.parametrize(
    "settings",
    [
        replace(SourceSettings(), operations_sheet=""),
        replace(SourceSettings(), funds_header_row=0),
        replace(SourceSettings(), operations_bill_no="字段", operations_project_type="字段"),
    ],
)
def test_rejects_invalid_settings(settings: SourceSettings) -> None:
    with pytest.raises(ValueError):
        settings.validate()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/io/test_source_settings.py -q`

Expected: FAIL，原因是 `ledger_reporter.io.source_settings` 尚不存在。

- [ ] **Step 3: 实现最小配置模块**

```python
@dataclass(frozen=True, slots=True)
class SourceSettings:
    funds_sheet: str = "资金散板汇总{年份}"
    funds_header_row: int = 1
    funds_channel: str = "渠道名称"
    funds_payment_date: str = "信容付款日期"
    funds_amount: str = "付款金额合计（90%）"
    funds_operation_fee: str = "应收操作费"
    operations_sheet: str = "台账明细"
    operations_header_row: int = 1
    operations_bill_no: str = "提单号"
    operations_project_type: str = "项目类型"
    operations_destination: str = "目的口岸"
    operations_departure: str = "预计起飞时间"
    operations_supplier: str = "B1供应商"
    operations_receivable: str = "预估总应收"
    operations_gross_profit: str = "预估毛利润"

    def validate(self) -> None:
        values = asdict(self)
        names = {key: value for key, value in values.items() if not key.endswith("header_row")}
        empty = [key for key, value in names.items() if not isinstance(value, str) or not value.strip()]
        if empty:
            raise ValueError("工作表名称和字段名称不能为空。")
        header_rows = (self.funds_header_row, self.operations_header_row)
        if any(type(value) is not int or value < 1 for value in header_rows):
            raise ValueError("表头行必须是正整数。")
        for prefix in ("funds_", "operations_"):
            fields = [
                value
                for key, value in names.items()
                if key.startswith(prefix) and key != f"{prefix}sheet"
            ]
            if len(fields) != len(set(fields)):
                raise ValueError("同一张表内的关键字段名称不能重复。")


DEFAULT_SOURCE_SETTINGS = SourceSettings()


def load_source_settings(path: Path) -> SourceSettings:
    path = Path(path)
    if not path.is_file():
        return DEFAULT_SOURCE_SETTINGS
    try:
        settings = SourceSettings(**json.loads(path.read_text(encoding="utf-8")))
        settings.validate()
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError(f"字段设置文件无法读取：{error}") from None
    return settings


def save_source_settings(path: Path, settings: SourceSettings) -> None:
    settings.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(asdict(settings), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: 运行配置测试**

Run: `pytest tests/io/test_source_settings.py -q`

Expected: PASS。

### Task 2: 工作簿读取器使用用户配置

**Files:**
- Modify: `src/ledger_reporter/io/workbooks.py`
- Modify: `tests/io/test_workbooks.py`

- [ ] **Step 1: 写自定义工作表、表头行和字段名称的失败测试**

```python
def test_read_operations_uses_custom_sheet_header_row_and_fields(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "运营数据"
    sheet.append(("说明",))
    sheet.append(("起飞日", "利润", "单号", "类型", "口岸", "供应商", "应收"))
    sheet.append(("2026-08-02", 10, "B-1", "散板", "LAX", "供应商 A", 100))
    workbook.save(path)
    settings = replace(
        SourceSettings(),
        operations_sheet="运营数据",
        operations_header_row=2,
        operations_bill_no="单号",
        operations_project_type="类型",
        operations_destination="口岸",
        operations_departure="起飞日",
        operations_supplier="供应商",
        operations_receivable="应收",
        operations_gross_profit="利润",
    )
    assert read_operations(path, settings)[0].bill_no == "B-1"


def test_read_funds_replaces_year_in_custom_sheet_name(tmp_path: Path) -> None:
    path = tmp_path / "funds.xlsx"
    save_book(path, "资金数据2026", ("渠道", "付款日", "金额", "操作费"), [("A", "2026-08-05", 90, 3)])
    settings = replace(
        SourceSettings(),
        funds_sheet="资金数据{年份}",
        funds_channel="渠道",
        funds_payment_date="付款日",
        funds_amount="金额",
        funds_operation_fee="操作费",
    )
    assert read_funds(path, {2026}, settings)[0].amount == Decimal(90)
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `pytest tests/io/test_workbooks.py -q`

Expected: FAIL，读取函数尚不接受 `SourceSettings`。

- [ ] **Step 3: 将逻辑字段映射到用户表头**

将 `_header_positions` 的参数改成 `Mapping[str, str]`，键是程序内部逻辑字段，值是用户配置的真实表头；返回值继续以逻辑字段为键，使后续业务代码无需改名。

```python
def _header_positions(
    headers: tuple[object, ...], required_headers: Mapping[str, str], sheet_name: str
) -> dict[str, int]:
    positions = {}
    for logical_name, configured_header in required_headers.items():
        matches = [index for index, value in enumerate(headers) if value == configured_header]
        if len(matches) > 1:
            raise WorkbookDataError(
                f"工作表「{sheet_name}」存在重复字段「{configured_header}」。"
            )
        if not matches:
            raise WorkbookDataError(
                f"工作表「{sheet_name}」缺少设置字段「{configured_header}」。"
            )
        positions[logical_name] = matches[0]
    return positions
```

用两个明确的映射函数连接逻辑字段和用户输入，不修改 `OperationalRecord`、`FundRecord` 或计算层字段名。

```python
def _operations_headers(settings: SourceSettings) -> dict[str, str]:
    return {
        "提单号": settings.operations_bill_no,
        "项目类型": settings.operations_project_type,
        "目的口岸": settings.operations_destination,
        "预计起飞时间": settings.operations_departure,
        "B1供应商": settings.operations_supplier,
        "预估总应收": settings.operations_receivable,
        "预估毛利润": settings.operations_gross_profit,
    }


def _fund_headers(settings: SourceSettings) -> dict[str, str]:
    return {
        "渠道名称": settings.funds_channel,
        "信容付款日期": settings.funds_payment_date,
        "付款金额合计（90%）": settings.funds_amount,
        "应收操作费": settings.funds_operation_fee,
    }
```

给 `_validated_rows` 增加 `header_row` 参数，读取第 `header_row` 行作为表头；之前的行只跳过，不进入数据迭代。

```python
for _row_number in range(1, header_row + 1):
    try:
        cached_headers = next(cached_rows)
        formula_headers = next(formula_rows)
    except StopIteration:
        raise WorkbookDataError(
            f"工作表「{sheet_name}」没有设置的第 {header_row} 行表头。"
        ) from None
```

给 `read_operations` 和 `read_funds` 增加默认配置参数；资金工作表有 `{年份}` 时替换请求年份，没有占位符时按完整名称读取一次。

```python
def read_operations(
    path: Path, settings: SourceSettings = DEFAULT_SOURCE_SETTINGS
) -> list[OperationalRecord]:
    source = Path(path)
    settings.validate()
    try:
        return _read_operations(source, settings)
    except WorkbookDataError:
        raise
    except (BadZipFile, KeyError, ParseError, ValueError):
        raise WorkbookDataError(f"文件「{source}」不是有效的 XLSX 工作簿。") from None


def read_funds(
    path: Path,
    allowed_years: Iterable[int],
    settings: SourceSettings = DEFAULT_SOURCE_SETTINGS,
) -> list[FundRecord]:
    source = Path(path)
    settings.validate()
    try:
        return _read_funds(source, allowed_years, settings)
    except WorkbookDataError:
        raise
    except (BadZipFile, KeyError, ParseError, ValueError):
        raise WorkbookDataError(f"文件「{source}」不是有效的 XLSX 工作簿。") from None
```

两个公开读取函数首先调用 `settings.validate()`。资金表候选名称使用以下完整规则，保留“请求的两个年份中存在几个就读取几个”的当前行为：

```python
if "{年份}" in settings.funds_sheet:
    requested_sheets = [
        settings.funds_sheet.replace("{年份}", str(year))
        for year in sorted(set(allowed_years))
    ]
else:
    requested_sheets = [settings.funds_sheet]
selected_sheets = [name for name in requested_sheets if name in cached_book.sheetnames]
if not selected_sheets:
    names = "、".join(requested_sheets)
    raise WorkbookDataError(f"工作簿「{source}」未找到设置的资金工作表：{names}。")
```

- [ ] **Step 4: 运行读取器测试和真实样例测试**

Run: `pytest tests/io/test_workbooks.py tests/integration/test_real_samples.py -q`

Expected: PASS，默认配置继续读取原始样例，自定义配置读取改名后的表。

### Task 3: 服务层与应用启动接线

**Files:**
- Modify: `src/ledger_reporter/services/report_service.py`
- Modify: `src/ledger_reporter/__main__.py`
- Modify: `tests/services/test_report_service.py`
- Modify: `tests/ui/test_app_entry.py`

- [ ] **Step 1: 写配置传递失败测试**

```python
settings = replace(SourceSettings(), operations_sheet="运营数据")
service = ReportService(history, settings)

def fake_read_operations(path: Path, received: SourceSettings):
    captured["operations_settings"] = received
    return operations

def fake_read_funds(path: Path, years: set[int], received: SourceSettings):
    captured["funds_settings"] = received
    return funds

service.generate(funds_path, operations_path, date(2027, 4, 9))
assert captured["operations_settings"] is settings
assert captured["funds_settings"] is settings
```

在应用入口测试中替换 `load_source_settings`，断言 `ReportService` 收到配置，`MainWindow` 收到 `source-fields.json` 路径。

- [ ] **Step 2: 运行定向测试确认失败**

Run: `pytest tests/services/test_report_service.py tests/ui/test_app_entry.py -q`

Expected: FAIL，当前构造函数和读取调用尚未传递配置。

- [ ] **Step 3: 实现服务配置和启动加载**

```python
class ReportService:
    def __init__(
        self,
        history: HistoryRepository,
        source_settings: SourceSettings = DEFAULT_SOURCE_SETTINGS,
    ) -> None:
        self.history = history
        self.source_settings = source_settings

    def set_source_settings(self, settings: SourceSettings) -> None:
        settings.validate()
        self.source_settings = settings
```

`inspect_sources` 和 `generate` 将 `self.source_settings` 传给两个读取函数。应用入口使用同一个应用数据目录构造：

```python
data_dir = app_data_dir()
history_path = data_dir / "history.sqlite3"
settings_path = data_dir / "source-fields.json"
repository = HistoryRepository(history_path)
settings = load_source_settings(settings_path)
window = MainWindow(ReportService(repository, settings), settings_path)
```

配置加载放在界面初始化错误处理范围内，不能把配置损坏误报为历史数据库损坏。

- [ ] **Step 4: 运行服务与入口测试**

Run: `pytest tests/services/test_report_service.py tests/ui/test_app_entry.py -q`

Expected: PASS。

### Task 4: 字段设置窗口

**Files:**
- Create: `src/ledger_reporter/ui/source_settings_dialog.py`
- Create: `tests/ui/test_source_settings_dialog.py`

- [ ] **Step 1: 写界面行为失败测试**

```python
def test_dialog_lists_only_editable_settings(qtbot) -> None:
    dialog = SourceSettingsDialog(SourceSettings())
    qtbot.addWidget(dialog)
    assert dialog.tabs.count() == 2
    assert dialog.tabs.tabText(0) == "资金台账"
    assert dialog.tabs.tabText(1) == "运营台账"
    assert dialog.funds_sheet.text() == "资金散板汇总{年份}"
    assert dialog.operations_gross_profit.text() == "预估毛利润"
    assert dialog.findChildren(QLabel, "description") == []


def test_save_rejects_empty_or_duplicate_fields(qtbot, monkeypatch) -> None:
    messages = []
    dialog = SourceSettingsDialog(SourceSettings())
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args))
    dialog.operations_bill_no.setText("")
    dialog.accept_settings()
    assert dialog.result() == 0
    assert messages


def test_restore_defaults_repopulates_all_inputs(qtbot) -> None:
    dialog = SourceSettingsDialog(replace(SourceSettings(), operations_sheet="改名"))
    qtbot.addWidget(dialog)
    dialog.restore_defaults()
    assert dialog.operations_sheet.text() == "台账明细"
```

- [ ] **Step 2: 运行界面测试确认失败**

Run: `pytest tests/ui/test_source_settings_dialog.py -q`

Expected: FAIL，设置窗口模块尚不存在。

- [ ] **Step 3: 实现两标签页表单**

使用 `QTabWidget`、`QFormLayout`、`QLineEdit`、`QSpinBox` 和 `QDialogButtonBox`。输入框属性名与 `SourceSettings` 字段名一致；`values()` 构造并验证配置，`accept_settings()` 只在验证成功时设置 `selected_settings` 并接受窗口。

```python
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
    try:
        self.selected_settings = self.values()
    except ValueError as error:
        QMessageBox.warning(self, "无法保存字段设置", str(error))
        return
    self.accept()
```

“恢复默认”只回填输入框，不立即写文件；用户仍需点击“保存”。窗口不显示说明段落。

- [ ] **Step 4: 运行设置窗口测试**

Run: `pytest tests/ui/test_source_settings_dialog.py -q`

Expected: PASS。

### Task 5: 主窗口保存与重新校验

**Files:**
- Modify: `src/ledger_reporter/ui/main_window.py`
- Modify: `tests/ui/test_main_window.py`

- [ ] **Step 1: 写主窗口接入失败测试**

```python
def test_saving_source_settings_updates_service_and_revalidates_selected_files(
    qtbot, monkeypatch, tmp_path, fake_report_service
) -> None:
    settings_path = tmp_path / "source-fields.json"
    selected = replace(SourceSettings(), operations_sheet="运营数据")
    window = MainWindow(fake_report_service, settings_path)
    qtbot.addWidget(window)
    _select_sources(window, tmp_path)
    validation_calls = []

    class AcceptedDialog:
        selected_settings = selected
        def __init__(self, *_args): pass
        def exec(self): return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "SourceSettingsDialog", AcceptedDialog)
    monkeypatch.setattr(window, "start_validation", lambda: validation_calls.append(True))
    window.open_source_settings()

    assert fake_report_service.source_settings == selected
    assert load_source_settings(settings_path) == selected
    assert validation_calls == [True]
```

另加测试：取消不保存；写文件失败时不更新服务；后台任务运行时字段设置按钮保持禁用。

测试用 `FakeReportService` 增加 `source_settings = SourceSettings()` 和以下方法，与真实服务保持同一接口：

```python
def set_source_settings(self, settings: SourceSettings) -> None:
    self.source_settings = settings
```

- [ ] **Step 2: 运行主窗口测试确认失败**

Run: `pytest tests/ui/test_main_window.py -q`

Expected: FAIL，主窗口尚无字段设置按钮和处理方法。

- [ ] **Step 3: 实现按钮和保存流程**

在“数据源”标题同一行右侧放置“字段设置”次级按钮，并连接：

```python
def open_source_settings(self) -> None:
    dialog = SourceSettingsDialog(self.report_service.source_settings, self)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    settings = dialog.selected_settings
    assert settings is not None
    try:
        if self.source_settings_path is not None:
            save_source_settings(self.source_settings_path, settings)
    except Exception as error:  # UI boundary
        QMessageBox.critical(self, "字段设置保存失败", str(error) or error.__class__.__name__)
        return
    self.report_service.set_source_settings(settings)
    self.refresh_ready()
    if self._sources_ready():
        self.start_validation()
```

启动校验或生成时禁用该按钮，所有后台线程结束后恢复。设置保存成功会清除旧预览和旧校验结果，避免继续使用旧字段映射。

- [ ] **Step 4: 运行全部 UI 测试**

Run: `pytest tests/ui -q`

Expected: PASS。

### Task 6: 全量验证与单次提交

**Files:**
- Verify: all files above

- [ ] **Step 1: 运行全量自动化测试**

Run: `pytest -q`

Expected: PASS，零失败；其中现有卸载测试继续证明整个应用数据目录会被删除，因此 `source-fields.json` 不需要新增卸载路径。

- [ ] **Step 2: 运行静态和格式检查**

Run: `ruff check .`

Expected: `All checks passed!`

Run: `ruff format --check .`

Expected: 所有文件已格式化。

- [ ] **Step 3: 运行 Git 差异检查并核对范围**

Run: `git diff --check`

Expected: 无输出、退出码 0。

Run: `git status --short`

Expected: 只包含本计划列出的源码、测试和文档；本地 `.release/` 目录不得暂存。

- [ ] **Step 4: 创建一个功能提交**

```bash
git add src/ledger_reporter/io/source_settings.py \
  src/ledger_reporter/io/workbooks.py \
  src/ledger_reporter/services/report_service.py \
  src/ledger_reporter/ui/source_settings_dialog.py \
  src/ledger_reporter/ui/main_window.py \
  src/ledger_reporter/__main__.py \
  tests/io/test_source_settings.py \
  tests/io/test_workbooks.py \
  tests/services/test_report_service.py \
  tests/ui/test_source_settings_dialog.py \
  tests/ui/test_main_window.py \
  tests/ui/test_app_entry.py \
  docs/superpowers/plans/2026-08-17-source-field-settings-implementation.md
git commit -m "feat: configure source workbook fields"
```

- [ ] **Step 5: 提交后复核**

Run: `git status --short --branch`

Expected: 功能文件无未提交改动；只允许保留未跟踪且不提交的 `.release/`。
