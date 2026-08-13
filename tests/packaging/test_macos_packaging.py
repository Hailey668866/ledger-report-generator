from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
APP_NAME = "台账报表生成器"
APP_BUNDLE = f"{APP_NAME}.app"
BUNDLE_ID = "com.local.ledger-report-generator"
ICON_SHA256 = "099785508d395006c46be51679ddd471b038faf09a60985de212fe4afbd86bfa"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_dmgbuild_is_pinned_before_the_macos_sync_regression() -> None:
    project = tomllib.loads(_read("pyproject.toml"))
    dev_dependencies = project["project"]["optional-dependencies"]["dev"]

    assert "dmgbuild==1.4.2" in dev_dependencies
    assert "setuptools>=75,<81" in dev_dependencies
    assert all("setuptools>=75,<82" not in dependency for dependency in dev_dependencies)


def test_packaged_icon_is_the_original_rgb_source() -> None:
    icon_path = ROOT / "src/ledger_reporter/resources/app-icon.png"

    assert hashlib.sha256(icon_path.read_bytes()).hexdigest() == ICON_SHA256
    with Image.open(icon_path) as image:
        assert image.size == (1254, 1254)
        assert image.mode == "RGB"
        assert image.format == "PNG"


def test_icns_script_builds_all_standard_icon_sizes_in_a_temporary_directory() -> None:
    script = _read("scripts/make_icns.sh")

    assert "set -euo pipefail" in script
    assert "mktemp -d" in script
    assert "trap " in script
    assert "16 32 128 256 512" in script
    assert "icon_${size}x${size}.png" in script
    assert "icon_${size}x${size}@2x.png" in script
    assert "sips -z" in script
    assert "iconutil -c icns" in script


def test_pyinstaller_spec_builds_a_windowed_self_contained_app_with_resources() -> None:
    spec = _read("packaging/ledger_reporter.spec")

    assert "ROOT = Path(SPECPATH).resolve().parent" in spec
    assert "ROOT = Path(SPECPATH).resolve().parent.parent" not in spec
    assert '"src" / "ledger_reporter" / "__main__.py"' in spec
    assert '"ledger_reporter/resources"' in spec
    assert "exclude_binaries=True" in spec
    assert "console=False" in spec
    assert f'name="{APP_NAME}"' in spec
    assert f'name="{APP_BUNDLE}"' in spec
    assert f'bundle_identifier="{BUNDLE_ID}"' in spec
    assert '"CFBundleName": "台账报表生成器"' in spec
    assert '"CFBundleDisplayName": "台账报表生成器"' in spec
    assert '"LSMinimumSystemVersion": "12.0"' in spec
    assert '"NSHighResolutionCapable": True' in spec
    assert "NotoSansSC-Variable.ttf" in {
        path.name for path in (ROOT / "src/ledger_reporter/resources").iterdir()
    }


def test_dmg_contains_app_applications_link_and_installation_guide(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    settings_path = ROOT / "packaging/dmg_settings.py"
    settings: dict[str, object] = {}
    source = settings_path.read_bytes()
    exec(compile(source, str(settings_path), "exec"), settings, settings)  # noqa: S102

    filenames = {Path(path).name for path in settings["files"]}
    assert filenames == {APP_BUNDLE, "安装说明.md"}
    assert settings["symlinks"] == {"Applications": "/Applications"}
    assert set(settings["icon_locations"]) == {APP_BUNDLE, "Applications", "安装说明.md"}
    assert settings["default_view"] == "icon-view"


def test_build_script_requires_macos_native_architecture_and_verifies_dmg_contents() -> None:
    script = _read("scripts/build_macos.sh")

    assert "set -euo pipefail" in script
    assert '[[ "$(uname -s)" == "Darwin" ]]' in script
    assert '[[ "$(uname -m)" == "$TARGET_ARCH" ]]' in script
    assert "python -m pytest -q" in script
    assert "python -m PyInstaller" in script
    assert '--target-architecture "$TARGET_ARCH"' not in script
    assert "dmgbuild -s packaging/dmg_settings.py" in script
    assert "hdiutil attach" in script
    assert "hdiutil detach" in script
    assert 'test -d "$MOUNT_POINT/$APP_BUNDLE"' in script
    assert 'test -L "$MOUNT_POINT/Applications"' in script
    assert 'test -f "$MOUNT_POINT/安装说明.md"' in script
    assert "shasum -a 256" in script
    assert "cleanup_smoke()" in script
    assert "trap cleanup_smoke EXIT" in script
    assert 'LEDGER_REPORTER_SMOKE_READY_FILE="$SMOKE_READY_FILE"' in script
    assert 'if [[ -f "$SMOKE_READY_FILE" ]]' in script
    assert 'if ! kill -0 "$APP_PID" 2>/dev/null' in script
    assert 'cat -- "$SMOKE_LOG_FILE" >&2' in script
    assert "sleep 0.1" in script
    assert "sleep 3" not in script
    assert 'cd "$DIST_DIR"' in script
    assert 'shasum -a 256 "$DMG_BASENAME" > "$CHECKSUM_BASENAME"' in script


def test_ci_builds_and_uploads_separate_native_intel_and_apple_silicon_artifacts() -> None:
    workflow = _read(".github/workflows/build-macos.yml")

    assert "runner: macos-15-intel" in workflow
    assert "runner: macos-15" in workflow
    assert "macos-14-arm64" not in workflow
    assert "arch: x86_64" in workflow
    assert "arch: arm64" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "TARGET_ARCH=${{ matrix.arch }} bash scripts/build_macos.sh" in workflow
    assert "ledger-report-generator-macos-${{ matrix.arch }}" in workflow
    assert "dist/台账报表生成器-${{ matrix.arch }}.dmg" in workflow
    assert "dist/台账报表生成器-${{ matrix.arch }}.dmg.sha256" in workflow
    assert "if-no-files-found: error" in workflow


def test_install_guide_covers_unsigned_install_dock_and_uninstall_behavior() -> None:
    guide = _read("docs/INSTALL_MACOS.md")

    for required_text in (
        "打开 DMG",
        "应用程序",
        "右键",
        "打开",
        "未签名",
        "Dock",
        "卸载",
        "Excel",
        "PNG",
        "不会删除",
    ):
        assert required_text in guide
