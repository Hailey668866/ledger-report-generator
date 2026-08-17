import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from ledger_reporter.io import source_settings
from ledger_reporter.io.source_settings import (
    DEFAULT_SOURCE_SETTINGS,
    SourceSettings,
    load_source_settings,
    save_source_settings,
)


def test_default_source_settings() -> None:
    assert DEFAULT_SOURCE_SETTINGS == SourceSettings(
        funds_sheet="资金散板汇总{年份}",
        funds_header_row=1,
        funds_channel="渠道名称",
        funds_payment_date="信容付款日期",
        funds_amount="付款金额合计（90%）",
        funds_operation_fee="应收操作费",
        operations_sheet="台账明细",
        operations_header_row=1,
        operations_bill_no="提单号",
        operations_project_type="项目类型",
        operations_destination="目的口岸",
        operations_departure="预计起飞时间",
        operations_supplier="B1供应商",
        operations_receivable="预估总应收",
        operations_gross_profit="预估毛利润",
    )


def test_source_settings_is_frozen_and_slotted() -> None:
    settings = SourceSettings()

    with pytest.raises(FrozenInstanceError):
        settings.funds_sheet = "其他"  # type: ignore[misc]
    assert not hasattr(settings, "__dict__")


def test_modified_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "source-settings.json"
    settings = replace(
        DEFAULT_SOURCE_SETTINGS,
        funds_sheet="资金表{年份}",
        funds_header_row=3,
        operations_bill_no="运单号",
    )

    save_source_settings(path, settings)

    assert load_source_settings(path) == settings


def test_load_missing_file_returns_default(tmp_path: Path) -> None:
    assert load_source_settings(tmp_path / "missing.json") is DEFAULT_SOURCE_SETTINGS


@pytest.mark.parametrize(
    "field_name",
    [field.name for field in fields(SourceSettings) if not field.name.endswith("_header_row")],
)
@pytest.mark.parametrize("value", ["", "   "])
def test_validate_rejects_empty_sheet_and_field_names(field_name: str, value: str) -> None:
    settings = replace(DEFAULT_SOURCE_SETTINGS, **{field_name: value})

    with pytest.raises(ValueError, match="非空字符串"):
        settings.validate()


@pytest.mark.parametrize("field_name", ["funds_sheet", "operations_bill_no"])
def test_validate_rejects_non_string_names(field_name: str) -> None:
    settings = replace(DEFAULT_SOURCE_SETTINGS, **{field_name: 1})

    with pytest.raises(ValueError, match="非空字符串"):
        settings.validate()


@pytest.mark.parametrize("field_name", ["funds_header_row", "operations_header_row"])
@pytest.mark.parametrize("value", [0, -1, "1", True])
def test_validate_rejects_invalid_header_rows(field_name: str, value: object) -> None:
    settings = replace(DEFAULT_SOURCE_SETTINGS, **{field_name: value})

    with pytest.raises(ValueError, match="正整数"):
        settings.validate()


@pytest.mark.parametrize("field_name", ["funds_header_row", "operations_header_row"])
def test_validate_accepts_xlsx_maximum_header_row(field_name: str) -> None:
    replace(DEFAULT_SOURCE_SETTINGS, **{field_name: 1_048_576}).validate()


@pytest.mark.parametrize("field_name", ["funds_header_row", "operations_header_row"])
def test_validate_rejects_header_rows_beyond_xlsx_limit(field_name: str) -> None:
    settings = replace(DEFAULT_SOURCE_SETTINGS, **{field_name: 1_048_577})

    with pytest.raises(ValueError, match="1 至 1048576"):
        settings.validate()


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("funds_channel", "funds_payment_date"),
        ("operations_bill_no", "operations_project_type"),
    ],
)
def test_validate_rejects_duplicate_fields_on_same_sheet(first: str, second: str) -> None:
    duplicate = getattr(DEFAULT_SOURCE_SETTINGS, first)
    settings = replace(DEFAULT_SOURCE_SETTINGS, **{second: duplicate})

    with pytest.raises(ValueError, match="同一工作表.*重复"):
        settings.validate()


def test_validate_allows_same_field_name_on_different_sheets() -> None:
    settings = replace(DEFAULT_SOURCE_SETTINGS, operations_bill_no="渠道名称")

    settings.validate()


@pytest.mark.parametrize(
    ("contents", "error_text"),
    [
        ("{broken", "字段设置文件无法读取"),
        (json.dumps({"unknown": "value"}), "字段设置文件无法读取"),
    ],
)
def test_load_rejects_invalid_json_and_unknown_keys(
    tmp_path: Path, contents: str, error_text: str
) -> None:
    path = tmp_path / "source-settings.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=error_text):
        load_source_settings(path)


def test_load_wraps_validation_errors(tmp_path: Path) -> None:
    path = tmp_path / "source-settings.json"
    data = {
        field.name: getattr(DEFAULT_SOURCE_SETTINGS, field.name) for field in fields(SourceSettings)
    }
    data["funds_header_row"] = False
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="字段设置文件无法读取.*正整数"):
        load_source_settings(path)


def test_save_writes_readable_chinese_json(tmp_path: Path) -> None:
    path = tmp_path / "source-settings.json"

    save_source_settings(path, DEFAULT_SOURCE_SETTINGS)

    text = path.read_text(encoding="utf-8")
    assert "资金散板汇总{年份}" in text
    assert "\\u8d44" not in text
    assert json.loads(text)["operations_sheet"] == "台账明细"


def test_save_replace_failure_preserves_old_file_and_cleans_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "source-settings.json"
    old_contents = '{"old": true}'
    path.write_text(old_contents, encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(source_settings.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        save_source_settings(path, DEFAULT_SOURCE_SETTINGS)

    assert path.read_text(encoding="utf-8") == old_contents
    assert list(tmp_path.iterdir()) == [path]


def test_save_write_failure_preserves_old_file_and_cleans_partial_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "source-settings.json"
    old_contents = '{"old": true}'
    path.write_text(old_contents, encoding="utf-8")

    def fail_dump(value: object, handle: object, **kwargs: object) -> None:
        handle.write('{"partial":')  # type: ignore[attr-defined]
        raise OSError("write failed")

    monkeypatch.setattr(source_settings.json, "dump", fail_dump)

    with pytest.raises(OSError, match="write failed"):
        save_source_settings(path, DEFAULT_SOURCE_SETTINGS)

    assert path.read_text(encoding="utf-8") == old_contents
    assert list(tmp_path.iterdir()) == [path]
