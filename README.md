# 台账报表生成器

这是一个本地运行的 macOS 桌面应用，用两份 XLSX 台账生成“经营汇总”和“自营项目周报”，并可导出为一个 Excel 工作簿或两张 PNG 图片。打包后的应用包含 Python 运行环境，使用者无需另行安装 Python。生成报表不联网；仅检查或下载新版本时访问 GitHub Releases。

## 输入工作簿

应用只读取源文件，不会保存或改写源台账。每次使用需要选择：

- 资金台账：AB 台账中的 `资金散板汇总YYYY` 工作表。必填字段为 `渠道名称`、`信容付款日期`、`付款金额合计（90%）`、`应收操作费`。
- 运营台账：台账交接文件中的 `台账明细` 工作表。必填字段为 `提单号`、`项目类型`、`目的口岸`、`预计起飞时间`、`B1供应商`、`预估总应收`、`预估毛利润`。

“字段设置”包含数据源设置、经营汇总和自营项目周报三部分。工作表名称、表头行、每个输出项使用的字段、筛选值及资金计算参数均可修改；相同字段在不同输出项中独立保存。计数、求和、利润率和资金收益等计算类型由程序固定，不支持自由公式。

字段名必须完整。金额和日期必须是有效值；没有缓存结果的公式需要先用 Excel 或 WPS 重新计算并保存。资金台账中日期精确标记为“未放款”的记录不会进入报表；运营台账中明确重复标记为“产品表”的字段说明行会被忽略，普通业务行的错误日期仍会被拒绝。

## 财年和 Week 规则

- 财年从 4 月 1 日开始，到次年 3 月 31 日结束；每个财年导出一个独立 Excel 文件。
- 2026 财年 8 月以前的数据使用冻结基线，后续生成不会更新这些行。
- 常规 Week 是上周五到本周四。只有已经完整结束的 Week 才会生成。
- 每月第一个周期从 1 日开始；月末不会划入下个月。
- 月末剩 1 天时合并到最近的 Week；剩 2 天或以上时单独新增一个 Week。
- 每次生成会写入最新完整周期，并回刷前一个周期，以纳入周末发生的数据变化。
- “自营项目周报”只展示最新完整 Week；“经营汇总”保留本财年历史并更新受影响周期。

## 使用和导出

1. 分别选择资金台账和运营台账。
2. 点击“校验数据源”，确认本次新增和回刷范围。
3. 点击“生成两张报表”。
4. 按需点击“预览报表”“导出 Excel”或“导出图片”。

Excel 默认文件名为 `YYYY财年台账报表.xlsx`，包含 `经营汇总` 和 `自营项目周报` 两张工作表。图片导出生成 `经营汇总.png` 和 `自营项目周报.png`。所有导出文件都写到用户选择的位置，不写回源工作簿。

应用内部历史保存在：

```text
~/Library/Application Support/com.local.ledger-report-generator/history.sqlite3
```

历史只用于保留和回刷 Week 快照，不包含源 XLSX 副本。开发或测试时可通过 `LEDGER_REPORTER_DATA_DIR` 改写内部数据目录。

## macOS 安装和卸载

macOS 安装包由 macOS 构建，不在 Windows 上伪造。当前 DMG 未签名且未经过 Apple 公证，首次打开需要在 Finder 的“应用程序”中右键应用并选择“打开”。完整步骤见 [macOS 安装说明](docs/INSTALL_MACOS.md)。

安装后可从“应用程序”、启动台或 Dock 打开。macOS 通常不创建桌面快捷方式；可在 Dock 中选择“在程序坞中保留”。

应用菜单中的“卸载台账报表生成器…”会删除应用本身，以及 Application Support 数据、缓存、偏好设置、日志和临时数据。已经导出到用户自选位置的 Excel/PNG 不会被删除。

应用在 macOS 启动后会后台检查 GitHub Releases，也可在“应用”菜单中点击“检查更新…”。发现新版本后，程序只在用户同意时下载当前芯片对应的 DMG，完成 SHA-256 校验后打开安装包；是否替换旧应用仍由用户在 macOS 中确认操作。

## 开发和测试

项目要求 Python 3.12。在 Windows PowerShell 中：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m ruff format --check src tests tools
```

真实样例默认不会运行，也不会进入 Git。指定仅包含本地样例的目录后运行：

```powershell
$env:LEDGER_REPORTER_SAMPLE_DIR = "D:\台账"
.\.venv\Scripts\python.exe -m pytest tests\integration\test_real_samples.py -q
.\.venv\Scripts\python.exe tools\reconcile_real_data.py `
  "D:\台账\AB台账-线上版(1).xlsx" `
  "D:\台账\台账交接(1).xlsx"
```

对账工具用独立的 openpyxl 行循环核对 2026-08-01 至 2026-08-06 的项目数量/利润、散采数量/利润、资金金额/利润六项指标；任一差异非零或源文件在运行期间发生变化时返回失败。

## macOS 构建

在原生 `arm64` 或 `x86_64` Mac 上运行：

```bash
TARGET_ARCH="$(uname -m)" bash scripts/build_macos.sh
```

脚本会运行全量测试、生成 `.icns`、构建 PyInstaller `.app`、执行打包应用启动冒烟测试、创建 DMG 并生成 SHA-256 文件。GitHub Actions 也会分别构建 Apple 芯片和 Intel 版本；Windows 只验证代码和配置，不能替代真实 macOS 构建验收。

发布时先同步 `pyproject.toml` 和 `src/ledger_reporter/__init__.py` 中的版本号，再推送同版本标签，例如 `v0.2.0`。标签会触发两个原生 macOS 构建，并将两份 DMG 和两份 `.sha256` 文件发布到对应的 GitHub Release；应用的自动更新直接读取该 Release。
