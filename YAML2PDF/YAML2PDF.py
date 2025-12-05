import io
from io import BytesIO
from pathlib import Path

import streamlit as st
import yaml

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


# ============================================================
# CORE FUNCTION: YAML → PDF (copied/adapted from your big app)
# ============================================================
def yaml_to_pdf_bytes(yaml_text: str, language_label: str, uploaded_figures=None) -> bytes:
    """
    Create a nicely formatted A4 PDF 'resource sheet' from the YAML text.
    Uses a structured layout (sections, tables, figure section).
    """
    data = yaml.safe_load(yaml_text) or {}

    buffer = BytesIO()

    # --- Document setup ---
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    project_style = ParagraphStyle(
        "ProjectHeader",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        textColor=colors.black,
        spaceAfter=4,
    )
    title_style = ParagraphStyle(
        "ResourceTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        spaceAfter=8,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=10,
        leading=12,
        textColor=colors.black,
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=4,
    )
    caption_style = ParagraphStyle(
        "FigureCaption",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        italic=True,
        alignment=1,  # center
        spaceBefore=2,
        spaceAfter=0,
    )

    story = []

    # ---------- COVER PAGE ----------
    cover_title_style = ParagraphStyle(
        "CoverTitle",
        parent=styles["Heading1"],
        fontSize=24,
        leading=28,
        alignment=1,        # centered
        spaceAfter=12,
    )
    cover_subtitle_style = ParagraphStyle(
        "CoverSubtitle",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        alignment=1,        # centered
        textColor=colors.black,
        spaceAfter=6,
    )

    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph("iNUX Groundwater", cover_title_style))
    story.append(Paragraph("An Erasmus+ Project", cover_subtitle_style))
    story.append(Spacer(1, 20 * mm))
    story.append(Paragraph("Resource description sheet", cover_subtitle_style))

    # Try to add logo; ignore if missing
    try:
        story.append(Image("FIGS/iNUX_wLogo.png", width=40 * mm, height=40 * mm))
    except Exception:
        pass

    story.append(PageBreak())

    # -------- HEADER / TITLE BLOCK --------
    raw_title = data.get("title") or "Untitled resource"
    title = str(raw_title)

    topic = str((data.get("topic") or "—") or "—")
    raw_item_id = (data.get("item_id") or "").strip()
    show_item_id = bool(raw_item_id) and "TO_BE_FILLED" not in raw_item_id.upper()

    story.append(
        Paragraph(
            "iNUX – Interactive Understanding of Groundwater Hydrology and Hydrogeology",
            project_style,
        )
    )
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(f"<b>Topic:</b> {topic}", label_style))
    story.append(Paragraph(f"<b>Language:</b> {language_label}", label_style))
    if show_item_id:
        story.append(Paragraph(f"<b>Item ID:</b> {raw_item_id}", label_style))
    story.append(Spacer(1, 8))

    # -------- 1. BASIC INFORMATION --------
    story.append(Paragraph("1. Basic information", section_style))

    basic_data = [
        ["Resource type", data.get("resource_type", "—")],
        ["URL", data.get("url", "—")],
        ["Date released", data.get("date_released", "TO_BE_FILLED_BY_COURSE_MANAGER")],
        ["Time required", data.get("time_required", "—")],
    ]
    basic_table = Table(basic_data, colWidths=[45 * mm, 115 * mm])
    basic_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    story.append(basic_table)
    story.append(Spacer(1, 6))

    # -------- 2. PEDAGOGICAL OVERVIEW --------
    story.append(Paragraph("2. Pedagogical overview", section_style))

    desc = (data.get("description_short") or "").strip()
    if desc:
        story.append(Paragraph("<b>Short description</b>", label_style))
        story.append(Paragraph(desc, styles["Normal"]))
        story.append(Spacer(1, 4))

    keywords = data.get("keywords", [])
    if isinstance(keywords, list) and keywords:
        kw_text = ", ".join(str(k) for k in keywords)
    elif isinstance(keywords, str) and keywords.strip():
        kw_text = keywords
    else:
        kw_text = "—"

    fit_for = data.get("fit_for", [])
    if isinstance(fit_for, list) and fit_for:
        fit_for_text = ", ".join(str(x) for x in fit_for)
    else:
        fit_for_text = "—"

    story.append(Paragraph(f"<b>Keywords:</b> {kw_text}", label_style))
    story.append(Paragraph(f"<b>Best suited for:</b> {fit_for_text}", label_style))
    story.append(Spacer(1, 6))

    # -------- 3. TECHNICAL DETAILS --------
    story.append(Paragraph("3. Technical details", section_style))

    tech_data = []

    multipage = data.get("multipage_app")
    num_pages_val = data.get("num_pages")
    if multipage:
        pages_str = str(num_pages_val) if num_pages_val not in (None, "", 0) else "unknown"
        tech_data.append(["Multipage app", f" approximately {pages_str} page(s)"])

    interactive = data.get("interactive_plots")
    num_ip_val = data.get("num_interactive_plots")
    if interactive:
        ip_str = str(num_ip_val) if num_ip_val not in (None, "", 0) else "unknown number of"
        tech_data.append(["Interactive plots", f" {ip_str} interactive plot(s)"])

    assessments = data.get("assessments_included")
    num_q_val = data.get("num_assessment_questions")
    if assessments:
        q_str = str(num_q_val) if num_q_val not in (None, "", 0) else "unknown number of"
        tech_data.append(["Assessments", f" {q_str} question(s)"])

    videos = data.get("videos_included")
    num_vid_val = data.get("num_videos")
    if videos:
        v_str = str(num_vid_val) if num_vid_val not in (None, "", 0) else "unknown number of"
        tech_data.append(["Videos", f"{v_str} video(s)"])

    if not tech_data:
        tech_data = [["No additional technical features reported", "—"]]

    tech_table = Table(tech_data, colWidths=[60 * mm, 100 * mm])
    tech_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    story.append(tech_table)
    story.append(Spacer(1, 6))

    # -------- 4. EDUCATIONAL FIT --------
    story.append(Paragraph("4. Educational fit", section_style))

    time_required = data.get("time_required", "—")
    prereq = data.get("prerequisites", "—")

    edu_data = [
        ["Time required", time_required],
        ["Prerequisites", prereq],
        ["Best suited for", fit_for_text],
    ]
    edu_table = Table(edu_data, colWidths=[60 * mm, 100 * mm])
    edu_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ]
        )
    )
    story.append(edu_table)
    story.append(Spacer(1, 6))

    # -------- 5. AUTHORS & REFERENCES --------
    story.append(Paragraph("5. Authors & references", section_style))

    authors_list = data.get("authors", [])
    if authors_list:
        story.append(Paragraph("<b>Authors</b>", label_style))
        for a in authors_list:
            name = a.get("name", "Unknown")
            aff = a.get("affiliation", "")
            line = name
            if aff:
                line += f" ({aff})"
            story.append(Paragraph(f"• {line}", styles["Normal"]))
        story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No authors provided.", styles["Normal"]))
        story.append(Spacer(1, 4))

    refs = data.get("references", [])
    story.append(Paragraph("<b>References</b>", label_style))
    if refs:
        for r in refs:
            story.append(Paragraph(f"– {r}", styles["Normal"]))
    else:
        story.append(Paragraph("No references provided.", styles["Normal"]))
    story.append(Spacer(1, 8))

    # -------- 6. FIGURES & ILLUSTRATIONS (OPTIONAL) --------
    figures_info = data.get("figures") or []
    uploaded_figures = uploaded_figures or []

    if uploaded_figures:
        story.append(Paragraph("6. Figures and illustrations", section_style))
        story.append(Spacer(1, 4))

        for idx, fig_file in enumerate(uploaded_figures, start=1):
            info = figures_info[idx - 1] if idx - 1 < len(figures_info) else {}

            ftype = (info.get("type") or "").strip()
            fcap = (info.get("caption") or "").strip()

            if not fcap:
                base_caption = f"Uploaded image {idx}"
            else:
                base_caption = fcap

            media_suffix = f" ({ftype})" if ftype else ""
            caption_text = f"Figure {idx}. {base_caption}{media_suffix}"

            try:
                img = Image(BytesIO(fig_file.getvalue()))
                img._restrictSize(160 * mm, 90 * mm)

                fig_table = Table(
                    [[img], [Paragraph(caption_text, caption_style)]],
                    colWidths=[160 * mm],
                )
                fig_table.setStyle(
                    TableStyle(
                        [
                            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                            ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )

                story.append(fig_table)
            except Exception:
                story.append(Paragraph(caption_text, caption_style))

            story.append(Spacer(1, 10))

    # ---------- HEADER & FOOTER DRAWING FUNCTION ----------
    def add_header_footer(canvas, doc_):
        page_num = canvas.getPageNumber()
        width, height = A4
        margin = 20 * mm

        # No header/footer on the cover page (page 1)
        if page_num == 1:
            return

        # ----- Header (even pages only) -----
        if page_num % 2 == 0:
            header_y = height - 15 * mm
            canvas.setFont("Helvetica", 9)
            header_text = "iNUX Groundwater - An Erasmus+ Project"
            canvas.drawCentredString(width / 2.0, header_y, header_text)
            canvas.setLineWidth(0.5)
            canvas.line(margin, header_y - 2 * mm, width - margin, header_y - 2 * mm)

        # ----- Footer (all pages from 2 onward) -----
        footer_y = 15 * mm
        canvas.setFont("Helvetica", 9)

        logical_page_num = page_num - 1
        page_label = str(logical_page_num)

        canvas.setLineWidth(0.5)
        canvas.line(margin, footer_y + 3 * mm, width - margin, footer_y + 3 * mm)
        canvas.drawCentredString(width / 2.0, footer_y, page_label)

    doc.build(
        story,
        onFirstPage=add_header_footer,
        onLaterPages=add_header_footer,
    )

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ============================================================
# STREAMLIT FRONTEND: STANDALONE YAML → PDF TOOL
# ============================================================
st.set_page_config(page_title="YAML → PDF Resource Sheet", page_icon="📄", layout="centered")

st.title("YAML ➜ PDF generator 📄")
st.write(
    """
Upload a YAML file describing an iNUX resource, optionally add figures,  
and this tool will generate the **resource description sheet** as a PDF.
"""
)

# 1. Upload YAML
uploaded_yaml = st.file_uploader(
    "Upload YAML file",
    type=["yaml", "yml", "txt"],
    accept_multiple_files=False,
)

# 2. Choose language label for the PDF header
language_label = st.selectbox(
    "Language shown in the PDF",
    ["English", "German", "French", "Italian", "Swedish", "Hindi", "Polish", "Dutch"],
    index=0,
)

# 3. Upload figures (optional)
uploaded_figures = st.file_uploader(
    "Upload figure images (optional, multiple allowed)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

if uploaded_yaml:
    st.markdown("### YAML preview")
    raw_yaml_bytes = uploaded_yaml.read()
    try:
        yaml_text = raw_yaml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        yaml_text = raw_yaml_bytes.decode("latin-1")

    preview_lines = yaml_text.splitlines()
    head_preview = yaml_text
    st.code(head_preview, language="yaml")

    if st.button("Generate PDF"):
        try:
            pdf_bytes = yaml_to_pdf_bytes(yaml_text, language_label, uploaded_figures)
            pdf_name = Path(uploaded_yaml.name).stem + ".pdf"

            st.download_button(
                label=f"⬇️ Download PDF ({pdf_name})",
                data=pdf_bytes,
                file_name=pdf_name,
                mime="application/pdf",
            )
            st.success("PDF generated successfully.")
        except Exception as e:
            st.error(f"Error while generating PDF: {e}")
else:
    st.info("Please upload a YAML file to start.")
