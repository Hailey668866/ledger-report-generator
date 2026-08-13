# 台账报表生成器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建无需 Python 环境、完全离线运行的 macOS 台账报表应用，按冻结基线与月内 Week 规则生成 Excel/PNG，并提供历史保存和一键卸载。

**Architecture:** 业务核心采用纯 Python 领域模型，数据读取、周期计算、历史存储、表格表达和桌面 UI 分层。两种导出和界面预览消费同一个 `ReportBundle`/`TableSpec`，SQLite 只保存应用内部周快照，源 XLSX 始终只读。

**Tech Stack:** Python 3.12、PySide6、openpyxl、Pillow、SQLite、pytest、pytest-qt、PyInstaller、dmgbuild、GitHub Actions macOS runner。

---

## 执行约束

- 所有任务在 `D:\自动化表格\.worktrees\ledger-report-generator` 的 `feature/ledger-report-generator` 分支执行。
- 严格采用 TDD：先写失败测试、确认失败、实现最小代码、确认通过。
- 每个提交步骤前必须先向用户明确提醒“现在是可提交 Git 节点”，展示 `git status --short`、变更范围和建议提交信息，然后再提交。
- 不提交三份真实源台账；真实文件只用于本地最终核对。
- 不在 Windows 上伪造 macOS 产物；Windows 完成代码与测试，DMG 在真实 Mac 或 macOS CI 构建。

## 文件结构

```text
pyproject.toml                         项目元数据、运行和开发依赖
src/ledger_reporter/__main__.py       应用入口
src/ledger_reporter/app_paths.py      应用数据、缓存、日志和资源路径
src/ledger_reporter/domain/models.py  领域数据类型
src/ledger_reporter/domain/periods.py 财年与月内 Week 算法
src/ledger_reporter/io/errors.py      用户可读的数据错误
src/ledger_reporter/io/workbooks.py   XLSX 校验与记录读取
src/ledger_reporter/rules.py          供应商、目标和业务筛选常量
src/ledger_reporter/services/calculations.py 两张报表的计算
src/ledger_reporter/services/baseline.py     2026 固定基线
src/ledger_reporter/services/update_planner.py 周更与漏周补齐计划
src/ledger_reporter/services/history.py      SQLite 历史事务
src/ledger_reporter/services/report_service.py 生成流程编排
src/ledger_reporter/presentation/models.py   与格式无关的 TableSpec
src/ledger_reporter/presentation/builders.py 两张正式表布局
src/ledger_reporter/presentation/theme.py    模板样式令牌
src/ledger_reporter/exporters/excel.py       XLSX 导出
src/ledger_reporter/exporters/png.py         PNG 导出
src/ledger_reporter/ui/main_window.py        主窗口
src/ledger_reporter/ui/source_picker.py      数据源选择控件
src/ledger_reporter/ui/preview_dialog.py     收起式预览弹窗
src/ledger_reporter/ui/workers.py            后台生成任务
src/ledger_reporter/ui/uninstall_dialog.py   卸载确认
src/ledger_reporter/uninstall.py             安全卸载助手生成
src/ledger_reporter/resources/app-icon.png   用户提供的源图标
src/ledger_reporter/resources/fy2026_baseline.json 固定基线
tests/                                      单元与集成测试
tools/extract_baseline.py                   一次性基线提取工具
scripts/make_icns.sh                        macOS 图标集生成
scripts/build_macos.sh                      Mac 一键测试和打包
packaging/ledger_reporter.spec              PyInstaller 配置
packaging/dmg_settings.py                   DMG 布局
.github/workflows/build-macos.yml           macOS CI
docs/INSTALL_MACOS.md                       安装与首次打开说明
```

### Task 1: Python 项目骨架与资源访问

**Files:**
- Create: `pyproject.toml`
- Create: `src/ledger_reporter/__init__.py`
- Create: `src/ledger_reporter/app_paths.py`
- Create: `tests/test_app_paths.py`
- Modify: `.gitignore`

- [ ] **Step 1: 写资源与数据目录的失败测试**

```python
# tests/test_app_paths.py
from pathlib import Path

from ledger_reporter.app_paths import app_data_dir, resource_path


def test_data_dir_can_be_overridden(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEDGER_REPORTER_DATA_DIR", str(tmp_path))
    assert app_data_dir() == tmp_path


def test_resource_path_stays_inside_resources() -> None:
    path = resource_path("fy2026_baseline.json")
    assert path.name == "fy2026_baseline.json"
    assert path.parent.name == "resources"
```

- [ ] **Step 2: 创建虚拟环境并确认测试因包不存在而失败**

Run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_app_paths.py -q
```

Expected: 首次安装前因 `pyproject.toml` 不存在失败；创建下一步文件并重新安装后，测试因 `ledger_reporter.app_paths` 不存在失败。

- [ ] **Step 3: 创建最小项目配置和路径实现**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ledger-report-generator"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "openpyxl>=3.1,<4",
  "Pillow>=11,<13",
  "PySide6>=6.8,<7",
]

[project.optional-dependencies]
dev = [
  "dmgbuild>=1.6,<2",
  "pyinstaller>=6.11,<7",
  "pytest>=8,<9",
  "pytest-qt>=4.4,<5",
  "ruff>=0.9,<1",
]

[project.scripts]
ledger-report-generator = "ledger_reporter.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
ledger_reporter = ["resources/*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py312"
```

```python
# src/ledger_reporter/__init__.py
__version__ = "0.1.0"
```

```python
# src/ledger_reporter/app_paths.py
import os
import sys
from pathlib import Path


APP_ID = "com.local.ledger-report-generator"


def app_data_dir() -> Path:
    override = os.getenv("LEDGER_REPORTER_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    return Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_ID


def resource_path(name: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS) / "ledger_reporter"
    else:
        base = Path(__file__).resolve().parent
    resources = base / "resources"
    candidate = (resources / name).resolve()
    if resources.resolve() not in candidate.parents:
        raise ValueError("resource path escapes resources directory")
    return candidate
```

在 `.gitignore` 中将 `*.spec` 改为：

```gitignore
*.spec
!packaging/ledger_reporter.spec
```

- [ ] **Step 4: 安装并验证测试通过**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/test_app_paths.py -q
```

Expected: `2 passed`。

- [ ] **Step 5: 提醒用户并提交项目骨架**

Run `git status --short`，提醒用户此节点建议提交：

```powershell
git add .gitignore pyproject.toml src/ledger_reporter/__init__.py src/ledger_reporter/app_paths.py tests/test_app_paths.py
git commit -m "build: scaffold ledger report application"
```

### Task 2: 领域模型与月内 Week 算法

**Files:**
- Create: `src/ledger_reporter/domain/models.py`
- Create: `src/ledger_reporter/domain/periods.py`
- Create: `tests/domain/test_periods.py`

- [ ] **Step 1: 写财年和月末规则失败测试**

```python
# tests/domain/test_periods.py
from datetime import date
from pathlib import Path

from ledger_reporter.domain.periods import fiscal_year_for, latest_completed_week, month_weeks


def test_fiscal_year_starts_on_april_first() -> None:
    assert fiscal_year_for(date(2027, 3, 31)) == 2026
    assert fiscal_year_for(date(2027, 4, 1)) == 2027


def test_august_2026_periods_create_four_day_tail() -> None:
    periods = month_weeks(2026, 8)
    assert [(p.start.day, p.end.day) for p in periods] == [
        (1, 6), (7, 13), (14, 20), (21, 27), (28, 31)
    ]


def test_one_day_tail_merges_into_previous_week() -> None:
    periods = month_weeks(2026, 7)
    assert (periods[-1].start.day, periods[-1].end.day) == (24, 31)


def test_latest_period_must_end_before_today() -> None:
    period = latest_completed_week(date(2026, 8, 7))
    assert (period.start, period.end) == (date(2026, 8, 1), date(2026, 8, 6))
```

- [ ] **Step 2: 运行测试并确认导入失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/domain/test_periods.py -q`

Expected: FAIL with `ModuleNotFoundError: ledger_reporter.domain`。

- [ ] **Step 3: 实现不可变模型和周期函数**

```python
# src/ledger_reporter/domain/models.py
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class ReportingPeriod:
    start: date
    end: date
    label: str


@dataclass(frozen=True, slots=True)
class OperationalRecord:
    bill_no: str | None
    project_type: str | None
    destination: str | None
    departure: date
    supplier: str | None
    receivable: Decimal
    gross_profit: Decimal


@dataclass(frozen=True, slots=True)
class FundRecord:
    channel: str
    payment_date: date
    amount: Decimal
    operation_fee: Decimal


@dataclass(frozen=True, slots=True)
class PeriodMetrics:
    project_count: int = 0
    project_profit: Decimal = ZERO
    scatter_count: int = 0
    scatter_profit: Decimal = ZERO
    fund_amount: Decimal = ZERO
    fund_profit: Decimal = ZERO
    card_count: int = 0
    card_profit: Decimal = ZERO

    @property
    def total_profit(self) -> Decimal:
        return self.project_profit + self.scatter_profit + self.fund_profit + self.card_profit


@dataclass(frozen=True, slots=True)
class WeekSnapshot:
    fiscal_year: int
    period: ReportingPeriod
    metrics: PeriodMetrics


@dataclass(frozen=True, slots=True)
class BusinessMetric:
    name: str
    count: int
    profit: Decimal
    receivable: Decimal

    @property
    def margin(self) -> Decimal | None:
        return None if self.receivable == ZERO else self.profit / self.receivable
```

```python
# src/ledger_reporter/domain/periods.py
import calendar
from datetime import date, timedelta

from .models import ReportingPeriod


def fiscal_year_for(day: date) -> int:
    return day.year if day.month >= 4 else day.year - 1


def _label(index: int, start: date, end: date) -> str:
    return f"W{index}（{start.month}.{start.day}-{end.month}.{end.day}）"


def month_weeks(year: int, month: int) -> list[ReportingPeriod]:
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    cursor = date(year, month, 1)
    first_end = cursor + timedelta(days=(3 - cursor.weekday()) % 7)
    periods = [ReportingPeriod(cursor, first_end, "")]
    cursor = first_end + timedelta(days=1)
    while cursor <= month_end:
        nominal_end = cursor + timedelta(days=6)
        if nominal_end <= month_end:
            periods.append(ReportingPeriod(cursor, nominal_end, ""))
            cursor = nominal_end + timedelta(days=1)
            continue
        tail_days = (month_end - cursor).days + 1
        if tail_days == 1:
            previous = periods[-1]
            periods[-1] = ReportingPeriod(previous.start, month_end, "")
        else:
            periods.append(ReportingPeriod(cursor, month_end, ""))
        break
    return [ReportingPeriod(p.start, p.end, _label(i, p.start, p.end)) for i, p in enumerate(periods, 1)]


def latest_completed_week(today: date) -> ReportingPeriod:
    candidates = [period for period in month_weeks(today.year, today.month) if period.end < today]
    if candidates:
        return candidates[-1]
    previous_month_end = today.replace(day=1) - timedelta(days=1)
    return month_weeks(previous_month_end.year, previous_month_end.month)[-1]


def previous_week(period: ReportingPeriod) -> ReportingPeriod:
    month = month_weeks(period.start.year, period.start.month)
    index = next(i for i, candidate in enumerate(month) if candidate.start == period.start)
    if index:
        return month[index - 1]
    previous_month_end = period.start - timedelta(days=1)
    return month_weeks(previous_month_end.year, previous_month_end.month)[-1]
```

- [ ] **Step 4: 运行周期测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests/domain/test_periods.py -q`

Expected: `4 passed`。

- [ ] **Step 5: 提醒用户并提交周期引擎**

```powershell
git add src/ledger_reporter/domain tests/domain
git commit -m "feat: add fiscal week period engine"
```

### Task 3: XLSX 结构校验与记录读取

**Files:**
- Create: `src/ledger_reporter/io/errors.py`
- Create: `src/ledger_reporter/io/workbooks.py`
- Create: `tests/io/test_workbooks.py`

- [ ] **Step 1: 写合成工作簿读取测试**

```python
# tests/io/test_workbooks.py
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.io.workbooks import read_funds, read_operations


def save_book(path: Path, sheet_name: str, headers: list[str], row: list[object]) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = sheet_name
    sheet.append(headers)
    sheet.append(row)
    book.save(path)


