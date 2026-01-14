"""Generate a 3-page sample PDF with Chinese text, tables, and graphics."""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def ensure_font() -> str:
    font_override = os.getenv("SAMPLE_FONT_PATH")
    if font_override:
        font_path = Path(font_override)
        if not font_path.is_file():
            raise FileNotFoundError(f"SAMPLE_FONT_PATH not found: {font_path}")
        font_name = "SampleFont"
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        return font_name
    return "Helvetica"


def draw_table(cnv: canvas.Canvas, x: float, y: float, rows: int, cols: int) -> None:
    cell_w = 120
    cell_h = 40
    for row in range(rows + 1):
        cnv.line(x, y - row * cell_h, x + cols * cell_w, y - row * cell_h)
    for col in range(cols + 1):
        cnv.line(x + col * cell_w, y, x + col * cell_w, y - rows * cell_h)
    for row in range(rows):
        for col in range(cols):
            text = f"R{row + 1}C{col + 1}"
            cnv.drawString(x + col * cell_w + 10, y - row * cell_h - 25, text)


def main() -> None:
    output_path = Path(__file__).parent / "sample.pdf"
    font_name = ensure_font()

    width, height = landscape((1280, 720))
    cnv = canvas.Canvas(str(output_path), pagesize=(width, height))

    cnv.setFillColor(colors.darkblue)
    cnv.setFont(font_name, 36)
    cnv.drawString(80, height - 120, "NotebookLM 幻灯片示例")
    cnv.setFillColor(colors.black)
    cnv.setFont(font_name, 20)
    cnv.drawString(80, height - 180, "这是一段中文文本，用于测试渲染与清晰度。")
    cnv.setStrokeColor(colors.darkblue)
    cnv.rect(80, height - 420, 520, 180, stroke=1, fill=0)
    cnv.setFont(font_name, 16)
    cnv.drawString(100, height - 260, "重点：保持版式与文字不变")
    cnv.showPage()

    cnv.setFont(font_name, 28)
    cnv.drawString(80, height - 100, "表格页 / Table Page")
    cnv.setFont(font_name, 14)
    cnv.drawString(80, height - 140, "包含 4x3 表格示例")
    cnv.setStrokeColor(colors.gray)
    draw_table(cnv, 80, height - 200, rows=4, cols=3)
    cnv.showPage()

    cnv.setFont(font_name, 28)
    cnv.drawString(80, height - 100, "图形页 / Charts")
    cnv.setFillColor(colors.green)
    cnv.circle(200, height - 260, 60, stroke=1, fill=1)
    cnv.setFillColor(colors.red)
    cnv.rect(320, height - 320, 160, 120, stroke=1, fill=1)
    cnv.setStrokeColor(colors.black)
    cnv.line(80, height - 420, 600, height - 420)
    cnv.setFillColor(colors.black)
    cnv.setFont(font_name, 16)
    cnv.drawString(80, height - 460, "简单图形用于测试渲染和排版")
    cnv.save()

    if font_name == "Helvetica":
        print(
            "Sample PDF generated without a Chinese font. "
            "Set SAMPLE_FONT_PATH to a .ttf/.otf font for better results."
        )

    print(f"Sample PDF generated at {output_path}")


if __name__ == "__main__":
    main()
