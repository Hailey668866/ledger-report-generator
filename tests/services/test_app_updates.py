import hashlib
import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest

from ledger_reporter.services.app_updates import (
    ReleaseUpdate,
    UpdateCancelled,
    UpdateError,
    check_for_update,
    download_update,
    version_key,
)


class Response(io.BytesIO):
    def __init__(self, data: bytes, content_length: bool = False) -> None:
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))} if content_length else {}

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def test_version_comparison_is_numeric() -> None:
    assert version_key("v0.10.0") > version_key("0.9.0")
    assert version_key("1.2") == (1, 2)
    with pytest.raises(UpdateError, match="版本号"):
        version_key("version-next")


def test_check_selects_current_architecture_assets() -> None:
    payload = {
        "tag_name": "v0.2.0",
        "draft": False,
        "prerelease": False,
        "body": "更新说明",
        "assets": [
            {"name": "台账报表生成器-arm64.dmg", "browser_download_url": "https://x/arm.dmg"},
            {
                "name": "台账报表生成器-arm64.dmg.sha256",
                "browser_download_url": "https://x/arm.sha",
            },
            {"name": "台账报表生成器-x86_64.dmg", "browser_download_url": "https://x/intel.dmg"},
            {
                "name": "台账报表生成器-x86_64.dmg.sha256",
                "browser_download_url": "https://x/intel.sha",
            },
        ],
    }

    update = check_for_update(
        "0.1.0",
        machine="arm64",
        opener=lambda *_args, **_kwargs: Response(json.dumps(payload).encode()),
    )

    assert update == ReleaseUpdate(
        "0.2.0", "v0.2.0", "https://x/arm.dmg", "https://x/arm.sha", "更新说明"
    )


def test_check_uses_asset_label_when_github_sanitizes_unicode_name() -> None:
    payload = {
        "tag_name": "v0.2.2",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": "-arm64.dmg",
                "label": "台账报表生成器-arm64.dmg",
                "browser_download_url": "https://x/arm.dmg",
            },
            {
                "name": "-arm64.dmg.sha256",
                "label": "台账报表生成器-arm64.dmg.sha256",
                "browser_download_url": "https://x/arm.sha",
            },
        ],
    }

    update = check_for_update(
        "0.2.1",
        machine="arm64",
        opener=lambda *_args, **_kwargs: Response(json.dumps(payload).encode()),
    )

    assert update is not None
    assert update.dmg_url == "https://x/arm.dmg"
    assert update.checksum_url == "https://x/arm.sha"


def test_check_returns_none_for_current_or_prerelease() -> None:
    payload = {"tag_name": "v0.1.0", "draft": False, "prerelease": False, "assets": []}

    def opener(*_args, **_kwargs):
        return Response(json.dumps(payload).encode())

    assert check_for_update("0.1.0", machine="arm64", opener=opener) is None
    payload["tag_name"] = "v0.1.0"
    assert check_for_update("0.1", machine="arm64", opener=opener) is None
    payload["tag_name"] = "v9.0.0"
    payload["prerelease"] = True
    assert check_for_update("0.1.0", machine="arm64", opener=opener) is None


def test_check_wraps_network_errors() -> None:
    def offline(*_args, **_kwargs):
        raise URLError("offline")

    with pytest.raises(UpdateError, match="无法连接更新服务器"):
        check_for_update("0.1.0", machine="arm64", opener=offline)


def test_check_rejects_missing_or_unknown_architecture_assets() -> None:
    payload = {
        "tag_name": "v0.2.0",
        "draft": False,
        "prerelease": False,
        "assets": [],
    }

    def opener(*_args, **_kwargs):
        return Response(json.dumps(payload).encode())

    with pytest.raises(UpdateError, match="附件不完整"):
        check_for_update("0.1.0", machine="arm64", opener=opener)
    with pytest.raises(UpdateError, match="芯片架构"):
        check_for_update("0.1.0", machine="mips", opener=opener)


def test_download_verifies_checksum_reports_progress_and_renames(tmp_path: Path) -> None:
    data = b"native dmg contents"
    digest = hashlib.sha256(data).hexdigest()
    update = ReleaseUpdate("0.2.0", "v0.2.0", "https://x/dmg", "https://x/sha", "")
    responses = {
        "https://x/sha": f"{digest}  台账报表生成器-arm64.dmg\n".encode(),
        "https://x/dmg": data,
    }
    progress = []

    output = download_update(
        update,
        tmp_path,
        opener=lambda request, **_kwargs: Response(
            responses[request.full_url], content_length=request.full_url.endswith("/dmg")
        ),
        progress=lambda received, total: progress.append((received, total)),
    )

    assert output.name == "台账报表生成器-arm64.dmg"
    assert output.read_bytes() == data
    assert progress[-1] == (len(data), len(data))
    assert not list(tmp_path.glob("*.part"))


def test_download_cancellation_and_bad_checksum_remove_partial_files(tmp_path: Path) -> None:
    update = ReleaseUpdate("0.2.0", "v0.2.0", "https://x/dmg", "https://x/sha", "")
    responses = {"https://x/sha": b"0" * 64, "https://x/dmg": b"bad"}

    def opener(request, **_kwargs):
        return Response(responses[request.full_url])

    with pytest.raises(UpdateCancelled):
        download_update(update, tmp_path, opener=opener, cancelled=lambda: True)
    with pytest.raises(UpdateError, match="校验失败"):
        download_update(update, tmp_path, opener=opener)

    assert list(tmp_path.iterdir()) == []
