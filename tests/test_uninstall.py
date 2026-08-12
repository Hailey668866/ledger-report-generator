import os
import shlex
from pathlib import Path

import pytest

import ledger_reporter.uninstall as uninstall_module
from ledger_reporter.uninstall import (
    UninstallTargets,
    build_uninstall_script,
    resolve_installed_app,
    write_uninstall_helper,
)


def test_script_only_contains_owned_paths_and_preserves_exports(tmp_path: Path) -> None:
    home = tmp_path / "home"
    app = Path("/Applications") / "台账报表生成器.app"
    targets = UninstallTargets.for_home(home, app, tmp_path / "temp")

    script = build_uninstall_script(targets, parent_pid=4321)

    assert targets.app.parent.as_posix() in script
    assert targets.app.name in script
    for target in targets.paths[1:]:
        assert target.parent.as_posix() in script
        assert target.name in script
    assert script.count("/bin/rm -rf --") == 6
    assert "com.local.ledger-report-generator" in str(targets.temp)
    assert "Desktop" not in script
    assert "Documents" not in script
    assert "trap" in script
    assert "osascript" in script
    assert "PARENT_PID=4321" in script
    assert 'while /bin/kill -0 "$PARENT_PID"' in script
    assert script.index('while /bin/kill -0 "$PARENT_PID"') < script.index("do shell script")


@pytest.mark.parametrize(
    "app",
    [
        Path("/Applications/Other.app"),
        Path("/tmp/台账报表生成器.app"),
    ],
)
def test_rejects_application_outside_exact_whitelist(tmp_path: Path, app: Path) -> None:
    with pytest.raises(ValueError, match="应用路径"):
        UninstallTargets.for_home(tmp_path, app)


def test_accepts_user_applications_install(tmp_path: Path) -> None:
    app = tmp_path / "Applications" / "台账报表生成器.app"

    targets = UninstallTargets.for_home(tmp_path, app)

    assert targets.app == app


@pytest.mark.parametrize(
    ("home", "app", "temp_root"),
    [
        (Path("relative-home"), Path("relative-home/Applications/台账报表生成器.app"), None),
        (
            Path("/Users/example/../victim"),
            Path("/Users/victim/Applications/台账报表生成器.app"),
            None,
        ),
        (Path("/Users/example"), Path("/Applications/台账报表生成器.app"), Path("../temp")),
    ],
)
def test_rejects_relative_or_non_normalized_roots(
    home: Path,
    app: Path,
    temp_root: Path | None,
) -> None:
    with pytest.raises(ValueError, match="绝对|规范"):
        UninstallTargets.for_home(home, app, temp_root)


def test_script_generator_revalidates_manually_constructed_targets() -> None:
    targets = UninstallTargets(
        app=Path("/Library/Victim.app"),
        data=Path("/tmp/data"),
        cache=Path("/tmp/cache"),
        preferences=Path("/tmp/preferences"),
        logs=Path("/tmp/logs"),
        temp=Path("/tmp/temp"),
    )

    with pytest.raises(ValueError, match="卸载目标"):
        build_uninstall_script(targets, parent_pid=4321)


def test_user_install_uses_unprivileged_anchored_removal(tmp_path: Path) -> None:
    home = tmp_path / "home"
    targets = UninstallTargets.for_home(
        home,
        home / "Applications" / "台账报表生成器.app",
        tmp_path / "temp",
    )

    script = build_uninstall_script(targets, parent_pid=4321)

    assert "administrator privileges" not in script
    assert "cd -P" in script
    assert targets.app.parent.resolve(strict=False).as_posix() in script
    assert "/bin/rm -rf -- '台账报表生成器.app'" in script
    quoted_parent = shlex.quote(targets.app.parent.as_posix())
    assert f"cd -P -- {quoted_parent} &&" in script
    assert f"= {quoted_parent} ] &&" in script


def test_rejects_user_applications_symlink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    applications = home / "Applications"
    app = applications / "台账报表生成器.app"
    targets = UninstallTargets.for_home(home, app, tmp_path / "temp")
    original_resolve = Path.resolve

    def redirected_resolve(path: Path, *, strict: bool = False) -> Path:
        if path == applications:
            return Path("/Applications")
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", redirected_resolve)
    monkeypatch.setattr(uninstall_module.sys, "platform", "darwin")

    with pytest.raises(ValueError, match="符号链接|物理路径"):
        build_uninstall_script(targets, parent_pid=4321)


def test_system_install_uses_privileged_anchored_removal(tmp_path: Path) -> None:
    targets = UninstallTargets.for_home(
        tmp_path / "home",
        Path("/Applications") / "台账报表生成器.app",
        tmp_path / "temp",
    )

    script = build_uninstall_script(targets, parent_pid=4321)

    assert "administrator privileges" in script
    assert "cd -P -- /Applications" in script
    assert "/bin/rm -rf --" in script
    assert "台账报表生成器.app" in script


def test_helper_wait_is_bounded_and_reports_final_outcome(tmp_path: Path) -> None:
    targets = UninstallTargets.for_home(
        tmp_path / "home",
        Path("/Applications") / "台账报表生成器.app",
        tmp_path / "temp",
    )

    script = build_uninstall_script(targets, parent_pid=4321)

    assert "MAX_WAIT_ATTEMPTS=300" in script
    assert 'if [ "$WAIT_ATTEMPTS" -ge "$MAX_WAIT_ATTEMPTS" ]' in script
    assert "卸载未完成" in script
    assert "卸载完成" in script
    assert "on run argv" in script
    assert "message (item 1 of argv) as critical" in script
    assert "end run" in script


def test_resolves_bundle_from_frozen_executable(tmp_path: Path) -> None:
    home = tmp_path / "home"
    app = home / "Applications" / "台账报表生成器.app"
    executable = app / "Contents" / "MacOS" / "台账报表生成器"

    assert resolve_installed_app(home, executable, frozen=True) == app
    assert resolve_installed_app(home, executable, frozen=False) is None
    assert (
        resolve_installed_app(home, tmp_path / "Downloads" / executable.name, frozen=True) is None
    )


def test_writes_private_executable_helper_to_requested_temp_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    targets = UninstallTargets.for_home(
        home,
        home / "Applications" / "台账报表生成器.app",
        tmp_path / "owned-temp",
    )

    chmod_calls: list[tuple[Path, int]] = []
    original_chmod = Path.chmod

    def record_chmod(path: Path, mode: int) -> None:
        chmod_calls.append((path, mode))
        original_chmod(path, mode)

    monkeypatch.setattr(Path, "chmod", record_chmod)

    helper = write_uninstall_helper(targets, tmp_path / "helpers")

    assert helper.parent == tmp_path / "helpers"
    script = helper.read_text(encoding="utf-8")
    assert script == build_uninstall_script(targets, parent_pid=os.getpid())
    assert chmod_calls == [(helper, 0o700)]

    second = write_uninstall_helper(targets, tmp_path / "helpers")
    assert second != helper
    assert second.is_file()


def test_failed_chmod_removes_partially_created_helper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    targets = UninstallTargets.for_home(
        home,
        home / "Applications" / "台账报表生成器.app",
        tmp_path / "owned-temp",
    )
    helper_dir = tmp_path / "helpers"

    def fail_chmod(_path: Path, _mode: int) -> None:
        raise OSError("chmod failed")

    monkeypatch.setattr(Path, "chmod", fail_chmod)

    with pytest.raises(OSError, match="chmod failed"):
        write_uninstall_helper(targets, helper_dir)

    assert list(helper_dir.iterdir()) == []
