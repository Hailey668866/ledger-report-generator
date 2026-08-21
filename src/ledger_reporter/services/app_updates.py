import hashlib
import json
import platform
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RELEASES_LATEST_URL = (
    "https://api.github.com/repos/Hailey668866/ledger-report-generator/releases/latest"
)
USER_AGENT = "ledger-report-generator-update-check"
TIMEOUT_SECONDS = 15


class UpdateError(RuntimeError):
    pass


class UpdateCancelled(UpdateError):
    pass


@dataclass(frozen=True, slots=True)
class ReleaseUpdate:
    version: str
    tag: str
    dmg_url: str
    checksum_url: str
    notes: str


def version_key(value: str) -> tuple[int, ...]:
    text = value.strip().removeprefix("v")
    if not re.fullmatch(r"\d+(?:\.\d+)*", text):
        raise UpdateError(f"无法识别版本号：{value!r}。")
    return tuple(int(part) for part in text.split("."))


def _request(url: str) -> Request:
    return Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _open(opener: Callable[..., object], url: str):
    try:
        return opener(_request(url), timeout=TIMEOUT_SECONDS)
    except (HTTPError, URLError, OSError) as error:
        raise UpdateError(f"无法连接更新服务器：{error}") from None


def check_for_update(
    current_version: str,
    *,
    machine: str | None = None,
    opener: Callable[..., object] = urlopen,
) -> ReleaseUpdate | None:
    architecture = (machine or platform.machine()).lower()
    if architecture in {"aarch64", "arm64"}:
        architecture = "arm64"
    elif architecture in {"amd64", "x86_64"}:
        architecture = "x86_64"
    else:
        raise UpdateError(f"不支持的 Mac 芯片架构：{architecture or '<空白>'}。")
    try:
        with _open(opener, RELEASES_LATEST_URL) as response:
            payload = json.loads(response.read(1024 * 1024 + 1))
    except UpdateError:
        raise
    except (AttributeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise UpdateError(f"更新信息无法读取：{error}") from None
    if not isinstance(payload, dict):
        raise UpdateError("更新信息格式无效。")
    if payload.get("draft") or payload.get("prerelease"):
        return None
    tag = str(payload.get("tag_name", ""))
    latest = version_key(tag)
    current = version_key(current_version)
    width = max(len(latest), len(current))
    if latest + (0,) * (width - len(latest)) <= current + (0,) * (width - len(current)):
        return None
    names = {
        str(asset.get("label") or asset.get("name")): str(asset.get("browser_download_url"))
        for asset in payload.get("assets", [])
        if isinstance(asset, dict)
    }
    dmg_name = f"台账报表生成器-{architecture}.dmg"
    checksum_name = f"{dmg_name}.sha256"
    if not names.get(dmg_name) or not names.get(checksum_name):
        raise UpdateError(f"版本 {tag} 的 {architecture} 安装附件不完整。")
    return ReleaseUpdate(
        ".".join(str(part) for part in latest),
        tag,
        names[dmg_name],
        names[checksum_name],
        str(payload.get("body") or ""),
    )


def _checksum(data: bytes) -> tuple[str, str]:
    text = data.decode("utf-8", errors="strict").strip()
    match = re.fullmatch(r"([0-9a-fA-F]{64})(?:\s+\*?(.+))?", text)
    if not match:
        raise UpdateError("更新安装包校验文件无效。")
    name = Path(match.group(2) or "台账报表生成器.dmg").name
    if name != (match.group(2) or name) or not name.endswith(".dmg"):
        raise UpdateError("更新安装包文件名无效。")
    return match.group(1).lower(), name


def download_update(
    update: ReleaseUpdate,
    cache_dir: Path,
    *,
    opener: Callable[..., object] = urlopen,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    part: Path | None = None
    try:
        with _open(opener, update.checksum_url) as response:
            expected, filename = _checksum(response.read(4096))
        target = target_dir / filename
        part = target.with_suffix(target.suffix + ".part")
        part.unlink(missing_ok=True)
        digest = hashlib.sha256()
        received = 0
        with _open(opener, update.dmg_url) as response, part.open("wb") as output:
            try:
                total = int(response.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                total = 0
            while True:
                if cancelled is not None and cancelled():
                    raise UpdateCancelled("更新下载已取消。")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress is not None:
                    progress(received, total)
        if digest.hexdigest() != expected:
            raise UpdateError("更新安装包 SHA-256 校验失败。")
        part.replace(target)
        return target
    except (UpdateError, UpdateCancelled):
        if part is not None:
            part.unlink(missing_ok=True)
        raise
    except (HTTPError, URLError, OSError, UnicodeError) as error:
        if part is not None:
            part.unlink(missing_ok=True)
        raise UpdateError(f"更新安装包下载失败：{error}") from None
