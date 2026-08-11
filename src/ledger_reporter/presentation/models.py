from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CellSpec:
    row: int
    column: int
    value: object
    style: str = "body"
    number_format: str | None = None


@dataclass(frozen=True, slots=True)
class MergeSpec:
    start_row: int
    start_column: int
    end_row: int
    end_column: int


@dataclass(frozen=True, slots=True)
class TableSpec:
    name: str
    cells: tuple[CellSpec, ...]
    merges: tuple[MergeSpec, ...]
    column_widths: tuple[float, ...]
    row_heights: tuple[float, ...]
