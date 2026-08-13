from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image, ImageFont, ImageStat

from ledger_reporter.exporters.png import _font, _format, export_pngs, render_table
from ledger_reporter.presentation.builders import build_tables


def test_exports_two_nonblank_high_resolution_pngs(report_bundle, tmp_path: Path) -> None:
    paths = export_pngs(report_bundle, tmp_path / "nested")

    assert [path.name for path in paths] == ["经营汇总.png", "自营项目周报.png"]
    for path in paths:
        assert path.is_file()
        with Image.open(path) as opened:
            assert opened.format == "PNG"
            image = opened.convert("RGB")
        assert image.width >= 1000
        assert image.height >= 400
        assert sum(ImageStat.Stat(image).var) > 0


def test_render_preserves_template_colors_across_merged_cells(report_bundle) -> None:
    summary, business = build_tables(report_bundle)
    summary_image = render_table(summary, scale=1)
    business_image = render_table(business, scale=1)

    summary_widths = [int(value * 8) for value in summary.column_widths]
    summary_heights = [int(value * 1.5) for value in summary.row_heights]
    quarter_row = next(
        cell.row
        for cell in summary.cells
        if isinstance(cell.value, str) and cell.value.startswith("Q")
    )
    column_c_inside = sum(summary_widths[:3]) - 5
    quarter_row_inside = sum(summary_heights[: quarter_row - 1]) + 5

    assert summary_image.getpixel((5, 5)) == (145, 170, 221)
    assert summary_image.getpixel((column_c_inside, 5)) == (145, 170, 221)
    assert summary_image.getpixel((5, quarter_row_inside)) == (239, 156, 165)
    assert business_image.getpixel((5, 5)) == (96, 112, 142)
    assert summary_image.getpixel((summary_image.width - 1, 5)) == (183, 192, 187)
    assert summary_image.getpixel((5, summary_image.height - 1)) == (183, 192, 187)


def test_formats_report_values_without_excel() -> None:
    assert _format(Decimal("-0.4231"), "0%") == "-42%"
    assert _format(Decimal("0.0102"), "0.00%") == "1.02%"
    assert _format(Decimal("1234.5"), "#,##0.00") == "1,234.50"
    assert _format(Decimal("0.125"), "#,##0.00") == "0.13"
    assert _format(Decimal("1234.5"), "#,##0") == "1,235"
    assert _format(None, "0.00%") == "-"


def test_pingfang_uses_distinct_faces_for_regular_and_bold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []
    fallback = ImageFont.load_default()

    def fake_truetype(name: str, _size: int, **kwargs):
        calls.append((name, kwargs.get("index", 0)))
        return fallback

    _font.cache_clear()
    monkeypatch.setattr(ImageFont, "truetype", fake_truetype)
    try:
        _font(20, False)
        _font(20, True)
    finally:
        _font.cache_clear()

    assert calls == [
        ("/System/Library/Fonts/PingFang.ttc", 0),
        ("/System/Library/Fonts/PingFang.ttc", 5),
    ]
