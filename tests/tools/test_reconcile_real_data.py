import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

from tools import reconcile_real_data
from tools.reconcile_real_data import main, reconcile

OPS_HEADERS = (
    "提单号",
    "项目类型",
    "目的口岸",
    "预计起飞时间",
    "B1供应商",
    "预估总应收",
    "预估毛利润",
)
FUND_HEADERS = ("渠道名称", "信容付款日期", "付款金额合计（90%）", "应收操作费")


def _save_book(
    path: Path,
    sheet_name: str,
    headers: tuple[str, ...],
    rows: list[tuple[object, ...]],
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


def test_independent_reconciliation_matches_service_for_all_six_metrics(tmp_path: Path) -> None:
    operations_path = tmp_path / "operations.xlsx"
    funds_path = tmp_path / "funds.xlsx"
    _save_book(
        operations_path,
        "台账明细",
        OPS_HEADERS,
        [
            ("P-1", "BSA", "LAX", date(2026, 8, 1), "供应商 A", 1000, 100),
            ("S-1", "散采", "OSL", date(2026, 8, 6), "供应商 B", 500, 20),
            ("P-2", "BSA", "LAX", date(2026, 8, 7), "供应商 A", 700, 70),
            ("产品表", "运费计费重时更新", "产品表", "产品表", "产品表", "公式", None),
        ],
    )
    _save_book(
        funds_path,
        "资金散板汇总2026",
        FUND_HEADERS,
        [
            (
                "广州美鑫通国际供应链有限公司",
                date(2026, 8, 4),
                900,
                5,
            ),
            ("浙江飞速供应链管理有限公司", "未放款", 1000, 10),
        ],
    )

    result = reconcile(funds_path, operations_path, tmp_path / "history.sqlite3")

    assert result["differences"] == {
        "project_count": 0,
        "project_profit": Decimal(0),
        "scatter_count": 0,
        "scatter_profit": Decimal(0),
        "fund_amount": Decimal(0),
        "fund_profit": Decimal(0),
    }
    assert result["actual"] == {
        "project_count": 1,
        "project_profit": Decimal(100),
        "scatter_count": 1,
        "scatter_profit": Decimal(20),
        "fund_amount": Decimal(900),
        "fund_profit": Decimal("13.16657534246575342465753425"),
    }


def _result(difference: Decimal = Decimal(0)) -> dict[str, object]:
    values = {
        "project_count": 1,
        "project_profit": Decimal(2),
        "scatter_count": 3,
        "scatter_profit": Decimal(4),
        "fund_amount": Decimal(5),
        "fund_profit": Decimal(6),
    }
    differences = {name: 0 for name in values}
    differences["fund_profit"] = difference
    return {"expected": values, "actual": values, "differences": differences}


def _stub_main_dependencies(monkeypatch, result: dict[str, object]) -> None:
    monkeypatch.setattr(reconcile_real_data, "_fingerprint", lambda _path: (1, 2, "hash"))
    monkeypatch.setattr(reconcile_real_data, "reconcile", lambda *_args: result)


def test_main_prints_json_and_returns_zero_when_metrics_match(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    _stub_main_dependencies(monkeypatch, _result())

    status = main([str(tmp_path / "funds.xlsx"), str(tmp_path / "operations.xlsx")])

    assert status == 0
    output = json.loads(capsys.readouterr().out)
    assert output["period"] == ["2026-08-01", "2026-08-06"]
    assert output["actual"]["fund_profit"] == "6"
    assert output["differences"]["fund_profit"] == "0"


def test_main_returns_one_when_any_metric_differs(monkeypatch, tmp_path: Path) -> None:
    _stub_main_dependencies(monkeypatch, _result(Decimal("0.01")))

    status = main([str(tmp_path / "funds.xlsx"), str(tmp_path / "operations.xlsx")])

    assert status == 1


def test_main_returns_two_for_wrong_argument_count(capsys) -> None:
    assert main([]) == 2
    assert "用法" in capsys.readouterr().out


def test_main_returns_one_when_source_fingerprint_changes(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    fingerprints = iter(
        (
            (1, 2, "before"),
            (1, 2, "before"),
            (1, 3, "after"),
            (1, 2, "before"),
        )
    )
    monkeypatch.setattr(reconcile_real_data, "_fingerprint", lambda _path: next(fingerprints))
    monkeypatch.setattr(reconcile_real_data, "reconcile", lambda *_args: _result())

    status = main([str(tmp_path / "funds.xlsx"), str(tmp_path / "operations.xlsx")])

    assert status == 1
    assert "源工作簿发生变化" in capsys.readouterr().err
