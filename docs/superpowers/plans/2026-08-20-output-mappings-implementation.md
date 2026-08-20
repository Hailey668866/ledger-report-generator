# Output Mappings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace shared source-field settings with independently editable mappings for every configurable output in both reports.

**Architecture:** Extend the existing immutable settings model with aggregate, ratio, fund-profit, and business-row rules. Workbook readers load the union of configured headers into each record, while calculations resolve values through each output's own rule. Existing report, history, preview, Excel, and PNG models remain intact.

**Tech Stack:** Python 3.12, dataclasses, JSON, openpyxl, PySide6, pytest, pytest-qt.

---

### Task 1: Versioned settings model and migration

**Files:**
- Modify: `src/ledger_reporter/io/source_settings.py`
- Modify: `tests/io/test_source_settings.py`

- [ ] Add failing tests for nested default rules, independent mappings, optional filter-pair validation, numeric parameter validation, JSON round trips, and migration from every legacy flat key.
- [ ] Run `python -m pytest tests/io/test_source_settings.py -q`; expect failures for missing rule types.
- [ ] Add frozen/slotted `FilterRule`, `AggregateRule`, `RatioRule`, `FundProfitRule`, `BusinessRowRule`, `BusinessTotalRule`, and expanded `SourceSettings` dataclasses. Keep `funds_sheet`, `funds_header_row`, `operations_sheet`, and `operations_header_row` at the top level.
- [ ] Define defaults matching `需求(1).xlsx`, including all existing business names, display values, suppliers, project types, destinations, two fund channels, rates `0.10`/`0.12`, capital cost `0.0448`, and 60 days.
- [ ] Load `schema_version: 2` recursively; migrate legacy flat JSON by copying each old shared field into every dependent rule. Save versioned JSON atomically through the existing temporary-file replacement.
- [ ] Run `python -m pytest tests/io/test_source_settings.py -q`; expect pass.

### Task 2: Dynamic workbook fields and independent calculations

**Files:**
- Modify: `src/ledger_reporter/domain/models.py`
- Modify: `src/ledger_reporter/io/workbooks.py`
- Modify: `src/ledger_reporter/services/calculations.py`
- Modify: `src/ledger_reporter/services/report_service.py`
- Modify: `tests/io/test_workbooks.py`
- Modify: `tests/services/test_summary_calculations.py`
- Modify: `tests/services/test_business_calculations.py`
- Modify: `tests/services/test_report_service.py`

- [ ] Add failing tests proving two summary outputs can use different date/filter/value headers, each weekly calculated column can use different filters, an empty filter pair disables that filter, and missing fields name the affected output.
- [ ] Run the focused tests; expect failures because records only expose shared semantic fields.
- [ ] Add a default-empty raw `values` mapping to `OperationalRecord` and `FundRecord`, preserving existing constructors and in-memory tests.
- [ ] Change workbook readers to collect the deduplicated union returned by settings methods, preserve raw cached values by actual header name, and validate formula caches for all configured numeric fields.
- [ ] Add calculation helpers that resolve configured fields from `record.values`, falling back to current semantic attributes for existing in-memory records. Parse dates and decimals at the calculation boundary with output-specific error messages.
- [ ] Calculate each summary output and each weekly count/profit/margin independently. Preserve `PeriodMetrics`, `BusinessMetric`, history snapshots, frozen baseline behavior, and report bundle shape.
- [ ] Pass current settings from `ReportService` into both calculation functions and update presentation metadata to use configured business display values.
- [ ] Run all focused service, workbook, presentation, exporter, and integration tests; expect pass.

### Task 3: Finished settings window

**Files:**
- Modify: `src/ledger_reporter/ui/source_settings_dialog.py`
- Modify: `src/ledger_reporter/ui/main_window.py`
- Modify: `tests/ui/test_source_settings_dialog.py`
- Modify: `tests/ui/test_main_window.py`

- [ ] Add failing Qt tests for the three navigation entries, data-source fields, output-specific edits, business selection, restore defaults, save validation, cancel behavior, and selected settings.
- [ ] Run `python -m pytest tests/ui/test_source_settings_dialog.py tests/ui/test_main_window.py -q`; expect failures against the old two-tab dialog.
- [ ] Build the approved left-navigation `QDialog` with `QStackedWidget`: data sources, summary outputs, and weekly business rows. Use one selected output/business at a time, standard labels and inputs only, and no instructional copy.
- [ ] Reuse the existing stylesheet colors and native Qt controls. Keep inputs accessible by labels, constrain widths, and keep all content reachable at the minimum window size through scroll areas.
- [ ] On save, build and validate one immutable `SourceSettings`; preserve the existing atomic save, service update, result invalidation, and immediate revalidation flow.
- [ ] Run the focused Qt tests; expect pass.

### Task 4: Verification and one feature commit

**Files:**
- Modify: `README.md`
- Modify: `docs/INSTALL_MACOS.md` only if settings wording is present

- [ ] Update user documentation with the three setting sections and fixed-calculation boundary.
- [ ] Run `python -m pytest -q`, `python -m ruff check src tests tools`, and `python -m ruff format --check src tests tools` with `QT_QPA_PLATFORM=offscreen`; expect all pass.
- [ ] Run the real-sample integration test with `LEDGER_REPORTER_SAMPLE_DIR=D:\台账`; expect pass and unchanged default results.
- [ ] Inspect `git diff --check` and ensure `.release/` and `.superpowers/` are not staged.
- [ ] Commit the complete field-settings feature once with `feat: configure each report output independently`.
