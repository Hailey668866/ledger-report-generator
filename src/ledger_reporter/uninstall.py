import json
import os
import shlex
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ledger_reporter.app_paths import APP_ID

APP_NAME = "台账报表生成器.app"
SYSTEM_APPLICATIONS = Path("/Applications")


@dataclass(frozen=True, slots=True)
class UninstallTargets:
    app: Path
    data: Path
    cache: Path
    preferences: Path
    logs: Path
    temp: Path

    @property
    def paths(self) -> tuple[Path, ...]:
        return (self.app, self.data, self.cache, self.preferences, self.logs, self.temp)

    @classmethod
    def for_home(
        cls,
        home: Path,
        app: Path,
        temp_root: Path | None = None,
    ) -> "UninstallTargets":
        home = Path(home)
        app = Path(app)
        temp_root = Path(temp_root) if temp_root else Path(tempfile.gettempdir())
        _validate_root(home, "用户目录")
        _validate_root(app, "应用路径")
        _validate_root(temp_root, "临时目录")
        allowed = {
            SYSTEM_APPLICATIONS / APP_NAME,
            home / "Applications" / APP_NAME,
        }
        if app not in allowed:
            raise ValueError("应用路径不符合卸载白名单")
        library = home / "Library"
        return cls(
            app=app,
            data=library / "Application Support" / APP_ID,
            cache=library / "Caches" / APP_ID,
            preferences=library / "Preferences" / f"{APP_ID}.plist",
            logs=library / "Logs" / APP_ID,
            temp=temp_root / APP_ID,
        )


def _validate_root(path: Path, label: str) -> None:
    value = path.as_posix()
    if not (path.is_absolute() or value.startswith("/")):
        raise ValueError(f"{label}必须是绝对路径")
    if ".." in path.parts:
        raise ValueError(f"{label}必须是规范路径")
    if value in {"/", ""}:
        raise ValueError(f"{label}不能是根目录")


def _validated_home(targets: UninstallTargets) -> Path:
    app = targets.app
    _validate_root(app, "应用路径")
    physical_parent = _physical_path(app.parent)
    if physical_parent != app.parent.as_posix():
        raise ValueError("应用父目录不能是符号链接，且物理路径必须与白名单一致")
    if app == SYSTEM_APPLICATIONS / APP_NAME:
        try:
            home = targets.data.parents[2]
        except IndexError:
            raise ValueError("卸载目标不完整") from None
    elif app.name == APP_NAME and app.parent.name == "Applications":
        home = app.parent.parent
    else:
        raise ValueError("卸载目标不符合应用白名单")
    expected = UninstallTargets.for_home(home, app, targets.temp.parent)
    if targets.paths != expected.paths:
        raise ValueError("卸载目标与应用内部路径不一致")
    return home


def _physical_path(path: Path) -> str:
    if sys.platform == "darwin":
        return path.resolve(strict=False).as_posix()
    return path.as_posix()


def _anchored_remove(path: Path, failure_message: str) -> tuple[str, ...]:
    parent = path.parent
    quoted_parent = shlex.quote(parent.as_posix())
    quoted_physical = shlex.quote(_physical_path(parent))
    quoted_name = shlex.quote(path.name)
    return (
        f"if [ -d {quoted_parent} ]; then",
        "    (",
        f"        cd -P -- {quoted_parent} &&",
        f'        [ "$(/bin/pwd -P)" = {quoted_physical} ] &&',
        f"        /bin/rm -rf -- {quoted_name}",
        f"    ) || fail {shlex.quote(failure_message)}",
        "fi",
    )


def resolve_installed_app(home: Path, executable: Path, *, frozen: bool) -> Path | None:
    if not frozen:
        return None
    executable = Path(executable)
    for parent in executable.parents:
        if parent.name != APP_NAME:
            continue
        try:
            UninstallTargets.for_home(home, parent)
        except ValueError:
            return None
        return parent
    return None


def default_uninstall_targets() -> UninstallTargets | None:
    home = Path.home()
    app = resolve_installed_app(
        home, Path(sys.executable), frozen=bool(getattr(sys, "frozen", False))
    )
    return None if app is None else UninstallTargets.for_home(home, app)


def build_uninstall_script(targets: UninstallTargets, *, parent_pid: int) -> str:
    if parent_pid <= 0:
        raise ValueError("parent PID must be positive")
    _validated_home(targets)
    error_script = shlex.quote(
        'on run argv\n    display alert "卸载未完成" message (item 1 of argv) as critical\nend run'
    )
    lines = [
        "#!/bin/sh",
        "set -u",
        'SCRIPT_PATH="$0"',
        "trap '/bin/rm -f -- \"$SCRIPT_PATH\"' EXIT",
        "fail() {",
        f'    /usr/bin/osascript -e {error_script} -- "$1" >/dev/null 2>&1 || true',
        "    exit 1",
        "}",
        f"PARENT_PID={parent_pid}",
        "WAIT_ATTEMPTS=0",
        "MAX_WAIT_ATTEMPTS=300",
        'while /bin/kill -0 "$PARENT_PID" 2>/dev/null; do',
        '    if [ "$WAIT_ATTEMPTS" -ge "$MAX_WAIT_ATTEMPTS" ]; then',
        '        fail "应用未能及时退出，请重新打开应用后再试。"',
        "    fi",
        "    sleep 0.2",
        "    WAIT_ATTEMPTS=$((WAIT_ATTEMPTS + 1))",
        "done",
    ]
    app_failure = "无法删除应用。若取消了系统授权，请重新打开应用后再试。"
    if targets.app.parent == SYSTEM_APPLICATIONS:
        app_command = " && ".join(
            (
                f"cd -P -- {shlex.quote(SYSTEM_APPLICATIONS.as_posix())}",
                f'[ "$(/bin/pwd -P)" = {shlex.quote(_physical_path(SYSTEM_APPLICATIONS))} ]',
                f"/bin/rm -rf -- {shlex.quote(APP_NAME)}",
            )
        )
        apple_script = shlex.quote(
            f"do shell script {json.dumps(app_command, ensure_ascii=False)} "
            "with administrator privileges"
        )
        lines.append(f"/usr/bin/osascript -e {apple_script} || fail {shlex.quote(app_failure)}")
    else:
        lines.extend(_anchored_remove(targets.app, app_failure))
    for path in targets.paths[1:]:
        lines.extend(_anchored_remove(path, f"无法删除内部数据：{path.name}"))
    success_script = shlex.quote(
        'display notification "应用及内部数据已删除" with title "台账报表生成器卸载完成"'
    )
    lines.append(f"/usr/bin/osascript -e {success_script} >/dev/null 2>&1 || true")
    return "\n".join(lines) + "\n"


def write_uninstall_helper(
    targets: UninstallTargets,
    helper_dir: Path | None = None,
) -> Path:
    directory = Path(helper_dir) if helper_dir else Path(tempfile.gettempdir())
    directory.mkdir(parents=True, exist_ok=True)
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix="uninstall-ledger-report-generator-",
            suffix=".sh",
            dir=directory,
            delete=False,
        ) as handle:
            path = Path(handle.name)
            handle.write(build_uninstall_script(targets, parent_pid=os.getpid()))
        path.chmod(0o700)
        return path
    except BaseException:
        if path is not None:
            path.unlink(missing_ok=True)
        raise
