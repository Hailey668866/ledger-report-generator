from collections.abc import Iterable, Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from itertools import zip_longest
from pathlib import Path
from re import compile as re_compile
from xml.etree.ElementTree import ParseError
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
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise WorkbookDataError(f"字段「{label}」包含无法识别的金额：{value!r}。") from None
    if not result.is_finite():
        raise WorkbookDataError(f"字段「{label}」包含无法识别的金额：{value!r}。")
    return result


def _date(value: object, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
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


def _validated_rows(
    cached_sheet: Worksheet,
    formula_sheet: Worksheet,
    required_headers: tuple[str, ...],
    numeric_headers: tuple[str, ...],
    active_date_header: str,
) -> Iterator[dict[str, object]]:
    sheet_name = cached_sheet.title
    cached_rows = cached_sheet.iter_rows(values_only=True)
    formula_rows = formula_sheet.iter_rows()
    try:
        cached_headers = next(cached_rows)
        formula_headers = next(formula_rows)
    except StopIteration:
        raise WorkbookDataError(f"工作表「{sheet_name}」为空，无法读取表头。") from None
    cached_positions = _header_positions(cached_headers, required_headers, sheet_name)
    formula_positions = _header_positions(
        tuple(cell.value for cell in formula_headers), numeric_headers, sheet_name
    )
    cached_numeric_positions = {header: cached_positions[header] for header in numeric_headers}
    if cached_numeric_positions != formula_positions:
        raise WorkbookDataError(f"工作表「{sheet_name}」的公式和值视图行结构不一致。")

    missing = object()
    for cached_row, formula_row in zip_longest(cached_rows, formula_rows, fillvalue=missing):
        if cached_row is missing or formula_row is missing:
            raise WorkbookDataError(f"工作表「{sheet_name}」的公式和值视图行结构不一致。")
        active_date = cached_row[cached_positions[active_date_header]]
        if active_date is not None and active_date != "":
            for header, formula_index in formula_positions.items():
                formula_cell = formula_row[formula_index]
                cached_value = cached_row[cached_positions[header]]
                if formula_cell.data_type == "f" and cached_value is None:
                    raise WorkbookDataError(
                        f"工作表「{sheet_name}」字段「{header}」的公式没有缓存结果。"
                        "请用 Excel 或 WPS 重新计算后保存该工作簿，再重新导入。"
                    )
        yield {
            header: cached_row[index] if index < len(cached_row) else None
            for header, index in cached_positions.items()
        }


def _open_workbook_views(path: Path):
    cached_book = _open_workbook(path, data_only=True)
    try:
        formula_book = _open_workbook(path, data_only=False)
    except (WorkbookDataError, ParseError, ValueError):
        cached_book.close()
        raise
    return cached_book, formula_book


def _sheet_pair(cached_book, formula_book, path: Path, sheet_name: str):
    try:
        return cached_book[sheet_name], formula_book[sheet_name]
    except KeyError:
        raise WorkbookDataError(f"工作簿「{path}」缺少工作表「{sheet_name}」。") from None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def _read_operations(path: Path) -> list[OperationalRecord]:
    source = Path(path)
    cached_book, formula_book = _open_workbook_views(source)
    try:
        worksheet, formula_sheet = _sheet_pair(cached_book, formula_book, source, "台账明细")

        records: list[OperationalRecord] = []
        for row in _validated_rows(
            worksheet,
            formula_sheet,
            OPS_HEADERS,
            ("预估总应收", "预估毛利润"),
            "预计起飞时间",
        ):
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
        formula_book.close()
        cached_book.close()


def _read_funds(path: Path, allowed_years: Iterable[int]) -> list[FundRecord]:
    source = Path(path)
    allowed_years = set(allowed_years)
    cached_book, formula_book = _open_workbook_views(source)
    try:
        selected_sheets = [
            name
            for name in cached_book.sheetnames
            if FUND_SHEET_PATTERN.fullmatch(name) and int(name[-4:]) in allowed_years
        ]
        if not selected_sheets:
            years_text = "、".join(str(year) for year in sorted(allowed_years))
            raise WorkbookDataError(f"工作簿「{source}」未找到资金散板汇总工作表（请求年度：{years_text}）。")

        records: list[FundRecord] = []
        for sheet_name in selected_sheets:
            worksheet, formula_sheet = _sheet_pair(cached_book, formula_book, source, sheet_name)
            for row in _validated_rows(
                worksheet,
                formula_sheet,
                FUND_HEADERS,
                ("付款金额合计（90%）", "应收操作费"),
                "信容付款日期",
            ):
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
        return records
    finally:
        formula_book.close()
        cached_book.close()


def read_operations(path: Path) -> list[OperationalRecord]:
    source = Path(path)
    try:
        return _read_operations(source)
    except WorkbookDataError:
        raise
    except (BadZipFile, KeyError, ParseError, ValueError):
        raise WorkbookDataError(f"文件「{source}」不是有效的 XLSX 工作簿。") from None


def read_funds(path: Path, allowed_years: Iterable[int]) -> list[FundRecord]:
    source = Path(path)
    try:
        return _read_funds(source, allowed_years)
    except WorkbookDataError:
        raise
    except (BadZipFile, KeyError, ParseError, ValueError):
        raise WorkbookDataError(f"文件「{source}」不是有效的 XLSX 工作簿。") from None
