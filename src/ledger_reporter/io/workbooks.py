from collections.abc import Iterable, Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from itertools import zip_longest
from pathlib import Path
from re import compile as re_compile
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.worksheet import Worksheet

from ledger_reporter.domain.models import FundRecord, OperationalRecord
from ledger_reporter.io.errors import WorkbookDataError

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
FUND_SHEET_PATTERN = re_compile(r"资金散板汇总\d{4}")


def _open_workbook(path: Path, data_only: bool):
    source = Path(path)
    if source.suffix.lower() != ".xlsx":
        raise WorkbookDataError(f"文件「{source}」不是 .xlsx 工作簿。")
    if not source.is_file():
        raise WorkbookDataError(f"找不到工作簿文件「{source}」。")
    try:
        return load_workbook(source, read_only=True, data_only=data_only, keep_links=False)
    except (BadZipFile, InvalidFileException, KeyError):
        raise WorkbookDataError(f"文件「{source}」不是有效的 XLSX 工作簿。") from None
    except OSError as error:
        raise WorkbookDataError(f"无法读取工作簿「{source}」：{error}") from None


def _decimal(value: object, label: str) -> Decimal:
    if value is None or value == "":
        return Decimal("0")  # noqa: FURB157
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise WorkbookDataError(f"字段「{label}」包含无法识别的金额：{value!r}。") from None


def _date(value: object, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise WorkbookDataError(f"字段「{label}」包含无法识别的日期：{value!r}。")


def _header_positions(headers: tuple[object, ...], required_headers: tuple[str, ...], sheet_name: str) -> dict[str, int]:
    positions: dict[str, int] = {}
    for header in required_headers:
        matches = [index for index, value in enumerate(headers) if value == header]
        if len(matches) > 1:
            raise WorkbookDataError(f"工作表「{sheet_name}」存在重复字段「{header}」。")
        if not matches:
            raise WorkbookDataError(f"工作表「{sheet_name}」缺少必填字段「{header}」。")
        positions[header] = matches[0]
    return positions


def _rows(worksheet: Worksheet, required_headers: tuple[str, ...]) -> Iterator[dict[str, object]]:
    row_iterator = worksheet.iter_rows(values_only=True)
    try:
        headers = next(row_iterator)
    except StopIteration:
        raise WorkbookDataError(f"工作表「{worksheet.title}」为空，无法读取表头。") from None
    positions = _header_positions(headers, required_headers, worksheet.title)
    for row in row_iterator:
        yield {
            header: row[index] if index < len(row) else None
            for header, index in positions.items()
        }


def _ensure_formula_cache(path: Path, sheet_name: str, numeric_headers: tuple[str, ...]) -> None:
    cached_book = _open_workbook(path, data_only=True)
    formula_book = None
    try:
        formula_book = _open_workbook(path, data_only=False)
        try:
            cached_sheet = cached_book[sheet_name]
            formula_sheet = formula_book[sheet_name]
        except KeyError:
            raise WorkbookDataError(f"工作簿「{path}」缺少工作表「{sheet_name}」。") from None

        cached_rows = cached_sheet.iter_rows(values_only=True)
        formula_rows = formula_sheet.iter_rows(values_only=True)
        try:
            cached_headers = next(cached_rows)
            formula_headers = next(formula_rows)
        except StopIteration:
            raise WorkbookDataError(f"工作表「{sheet_name}」为空，无法校验公式缓存。") from None
        cached_positions = _header_positions(cached_headers, numeric_headers, sheet_name)
        formula_positions = _header_positions(formula_headers, numeric_headers, sheet_name)
        if cached_positions != formula_positions:
            raise WorkbookDataError(f"工作表「{sheet_name}」的公式和值视图行结构不一致。")

        missing = object()
        for cached_row, formula_row in zip_longest(cached_rows, formula_rows, fillvalue=missing):
            if cached_row is missing or formula_row is missing:
                raise WorkbookDataError(f"工作表「{sheet_name}」的公式和值视图行结构不一致。")
            for header, index in formula_positions.items():
                formula = formula_row[index] if index < len(formula_row) else None
                cached = cached_row[index] if index < len(cached_row) else None
                if isinstance(formula, str) and formula.startswith("=") and cached is None:
                    raise WorkbookDataError(
                        f"工作表「{sheet_name}」字段「{header}」的公式没有缓存结果。"
                        "请用 Excel 或 WPS 重新计算后保存该工作簿，再重新导入。"
                    )
    finally:
        if formula_book is not None:
            formula_book.close()
        cached_book.close()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def read_operations(path: Path) -> list[OperationalRecord]:
    source = Path(path)
    _ensure_formula_cache(source, "台账明细", ("预估总应收", "预估毛利润"))
    workbook = _open_workbook(source, data_only=True)
    try:
        try:
            worksheet = workbook["台账明细"]
        except KeyError:
            raise WorkbookDataError(f"工作簿「{source}」缺少工作表「台账明细」。") from None

        records: list[OperationalRecord] = []
        for row in _rows(worksheet, OPS_HEADERS):
            departure_value = row["预计起飞时间"]
            if departure_value is None or departure_value == "":
                continue
            records.append(
                OperationalRecord(
                    bill_no=_optional_text(row["提单号"]),
                    project_type=_optional_text(row["项目类型"]),
                    destination=_optional_text(row["目的口岸"]),
                    departure=_date(departure_value, "预计起飞时间"),
                    supplier=_optional_text(row["B1供应商"]),
                    receivable=_decimal(row["预估总应收"], "预估总应收"),
                    gross_profit=_decimal(row["预估毛利润"], "预估毛利润"),
                )
            )
        return records
    finally:
        workbook.close()


def read_funds(path: Path, years: Iterable[int]) -> list[FundRecord]:
    source = Path(path)
    requested_years = set(years)
    workbook = _open_workbook(source, data_only=True)
    try:
        selected_sheets = [
            name
            for name in workbook.sheetnames
            if FUND_SHEET_PATTERN.fullmatch(name) and int(name[-4:]) in requested_years
        ]
    finally:
        workbook.close()

    if not selected_sheets:
        years_text = "、".join(str(year) for year in sorted(requested_years))
        raise WorkbookDataError(f"工作簿「{source}」未找到资金散板汇总工作表（请求年度：{years_text}）。")

    records: list[FundRecord] = []
    for sheet_name in selected_sheets:
        _ensure_formula_cache(source, sheet_name, ("付款金额合计（90%）", "应收操作费"))
        workbook = _open_workbook(source, data_only=True)
        try:
            worksheet = workbook[sheet_name]
            for row in _rows(worksheet, FUND_HEADERS):
                payment_date = row["信容付款日期"]
                if payment_date is None or payment_date == "":
                    continue
                channel = _optional_text(row["渠道名称"])
                records.append(
                    FundRecord(
                        channel=channel or "",
                        payment_date=_date(payment_date, "信容付款日期"),
                        amount=_decimal(row["付款金额合计（90%）"], "付款金额合计（90%）"),
                        operation_fee=_decimal(row["应收操作费"], "应收操作费"),
                    )
                )
        finally:
            workbook.close()
    return records
