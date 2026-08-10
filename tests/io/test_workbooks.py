from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook, load_workbook

from ledger_reporter.io import workbooks
from ledger_reporter.io.errors import WorkbookDataError
from ledger_reporter.io.workbooks import read_funds, read_operations

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


def save_book(path: Path, sheet_name: str, headers: tuple[str, ...], rows: list[tuple[object, ...]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()


def corrupt_first_sheet_xml(path: Path) -> None:
    with ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members["xl/worksheets/sheet1.xml"] += b"<"
    with ZipFile(path, "w") as archive:
        for name, contents in members.items():
            archive.writestr(name, contents)


def test_read_operations_maps_headers_and_converts_values(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    headers = (
        "预计起飞时间",
        "预估毛利润",
        "目的口岸",
        "B1供应商",
        "提单号",
        "预估总应收",
        "项目类型",
    )
    save_book(
        path,
        "台账明细",
        headers,
        [
            (
                datetime(2026, 8, 2, 10, 30),  # noqa: DTZ001
                12.5,
                "LAX",
                "供应商 A",
                "000123",
                100,
                "散板",
            )
        ],
    )

    records = read_operations(path)

    assert len(records) == 1
    record = records[0]
    assert record.bill_no == "000123"
    assert record.project_type == "散板"
    assert record.destination == "LAX"
    assert record.departure == date(2026, 8, 2)
    assert record.supplier == "供应商 A"
    assert record.receivable == Decimal(100)
    assert record.gross_profit == Decimal("12.5")


def test_read_operations_accepts_iso_datetime_string(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    save_book(
        path,
        "台账明细",
        OPS_HEADERS,
        [("B-1", "散板", "LAX", "2026-08-02 10:30:00", "供应商 A", 100, 10)],
    )

    records = read_operations(path)

    assert records[0].departure == date(2026, 8, 2)


def test_read_operations_rejects_missing_required_header(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    save_book(path, "台账明细", OPS_HEADERS[:-1], [])

    with pytest.raises(WorkbookDataError, match="预估毛利润"):
        read_operations(path)


def test_read_operations_rejects_duplicate_required_header(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    save_book(path, "台账明细", OPS_HEADERS + ("提单号",), [])

    with pytest.raises(WorkbookDataError, match="重复字段.*提单号"):
        read_operations(path)


def test_read_operations_rejects_corrupt_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    path.write_bytes(b"not an xlsx workbook")

    with pytest.raises(WorkbookDataError, match="不是有效的 XLSX"):
        read_operations(path)


@pytest.mark.parametrize("value", ["NaN", "Infinity"])
def test_read_operations_rejects_non_finite_amounts(tmp_path: Path, value: str) -> None:
    path = tmp_path / "operations.xlsx"
    save_book(
        path,
        "台账明细",
        OPS_HEADERS,
        [("B-1", "散板", "LAX", "2026-08-02", "供应商 A", value, 10)],
    )

    with pytest.raises(WorkbookDataError, match="预估总应收"):
        read_operations(path)


def test_read_operations_rejects_zip_without_ooxml_parts(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr("dummy.txt", "not an OOXML workbook")

    with pytest.raises(WorkbookDataError, match="不是有效的 XLSX"):
        read_operations(path)


def test_read_operations_rejects_lazy_worksheet_xml_corruption(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    save_book(
        path,
        "台账明细",
        OPS_HEADERS,
        [("B-1", "散板", "LAX", "2026-08-02", "供应商 A", 100, 10)],
    )
    corrupt_first_sheet_xml(path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    workbook.close()

    with pytest.raises(WorkbookDataError, match="不是有效的 XLSX"):
        read_operations(path)


def test_read_funds_reads_requested_year_sheet(tmp_path: Path) -> None:
    path = tmp_path / "funds.xlsx"
    save_book(
        path,
        "资金散板汇总2026",
        FUND_HEADERS,
        [("渠道 A", "2026-08-05", 90, 3.25)],
    )

    records = read_funds(path, {2026})

    assert len(records) == 1
    record = records[0]
    assert record.channel == "渠道 A"
    assert record.payment_date == date(2026, 8, 5)
    assert record.amount == Decimal(90)
    assert record.operation_fee == Decimal("3.25")


def test_read_funds_uses_allowed_years_parameter(tmp_path: Path) -> None:
    path = tmp_path / "funds.xlsx"
    save_book(
        path,
        "资金散板汇总2026",
        FUND_HEADERS,
        [("渠道 A", "2026-08-05", 90, 3.25)],
    )

    records = read_funds(path, allowed_years={2026, 2027})

    assert len(records) == 1


def test_read_funds_reuses_two_workbook_views_across_selected_sheets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "funds.xlsx"
    save_book(
        path,
        "资金散板汇总2026",
        FUND_HEADERS,
        [("渠道 A", "2026-08-05", 90, 3.25)],
    )
    workbook = load_workbook(path)
    worksheet = workbook.create_sheet("资金散板汇总2027")
    worksheet.append(FUND_HEADERS)
    worksheet.append(("渠道 B", "2027-04-05", 80, 2.25))
    workbook.save(path)
    workbook.close()

    calls: list[bool] = []
    open_workbook = workbooks._open_workbook

    def spy_open_workbook(source: Path, data_only: bool):
        calls.append(data_only)
        return open_workbook(source, data_only)

    monkeypatch.setattr(workbooks, "_open_workbook", spy_open_workbook)

    records = workbooks.read_funds(path, allowed_years={2026, 2027})

    assert {record.channel for record in records} == {"渠道 A", "渠道 B"}
    assert calls == [True, False]


def test_read_operations_skips_formula_cache_check_for_blank_departure(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    save_book(
        path,
        "台账明细",
        OPS_HEADERS,
        [("B-1", "散板", "LAX", None, "供应商 A", 100, "=1+1")],
    )

    assert read_operations(path) == []


def test_read_funds_skips_formula_cache_check_for_blank_payment_date(tmp_path: Path) -> None:
    path = tmp_path / "funds.xlsx"
    save_book(
        path,
        "资金散板汇总2026",
        FUND_HEADERS,
        [("渠道 A", None, "=1+1", 3)],
    )

    assert read_funds(path, {2026}) == []


def test_read_operations_rejects_formula_without_cached_result(tmp_path: Path) -> None:
    path = tmp_path / "operations.xlsx"
    save_book(
        path,
        "台账明细",
        OPS_HEADERS,
        [("B-1", "散板", "LAX", "2026-08-02", "供应商 A", 100, "=1+1")],
    )

    with pytest.raises(WorkbookDataError, match="公式没有缓存结果"):
        read_operations(path)
