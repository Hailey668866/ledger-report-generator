# macOS Image Export Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ambiguous native macOS image-export chooser with an explicit folder-only dialog.

**Architecture:** Keep PNG rendering and export unchanged. Add one UI-boundary helper in `main_window.py` that configures `QFileDialog` for directories only, then have `export_png_files` consume the returned `Path`.

**Tech Stack:** Python 3.12, PySide6, pytest-qt

---

### Task 1: Add the folder-only chooser contract

**Files:**
- Modify: `tests/ui/test_main_window.py`

- [ ] Add a test that invokes the chooser while intercepting `QFileDialog.exec` and `selectedFiles`.
- [ ] Assert `Directory`, `ShowDirsOnly`, `DontUseNativeDialog`, and the “选择此文件夹” accept label.
- [ ] Run `pytest tests/ui/test_main_window.py -q` and confirm the new test fails because the helper does not exist.

### Task 2: Implement the explicit directory chooser

**Files:**
- Modify: `src/ledger_reporter/ui/main_window.py`
- Modify: `tests/ui/test_main_window.py`

- [ ] Add `_choose_png_output_directory(parent)` that configures and executes the folder-only dialog.
- [ ] Update `export_png_files` to return on cancellation and otherwise pass the selected `Path` to `export_pngs`.
- [ ] Update the existing cancellation/path test to patch the new helper instead of the static native API.
- [ ] Run the main-window UI tests and confirm they pass.

### Task 3: Verify the regression fix

**Files:**
- No production changes.

- [ ] Run the full pytest suite with the real sample directory enabled.
- [ ] Run Ruff check and format check for `src`, `tests`, and `tools`.
- [ ] Run `git diff --check` and inspect `git status --short`.
- [ ] Present the single commit checkpoint to the user; do not commit before confirmation.
