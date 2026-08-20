# GitHub Release Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish native macOS installers through GitHub Releases and let the app safely check, download, verify, and open the correct DMG.

**Architecture:** A standard-library update service reads GitHub's latest-release API, compares numeric versions, selects the current architecture's fixed-name assets, and verifies SHA-256. Qt workers keep network and download work off the UI thread; the main window owns prompts and progress.

**Tech Stack:** Python 3.12 stdlib (`urllib`, `hashlib`, `platform`, `subprocess`), PySide6, pytest, GitHub Actions.

---

### Task 1: Update service

**Files:**
- Create: `src/ledger_reporter/services/app_updates.py`
- Create: `tests/services/test_app_updates.py`
- Modify: `src/ledger_reporter/app_paths.py`
- Modify: `src/ledger_reporter/__init__.py`

- [ ] Add failing tests for numeric version comparison, ignored prereleases, arm64/x86_64 asset selection, missing assets, offline errors, progress callbacks, cancellation, and checksum mismatch cleanup.
- [ ] Run `python -m pytest tests/services/test_app_updates.py -q`; expect import failure.
- [ ] Define `APP_VERSION`, `RELEASES_LATEST_URL`, `ReleaseUpdate`, and `UpdateError`. Implement API parsing with `urllib.request`, an explicit timeout and User-Agent, and strict fixed asset names.
- [ ] Add `app_cache_dir()` using `~/Library/Caches/com.local.ledger-report-generator` on macOS and the existing local-app-data fallback elsewhere.
- [ ] Download DMG and checksum to `app_cache_dir()/updates` using `.part` files, stream SHA-256, compare the checksum token, atomically rename only after success, and expose cancellation/progress callbacks.
- [ ] Run the update-service tests; expect pass.

### Task 2: Non-blocking Qt update flow

**Files:**
- Modify: `src/ledger_reporter/ui/workers.py`
- Modify: `src/ledger_reporter/ui/main_window.py`
- Modify: `src/ledger_reporter/__main__.py`
- Modify: `tests/ui/test_main_window.py`
- Modify: `tests/ui/test_app_entry.py`

- [ ] Add failing tests for the “检查更新” menu, one startup check, silent automatic failure, visible manual failure/current-version result, update prompt, correct download request, progress cancellation, and opening a verified DMG.
- [ ] Run the focused UI tests; expect failures.
- [ ] Add check/download workers using existing `QObject`/`QThread` patterns and signals. Make cancellation a thread-safe flag checked between chunks.
- [ ] Add “检查更新” under the application menu. Schedule the startup check with `QTimer.singleShot(0, ...)`, prevent duplicate checks, and keep report controls independent from update checks.
- [ ] Show a native confirmation dialog only when a newer version exists. Use `QProgressDialog` for download; after verification run `open <dmg>` on macOS. Automatic failures stay silent; manual outcomes show concise dialogs.
- [ ] Pass cache path and current version from app startup without changing smoke-test readiness.
- [ ] Run the focused UI tests; expect pass.

### Task 3: GitHub Release publishing

**Files:**
- Modify: `.github/workflows/build-macos.yml`
- Modify: `tests/packaging/test_macos_packaging.py`
- Modify: `README.md`
- Modify: `docs/INSTALL_MACOS.md`

- [ ] Add failing packaging assertions for `contents: write`, artifact download, a release job dependent on both architecture builds, and four uploaded release attachments.
- [ ] Run `python -m pytest tests/packaging/test_macos_packaging.py -q`; expect failure.
- [ ] Keep the existing matrix builds. Add a tag-only release job that downloads both build artifacts and creates/updates the tag's GitHub Release with the two DMGs and two checksum files.
- [ ] Document version tags, automatic/manual checks, chip selection, checksum verification, and the user-controlled DMG installation step.
- [ ] Run the packaging tests; expect pass.

### Task 4: Verification and one feature commit

**Files:**
- Verify all modified update and packaging files.

- [ ] Run `python -m pytest -q`, `python -m ruff check src tests tools`, and `python -m ruff format --check src tests tools`; expect all pass.
- [ ] Run `git diff --check` and confirm no release binaries or preview artifacts are staged.
- [ ] Commit once with `feat: publish and install GitHub release updates`.
- [ ] Push only if the user has already authorized pushing in the current task; otherwise report the ready commit without changing the remote.
