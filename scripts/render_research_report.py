"""Render the reviewed Markdown report to a portable, paginated PDF.

Requires reportlab==4.4.9. Scientific results are produced separately by
scripts/diagnose_archive.py; rendering does not alter measurements.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def inline(text):
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="8">\1</font>', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2" color="#126875">\1</link>', text)
    return text


def render(source, output):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="BodyReport",
            fontName="Helvetica",
            fontSize=10,
            leading=14.3,
            spaceAfter=7,
            textColor=colors.HexColor("#24354a"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="TitleReport",
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=30,
            spaceAfter=18,
            textColor=colors.HexColor("#10283d"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="HeadingReport",
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=19,
            spaceBefore=12,
            spaceAfter=7,
            textColor=colors.HexColor("#126875"),
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallReport", fontName="Helvetica", fontSize=8, leading=11, spaceAfter=8
        )
    )
    styles.add(
        ParagraphStyle(
            name="CodeReport",
            fontName="Courier",
            fontSize=7.3,
            leading=10,
            spaceAfter=10,
            backColor=colors.HexColor("#eef3f5"),
        )
    )
    story = []
    lines = source.read_text().splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if line.startswith("```"):
            block = []
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            story.append(Preformatted("\n".join(block), styles["CodeReport"]))
        elif line.startswith("!["):
            match = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", line)
            if not match:
                raise ValueError("invalid figure")
            figure = Image(str(source.parent / match[2]))
            figure.drawHeight *= 6.45 * inch / figure.drawWidth
            figure.drawWidth = 6.45 * inch
            story.append(
                KeepTogether(
                    [figure, Spacer(1, 6), Paragraph(inline(match[1]), styles["SmallReport"])]
                )
            )
        elif line.startswith("|"):
            rows = [line]
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(lines[index].strip())
                index += 1
            cells = [
                [
                    Paragraph(inline(c.strip()), styles["SmallReport"])
                    for c in row.strip("|").split("|")
                ]
                for row in rows
                if not re.fullmatch(r"[|\s:\-]+", row)
            ]
            widths = [6.45 * inch / len(cells[0])] * len(cells[0])
            table = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3eff0")),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#126875")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f5f7f9")],
                        ),
                    ]
                )
            )
            story.append(table)
        elif line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), styles["TitleReport"]))
        elif line.startswith("## "):
            story.append(Paragraph(inline(line[3:]), styles["HeadingReport"]))
        elif line.startswith("- "):
            story.append(Paragraph(inline(line[2:]), styles["BodyReport"], bulletText="-"))
        else:
            paragraph = [line]
            while (
                index < len(lines)
                and lines[index].strip()
                and not lines[index].startswith(("#", "|", "- ", "```", "!["))
            ):
                paragraph.append(lines[index].strip())
                index += 1
            story.append(Paragraph(inline(" ".join(paragraph)), styles["BodyReport"]))

    def page(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#bfd0da"))
        canvas.line(0.8 * inch, 0.6 * inch, 7.25 * inch, 0.6 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#4b6072"))
        canvas.drawString(
            0.8 * inch, 0.4 * inch, "THEOXENIA / Research report 01 / Prepared for Zenodo"
        )
        canvas.drawRightString(7.25 * inch, 0.4 * inch, str(document.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output),
        pagesize=(8.27 * inch, 11.69 * inch),
        rightMargin=1.02 * inch,
        leftMargin=0.8 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.8 * inch,
        title="Empty tables, tested boundaries: a reproducible audit",
        author="Michael Petychakis",
        invariant=1,
    )
    doc.build(story, onFirstPage=page, onLaterPages=page)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("reports/first-results/report.md"))
    parser.add_argument("--output", type=Path, default=Path("reports/first-results/report.pdf"))
    args = parser.parse_args()
    render(args.source, args.output)
