# C 版桌面界面还原 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PySide6 主窗口还原为已确认的 C 版收起式预览界面，移除生成后的 Week 状态条，并通过内置中文字体保证跨平台清晰显示。

**Architecture:** 保留现有 `MainWindow` 的业务编排和 worker 信号，只重组主窗口的展示组件与状态映射。字体注册封装为独立资源加载函数，由主窗口和预览共享；PyInstaller 继续整体打包 `resources`。测试先锁定用户可见契约，再完成最小实现和真实截图验收。

**Tech Stack:** Python 3.12、PySide6、pytest-qt、PyInstaller、GitHub Actions macOS runner

---

### Task 1: 锁定 C 版主窗口契约

**Files:**
- Modify: `tests/ui/test_main_window.py`
- Modify: `tests/ui/test_source_picker.py`（若不存在则 Create）

- [ ] 新增失败测试，断言主窗口包含品牌图标/名称、两行 C 版数据源卡、周期信息区、整行生成按钮和底部结果操作区。
- [ ] 新增失败测试，断言生成成功后主界面不存在 `已生成：` 与最新 Week 文案，预览/导出按钮仍启用。
- [ ] 运行定向测试，确认因当前布局和状态文字失败。

### Task 2: 实现 C 版主窗口与数据源行

**Files:**
- Modify: `src/ledger_reporter/ui/main_window.py`
- Modify: `src/ledger_reporter/ui/source_picker.py`
- Modify: `tests/ui/test_main_window.py`

- [ ] 将标题、数据源、周期、生成和结果操作拆成清晰的布局构造方法，保持原信号与公开控件属性兼容。
- [ ] 使用 `app-icon.png` 显示 34px 品牌图标；数据源行显示短标识、完整按钮文案和省略文件名。
- [ ] 校验成功时填充两块周期信息；生成成功时仅切换结果操作区和简短就绪状态，不显示 Week 状态条。
- [ ] 按 C 版颜色、间距、边框、按钮状态和稳定尺寸重写样式表。
- [ ] 运行 UI 定向测试并确认通过。

### Task 3: 内置并注册中文字体

**Files:**
- Create: `src/ledger_reporter/ui/fonts.py`
- Add: `src/ledger_reporter/resources/NotoSansSC-Regular.ttf`
- Modify: `src/ledger_reporter/ui/main_window.py`
- Modify: `src/ledger_reporter/ui/preview_dialog.py`
- Modify: `tests/ui/test_fonts.py`
- Modify: `tests/packaging/test_macos_packaging.py`

- [ ] 新增失败测试，断言字体资源存在、可由 Qt 注册、内置字体优先于系统字体且资源仍由 PyInstaller 打包。
- [ ] 从本机已安装的开源 Noto Sans SC 字体生成/固化应用字体资源，并记录许可证来源说明。
- [ ] 实现缓存字体注册函数；主窗口和预览弹窗统一应用该字体。
- [ ] 运行字体和打包定向测试。

### Task 4: 真实界面与回归验收

**Files:**
- Modify: `tests/ui/test_main_window.py`
- Generate (ignored): `outputs/ui-c-refresh/主窗口.png`
- Generate (ignored): `outputs/ui-c-refresh/预览-经营汇总.png`
- Generate (ignored): `outputs/ui-c-refresh/预览-自营项目周报.png`

- [ ] 运行全量 pytest、Ruff lint、Ruff format check 和 `git diff --check`。
- [ ] 通过真实 `MainWindow`、真实图标、真实 `ReportBundle` 生成三张截图，不使用 HTML 原型冒充桌面端。
- [ ] 检查中文清晰度、C 版层级、按钮文字、无重叠/裁切，以及 `已生成：W1` 已移除。
- [ ] 将截图交给用户确认；未确认前不提交、不重建 DMG。

### Task 5: 单一里程碑提交与 macOS 重建

**Files:**
- Modify: `.github/workflows/build-macos.yml`（仅在资源路径测试要求时）

- [ ] 展示最终 `git status --short`、测试结果和截图路径，提醒用户这是本轮唯一提交节点。
- [ ] 用户确认后提交为 `feat: restore approved desktop interface`。
- [ ] 合并到 `master`、推送并触发 arm64/x86_64 构建。
- [ ] 下载并校验新 DMG，创建新版本发布，不覆盖 `v0.1.1`。
