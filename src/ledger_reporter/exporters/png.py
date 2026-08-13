from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ledger_reporter.domain.models import ReportBundle
from ledger_reporter.presentation.builders import build_tables
from ledger_reporter.presentation.models import TableSpec
from ledger_reporter.presentation.theme import STYLES


@lru_cache(maxsize=64)
def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        (
            ("/System/Library/Fonts/PingFang.ttc", 5),
            ("/System/Library/Fonts/STHeiti Medium.ttc", 0),
            ("C:/Windows/Fonts/msyhbd.ttc", 0),
            ("C:/Windows/Fonts/arialbd.ttf", 0),
            ("Arial Bold.ttf", 0),
        )
        if bold
        else (
            ("/System/Library/Fonts/PingFang.ttc", 0),
            ("/System/Library/Fonts/STHeiti Light.ttc", 0),
            ("C:/Windows/Fonts/msyh.ttc", 0),
            ("C:/Windows/Fonts/arial.ttf", 0),
            ("Arial.ttf", 0),
        )
    )
    for name, index in candidates:
        try:
            return ImageFont.truetype(name, size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def _format(value: object, number_format: str | None) -> str:
    if value is None:
        return "-"
    if number_format not in {"0%", "0.00%", "#,##0.00", "#,##0"}:
        return str(value)
    number = Decimal(str(value))
    if number_format in {"0%", "0.00%"}:
        precision = 0 if number_format == "0%" else 2
        quantum = Decimal(1) if precision == 0 else Decimal("0.01")
        percentage = (number * 100).quantize(quantum, rounding=ROUND_HALF_UP)
        return f"{percentage:.{precision}f}%"
    if number_format == "#,##0.00":
        return f"{number.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
    if number_format == "#,##0":
        return f"{number.quantize(Decimal(1), rounding=ROUND_HALF_UP):,.0f}"
    return str(value)


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    height: int,
    preferred_size: int,
    minimum_size: int,
    bold: bool,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for size in range(preferred_size, minimum_size - 1, -1):
        font = _font(size, bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= width and box[3] - box[1] <= height:
            return font
    return _font(minimum_size, bold)


def render_table(table: TableSpec, scale: int = 2) -> Image.Image:
    if scale < 1:
        raise ValueError("scale must be at least 1")

    widths = [max(1, int(value * 8 * scale)) for value in table.column_widths]
    heights = [max(1, int(value * 1.5 * scale)) for value in table.row_heights]
    image = Image.new("RGB", (sum(widths), sum(heights)), "#FFFFFF")
    draw = ImageDraw.Draw(image)
    x_positions = [0]
    y_positions = [0]
    for width in widths:
        x_positions.append(x_positions[-1] + width)
    for height in heights:
        y_positions.append(y_positions[-1] + height)

    merges = {(item.start_row, item.start_column): item for item in table.merges}
    covered = {
        (row, column)
        for item in table.merges
        for row in range(item.start_row, item.end_row + 1)
        for column in range(item.start_column, item.end_column + 1)
        if (row, column) != (item.start_row, item.start_column)
    }
    padding = 6 * scale
    for cell in table.cells:
        if (cell.row, cell.column) in covered:
            continue
        merge = merges.get((cell.row, cell.column))
        end_row = merge.end_row if merge else cell.row
        end_column = merge.end_column if merge else cell.column
        x0, x1 = x_positions[cell.column - 1], x_positions[end_column]
        y0, y1 = y_positions[cell.row - 1], y_positions[end_row]
        style = STYLES[cell.style]
        draw.rectangle(
            (x0, y0, min(x1, image.width - 1), min(y1, image.height - 1)),
            fill="#" + style["fill"],
            outline="#B7C0BB",
            width=max(1, scale),
        )

        text = _format(cell.value, cell.number_format)
        font = _fit_font(
            draw,
            text,
            max(1, x1 - x0 - 2 * padding),
            max(1, y1 - y0 - 4 * scale),
            10 * scale,
            6 * scale,
            bool(style["bold"]),
        )
        box = draw.textbbox((0, 0), text, font=font)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        if style["align"] == "center":
            text_x = x0 + (x1 - x0 - text_width) / 2
        elif style["align"] == "right":
            text_x = x1 - text_width - padding
        else:
            text_x = x0 + padding
        text_y = y0 + (y1 - y0 - text_height) / 2 - box[1]
        draw.text(
            (text_x, text_y),
            text,
            fill="#" + style.get("font", "000000"),
            font=font,
        )
    return image


def export_pngs(bundle: ReportBundle, output_dir: Path) -> list[Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for table in build_tables(bundle):
        path = output_dir / f"{table.name}.png"
        image = render_table(table)
        try:
            image.save(path, "PNG")
        finally:
            image.close()
        paths.append(path)
    return paths