def test_reads_operational_fields_by_header_name(tmp_path: Path) -> None:
    path = tmp_path / "ops.xlsx"
    headers = ["提单号", "项目类型", "目的口岸", "预计起飞时间", "B1供应商", "预估总应收", "预估毛利润"]
    save_book(path, "台账明细", headers, ["001", "散采", "OSL", datetime(2026, 8, 6), "供应商", 1000, 50])
    records = read_operations(path)
    assert records[0].bill_no == "001"
    assert records[0].gross_profit.as_tuple().exponent == 0


def test_rejects_missing_required_header(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    save_book(path, "台账明细", ["提单号"], ["001"])
    with pytest.raises(WorkbookDataError, match="预估毛利润"):
        read_operations(path)


def test_rejects_duplicate_required_header(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.xlsx"
    headers = ["提单号", "提单号", "项目类型", "目的口岸", "预计起飞时间", "B1供应商", "预估总应收", "预估毛利润"]
    save_book(path, "台账明细", headers, ["001", "002", "散采", "OSL", datetime(2026, 8, 6), "供应商", 1000, 50])
    with pytest.raises(WorkbookDataError, match="重复字段.*提单号"):
        read_operations(path)


def test_rejects_corrupt_xlsx_with_actionable_message(tmp_path: Path) -> None:
    path = tmp_path / "broken.xlsx"
    path.write_bytes(b"not an xlsx")
    with pytest.raises(WorkbookDataError, match="不是有效的 XLSX"):
        read_operations(path)


def test_reads_matching_fund_year_sheet(tmp_path: Path) -> None:
    path = tmp_path / "funds.xlsx"
    save_book(path, "资金散板汇总2026", ["渠道名称", "信容付款日期", "付款金额合计（90%）", "应收操作费"], ["渠道", datetime(2026, 8, 6), 900, 10])
    records = read_funds(path, {2026})
    assert records[0].amount.as_tuple().exponent == 0
```

- [ ] **Step 2: 运行读取测试并确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/io/test_workbooks.py -q`

Expected: FAIL with missing `ledger_reporter.io`。

- [ ] **Step 3: 实现精确表头读取与错误类型**

```python
# src/ledger_reporter/io/errors.py
class WorkbookDataError(ValueError):
    """可直接显示给用户的工作簿错误。"""
```

```python
# src/ledger_reporter/io/workbooks.py
import re
from zipfile import BadZipFile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from ledger_reporter.domain.models import FundRecord, OperationalRecord
from .errors import WorkbookDataError


OPS_HEADERS = ("提单号", "项目类型", "目的口岸", "预计起飞时间", "B1供应商", "预估总应收", "预估毛利润")
FUND_HEADERS = ("渠道名称", "信容付款日期", "付款金额合计（90%）", "应收操作费")


def _open_workbook(path: Path, *, data_only: bool):
    if path.suffix.lower() != ".xlsx" or not path.is_file():
        raise WorkbookDataError(f"{path.name} 不是有效的 XLSX 文件")
    try:
        return load_workbook(path, read_only=True, data_only=data_only)
    except (BadZipFile, InvalidFileException, OSError) as exc:
        raise WorkbookDataError(f"{path.name} 不是有效的 XLSX 文件，请重新导出后再试") from exc


def _decimal(value: object, label: str) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise WorkbookDataError(f"{label} 不是有效数字：{value}") from exc


def _date(value: object, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
        except ValueError as exc:
            raise WorkbookDataError(f"{label} 不是有效日期：{value}") from exc
    raise WorkbookDataError(f"{label} 不是有效日期：{value}")


def _rows(sheet, required: tuple[str, ...]):
    values = sheet.iter_rows(values_only=True)
    headers = list(next(values))
    missing = [name for name in required if name not in headers]
    duplicates = [name for name in required if headers.count(name) > 1]
    if missing or duplicates:
        parts = []
        if missing:
            parts.append(f"缺少字段：{'、'.join(missing)}")
        if duplicates:
            parts.append(f"重复字段：{'、'.join(duplicates)}")
        raise WorkbookDataError(f"工作表 {sheet.title} {'；'.join(parts)}")
    indexes = {name: headers.index(name) for name in required}
    for row in values:
        yield {name: row[indexes[name]] for name in required}


def read_operations(path: Path) -> list[OperationalRecord]:
    book = _open_workbook(path, data_only=True)
    if "台账明细" not in book.sheetnames:
        raise WorkbookDataError("缺少工作表：台账明细")
    return [
        OperationalRecord(
            bill_no=str(row["提单号"]) if row["提单号"] not in (None, "") else None,
            project_type=str(row["项目类型"]) if row["项目类型"] not in (None, "") else None,
            destination=str(row["目的口岸"]) if row["目的口岸"] not in (None, "") else None,
            departure=_date(row["预计起飞时间"], "预计起飞时间"),
            supplier=str(row["B1供应商"]) if row["B1供应商"] not in (None, "") else None,
            receivable=_decimal(row["预估总应收"], "预估总应收"),
            gross_profit=_decimal(row["预估毛利润"], "预估毛利润"),
        )
        for row in _rows(book["台账明细"], OPS_HEADERS)
        if row["预计起飞时间"] not in (None, "")
    ]


def read_funds(path: Path, years: set[int]) -> list[FundRecord]:
    book = _open_workbook(path, data_only=True)
    names = [name for name in book.sheetnames if re.fullmatch(r"资金散板汇总\d{4}", name) and int(name[-4:]) in years]
    if not names:
        raise WorkbookDataError("缺少所需年度的资金散板汇总工作表")
    records: list[FundRecord] = []
    for name in names:
        for row in _rows(book[name], FUND_HEADERS):
            if row["信容付款日期"] in (None, ""):
                continue
            records.append(FundRecord(
                channel=str(row["渠道名称"] or ""),
                payment_date=_date(row["信容付款日期"], "信容付款日期"),
                amount=_decimal(row["付款金额合计（90%）"], "付款金额合计（90%）"),
                operation_fee=_decimal(row["应收操作费"], "应收操作费"),
            ))
    return records
```

- [ ] **Step 4: 增加公式无缓存检测并跑测试**

在 `tests/io/test_workbooks.py` 添加：

```python
def test_rejects_formula_without_cached_value(tmp_path: Path) -> None:
    path = tmp_path / "formula.xlsx"
    headers = ["提单号", "项目类型", "目的口岸", "预计起飞时间", "B1供应商", "预估总应收", "预估毛利润"]
    save_book(path, "台账明细", headers, ["001", "BSA", "OSL", datetime(2026, 8, 6), "供应商", 1000, "=1+1"])
    with pytest.raises(WorkbookDataError, match="公式没有缓存结果"):
        read_operations(path)
```

在 `workbooks.py` 添加并在 `read_operations`、`read_funds` 读取值之前调用：

```python
def _ensure_formula_cache(path: Path, sheet_name: str, numeric_headers: tuple[str, ...]) -> None:
    values_book = _open_workbook(path, data_only=True)
    formulas_book = _open_workbook(path, data_only=False)
    values_sheet = values_book[sheet_name]
    formulas_sheet = formulas_book[sheet_name]
    values_rows = values_sheet.iter_rows()
    formulas_rows = formulas_sheet.iter_rows()
    value_header = [cell.value for cell in next(values_rows)]
    formula_header = [cell.value for cell in next(formulas_rows)]
    indexes = {name: value_header.index(name) for name in numeric_headers if name in value_header}
    if len(indexes) != len(numeric_headers) or formula_header != value_header:
        missing = [name for name in numeric_headers if name not in indexes]
        raise WorkbookDataError(f"工作表 {sheet_name} 缺少字段：{'、'.join(missing)}")
    for value_row, formula_row in zip(values_rows, formulas_rows, strict=True):
        for name, index in indexes.items():
            formula = formula_row[index].value
            cached = value_row[index].value
            if isinstance(formula, str) and formula.startswith("=") and cached is None:
                raise WorkbookDataError(
                    f"{sheet_name} 的 {name} 公式没有缓存结果，请使用 Excel/WPS 重新计算并保存源文件"
                )
```

调用点：

```python
_ensure_formula_cache(path, "台账明细", ("预估总应收", "预估毛利润"))
for name in names:
    _ensure_formula_cache(path, name, ("付款金额合计（90%）", "应收操作费"))
```

然后运行：

Run: `.\.venv\Scripts\python.exe -m pytest tests/io/test_workbooks.py -q`

Expected: `6 passed`。

- [ ] **Step 5: 提醒用户并提交工作簿读取器**

```powershell
git add src/ledger_reporter/io tests/io
git commit -m "feat: validate and read ledger workbooks"
```

### Task 4: 第一张表周期计算

**Files:**
- Create: `src/ledger_reporter/rules.py`
- Create: `src/ledger_reporter/services/calculations.py`
- Create: `tests/services/test_summary_calculations.py`

- [ ] **Step 1: 写项目、散采和资金公式测试**

```python
# tests/services/test_summary_calculations.py
from datetime import date
from decimal import Decimal

import pytest

from ledger_reporter.domain.models import FundRecord, OperationalRecord, ReportingPeriod
from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.services.calculations import calculate_period


PERIOD = ReportingPeriod(date(2026, 8, 1), date(2026, 8, 6), "W1（8.1-8.6）")


def op(kind: str, profit: str) -> OperationalRecord:
    return OperationalRecord("001", kind, "OSL", date(2026, 8, 3), "供应商", Decimal("1000"), Decimal(profit))


def test_calculates_summary_columns() -> None:
    funds = [FundRecord("广州美鑫通国际供应链有限公司", date(2026, 8, 4), Decimal("10000"), Decimal("20"))]
    metrics = calculate_period(PERIOD, [op("BSA", "100"), op("散采", "30")], funds)
    assert metrics.project_count == 1
    assert metrics.project_profit == Decimal("100")
    assert metrics.scatter_count == 1
    assert metrics.scatter_profit == Decimal("30")
    assert metrics.fund_amount == Decimal("10000")
    assert metrics.fund_profit == Decimal("10000") * Decimal("0.0552") * Decimal("60") / Decimal("365") + Decimal("20")


def test_rejects_unknown_fund_channel() -> None:
    funds = [FundRecord("未知渠道", date(2026, 8, 4), Decimal("100"), Decimal("0"))]
    with pytest.raises(WorkbookDataError, match="未知渠道"):
        calculate_period(PERIOD, [], funds)
```

- [ ] **Step 2: 运行测试并确认函数不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_summary_calculations.py -q`

Expected: FAIL importing `calculate_period`。

- [ ] **Step 3: 实现业务常量和周期汇总**

```python
# src/ledger_reporter/rules.py
from decimal import Decimal


SCATTER = "散采"
MONTH_TARGET = Decimal("1670000")
QUARTER_TARGET = Decimal("5000000")
CAPITAL_COST = Decimal("0.0448")
FUND_RATES = {
    "广州美鑫通国际供应链有限公司": Decimal("0.10"),
    "浙江飞速供应链管理有限公司": Decimal("0.12"),
}
```

```python
# src/ledger_reporter/services/calculations.py
from decimal import Decimal

from ledger_reporter.domain.models import FundRecord, OperationalRecord, PeriodMetrics, ReportingPeriod
from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.rules import CAPITAL_COST, FUND_RATES, SCATTER


def calculate_period(period: ReportingPeriod, operations: list[OperationalRecord], funds: list[FundRecord]) -> PeriodMetrics:
    selected_ops = [row for row in operations if period.start <= row.departure <= period.end]
    project = [row for row in selected_ops if row.project_type != SCATTER]
    scatter = [row for row in selected_ops if row.project_type == SCATTER]
    selected_funds = [row for row in funds if period.start <= row.payment_date <= period.end]
    unknown = sorted({row.channel for row in selected_funds if row.channel not in FUND_RATES})
    if unknown:
        raise WorkbookDataError(f"资金台账出现未配置渠道：{'、'.join(unknown)}")
    fund_profit = sum(
        (row.amount * (FUND_RATES[row.channel] - CAPITAL_COST) * Decimal("60") / Decimal("365") + row.operation_fee for row in selected_funds),
        Decimal("0"),
    )
    return PeriodMetrics(
        project_count=sum(row.bill_no is not None for row in project),
        project_profit=sum((row.gross_profit for row in project), Decimal("0")),
        scatter_count=sum(row.bill_no is not None for row in scatter),
        scatter_profit=sum((row.gross_profit for row in scatter), Decimal("0")),
        fund_amount=sum((row.amount for row in selected_funds), Decimal("0")),
        fund_profit=fund_profit,
    )
```

- [ ] **Step 4: 运行公式测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_summary_calculations.py -q`

Expected: `2 passed`。

- [ ] **Step 5: 提醒用户并提交第一张表计算**

```powershell
git add src/ledger_reporter/rules.py src/ledger_reporter/services tests/services/test_summary_calculations.py
git commit -m "feat: calculate weekly summary metrics"
```

### Task 5: 第二张表业务筛选与总计

**Files:**
- Modify: `src/ledger_reporter/rules.py`
- Modify: `src/ledger_reporter/services/calculations.py`
- Create: `tests/services/test_business_calculations.py`

- [ ] **Step 1: 写供应商拆分和全量总计测试**

```python
# tests/services/test_business_calculations.py
from datetime import date
from decimal import Decimal

import pytest

from ledger_reporter.domain.models import OperationalRecord, ReportingPeriod
from ledger_reporter.services.calculations import calculate_business_table


PERIOD = ReportingPeriod(date(2026, 8, 1), date(2026, 8, 6), "W1（8.1-8.6）")


def record(supplier: str, project: str, destination: str, profit: str, receivable: str) -> OperationalRecord:
    return OperationalRecord("001", project, destination, date(2026, 8, 3), supplier, Decimal(receivable), Decimal(profit))


@pytest.mark.parametrize(
    ("expected", "supplier", "project", "destination"),
    [
        ("WWP", "Worldwide Partner Logistics Company Limited", "其他", "CDG"),
        ("欧展-固定位（LAX）", "欧展国际货运（上海）有限公司北京货运代理分公司", "BSA-欧展", "LAX"),
        ("欧展-差价", "欧展国际货运（上海）有限公司北京货运代理分公司", "差价-欧展", "DXB"),
        ("金开宇", "北京金开宇国际货运代理有限公司", "其他", "CDG"),
        ("厦门伦升", "厦门伦升国际物流有限公司", "其他", "CDG"),
        ("印华固定位OSL", "上海印华国际货运代理有限公司深圳分公司", "其他", "OSL"),
        ("印华固定位ORD", "上海印华国际货运代理有限公司深圳分公司", "其他", "ORD"),
        ("印华固定位LGG", "上海印华国际货运代理有限公司深圳分公司", "其他", "LGG"),
        ("美鑫通GRU", "广州美鑫通国际供应链有限公司", "其他", "GRU"),
        ("迅達航空", "迅達航空貨運（香港）有限公司", "其他", "HKG"),
        ("散采", "其他供应商", "散采", "CDG"),
    ],
)
def test_each_business_rule(expected: str, supplier: str, project: str, destination: str) -> None:
    result = calculate_business_table(PERIOD, [record(supplier, project, destination, "100", "1000")])
    by_name = {item.name: item for item in result.rows}
    assert by_name[expected].count == 1
    assert by_name[expected].profit == Decimal("100")


def test_total_uses_all_week_rows_instead_of_summing_rule_rows() -> None:
    rows = [
        record("欧展国际货运（上海）有限公司北京货运代理分公司", "BSA-欧展", "LAX", "100", "1000"),
        record("欧展国际货运（上海）有限公司北京货运代理分公司", "差价-欧展", "DXB", "50", "500"),
        record("其他供应商", "其他", "CDG", "20", "200"),
    ]
    result = calculate_business_table(PERIOD, rows)
    assert result.total.count == 3
    assert result.total.profit == Decimal("170")
    assert result.total.receivable == Decimal("1700")
```

- [ ] **Step 2: 运行测试并确认缺少业务表函数**

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_business_calculations.py -q`

Expected: FAIL importing `calculate_business_table`。

- [ ] **Step 3: 添加固定筛选配置和结果模型**

在 `domain/models.py` 添加：

```python
@dataclass(frozen=True, slots=True)
class BusinessTable:
    period: ReportingPeriod
    rows: tuple[BusinessMetric, ...]
    total: BusinessMetric
```

在 `rules.py` 添加精确配置：

```python
OUZHANG = "欧展国际货运（上海）有限公司北京货运代理分公司"
YINHUA = "上海印华国际货运代理有限公司深圳分公司"
BUSINESS_RULES = (
    ("WWP", {"supplier": "Worldwide Partner Logistics Company Limited"}),
    ("欧展-固定位（LAX）", {"supplier": OUZHANG, "project_type": "BSA-欧展"}),
    ("欧展-差价", {"supplier": OUZHANG, "project_type": "差价-欧展"}),
    ("金开宇", {"supplier": "北京金开宇国际货运代理有限公司"}),
    ("厦门伦升", {"supplier": "厦门伦升国际物流有限公司"}),
    ("印华固定位OSL", {"supplier": YINHUA, "destination": "OSL"}),
    ("印华固定位ORD", {"supplier": YINHUA, "destination": "ORD"}),
    ("印华固定位LGG", {"supplier": YINHUA, "destination": "LGG"}),
    ("美鑫通GRU", {"supplier": "广州美鑫通国际供应链有限公司"}),
    ("迅達航空", {"supplier": "迅達航空貨運（香港）有限公司"}),
    ("散采", {"project_type": "散采"}),
)
```

- [ ] **Step 4: 实现筛选、利润率分母和独立总计**

```python
def _matches(row: OperationalRecord, filters: dict[str, str]) -> bool:
    return all(getattr(row, key) == value for key, value in filters.items())


def _business_metric(name: str, rows: list[OperationalRecord]) -> BusinessMetric:
    return BusinessMetric(
        name=name,
        count=sum(row.bill_no is not None for row in rows),
        profit=sum((row.gross_profit for row in rows), Decimal("0")),
        receivable=sum((row.receivable for row in rows), Decimal("0")),
    )


def calculate_business_table(period: ReportingPeriod, operations: list[OperationalRecord]) -> BusinessTable:
    selected = [row for row in operations if period.start <= row.departure <= period.end]
    rows = tuple(
        _business_metric(name, [row for row in selected if _matches(row, filters)])
        for name, filters in BUSINESS_RULES
    )
    return BusinessTable(period, rows, _business_metric("销售额合计", selected))
```

同时将 `calculations.py` 的导入更新为：

```python
from ledger_reporter.domain.models import (
    BusinessMetric,
    BusinessTable,
    FundRecord,
    OperationalRecord,
    PeriodMetrics,
    ReportingPeriod,
)
from ledger_reporter.rules import BUSINESS_RULES, CAPITAL_COST, FUND_RATES, SCATTER
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_business_calculations.py -q`

Expected: `12 passed`。

- [ ] **Step 5: 提醒用户并提交第二张表计算**

```powershell
git add src/ledger_reporter/domain/models.py src/ledger_reporter/rules.py src/ledger_reporter/services/calculations.py tests/services/test_business_calculations.py
git commit -m "feat: calculate weekly business report"
```

### Task 6: 2026 固定基线与周更计划

**Files:**
- Create: `tools/extract_baseline.py`
- Create: `src/ledger_reporter/resources/fy2026_baseline.json`
- Create: `src/ledger_reporter/services/baseline.py`
- Create: `src/ledger_reporter/services/update_planner.py`
- Create: `tests/services/test_update_planner.py`
- Create: `tests/services/test_baseline.py`

- [ ] **Step 1: 写冻结边界、双周回刷和漏周补齐测试**

```python
# tests/services/test_update_planner.py
from datetime import date

from ledger_reporter.domain.models import ReportingPeriod
from ledger_reporter.services.update_planner import plan_updates


def period(start: int, end: int, label: str) -> ReportingPeriod:
    return ReportingPeriod(date(2026, 8, start), date(2026, 8, end), label)


def test_first_august_run_does_not_refresh_frozen_july() -> None:
    plan = plan_updates(date(2026, 8, 7), set(), date(2026, 7, 31))
    assert plan.refresh_periods == ()
    assert [(item.start, item.end) for item in plan.periods] == [
        (date(2026, 8, 1), date(2026, 8, 6))
    ]


def test_refreshes_latest_and_previous_week() -> None:
    existing = {period(1, 6, "W1（8.1-8.6）")}
    plan = plan_updates(date(2026, 8, 14), existing, date(2026, 7, 31))
    assert [(item.start.day, item.end.day) for item in plan.new_periods] == [(7, 13)]
    assert [(item.start.day, item.end.day) for item in plan.refresh_periods] == [(1, 6)]
    assert [(item.start.day, item.end.day) for item in plan.periods] == [(1, 6), (7, 13)]


def test_backfills_missed_periods() -> None:
    plan = plan_updates(date(2026, 8, 28), set(), date(2026, 7, 31))
    assert [(item.start.day, item.end.day) for item in plan.periods] == [
        (1, 6), (7, 13), (14, 20), (21, 27)
    ]
```

- [ ] **Step 2: 运行测试并确认计划函数不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_update_planner.py -q`

Expected: FAIL importing `plan_updates`。

- [ ] **Step 3: 实现可排序更新计划**

在 `domain/models.py` 添加：

```python
@dataclass(frozen=True, slots=True)
class UpdatePlan:
    latest: ReportingPeriod
    new_periods: tuple[ReportingPeriod, ...]
    refresh_periods: tuple[ReportingPeriod, ...]

    @property
    def periods(self) -> tuple[ReportingPeriod, ...]:
        return tuple(sorted(set(self.new_periods + self.refresh_periods), key=lambda item: item.start))
```

```python
# src/ledger_reporter/services/update_planner.py
from datetime import date, timedelta

from ledger_reporter.domain.models import ReportingPeriod, UpdatePlan
from ledger_reporter.domain.periods import latest_completed_week, month_weeks, previous_week


def _periods_after(day: date, through: ReportingPeriod) -> list[ReportingPeriod]:
    cursor = day.replace(day=1)
    found: list[ReportingPeriod] = []
    while cursor <= through.end:
        found.extend(
            item for item in month_weeks(cursor.year, cursor.month)
            if item.start > day and item.end <= through.end
        )
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return found


def plan_updates(today: date, existing: set[ReportingPeriod], frozen_through: date) -> UpdatePlan:
    latest = latest_completed_week(today)
    expected = _periods_after(frozen_through, latest)
    new_periods = tuple(item for item in expected if item not in existing)
    refresh_periods = tuple(
        sorted(
            {
                item for item in (previous_week(latest), latest)
                if item in existing and item.start > frozen_through
            },
            key=lambda item: item.start,
        )
    )
    return UpdatePlan(latest, new_periods, refresh_periods)
```

- [ ] **Step 4: 提取并加载真实固定基线**

```python
# tools/extract_baseline.py
import json
import sys
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook


def label(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return f"{value.year}年{value.month}月"
    return str(value or "")


source = Path(sys.argv[1])
destination = Path(sys.argv[2])
book = load_workbook(source, read_only=True, data_only=True)
sheet = book["Sheet1"]
rows = []
for row_number in range(3, 29):
    values = [sheet.cell(row_number, column).value for column in range(1, 12)]
    rows.append({"label": label(values[0]), "values": values[1:]})
payload = {
    "version": "fy2026-requirement-2026-08-10-v1",
    "fiscal_year": 2026,
    "frozen_through": "2026-07-31",
    "rows": rows,
}
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
```

Run:

```powershell
.\.venv\Scripts\python.exe tools\extract_baseline.py "D:\台账\需求(1).xlsx" "src\ledger_reporter\resources\fy2026_baseline.json"
```

实现加载器：

```python
# src/ledger_reporter/services/baseline.py
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ledger_reporter.app_paths import resource_path


@dataclass(frozen=True, slots=True)
class Baseline:
    version: str
    fiscal_year: int
    frozen_through: date
    rows: tuple[dict[str, object], ...]


def load_fy2026_baseline() -> Baseline:
    payload = json.loads(resource_path("fy2026_baseline.json").read_text(encoding="utf-8"), parse_float=Decimal)
    return Baseline(
        version=str(payload["version"]),
        fiscal_year=int(payload["fiscal_year"]),
        frozen_through=date.fromisoformat(payload["frozen_through"]),
        rows=tuple(payload["rows"]),
    )
```

增加固定基线边界回归测试：

```python
# tests/services/test_baseline.py
from decimal import Decimal

from ledger_reporter.services.baseline import load_fy2026_baseline


def test_frozen_baseline_matches_requirement_template_boundary() -> None:
    baseline = load_fy2026_baseline()
    assert baseline.version == "fy2026-requirement-2026-08-10-v1"
    assert len(baseline.rows) == 26
    assert baseline.rows[0]["label"] == "Q1(26.4-26.6)"
    assert baseline.rows[-1]["label"] == "W5（24-31）"
    assert baseline.rows[-1]["values"][:6] == [
        168,
        Decimal("-729734.851957015"),
        9,
        Decimal("14016.4289426375"),
        Decimal("85644.23"),
        Decimal("729.266484493151"),
    ]
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_update_planner.py tests/services/test_baseline.py -q`

Expected: `4 passed`；同时确认 JSON 的 26 行范围与真实模板第 3 至 28 行一致。

- [ ] **Step 5: 提醒用户并提交基线与更新计划**

```powershell
git add tools/extract_baseline.py src/ledger_reporter/resources/fy2026_baseline.json src/ledger_reporter/services/baseline.py src/ledger_reporter/services/update_planner.py src/ledger_reporter/domain/models.py tests/services/test_update_planner.py tests/services/test_baseline.py
git commit -m "feat: add frozen baseline and weekly update plan"
```

### Task 7: SQLite 历史事务与财年隔离

**Files:**
- Create: `src/ledger_reporter/services/history.py`
- Create: `tests/services/test_history.py`

- [ ] **Step 1: 写保存、覆盖、财年隔离和回滚测试**

```python
# tests/services/test_history.py
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from ledger_reporter.domain.models import PeriodMetrics, ReportingPeriod, WeekSnapshot
from ledger_reporter.services.history import HistoryRepository


def snapshot(year: int, profit: str) -> WeekSnapshot:
    period = ReportingPeriod(date(year, 8, 1), date(year, 8, 6), "W1（8.1-8.6）")
    return WeekSnapshot(year, period, PeriodMetrics(project_profit=Decimal(profit)))


def test_upsert_replaces_same_week(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    repository.save_weeks([snapshot(2026, "10")])
    repository.save_weeks([snapshot(2026, "20")])
    assert repository.load_weeks(2026)[0].metrics.project_profit == Decimal("20")


def test_fiscal_years_are_isolated(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    repository.save_weeks([snapshot(2026, "10"), snapshot(2027, "30")])
    assert len(repository.load_weeks(2026)) == 1
    assert len(repository.load_weeks(2027)) == 1


def test_transaction_rolls_back_all_weeks(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    with pytest.raises(RuntimeError):
        with repository.transaction() as connection:
            repository.save_weeks([snapshot(2026, "10")], connection)
            repository.save_generation(
                2026,
                datetime(2026, 8, 7, tzinfo=timezone.utc),
                "fy2026-requirement-2026-08-10-v1",
                {"sha256": "abc"},
                {"sha256": "def"},
                connection,
            )
            raise RuntimeError("stop")
    assert repository.load_weeks(2026) == []
    assert repository.latest_generation(2026) is None


def test_records_baseline_version_and_source_summaries(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    generated_at = datetime(2026, 8, 7, 10, 30, tzinfo=timezone.utc)
    repository.save_generation(
        2026,
        generated_at,
        "fy2026-requirement-2026-08-10-v1",
        {"name": "funds.xlsx", "size": 12, "sha256": "abc"},
        {"name": "operations.xlsx", "size": 34, "sha256": "def"},
    )
    saved = repository.latest_generation(2026)
    assert saved["generated_at"] == generated_at.isoformat()
    assert saved["baseline_version"] == "fy2026-requirement-2026-08-10-v1"
    assert saved["funds"]["sha256"] == "abc"
    assert saved["operations"]["sha256"] == "def"
```

- [ ] **Step 2: 运行测试并确认仓储不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_history.py -q`

Expected: FAIL importing `HistoryRepository`。

- [ ] **Step 3: 实现确定字段的 SQLite schema 和事务**

```python
# src/ledger_reporter/services/history.py
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ledger_reporter.domain.models import PeriodMetrics, ReportingPeriod, WeekSnapshot


COLUMNS = (
    "project_count", "project_profit", "scatter_count", "scatter_profit",
    "fund_amount", "fund_profit", "card_count", "card_profit",
)


class HistoryRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS week_snapshots (
                    fiscal_year INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    label TEXT NOT NULL,
                    project_count INTEGER NOT NULL,
                    project_profit TEXT NOT NULL,
                    scatter_count INTEGER NOT NULL,
                    scatter_profit TEXT NOT NULL,
                    fund_amount TEXT NOT NULL,
                    fund_profit TEXT NOT NULL,
                    card_count INTEGER NOT NULL,
                    card_profit TEXT NOT NULL,
                    PRIMARY KEY (fiscal_year, start_date, end_date)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS generation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fiscal_year INTEGER NOT NULL,
                    generated_at TEXT NOT NULL,
                    baseline_version TEXT NOT NULL,
                    funds_summary TEXT NOT NULL,
                    operations_summary TEXT NOT NULL
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @contextmanager
    def transaction(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_weeks(self, weeks: list[WeekSnapshot], connection=None) -> None:
        owner = connection is None
        connection = connection or self._connect()
        try:
            for item in weeks:
                m = item.metrics
                connection.execute("""
                    INSERT OR REPLACE INTO week_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item.fiscal_year, item.period.start.isoformat(), item.period.end.isoformat(), item.period.label,
                    m.project_count, str(m.project_profit), m.scatter_count, str(m.scatter_profit),
                    str(m.fund_amount), str(m.fund_profit), m.card_count, str(m.card_profit),
                ))
            if owner:
                connection.commit()
        finally:
            if owner:
                connection.close()

    def load_weeks(self, fiscal_year: int) -> list[WeekSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM week_snapshots WHERE fiscal_year = ? ORDER BY start_date", (fiscal_year,)
            ).fetchall()
        return [WeekSnapshot(
            row[0], ReportingPeriod(date.fromisoformat(row[1]), date.fromisoformat(row[2]), row[3]),
            PeriodMetrics(row[4], Decimal(row[5]), row[6], Decimal(row[7]), Decimal(row[8]), Decimal(row[9]), row[10], Decimal(row[11])),
        ) for row in rows]

    def save_generation(
        self,
        fiscal_year: int,
        generated_at: datetime,
        baseline_version: str,
        funds: dict[str, object],
        operations: dict[str, object],
        connection=None,
    ) -> None:
        owner = connection is None
        connection = connection or self._connect()
        try:
            connection.execute(
                """INSERT INTO generation_runs
                   (fiscal_year, generated_at, baseline_version, funds_summary, operations_summary)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    fiscal_year,
                    generated_at.isoformat(),
                    baseline_version,
                    json.dumps(funds, ensure_ascii=False, sort_keys=True),
                    json.dumps(operations, ensure_ascii=False, sort_keys=True),
                ),
            )
            if owner:
                connection.commit()
        finally:
            if owner:
                connection.close()

    def latest_generation(self, fiscal_year: int) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT generated_at, baseline_version, funds_summary, operations_summary
                   FROM generation_runs WHERE fiscal_year = ? ORDER BY id DESC LIMIT 1""",
                (fiscal_year,),
            ).fetchone()
        if row is None:
            return None
        return {
            "generated_at": row[0],
            "baseline_version": row[1],
            "funds": json.loads(row[2]),
            "operations": json.loads(row[3]),
        }
```

- [ ] **Step 4: 运行仓储测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_history.py -q`

Expected: `4 passed`。

- [ ] **Step 5: 提醒用户并提交历史存储**

```powershell
git add src/ledger_reporter/services/history.py tests/services/test_history.py
git commit -m "feat: persist fiscal week history transactionally"
```

### Task 8: 报表服务编排与聚合

**Files:**
- Modify: `src/ledger_reporter/domain/models.py`
- Create: `src/ledger_reporter/services/report_service.py`
- Create: `tests/services/test_report_service.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: 写冻结基线、动态周和最新业务表组合测试**

```python
# tests/services/test_report_service.py
from datetime import date
from decimal import Decimal

from ledger_reporter.domain.models import FundRecord, OperationalRecord
from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService


def test_generates_latest_two_weeks_without_touching_baseline(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    operations = [OperationalRecord("1", "BSA", "LAX", date(2026, 8, 3), "供应商", Decimal("1000"), Decimal("100"))]
    funds = [FundRecord("广州美鑫通国际供应链有限公司", date(2026, 8, 4), Decimal("900"), Decimal("5"))]
    service = ReportService(repository)
    bundle = service.generate_from_records(date(2026, 8, 7), operations, funds)
    assert bundle.fiscal_year == 2026
    assert bundle.latest_period.end == date(2026, 8, 6)
    assert bundle.baseline_rows[-1]["label"] == "W5（24-31）"
    assert len(repository.load_weeks(2026)) == 1
    assert repository.latest_generation(2026)["baseline_version"] == "fy2026-requirement-2026-08-10-v1"
```

- [ ] **Step 2: 运行测试并确认服务不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_report_service.py -q`

Expected: FAIL importing `ReportService`。

- [ ] **Step 3: 定义最终 ReportBundle**

在 `domain/models.py` 添加：

```python
@dataclass(frozen=True, slots=True)
class ReportBundle:
    fiscal_year: int
    latest_period: ReportingPeriod
    baseline_rows: tuple[dict[str, object], ...]
    weeks: tuple[WeekSnapshot, ...]
    business: BusinessTable


@dataclass(frozen=True, slots=True)
class SourceInspection:
    fiscal_year: int
    update_plan: UpdatePlan
```

- [ ] **Step 4: 实现只读输入、计算后事务保存的服务**

```python
# src/ledger_reporter/services/report_service.py
import hashlib
from datetime import date, datetime
from pathlib import Path

from ledger_reporter.domain.models import (
    FundRecord,
    OperationalRecord,
    ReportBundle,
    SourceInspection,
    UpdatePlan,
    WeekSnapshot,
)
from ledger_reporter.domain.periods import fiscal_year_for
from ledger_reporter.io.workbooks import read_funds, read_operations
from ledger_reporter.services.baseline import Baseline, load_fy2026_baseline
from ledger_reporter.services.calculations import calculate_business_table, calculate_period
from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.update_planner import plan_updates


class ReportService:
    def __init__(self, history: HistoryRepository) -> None:
        self.history = history

    def _plan(self, today: date) -> tuple[int, Baseline, UpdatePlan]:
        fiscal_year = fiscal_year_for(today)
        baseline = load_fy2026_baseline()
        frozen_through = baseline.frozen_through if fiscal_year == 2026 else date(fiscal_year, 3, 31)
        existing = self.history.load_weeks(fiscal_year)
        plan = plan_updates(today, {item.period for item in existing}, frozen_through)
        return fiscal_year, baseline, plan

    def inspect_sources(self, funds_path: Path, operations_path: Path, today: date) -> SourceInspection:
        fiscal_year, _baseline, plan = self._plan(today)
        operations = read_operations(operations_path)
        funds = read_funds(funds_path, {fiscal_year, fiscal_year + 1})
        for period in plan.periods:
            calculate_period(period, operations, funds)
        calculate_business_table(plan.latest, operations)
        return SourceInspection(fiscal_year, plan)

    def generate_from_records(
        self,
        today: date,
        operations: list[OperationalRecord],
        funds: list[FundRecord],
        *,
        generated_at: datetime | None = None,
        funds_summary: dict[str, object] | None = None,
        operations_summary: dict[str, object] | None = None,
    ) -> ReportBundle:
        fiscal_year, baseline, plan = self._plan(today)
        calculated = [WeekSnapshot(fiscal_year, period, calculate_period(period, operations, funds)) for period in plan.periods]
        with self.history.transaction() as connection:
            self.history.save_weeks(calculated, connection)
            self.history.save_generation(
                fiscal_year,
                generated_at or datetime.now().astimezone(),
                baseline.version if fiscal_year == 2026 else "none",
                funds_summary or {"name": "in-memory", "size": 0, "sha256": ""},
                operations_summary or {"name": "in-memory", "size": 0, "sha256": ""},
                connection,
            )
        weeks = tuple(self.history.load_weeks(fiscal_year))
        business = calculate_business_table(plan.latest, operations)
        baseline_rows = baseline.rows if fiscal_year == 2026 else tuple()
        return ReportBundle(fiscal_year, plan.latest, baseline_rows, weeks, business)

    @staticmethod
    def _source_summary(path: Path) -> dict[str, object]:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return {"name": path.name, "size": path.stat().st_size, "sha256": digest.hexdigest()}

    def generate(self, funds_path: Path, operations_path: Path, today: date) -> ReportBundle:
        fiscal_year = fiscal_year_for(today)
        operations = read_operations(operations_path)
        funds = read_funds(funds_path, {fiscal_year, fiscal_year + 1})
        return self.generate_from_records(
            today,
            operations,
            funds,
            funds_summary=self._source_summary(funds_path),
            operations_summary=self._source_summary(operations_path),
        )
```

创建后续导出与 UI 测试共用的完整 fixture：

```python
# tests/conftest.py
from datetime import date
from decimal import Decimal

import pytest

from ledger_reporter.domain.models import (
    BusinessMetric,
    BusinessTable,
    PeriodMetrics,
    ReportBundle,
    ReportingPeriod,
    WeekSnapshot,
)
from ledger_reporter.rules import BUSINESS_RULES


@pytest.fixture
def report_bundle() -> ReportBundle:
    period = ReportingPeriod(date(2026, 8, 1), date(2026, 8, 6), "W1（8.1-8.6）")
    metrics = PeriodMetrics(2, Decimal("100"), 1, Decimal("20"), Decimal("900"), Decimal("5"))
    business_rows = tuple(BusinessMetric(name, 1, Decimal("100"), Decimal("1000")) for name, _ in BUSINESS_RULES)
    business = BusinessTable(period, business_rows, BusinessMetric("销售额合计", 12, Decimal("1200"), Decimal("12000")))
    baseline = ({"label": "W5（24-31）", "values": [168, -729734.85, 9, 14016.43, 85644.23, 729.27, 0, 0, -714989.15, None]},)
    return ReportBundle(2026, period, baseline, (WeekSnapshot(2026, period, metrics),), business)
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/services/test_report_service.py -q`

Expected: `1 passed`。

- [ ] **Step 5: 提醒用户并提交报表服务**

```powershell
git add src/ledger_reporter/domain/models.py src/ledger_reporter/services/report_service.py tests/services/test_report_service.py tests/conftest.py
git commit -m "feat: orchestrate fiscal report generation"
```

### Task 9: 统一 TableSpec 与 Excel 导出

**Files:**
- Create: `src/ledger_reporter/presentation/models.py`
- Create: `src/ledger_reporter/presentation/theme.py`
- Create: `src/ledger_reporter/presentation/builders.py`
- Create: `src/ledger_reporter/exporters/excel.py`
- Create: `tests/exporters/test_excel_export.py`

- [ ] **Step 1: 写正式工作表数量、标题、说明行和公式错误测试**

```python
# tests/exporters/test_excel_export.py
from openpyxl import load_workbook

from ledger_reporter.exporters.excel import export_excel


def test_exports_only_two_formal_sheets(report_bundle, tmp_path) -> None:
    output = tmp_path / "2026财年台账报表.xlsx"
    export_excel(report_bundle, output)
    book = load_workbook(output, data_only=False)
    assert book.sheetnames == ["经营汇总", "自营项目周报"]
    assert book["经营汇总"]["A1"].value == "日期"
    all_values = [cell.value for row in book["经营汇总"].iter_rows() for cell in row]
    assert "数据源" not in all_values
    assert not any(isinstance(value, str) and value.startswith("#") for value in all_values)
```

- [ ] **Step 2: 运行导出测试并确认模块不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/exporters/test_excel_export.py -q`

Expected: FAIL importing `export_excel`。

- [ ] **Step 3: 定义与格式无关的表格结构**

```python
# src/ledger_reporter/presentation/models.py
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CellSpec:
    row: int
    column: int
    value: Any
    style: str = "body"
    number_format: str | None = None


@dataclass(frozen=True, slots=True)
class MergeSpec:
    start_row: int
    start_column: int
    end_row: int
    end_column: int


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    cells: tuple[CellSpec, ...]
    merges: tuple[MergeSpec, ...]
    column_widths: tuple[float, ...]
    row_heights: tuple[float, ...]
```

在 `builders.py` 写入以下完整聚合骨架；动态数值保持 `Decimal`，第二张表利润和销售额除以 `Decimal("10000")`：

```python
# src/ledger_reporter/presentation/builders.py
from collections import defaultdict
from decimal import Decimal

from ledger_reporter.domain.models import PeriodMetrics
from ledger_reporter.rules import MONTH_TARGET, QUARTER_TARGET
from .models import CellSpec, MergeSpec, TableSpec


ZERO = Decimal("0")
BUSINESS_META = (
    ("WWP", "dl :26.9.31", "1.02%"),
    ("欧展-固定位（LAX）", "26.1.1--27.1.31", "2.41%"),
    ("欧展-差价", "长期", ""),
    ("金开宇", "长期", "固定差价2%"),
    ("厦门伦升", "长期", "1.52%"),
    ("印华固定位OSL", "dl :26.12.31", "0.08%"),
    ("印华固定位ORD", "26.1.17--27.1.14", ""),
    ("印华固定位LGG", "26.1.1--26.12.29", ""),
    ("美鑫通GRU", "26.6.8--26.12.31", "合计260W"),
    ("迅達航空", "26.6.1--26.12.31", "6.92%"),
    ("散采", "", ""),
)


def _decimal(value: object) -> Decimal:
    return ZERO if value in (None, "", "-") else Decimal(str(value).replace(",", ""))


def _metrics_from_baseline(values: list[object]) -> PeriodMetrics:
    return PeriodMetrics(
        project_count=int(values[0] or 0),
        project_profit=_decimal(values[1]),
        scatter_count=int(values[2] or 0),
        scatter_profit=_decimal(values[3]),
        fund_amount=_decimal(values[4]),
        fund_profit=_decimal(values[5]),
        card_count=int(values[6] or 0),
        card_profit=_decimal(values[7]),
    )


def _add(left: PeriodMetrics, right: PeriodMetrics) -> PeriodMetrics:
    return PeriodMetrics(
        left.project_count + right.project_count,
        left.project_profit + right.project_profit,
        left.scatter_count + right.scatter_count,
        left.scatter_profit + right.scatter_profit,
        left.fund_amount + right.fund_amount,
        left.fund_profit + right.fund_profit,
        left.card_count + right.card_count,
        left.card_profit + right.card_profit,
    )


def _sum_metrics(items) -> PeriodMetrics:
    result = PeriodMetrics()
    for item in items:
        result = _add(result, item.metrics)
    return result


def _quarter_number(month: int) -> int:
    return ((month - 4) % 12) // 3 + 1


def _quarter_label(fiscal_year: int, number: int) -> str:
    start_month = 4 + (number - 1) * 3
    start_year = fiscal_year
    while start_month > 12:
        start_month -= 12
        start_year += 1
    end_month = start_month + 2
    end_year = start_year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    return f"Q{number}({str(start_year)[-2:]}.{start_month}-{str(end_year)[-2:]}.{end_month})"


def _summary_rows(bundle) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    quarter_indexes: dict[int, int] = {}
    for raw in bundle.baseline_rows:
        label = str(raw["label"])
        values = list(raw["values"])
        kind = "quarter" if label.startswith("Q") else "month" if "年" in label else "week"
        target = _decimal(values[9]) if values[9] not in (None, "") else None
        rows.append({"kind": kind, "label": label, "metrics": _metrics_from_baseline(values), "target": target})
        if kind == "quarter":
            quarter_indexes[int(label[1])] = len(rows) - 1

    by_month = defaultdict(list)
    for week in bundle.weeks:
        by_month[(week.period.start.year, week.period.start.month)].append(week)

    for (year, month), weeks in sorted(by_month.items()):
        number = _quarter_number(month)
        month_metrics = _sum_metrics(weeks)
        if number in quarter_indexes:
            index = quarter_indexes[number]
            rows[index]["metrics"] = _add(rows[index]["metrics"], month_metrics)
        else:
            quarter_indexes[number] = len(rows)
            rows.append({
                "kind": "quarter",
                "label": _quarter_label(bundle.fiscal_year, number),
                "metrics": month_metrics,
                "target": QUARTER_TARGET,
            })
        rows.append({"kind": "month", "label": f"{year}年{month}月", "metrics": month_metrics, "target": MONTH_TARGET})
        rows.extend({"kind": "week", "label": week.period.label, "metrics": week.metrics, "target": None} for week in weeks)
    return rows


def _summary_table(bundle) -> TableSpec:
    cells = [
        CellSpec(1, 1, "日期", "header"), CellSpec(1, 2, "项目订单", "header"),
        CellSpec(1, 4, "散采订单", "header"), CellSpec(1, 6, "资金订单", "header"),
        CellSpec(1, 8, "卡转订单", "header"), CellSpec(1, 10, "合计利润", "header"),
        CellSpec(1, 11, "目标", "header"), CellSpec(1, 12, "完成度", "header"),
        CellSpec(2, 2, "板位数", "header"), CellSpec(2, 3, "预估利润", "header"),
        CellSpec(2, 4, "板位数", "header"), CellSpec(2, 5, "预估利润", "header"),
        CellSpec(2, 6, "放款金额", "header"), CellSpec(2, 7, "预估利润", "header"),
        CellSpec(2, 8, "车次", "header"), CellSpec(2, 9, "预估利润", "header"),
    ]
    for row_number, item in enumerate(_summary_rows(bundle), 3):
        m = item["metrics"]
        target = item["target"]
        completion = None if target in (None, ZERO) else m.total_profit / target
        style = item["kind"] if item["kind"] in {"quarter", "month"} else "body"
        values = (
            item["label"], m.project_count, m.project_profit, m.scatter_count, m.scatter_profit,
            m.fund_amount, m.fund_profit, m.card_count, m.card_profit, m.total_profit, target, completion,
        )
        formats = (None, "#,##0", "#,##0.00", "#,##0", "#,##0.00", "#,##0.00", "#,##0.00", "#,##0", "#,##0.00", "#,##0.00", "#,##0.00", "0%")
        cells.extend(CellSpec(row_number, column, value, style, formats[column - 1]) for column, value in enumerate(values, 1))
    merges = (
        MergeSpec(1, 1, 2, 1), MergeSpec(1, 2, 1, 3), MergeSpec(1, 4, 1, 5),
        MergeSpec(1, 6, 1, 7), MergeSpec(1, 8, 1, 9), MergeSpec(1, 10, 2, 10),
        MergeSpec(1, 11, 2, 11), MergeSpec(1, 12, 2, 12),
    )
    row_count = 2 + len(_summary_rows(bundle))
    return TableSpec("经营汇总", tuple(cells), merges, (18, 12, 16, 12, 16, 18, 16, 10, 14, 18, 16, 14), tuple([28, 24] + [22] * (row_count - 2)))


def _business_table(bundle) -> TableSpec:
    title = f"{bundle.latest_period.start.year}年{bundle.latest_period.start.month}月{bundle.latest_period.label}自营项目数据情况,单位：万元"
    cells = [CellSpec(1, 1, title, "total")]
    headers = ("业务名称", "项目周期", "利润率测算", "完成数量", "预估利润", "预估利润率")
    cells.extend(CellSpec(2, column, value, "header") for column, value in enumerate(headers, 1))
    metrics = {item.name: item for item in bundle.business.rows}
    for row_number, (name, cycle, measured_rate) in enumerate(BUSINESS_META, 3):
        metric = metrics[name]
        values = (name, cycle, measured_rate, metric.count, metric.profit / Decimal("10000"), metric.margin)
        formats = (None, None, None, "#,##0", "#,##0.00", "0.00%")
        cells.extend(CellSpec(row_number, column, value, "body", formats[column - 1]) for column, value in enumerate(values, 1))
    total_row = 3 + len(BUSINESS_META)
    total = bundle.business.total
    total_values = (f"销售额合计：{total.receivable / Decimal('10000'):.0f}", "", "", total.count, total.profit / Decimal("10000"), total.margin)
    cells.extend(CellSpec(total_row, column, value, "total", "0.00%" if column == 6 else None) for column, value in enumerate(total_values, 1))
    return TableSpec(
        "自营项目周报", tuple(cells), (MergeSpec(1, 1, 1, 6),),
        (27, 24, 18, 14, 16, 16), tuple([34, 26] + [23] * (total_row - 2)),
    )


def build_tables(bundle) -> tuple[TableSpec, TableSpec]:
    return _summary_table(bundle), _business_table(bundle)
```

- [ ] **Step 4: 实现主题和 Excel 写入器**

```python
# src/ledger_reporter/presentation/theme.py
STYLES = {
    "header": {"fill": "91AADD", "bold": True, "align": "center"},
    "quarter": {"fill": "EF9CA5", "bold": True, "align": "center"},
    "month": {"fill": "FFFFFF", "bold": True, "align": "right"},
    "total": {"fill": "60708E", "bold": True, "font": "FFFFFF", "align": "center"},
    "body": {"fill": "FFFFFF", "bold": False, "align": "right"},
}
```

```python
# src/ledger_reporter/exporters/excel.py
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from ledger_reporter.presentation.builders import build_tables
from ledger_reporter.presentation.theme import STYLES


def _excel_value(value):
    return float(value) if isinstance(value, Decimal) else value


def export_excel(bundle, output: Path) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    thin = Side(style="thin", color="B7C0BB")
    for table in build_tables(bundle):
        sheet = workbook.create_sheet(table.name)
        sheet.sheet_view.showGridLines = False
        for cell_spec in table.cells:
            cell = sheet.cell(cell_spec.row, cell_spec.column, _excel_value(cell_spec.value))
            style = STYLES[cell_spec.style]
            cell.fill = PatternFill("solid", fgColor=style["fill"])
            cell.font = Font(name="Arial", bold=style["bold"], color=style.get("font", "000000"))
            cell.alignment = Alignment(horizontal=style["align"], vertical="center")
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            if cell_spec.number_format:
                cell.number_format = cell_spec.number_format
        for merge in table.merges:
            sheet.merge_cells(start_row=merge.start_row, start_column=merge.start_column, end_row=merge.end_row, end_column=merge.end_column)
        for index, width in enumerate(table.column_widths, 1):
            sheet.column_dimensions[chr(64 + index)].width = width
        for index, height in enumerate(table.row_heights, 1):
            sheet.row_dimensions[index].height = height
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output)
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/exporters/test_excel_export.py -q`

Expected: `1 passed`。

- [ ] **Step 5: 提醒用户并提交 Excel 导出**

```powershell
git add src/ledger_reporter/presentation src/ledger_reporter/exporters/excel.py tests/exporters/test_excel_export.py
git commit -m "feat: export styled fiscal Excel reports"
```

### Task 10: PNG 渲染与像素级检查

**Files:**
- Create: `src/ledger_reporter/exporters/png.py`
- Create: `tests/exporters/test_png_export.py`

- [ ] **Step 1: 写双图片、尺寸和非空像素测试**

```python
# tests/exporters/test_png_export.py
from PIL import Image, ImageStat

from ledger_reporter.exporters.png import export_pngs


def test_exports_two_nonblank_pngs(report_bundle, tmp_path) -> None:
    paths = export_pngs(report_bundle, tmp_path)
    assert [path.name for path in paths] == ["经营汇总.png", "自营项目周报.png"]
    for path in paths:
        image = Image.open(path).convert("RGB")
        assert image.width >= 1000
        assert image.height >= 400
        assert sum(ImageStat.Stat(image).var) > 0
```

- [ ] **Step 2: 运行测试并确认 PNG 导出器不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/exporters/test_png_export.py -q`

Expected: FAIL importing `export_pngs`。

- [ ] **Step 3: 实现共享 TableSpec 的 Pillow 渲染器**

```python
# src/ledger_reporter/exporters/png.py
from pathlib import Path

from decimal import Decimal

from PIL import Image, ImageDraw, ImageFont

from ledger_reporter.presentation.builders import build_tables
from ledger_reporter.presentation.theme import STYLES


def _font(size: int, bold: bool):
    names = [
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "Arial Bold.ttf" if bold else "Arial.ttf",
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _format(value, number_format: str | None) -> str:
    if value is None:
        return "-"
    if number_format in {"0%", "0.00%"}:
        precision = 0 if number_format == "0%" else 2
        return f"{Decimal(str(value)):.{precision}%}"
    if number_format == "#,##0.00":
        return f"{Decimal(str(value)):,.2f}"
    if number_format == "#,##0":
        return f"{Decimal(str(value)):,.0f}"
    return str(value)


def render_table(table, scale: int = 2) -> Image.Image:
    widths = [int(value * 8 * scale) for value in table.column_widths]
    heights = [int(value * 1.35 * scale) for value in table.row_heights]
    image = Image.new("RGB", (sum(widths), sum(heights)), "FFFFFF")
    draw = ImageDraw.Draw(image)
    x_positions = [0]
    y_positions = [0]
    for width in widths:
        x_positions.append(x_positions[-1] + width)
    for height in heights:
        y_positions.append(y_positions[-1] + height)
    merges = {(item.start_row, item.start_column): item for item in table.merges}
    covered = {
        (row, column)
        for item in table.merges
        for row in range(item.start_row, item.end_row + 1)
        for column in range(item.start_column, item.end_column + 1)
        if (row, column) != (item.start_row, item.start_column)
    }
    for cell in table.cells:
        if (cell.row, cell.column) in covered:
            continue
        merge = merges.get((cell.row, cell.column))
        end_row = merge.end_row if merge else cell.row
        end_column = merge.end_column if merge else cell.column
        x0, x1 = x_positions[cell.column - 1], x_positions[end_column]
        y0, y1 = y_positions[cell.row - 1], y_positions[end_row]
        style = STYLES[cell.style]
        draw.rectangle((x0, y0, x1, y1), fill="#" + style["fill"], outline="#B7C0BB", width=1)
        font = _font(10 * scale, style["bold"])
        text = _format(cell.value, cell.number_format)
        box = draw.textbbox((0, 0), text, font=font)
        text_width = box[2] - box[0]
        if style["align"] == "center":
            text_x = x0 + (x1 - x0 - text_width) / 2
        elif style["align"] == "right":
            text_x = x1 - text_width - 6 * scale
        else:
            text_x = x0 + 6 * scale
        text_y = y0 + max(2 * scale, (y1 - y0 - (box[3] - box[1])) / 2)
        draw.text((text_x, text_y), text, fill="#" + style.get("font", "000000"), font=font)
    return image


def export_pngs(bundle, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for table in build_tables(bundle):
        path = output_dir / f"{table.name}.png"
        render_table(table).save(path, "PNG")
        paths.append(path)
    return paths
```

- [ ] **Step 4: 增加合并单元格和格式化回归断言**

在 `tests/exporters/test_png_export.py` 添加：

```python
from decimal import Decimal

from ledger_reporter.exporters.png import _format


def test_formats_report_numbers_without_excel() -> None:
    assert _format(Decimal("-0.4231"), "0%") == "-42%"
    assert _format(Decimal("1234.5"), "#,##0.00") == "1,234.50"
    assert _format(None, "0.00%") == "-"
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/exporters/test_png_export.py -q`

Expected: `1 passed`，并用 `Image.open` 确认两张图片可加载。

- [ ] **Step 5: 提醒用户并提交 PNG 导出**

```powershell
git add src/ledger_reporter/exporters/png.py tests/exporters/test_png_export.py
git commit -m "feat: render report tables as PNG"
```

### Task 11: PySide6 主窗口、后台生成与收起式预览

**Files:**
- Create: `src/ledger_reporter/ui/source_picker.py`
- Create: `src/ledger_reporter/ui/workers.py`
- Create: `src/ledger_reporter/ui/preview_dialog.py`
- Create: `src/ledger_reporter/ui/main_window.py`
- Create: `src/ledger_reporter/__main__.py`
- Create: `tests/ui/test_main_window.py`

- [ ] **Step 1: 写导入就绪、生成完成和预览按钮状态测试**

```python
# tests/ui/test_main_window.py
from pathlib import Path

import pytest

from ledger_reporter.domain.models import SourceInspection, UpdatePlan
from ledger_reporter.ui.main_window import MainWindow


class FakeReportService:
    def __init__(self, bundle) -> None:
        self.bundle = bundle

    def generate(self, funds, operations, today):
        return self.bundle

    def inspect_sources(self, funds, operations, today):
        period = self.bundle.latest_period
        return SourceInspection(self.bundle.fiscal_year, UpdatePlan(period, (period,), ()))


@pytest.fixture
def fake_report_service(report_bundle):
    return FakeReportService(report_bundle)


def test_generate_requires_two_existing_sources(qtbot, tmp_path: Path, fake_report_service) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    assert not window.generate_button.isEnabled()
    funds = tmp_path / "funds.xlsx"
    operations = tmp_path / "operations.xlsx"
    funds.touch()
    operations.touch()
    window.funds_picker.set_path(funds)
    window.operations_picker.set_path(operations)
    assert window.validate_button.isEnabled()
    assert not window.generate_button.isEnabled()
    assert not window.preview_button.isEnabled()
    period = fake_report_service.bundle.latest_period
    window.on_validation_succeeded(SourceInspection(2026, UpdatePlan(period, (period,), ())))
    assert window.generate_button.isEnabled()
    assert "新增" in window.status_label.text()


def test_success_enables_preview_and_exports(qtbot, fake_report_service, report_bundle) -> None:
    window = MainWindow(fake_report_service)
    qtbot.addWidget(window)
    window.on_generation_succeeded(report_bundle)
    assert window.preview_button.isEnabled()
    assert window.excel_button.isEnabled()
    assert window.png_button.isEnabled()
```

- [ ] **Step 2: 运行 UI 测试并确认窗口不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/ui/test_main_window.py -q`

Expected: FAIL importing `MainWindow`。

- [ ] **Step 3: 实现可拖放的数据源选择器和主窗口状态**

```python
# src/ledger_reporter/ui/source_picker.py
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QWidget


class SourcePicker(QWidget):
    path_changed = Signal(Path)

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._path: Path | None = None
        self.label = QLabel(f"{title}：未选择")
        self.button = QPushButton("选择文件")
        self.button.clicked.connect(self.choose_file)
        layout = QHBoxLayout(self)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.button)

    @property
    def path(self) -> Path | None:
        return self._path

    def set_path(self, path: Path) -> None:
        self._path = path
        self.label.setText(path.name)
        self.path_changed.emit(path)

    def choose_file(self) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "选择 XLSX", "", "Excel 工作簿 (*.xlsx)")
        if value:
            self.set_path(Path(value))

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".xlsx"):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.set_path(Path(event.mimeData().urls()[0].toLocalFile()))
        event.acceptProposedAction()
```

```python
# src/ledger_reporter/ui/main_window.py
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from .source_picker import SourcePicker


class MainWindow(QMainWindow):
    def __init__(self, report_service) -> None:
        super().__init__()
        self.report_service = report_service
        self.bundle = None
        self.inspection = None
        self.setWindowTitle("台账报表生成器")
        self.funds_picker = SourcePicker("资金台账")
        self.operations_picker = SourcePicker("运营台账")
        self.validate_button = QPushButton("校验数据源")
        self.generate_button = QPushButton("生成两张报表")
        self.preview_button = QPushButton("预览报表")
        self.excel_button = QPushButton("导出 Excel")
        self.png_button = QPushButton("导出图片")
        self.status_label = QLabel("请选择两份数据源")
        self.preview_button.setEnabled(False)
        self.excel_button.setEnabled(False)
        self.png_button.setEnabled(False)
        self.validate_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.funds_picker.path_changed.connect(self.refresh_ready)
        self.operations_picker.path_changed.connect(self.refresh_ready)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(self.funds_picker)
        layout.addWidget(self.operations_picker)
        layout.addWidget(self.status_label)
        layout.addWidget(self.validate_button)
        layout.addWidget(self.generate_button)
        actions = QHBoxLayout()
        for button in (self.preview_button, self.excel_button, self.png_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.setCentralWidget(body)

    def refresh_ready(self) -> None:
        ready = all(picker.path and picker.path.is_file() for picker in (self.funds_picker, self.operations_picker))
        self.bundle = None
        self.inspection = None
        self.validate_button.setEnabled(bool(ready))
        self.generate_button.setEnabled(False)
        for button in (self.preview_button, self.excel_button, self.png_button):
            button.setEnabled(False)
        self.status_label.setText("可以校验数据源" if ready else "请选择两份数据源")

    def on_validation_succeeded(self, inspection) -> None:
        self.inspection = inspection
        plan = inspection.update_plan
        added = "、".join(item.label for item in plan.new_periods) or "无"
        refreshed = "、".join(item.label for item in plan.refresh_periods) or "无"
        self.status_label.setText(
            f"{inspection.fiscal_year}财年｜最新 {plan.latest.label}｜新增 {added}｜回刷 {refreshed}"
        )
        self.generate_button.setEnabled(True)

    def on_generation_succeeded(self, bundle) -> None:
        self.bundle = bundle
        self.status_label.setText(f"已生成：{bundle.latest_period.label}")
        for button in (self.preview_button, self.excel_button, self.png_button):
            button.setEnabled(True)
```

- [ ] **Step 4: 添加后台线程、预览弹窗和导出对话框**

```python
# src/ledger_reporter/ui/workers.py
from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


class GenerationWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service, funds: Path, operations: Path, today: date) -> None:
        super().__init__()
        self.service = service
        self.funds = funds
        self.operations = operations
        self.today = today

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self.service.generate(self.funds, self.operations, self.today))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class ValidationWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, service, funds: Path, operations: Path, today: date) -> None:
        super().__init__()
        self.service = service
        self.funds = funds
        self.operations = operations
        self.today = today

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self.service.inspect_sources(self.funds, self.operations, self.today))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()
```

```python
# src/ledger_reporter/ui/preview_dialog.py
from PySide6.QtWidgets import QDialog, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout

from ledger_reporter.exporters.png import _format
from ledger_reporter.presentation.builders import build_tables


class PreviewDialog(QDialog):
    def __init__(self, bundle, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("报表预览")
        self.resize(1100, 720)
        tabs = QTabWidget()
        for table in build_tables(bundle):
            rows = max(cell.row for cell in table.cells)
            columns = max(cell.column for cell in table.cells)
            widget = QTableWidget(rows, columns)
            widget.horizontalHeader().hide()
            widget.verticalHeader().hide()
            for cell in table.cells:
                widget.setItem(cell.row - 1, cell.column - 1, QTableWidgetItem(_format(cell.value, cell.number_format)))
            for merge in table.merges:
                widget.setSpan(
                    merge.start_row - 1,
                    merge.start_column - 1,
                    merge.end_row - merge.start_row + 1,
                    merge.end_column - merge.start_column + 1,
                )
            tabs.addTab(widget, table.name)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
```

在 `main_window.py` 增加导入和以下方法：

```python
from datetime import date
from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ledger_reporter.exporters.excel import export_excel
from ledger_reporter.exporters.png import export_pngs
from .preview_dialog import PreviewDialog
from .workers import GenerationWorker, ValidationWorker


def start_validation(self) -> None:
    self.validate_button.setEnabled(False)
    self.status_label.setText("正在校验数据源…")
    self.validation_thread = QThread(self)
    self.validation_worker = ValidationWorker(
        self.report_service,
        self.funds_picker.path,
        self.operations_picker.path,
        date.today(),
    )
    self.validation_worker.moveToThread(self.validation_thread)
    self.validation_thread.started.connect(self.validation_worker.run)
    self.validation_worker.succeeded.connect(self.on_validation_succeeded)
    self.validation_worker.failed.connect(self.on_validation_failed)
    self.validation_worker.finished.connect(self.validation_thread.quit)
    self.validation_worker.finished.connect(self.validation_worker.deleteLater)
    self.validation_thread.finished.connect(self.validation_thread.deleteLater)
    self.validation_thread.finished.connect(
        lambda: self.validate_button.setEnabled(bool(self.funds_picker.path and self.operations_picker.path))
    )
    self.validation_thread.start()


def on_validation_failed(self, message: str) -> None:
    self.generate_button.setEnabled(False)
    self.status_label.setText("数据源校验失败")
    QMessageBox.critical(self, "数据源校验失败", message)


def start_generation(self) -> None:
    self.generate_button.setEnabled(False)
    self.status_label.setText("正在校验并生成…")
    self.thread = QThread(self)
    self.worker = GenerationWorker(
        self.report_service,
        self.funds_picker.path,
        self.operations_picker.path,
        date.today(),
    )
    self.worker.moveToThread(self.thread)
    self.thread.started.connect(self.worker.run)
    self.worker.succeeded.connect(self.on_generation_succeeded)
    self.worker.failed.connect(self.on_generation_failed)
    self.worker.finished.connect(self.thread.quit)
    self.worker.finished.connect(self.worker.deleteLater)
    self.thread.finished.connect(self.thread.deleteLater)
    self.thread.finished.connect(self.on_generation_finished)
    self.thread.start()


def on_generation_failed(self, message: str) -> None:
    self.status_label.setText("生成失败")
    QMessageBox.critical(self, "无法生成报表", message)


def on_generation_finished(self) -> None:
    ready = all(
        picker.path and picker.path.is_file()
        for picker in (self.funds_picker, self.operations_picker)
    )
    self.validate_button.setEnabled(bool(ready))
    self.generate_button.setEnabled(bool(ready and self.inspection is not None))


def open_preview(self) -> None:
    PreviewDialog(self.bundle, self).exec()


def export_excel_file(self) -> None:
    default_name = f"{self.bundle.fiscal_year}财年台账报表.xlsx"
    value, _ = QFileDialog.getSaveFileName(self, "导出 Excel", default_name, "Excel 工作簿 (*.xlsx)")
    if value:
        export_excel(self.bundle, Path(value))


def export_png_files(self) -> None:
    value = QFileDialog.getExistingDirectory(self, "选择图片保存文件夹")
    if value:
        export_pngs(self.bundle, Path(value))
```

在 `__init__` 末尾连接：

```python
self.validate_button.clicked.connect(self.start_validation)
self.generate_button.clicked.connect(self.start_generation)
self.preview_button.clicked.connect(self.open_preview)
self.excel_button.clicked.connect(self.export_excel_file)
self.png_button.clicked.connect(self.export_png_files)
```

在 UI 测试中用 monkeypatch 替换文件对话框和导出函数：返回空字符串时断言导出函数未调用；返回路径时断言路径与当前 `ReportBundle` 被传入；`on_generation_failed("缺少字段")` 后断言状态文本为“生成失败”。

- [ ] **Step 5: 添加应用入口并运行 UI 测试**

```python
# src/ledger_reporter/__main__.py
import sys

from PySide6.QtWidgets import QApplication

from ledger_reporter.app_paths import app_data_dir
from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService
from ledger_reporter.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("台账报表生成器")
    repository = HistoryRepository(app_data_dir() / "history.sqlite3")
    window = MainWindow(ReportService(repository))
    window.resize(760, 560)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/ui/test_main_window.py -q`

Expected: 所有 UI 测试通过。

- [ ] **Step 6: 提醒用户并提交桌面 UI**

```powershell
git add src/ledger_reporter/ui src/ledger_reporter/__main__.py tests/ui
git commit -m "feat: add desktop generation workflow"
```

### Task 12: 安全的一键卸载

**Files:**
- Create: `src/ledger_reporter/uninstall.py`
- Create: `src/ledger_reporter/ui/uninstall_dialog.py`
- Create: `tests/test_uninstall.py`
- Modify: `src/ledger_reporter/ui/main_window.py`

- [ ] **Step 1: 写路径白名单和“保留导出文件”测试**

```python
# tests/test_uninstall.py
from pathlib import Path

import pytest

from ledger_reporter.uninstall import UninstallTargets, build_uninstall_script


def test_script_only_contains_owned_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    app = Path("/Applications") / "台账报表生成器.app"
    targets = UninstallTargets.for_home(home, app, tmp_path / "temp")
    script = build_uninstall_script(targets)
    assert str(app) in script
    assert "Application Support/com.local.ledger-report-generator" in script
    assert "com.local.ledger-report-generator" in str(targets.temp)
    assert "Desktop" not in script
    assert "Documents" not in script


def test_rejects_wrong_application_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="应用路径"):
        UninstallTargets.for_home(tmp_path, tmp_path / "Applications" / "Other.app")


def test_rejects_same_name_outside_applications(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="应用路径"):
        UninstallTargets.for_home(tmp_path, tmp_path / "Downloads" / "台账报表生成器.app")
```

- [ ] **Step 2: 运行卸载测试并确认模块不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_uninstall.py -q`

Expected: FAIL importing `ledger_reporter.uninstall`。

- [ ] **Step 3: 实现精确目标和自删除助手**

```python
# src/ledger_reporter/uninstall.py
import json
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ledger_reporter.app_paths import APP_ID


@dataclass(frozen=True, slots=True)
class UninstallTargets:
    app: Path
    data: Path
    cache: Path
    preferences: Path
    logs: Path
    temp: Path

    @classmethod
    def for_home(cls, home: Path, app: Path, temp_root: Path | None = None) -> "UninstallTargets":
        app_name = "台账报表生成器.app"
        allowed = {Path("/Applications") / app_name, home / "Applications" / app_name}
        if app not in allowed:
            raise ValueError("应用路径不符合卸载白名单")
        library = home / "Library"
        return cls(
            app=app,
            data=library / "Application Support" / APP_ID,
            cache=library / "Caches" / APP_ID,
            preferences=library / "Preferences" / f"{APP_ID}.plist",
            logs=library / "Logs" / APP_ID,
            temp=(temp_root or Path(tempfile.gettempdir())) / APP_ID,
        )


def build_uninstall_script(targets: UninstallTargets) -> str:
    user_paths = " ".join(
        shlex.quote(str(path))
        for path in (targets.data, targets.cache, targets.preferences, targets.logs, targets.temp)
    )
    app_command = f"/bin/rm -rf -- {shlex.quote(str(targets.app))}"
    apple_script = shlex.quote(f"do shell script {json.dumps(app_command)} with administrator privileges")
    return "\n".join((
        "#!/bin/sh",
        "set -eu",
        'SCRIPT_PATH="$0"',
        "trap '/bin/rm -f -- \"$SCRIPT_PATH\"' EXIT",
        "sleep 1",
        f"/usr/bin/osascript -e {apple_script}",
        f"/bin/rm -rf -- {user_paths}",
    )) + "\n"


def write_uninstall_helper(targets: UninstallTargets) -> Path:
    path = Path(tempfile.gettempdir()) / "uninstall-ledger-report-generator.sh"
    path.write_text(build_uninstall_script(targets), encoding="utf-8", newline="\n")
    path.chmod(0o700)
    return path
```

- [ ] **Step 4: 添加确认对话框和菜单入口**

`UninstallDialog` 必须逐项显示 `UninstallTargets` 六个路径，并明确写出“不会删除用户导出的 Excel/PNG”。只有用户点击红色“卸载”按钮后，才执行：

```python
helper = write_uninstall_helper(targets)
QProcess.startDetached("/bin/sh", [str(helper)])
QApplication.quit()
```

在主窗口“应用”菜单中添加 `卸载台账报表生成器…`。测试取消时不调用 `startDetached`，确认时只传入生成的临时助手路径。

- [ ] **Step 5: 运行卸载测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_uninstall.py tests/ui -q`

Expected: 所有卸载和 UI 测试通过；测试不得执行真实删除命令。

- [ ] **Step 6: 提醒用户并提交卸载功能**

```powershell
git add src/ledger_reporter/uninstall.py src/ledger_reporter/ui/uninstall_dialog.py src/ledger_reporter/ui/main_window.py tests/test_uninstall.py tests/ui
git commit -m "feat: add safe one-click uninstaller"
```

### Task 13: 图标、PyInstaller、DMG 和 macOS CI

**Files:**
- Create: `src/ledger_reporter/resources/app-icon.png`
- Create: `scripts/make_icns.sh`
- Create: `scripts/build_macos.sh`
- Create: `packaging/ledger_reporter.spec`
- Create: `packaging/dmg_settings.py`
- Create: `.github/workflows/build-macos.yml`
- Create: `docs/INSTALL_MACOS.md`

- [ ] **Step 1: 固化用户图标并验证资源**

从以下已保存源图之一复制，不重新生成图标：

```powershell
Copy-Item -LiteralPath "D:\自动化表格\.superpowers\brainstorm\visual-20260808-145609-1333\content\app-icon.png" -Destination "src\ledger_reporter\resources\app-icon.png"
```

Run:

```powershell
.\.venv\Scripts\python.exe -c "from PIL import Image; im=Image.open('src/ledger_reporter/resources/app-icon.png'); assert im.size==(1254,1254); print(im.mode)"
```

Expected: 输出 `RGB`。

- [ ] **Step 2: 创建 ICNS 生成脚本**

```bash
#!/usr/bin/env bash
# scripts/make_icns.sh
set -euo pipefail
SOURCE="${1:-src/ledger_reporter/resources/app-icon.png}"
OUTPUT="${2:-packaging/app-icon.icns}"
ICONSET="$(mktemp -d)/app.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$SOURCE" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$SOURCE" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$OUTPUT"
rm -rf "$(dirname "$ICONSET")"
```

- [ ] **Step 3: 创建 PyInstaller 和 DMG 配置**

```python
# packaging/ledger_reporter.spec
from pathlib import Path

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "src" / "ledger_reporter" / "__main__.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=[(str(root / "src" / "ledger_reporter" / "resources"), "ledger_reporter/resources")],
    hiddenimports=["PySide6.QtSvg"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="台账报表生成器", console=False)
collection = COLLECT(exe, a.binaries, a.datas, strip=False, name="台账报表生成器")
app = BUNDLE(
    collection,
    name="台账报表生成器.app",
    icon=str(root / "packaging" / "app-icon.icns"),
    bundle_identifier="com.local.ledger-report-generator",
    info_plist={"NSHighResolutionCapable": True, "LSMinimumSystemVersion": "12.0"},
)
```

```python
# packaging/dmg_settings.py
import os

application = os.path.abspath("dist/台账报表生成器.app")
files = [application, os.path.abspath("docs/INSTALL_MACOS.md")]
symlinks = {"Applications": "/Applications"}
icon_locations = {"台账报表生成器.app": (150, 180), "Applications": (430, 180)}
window_rect = ((200, 200), (580, 380))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
```

- [ ] **Step 4: 创建 Mac 一键构建脚本**

```bash
#!/usr/bin/env bash
# scripts/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
TARGET_ARCH="${TARGET_ARCH:-$(uname -m)}"
"$PYTHON_BIN" -m venv .venv-macos
. .venv-macos/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest -q
bash scripts/make_icns.sh
rm -rf build dist
pyinstaller --clean --noconfirm --target-architecture "$TARGET_ARCH" packaging/ledger_reporter.spec
mkdir -p dist
dmgbuild -s packaging/dmg_settings.py "台账报表生成器" "dist/台账报表生成器-${TARGET_ARCH}.dmg"
shasum -a 256 "dist/台账报表生成器-${TARGET_ARCH}.dmg" > "dist/台账报表生成器-${TARGET_ARCH}.dmg.sha256"
```

- [ ] **Step 5: 创建 macOS CI 和安装说明**

```yaml
# .github/workflows/build-macos.yml
name: build-macos
on:
  workflow_dispatch:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: bash scripts/build_macos.sh
      - uses: actions/upload-artifact@v4
        with:
          name: ledger-report-generator-macos
          path: |
            dist/*.dmg
            dist/*.sha256
```

`docs/INSTALL_MACOS.md` 必须写明：打开 DMG、拖入“应用程序”、首次右键“打开”、未签名警告、固定到 Dock 的方法，以及应用内一键卸载不会删除导出文件。

- [ ] **Step 6: 在 Mac 或 macOS CI 构建并检查包内容**

Run on macOS: `bash scripts/build_macos.sh`

Expected:

- `dist/台账报表生成器-<arch>.dmg` 存在。
- DMG 内含 `.app`、Applications 链接和安装说明。
- 未安装 Python 的 Mac 可启动应用。

- [ ] **Step 7: 提醒用户并提交打包配置**

```powershell
git add src/ledger_reporter/resources/app-icon.png scripts packaging .github/workflows/build-macos.yml docs/INSTALL_MACOS.md .gitignore
git commit -m "build: package unsigned macOS application"
```

### Task 14: 真实数据对账、视觉验收与发布前验证

**Files:**
- Create: `tools/reconcile_real_data.py`
- Create: `tests/integration/test_end_to_end.py`
- Create: `tests/integration/test_real_samples.py`
- Create: `README.md`

- [ ] **Step 1: 写合成端到端测试**

```python
# tests/integration/test_end_to_end.py
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from ledger_reporter.domain.models import FundRecord, OperationalRecord
from ledger_reporter.exporters.excel import export_excel
from ledger_reporter.exporters.png import export_pngs
from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService


def test_generates_persists_and_exports_both_tables(tmp_path) -> None:
    repository = HistoryRepository(tmp_path / "history.sqlite3")
    service = ReportService(repository)
    operations = [
        OperationalRecord("001", "BSA", "LAX", date(2026, 8, 3), "其他供应商", Decimal("1000"), Decimal("100")),
        OperationalRecord("002", "散采", "OSL", date(2026, 8, 4), "其他供应商", Decimal("500"), Decimal("20")),
    ]
    funds = [
        FundRecord("广州美鑫通国际供应链有限公司", date(2026, 8, 4), Decimal("900"), Decimal("5")),
    ]
    bundle = service.generate_from_records(date(2026, 8, 7), operations, funds)
    excel_path = tmp_path / "2026财年台账报表.xlsx"
    export_excel(bundle, excel_path)
    png_paths = export_pngs(bundle, tmp_path / "png")
    assert excel_path.exists()
    assert len(png_paths) == 2
    assert load_workbook(excel_path).sheetnames == ["经营汇总", "自营项目周报"]
    assert repository.load_weeks(2026)[0].period.start == date(2026, 8, 1)
```

Run: `.\.venv\Scripts\python.exe -m pytest tests/integration/test_end_to_end.py -q`

Expected: PASS；若失败，修复最先出现的跨层契约错误后重复运行，直到 `1 passed`。

- [ ] **Step 2: 创建不提交源数据的真实文件核对入口**

```python
# tests/integration/test_real_samples.py
import os
from datetime import date
from pathlib import Path

import pytest

from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService


SAMPLE_DIR = os.getenv("LEDGER_REPORTER_SAMPLE_DIR")
pytestmark = pytest.mark.skipif(not SAMPLE_DIR, reason="需要本地真实样例路径")


def test_real_samples_generate_latest_complete_period(tmp_path: Path) -> None:
    root = Path(SAMPLE_DIR)
    service = ReportService(HistoryRepository(tmp_path / "history.sqlite3"))
    bundle = service.generate(
        root / "AB台账-线上版(1).xlsx",
        root / "台账交接(1).xlsx",
        date(2026, 8, 10),
    )
    assert bundle.latest_period.start == date(2026, 8, 1)
    assert bundle.latest_period.end == date(2026, 8, 6)
    assert bundle.baseline_rows[-1]["label"] == "W5（24-31）"
```

Run:

```powershell
$env:LEDGER_REPORTER_SAMPLE_DIR='D:\台账'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_real_samples.py -q
```

Expected: PASS；源文件修改时间和哈希在测试前后完全一致。

- [ ] **Step 3: 独立对账最新 Week**

`tools/reconcile_real_data.py` 使用直接、独立的 openpyxl 循环，不复用 `calculate_period`：

```python
# tools/reconcile_real_data.py
import json
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

from ledger_reporter.services.history import HistoryRepository
from ledger_reporter.services.report_service import ReportService


START = date(2026, 8, 1)
END = date(2026, 8, 6)
RATES = {
    "广州美鑫通国际供应链有限公司": Decimal("0.10"),
    "浙江飞速供应链管理有限公司": Decimal("0.12"),
}


def as_date(value, epoch) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return from_excel(value, epoch).date()


def dec(value) -> Decimal:
    return Decimal("0") if value in (None, "") else Decimal(str(value))


def header_map(sheet) -> dict[str, int]:
    return {cell.value: index for index, cell in enumerate(next(sheet.iter_rows()), 0)}


def direct_operations(path: Path) -> dict[str, object]:
    book = load_workbook(path, read_only=True, data_only=True)
    sheet = book["台账明细"]
    columns = header_map(sheet)
    selected = []
    for row in sheet.iter_rows(min_row=2, values_only=True):
        current = as_date(row[columns["预计起飞时间"]], book.epoch)
        if START <= current <= END:
            selected.append(row)
    project = [row for row in selected if row[columns["项目类型"]] != "散采"]
    scatter = [row for row in selected if row[columns["项目类型"]] == "散采"]
    return {
        "project_count": sum(row[columns["提单号"]] not in (None, "") for row in project),
        "project_profit": str(sum((dec(row[columns["预估毛利润"]]) for row in project), Decimal("0"))),
        "scatter_count": sum(row[columns["提单号"]] not in (None, "") for row in scatter),
        "scatter_profit": str(sum((dec(row[columns["预估毛利润"]]) for row in scatter), Decimal("0"))),
    }


def direct_funds(path: Path) -> dict[str, str]:
    book = load_workbook(path, read_only=True, data_only=True)
    amount = Decimal("0")
    profit = Decimal("0")
    for sheet_name in [name for name in book.sheetnames if name.startswith("资金散板汇总2026")]:
        sheet = book[sheet_name]
        columns = header_map(sheet)
        for row in sheet.iter_rows(min_row=2, values_only=True):
            raw_date = row[columns["信容付款日期"]]
            if raw_date in (None, ""):
                continue
            current = as_date(raw_date, book.epoch)
            if not START <= current <= END:
                continue
            channel = str(row[columns["渠道名称"]] or "")
            row_amount = dec(row[columns["付款金额合计（90%）"]])
            amount += row_amount
            profit += row_amount * (RATES[channel] - Decimal("0.0448")) * Decimal("60") / Decimal("365")
            profit += dec(row[columns["应收操作费"]])
    return {"fund_amount": str(amount), "fund_profit": str(profit)}


funds_path = Path(sys.argv[1])
operations_path = Path(sys.argv[2])
expected = direct_operations(operations_path) | direct_funds(funds_path)
with tempfile.TemporaryDirectory() as directory:
    service = ReportService(HistoryRepository(Path(directory) / "history.sqlite3"))
    bundle = service.generate(funds_path, operations_path, date(2026, 8, 10))
    snapshot = next(item for item in bundle.weeks if item.period.start == START and item.period.end == END)
    actual = {
        "project_count": snapshot.metrics.project_count,
        "project_profit": str(snapshot.metrics.project_profit),
        "scatter_count": snapshot.metrics.scatter_count,
        "scatter_profit": str(snapshot.metrics.scatter_profit),
        "fund_amount": str(snapshot.metrics.fund_amount),
        "fund_profit": str(snapshot.metrics.fund_profit),
    }
if actual != expected:
    raise SystemExit(json.dumps({"expected": expected, "actual": actual}, ensure_ascii=False, indent=2))
print(json.dumps({"period": [START.isoformat(), END.isoformat()], "differences": 0, "metrics": actual}, ensure_ascii=False, indent=2))
```

Run:

```powershell
.\.venv\Scripts\python.exe tools\reconcile_real_data.py "D:\台账\AB台账-线上版(1).xlsx" "D:\台账\台账交接(1).xlsx"
```

Expected: 项目、散采、资金金额和资金利润六个核心指标差异为 `0`；业务行继续由 Task 5 的逐规则测试覆盖。

- [ ] **Step 4: 全量自动化验证**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected: Ruff 无错误；全部测试通过；真实样例测试在未设置环境变量时仅显示预期 skip；Git 无空白错误。

- [ ] **Step 5: 视觉检查 Excel 和 PNG**

使用真实样例生成到 `outputs/acceptance/`，逐张打开：

- `2026财年台账报表.xlsx` 的两张工作表。
- `经营汇总.png`。
- `自营项目周报.png`。
- PySide6 主窗口截图和预览弹窗截图。

检查标题、合并、列宽、数字、负百分比、长表滚动、无裁切、无说明行、无重叠。修复严重视觉缺陷后重新运行 Task 9、10、11 的测试。

- [ ] **Step 6: 完成 README 和卸载边界说明**

`README.md` 写明开发环境、Windows 测试命令、Mac 构建命令、两份输入表要求、财年/Week 规则、历史目录、导出行为、未签名安装和一键卸载保留用户导出文件。

- [ ] **Step 7: 提醒用户并提交验收结果**

先展示测试数量、真实对账结果、视觉截图路径和 `git status --short`，提醒用户这是发布前提交节点，然后执行：

```powershell
git add tools tests README.md
git commit -m "test: verify end-to-end ledger report workflow"
```

- [ ] **Step 8: 最终分支检查**

Run:

```powershell
git status --short
git log --oneline --decorate -15
```

Expected: 工作树干净；每个任务有独立提交；等待用户选择合并、推送或保留功能分支。
