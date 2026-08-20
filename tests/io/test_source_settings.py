import json
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from ledger_reporter.io import source_settings
from ledger_reporter.io.source_settings import (
    DEFAULT_SOURCE_SETTINGS,
    AggregateRule,
    FilterRule,
    load_source_settings,
    save_source_settings,
)


def test_defaults_keep_every_summary_output_independent() -> None:
    settings = DEFAULT_SOURCE_SETTINGS

    assert settings.project_count is not settings.project_profit
    assert settings.project_count.date_field == "预计起飞时间"
    assert settings.project_count.value_field == "提单号"
    assert settings.project_profit.value_field == "预估毛利润"
    assert settings.scatter_count.filters == (FilterRule("项目类型", "散采"),)
    assert settings.project_count.filters == (FilterRule("项目类型", "散采", exclude=True),)
    assert settings.fund_profit.channels[0].rate == Decimal("0.10")
    assert settings.fund_profit.capital_cost == Decimal("0.0448")
    assert settings.fund_profit.term_days == 60


def test_defaults_cover_all_weekly_rows_and_independent_metrics() -> None:
    settings = DEFAULT_SOURCE_SETTINGS

    assert len(settings.business_rows) == 11
    yinhua = next(row for row in settings.business_rows if row.name == "印华固定位LGG")
    assert yinhua.count is not yinhua.profit
    assert yinhua.profit is not yinhua.margin
    assert FilterRule("目的口岸", "LGG") in yinhua.count.filters
    assert yinhua.cycle == "26.1.1--26.12.29"


def test_settings_are_frozen_and_slotted() -> None:
    with pytest.raises(FrozenInstanceError):
        DEFAULT_SOURCE_SETTINGS.funds_sheet = "其他"  # type: ignore[misc]
    assert not hasattr(DEFAULT_SOURCE_SETTINGS, "__dict__")


def test_validation_accepts_disabled_filter_and_rejects_half_filter() -> None:
    FilterRule("", "").validate("测试")

    with pytest.raises(ValueError, match="字段和值必须同时填写"):
        FilterRule("供应商", "").validate("测试")


@pytest.mark.parametrize("rate", [Decimal("-0.01"), Decimal("1.01")])
def test_validation_rejects_invalid_percentages(rate: Decimal) -> None:
    channel = replace(DEFAULT_SOURCE_SETTINGS.fund_profit.channels[0], rate=rate)
    rule = replace(DEFAULT_SOURCE_SETTINGS.fund_profit, channels=(channel,))

    with pytest.raises(ValueError, match="0% 至 100%"):
        replace(DEFAULT_SOURCE_SETTINGS, fund_profit=rule).validate()


def test_validation_rejects_duplicate_fund_channels() -> None:
    channel = DEFAULT_SOURCE_SETTINGS.fund_profit.channels[0]
    rule = replace(DEFAULT_SOURCE_SETTINGS.fund_profit, channels=(channel, channel))

    with pytest.raises(ValueError, match="资金渠道名称不可重复"):
        replace(DEFAULT_SOURCE_SETTINGS, fund_profit=rule).validate()


def test_modified_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "source-fields.json"
    project_count = replace(
        DEFAULT_SOURCE_SETTINGS.project_count,
        date_field="订单日期",
        value_field="订单编号",
    )
    settings = replace(
        DEFAULT_SOURCE_SETTINGS,
        funds_sheet="资金表{年份}",
        funds_header_row=3,
        project_count=project_count,
    )

    save_source_settings(path, settings)

    assert load_source_settings(path) == settings
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["project_count"]["date_field"] == "订单日期"
    assert data["fund_profit"]["channels"][0]["rate"] == "0.10"


def test_legacy_flat_settings_migrate_to_every_dependent_output(tmp_path: Path) -> None:
    path = tmp_path / "source-fields.json"
    path.write_text(
        json.dumps(
            {
                "funds_sheet": "资金表{年份}",
                "funds_header_row": 3,
                "funds_channel": "渠道字段",
                "funds_payment_date": "放款日",
                "funds_amount": "放款额",
                "funds_operation_fee": "操作费",
                "operations_sheet": "运营表",
                "operations_header_row": 4,
                "operations_bill_no": "订单号",
                "operations_project_type": "业务类型",
                "operations_destination": "港口",
                "operations_departure": "起飞日",
                "operations_supplier": "供应商",
                "operations_receivable": "应收",
                "operations_gross_profit": "毛利",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    settings = load_source_settings(path)

    assert (settings.funds_sheet, settings.operations_sheet) == ("资金表{年份}", "运营表")
    assert settings.project_count == AggregateRule(
        "起飞日", "订单号", (FilterRule("业务类型", "散采", exclude=True),)
    )
    assert settings.project_profit.value_field == "毛利"
    assert settings.fund_amount == AggregateRule("放款日", "放款额")
    assert settings.fund_profit.channel_field == "渠道字段"
    assert all(row.count.date_field == "起飞日" for row in settings.business_rows)
    assert all(row.margin.denominator_field == "应收" for row in settings.business_rows)


def test_load_missing_file_returns_default(tmp_path: Path) -> None:
    assert load_source_settings(tmp_path / "missing.json") is DEFAULT_SOURCE_SETTINGS


@pytest.mark.parametrize(
    ("contents", "error_text"),
    [
        ("{broken", "字段设置文件无法读取"),
        (json.dumps({"unknown": "value"}), "字段设置文件无法读取"),
        (json.dumps({"schema_version": 99}), "不支持的设置版本"),
    ],
)
def test_load_rejects_invalid_json_unknown_keys_and_versions(
    tmp_path: Path, contents: str, error_text: str
) -> None:
    path = tmp_path / "source-fields.json"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=error_text):
        load_source_settings(path)


def test_save_replace_failure_preserves_old_file_and_cleans_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "source-fields.json"
    path.write_text('{"old": true}', encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(source_settings.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        save_source_settings(path, DEFAULT_SOURCE_SETTINGS)

    assert path.read_text(encoding="utf-8") == '{"old": true}'
    assert list(tmp_path.iterdir()) == [path]
