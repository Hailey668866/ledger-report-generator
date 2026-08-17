import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

XLSX_MAX_ROW = 1_048_576


@dataclass(frozen=True, slots=True)
class SourceSettings:
    funds_sheet: str = "资金散板汇总{年份}"
    funds_header_row: int = 1
    funds_channel: str = "渠道名称"
    funds_payment_date: str = "信容付款日期"
    funds_amount: str = "付款金额合计（90%）"
    funds_operation_fee: str = "应收操作费"
    operations_sheet: str = "台账明细"
    operations_header_row: int = 1
    operations_bill_no: str = "提单号"
    operations_project_type: str = "项目类型"
    operations_destination: str = "目的口岸"
    operations_departure: str = "预计起飞时间"
    operations_supplier: str = "B1供应商"
    operations_receivable: str = "预估总应收"
    operations_gross_profit: str = "预估毛利润"

    def validate(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name.endswith("_header_row"):
                if type(value) is not int or not 1 <= value <= XLSX_MAX_ROW:
                    raise ValueError(f"表头行必须是 1 至 {XLSX_MAX_ROW} 之间的正整数。")
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f"工作表或字段名称「{field.name}」必须是非空字符串。")

        groups = (
            (
                self.funds_channel,
                self.funds_payment_date,
                self.funds_amount,
                self.funds_operation_fee,
            ),
            (
                self.operations_bill_no,
                self.operations_project_type,
                self.operations_destination,
                self.operations_departure,
                self.operations_supplier,
                self.operations_receivable,
                self.operations_gross_profit,
            ),
        )
        if any(len(group) != len(set(group)) for group in groups):
            raise ValueError("同一工作表中的业务字段名称不可重复。")


DEFAULT_SOURCE_SETTINGS = SourceSettings()


def load_source_settings(path: Path) -> SourceSettings:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
        settings = SourceSettings(**data)
        settings.validate()
        return settings
    except FileNotFoundError:
        return DEFAULT_SOURCE_SETTINGS
    except (OSError, UnicodeError, TypeError, ValueError) as error:
        raise ValueError(f"字段设置文件无法读取：{error}") from None


def save_source_settings(path: Path, settings: SourceSettings) -> None:
    settings.validate()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(asdict(settings), temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
