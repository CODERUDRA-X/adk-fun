"""
Generates a styled PDF evaluation report from the structured JSON result.

Uses ReportLab instead of WeasyPrint — ReportLab is pure Python with no
native DLL/library dependency (no Pango/GObject/GTK needed), so it works
identically on Windows, Linux, and Mac without any system-level install.

Public interface is unchanged: generate_pdf_report(subject, question,
evaluation) -> path. main.py does not need any changes.
"""

import os
import uuid
import tempfile
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_CENTER

BLUE = colors.HexColor("#2b6cb0")
LIGHT_BLUE_BG = colors.HexColor("#ebf8ff")
GREY = colors.HexColor("#555555")


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TitleBlue", fontSize=22, textColor=BLUE, alignment=TA_CENTER,
        fontName="Helvetica-Bold", spaceAfter=2,
    ))
    styles.add(ParagraphStyle(
        name="Subtitle", fontSize=10, textColor=GREY, alignment=TA_CENTER,
        spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="Meta", fontSize=10, textColor=colors.HexColor("#333333"),
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="ScoreLabel", fontSize=9, textColor=GREY, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="ScoreValue", fontSize=30, textColor=BLUE, alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle", fontSize=12, textColor=BLUE, fontName="Helvetica-Bold",
        spaceBefore=14, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Body", fontSize=10, textColor=colors.HexColor("#1a1a1a"), leading=14,
    ))
    styles.add(ParagraphStyle(
        name="Footer", fontSize=8, textColor=colors.HexColor("#999999"),
        alignment=TA_CENTER, spaceBefore=20,
    ))
    return styles


def _bullet_list(items, styles):
    if not items:
        items = ["None noted."]
    return ListFlowable(
        [ListItem(Paragraph(str(i), styles["Body"]), leftIndent=4) for i in items],
        bulletType="bullet", start="circle", leftIndent=14,
    )


def generate_pdf_report(subject: str, question: str, evaluation: dict) -> str:
    styles = _build_styles()

    out_dir = tempfile.gettempdir()
    out_path = os.path.join(out_dir, f"notegrade_{uuid.uuid4().hex}.pdf")

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )

    story = []

    story.append(Paragraph("NOTEGRADE AI", styles["TitleBlue"]))
    story.append(Paragraph("AI-Assisted Evaluation Report", styles["Subtitle"]))

    story.append(Paragraph(f"<b>Subject:</b> {subject or 'N/A'}", styles["Meta"]))
    story.append(Paragraph(f"<b>Question:</b> {question or 'N/A'}", styles["Meta"]))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%d %b %Y, %I:%M %p')}", styles["Meta"]))
    story.append(Spacer(1, 10))

    marks_obtained = evaluation.get("marks_obtained", 0)
    maximum_marks = evaluation.get("maximum_marks", 0)
    score_table = Table(
        [[Paragraph("SCORE", styles["ScoreLabel"])],
         [Paragraph(f"{marks_obtained} / {maximum_marks}", styles["ScoreValue"])]],
        colWidths=[17 * cm],
    )
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BLUE_BG),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#90cdf4")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("CRITERIA BREAKDOWN", styles["SectionTitle"]))
    rows = [["Criterion", "Score", "Feedback"]]
    for c in evaluation.get("criteria", []):
        rows.append([
            Paragraph(str(c.get("name", "")), styles["Body"]),
            f"{c.get('score', '')} / {c.get('max_score', '')}",
            Paragraph(str(c.get("feedback", "")), styles["Body"]),
        ])
    if len(rows) == 1:
        rows.append(["No criteria breakdown.", "", ""])

    criteria_table = Table(rows, colWidths=[4 * cm, 2.5 * cm, 10.5 * cm], repeatRows=1)
    criteria_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f7fafc")),
        ("TEXTCOLOR", (0, 0), (-1, 0), BLUE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(criteria_table)

    story.append(Paragraph("STRENGTHS", styles["SectionTitle"]))
    story.append(_bullet_list(evaluation.get("strengths", []), styles))

    story.append(Paragraph("WEAKNESSES", styles["SectionTitle"]))
    story.append(_bullet_list(evaluation.get("weaknesses", []), styles))

    story.append(Paragraph("OVERALL FEEDBACK", styles["SectionTitle"]))
    story.append(Paragraph(evaluation.get("overall_feedback", "") or "N/A", styles["Body"]))

    story.append(Paragraph("SUGGESTIONS", styles["SectionTitle"]))
    story.append(_bullet_list(evaluation.get("suggestions", []), styles))

    story.append(Paragraph(
        "Generated by NoteGrade AI \u2014 AI-assisted evaluation. Please review before "
        "finalizing marks; AI grading may misread handwriting or misjudge partial credit.",
        styles["Footer"],
    ))

    doc.build(story)
    return out_path