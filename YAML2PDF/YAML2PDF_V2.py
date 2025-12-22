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
# CORE FUNCTION: YAML → PDF
# ============================================================
def yaml_to_pdf_bytes(yaml_text: str, language_label: str, uploaded_figures=None) -> bytes:
    """
    Create a nicely formatted A4 PDF 'resource sheet' from the YAML text.
    Uses a structured layout (sections, tables, figure section).
    """
    # ---- YAML parsing (: if you want to validate keys, do it here) ----
    data = yaml.safe_load(yaml_text) or {}

    # ---- Toggle flags (: enable/disable optional fields) ----
    SHOW_ITEM_ID = False  # set True only if you  want to display item_id again

    # ---- Helpers (: add more formatting rules here if needed) ----
    def safe_str(val):
        # Converts YAML values to strings safely (None -> "")
        if val is None:
            return ""
        return str(val)

    def as_list(val):
        # Normalizes a field to a list so code can treat str/list uniformly
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]

    buffer = BytesIO()

    # ============================================================
    # DOCUMENT SETUP (PAGE SIZE + MARGINS)
    # ============================================================
    #  HERE:
    # - Adjust left/right/top/bottom margin values
    # - Change pagesize (e.g., letter) if required
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    table_text_style = ParagraphStyle(
        "TableText",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )


    def cell(val):
        return Paragraph(safe_str(val), table_text_style)

    # ============================================================
    # TEXT STYLES (MAIN PLACE TO  TYPOGRAPHY)
    # ============================================================
    #  HERE:
    # - fontSize / leading
    # - spacing (spaceBefore/spaceAfter)
    # - alignment (0=left, 1=center, 2=right, 4=justify)
    #
    # NOTE: project_style is currently not used  (safe to keep).
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
    

    # ✅ Dynamic section numbering (only increments for rendered sections)
    section_no = 0

    def add_section(title_text: str) -> int:
        """
        Adds a numbered section heading to the story and returns the number used.
        Numbering is dynamic: only increments when the section is actually rendered.
        """
        nonlocal section_no
        section_no += 1
        story.append(Paragraph(f"{section_no}. {title_text}", section_style))
        return section_no


    # ============================================================
    # TITLE BLOCK (TOP OF FIRST CONTENT PAGE)
    # ============================================================
    #  HERE:
    # - Order of title/topic/language
    # - What metadata to show at top
    title = safe_str(data.get("title")) or "Untitled resource"

    topic = safe_str(data.get("topic")) or "—"
    raw_item_id = safe_str(data.get("item_id")).strip()

    story.append(Paragraph(title, title_style))
    story.append(Paragraph(f"<b>Topic:</b> {topic}", label_style))
    story.append(Paragraph(f"<b>Language:</b> {language_label}", label_style))

    # Optional: show/hide item_id (currently OFF by default)
    if SHOW_ITEM_ID and raw_item_id and "TO_BE_FILLED" not in raw_item_id.upper():
        story.append(Paragraph(f"<b>Item ID:</b> {raw_item_id}", label_style))

    story.append(Spacer(1, 8))  # : vertical spacing after title block

    # ============================================================
    # BASIC INFORMATION — render only if something exists
    # ============================================================

    basic_data = []

    resource_type = safe_str(data.get("resource_type")).strip()
    if resource_type:
        basic_data.append(["Resource type", cell(resource_type)])

    url = safe_str(data.get("url")).strip()
    if url:
        basic_data.append(["URL", cell(url)])

    date_released = safe_str(data.get("date_released")).strip()
    if date_released and "TO_BE_FILLED" not in date_released.upper():
        basic_data.append(["Date released", cell(date_released)])

    time_required = safe_str(data.get("time_required")).strip()
    if time_required:
        basic_data.append(["Time required", cell(time_required)])

    if basic_data:
        add_section("Basic information")
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


    # ============================================================
    # 2. PEDAGOGICAL OVERVIEW
    # ============================================================
    add_section("Pedagogical overview")

    desc = safe_str(data.get("description_short")).strip()
    if desc:
        story.append(Paragraph("<b>Short description</b>", label_style))

        #  HERE:
        # - This preserves line breaks from YAML by converting "\n" -> "<br/>"
        # - Also escapes basic HTML-sensitive characters so the PDF doesn’t break
        desc_html = desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        desc_html = desc_html.replace("\n", "<br/>")

        story.append(Paragraph(desc_html, styles["Normal"]))
        story.append(Spacer(1, 4))

    # Keywords (handles str or list)
    keywords = as_list(data.get("keywords"))
    if isinstance(keywords, list) and keywords:
        kw_text = ", ".join(str(k) for k in keywords)
    elif isinstance(keywords, str) and keywords.strip():
        kw_text = keywords
    else:
        kw_text = "—"

    # Fit-for (handles str or list)
    fit_for = as_list(data.get("fit_for"))
    if isinstance(fit_for, list) and fit_for:
        fit_for_text = ", ".join(str(x) for x in fit_for)
    else:
        fit_for_text = "—"

    story.append(Paragraph(f"<b>Keywords:</b> {kw_text}", label_style))
    story.append(Paragraph(f"<b>Best suited for:</b> {fit_for_text}", label_style))
    story.append(Spacer(1, 6))

    # ============================================================
    # 3. TECHNICAL DETAILS (TABLE) — render only if something exists
    # ============================================================

    tech_data = []

    multipage = data.get("multipage_app")
    num_pages_val = data.get("num_pages")
    if multipage:
        pages_str = str(num_pages_val) if num_pages_val not in (None, "", 0) else "unknown"
        tech_data.append(["Multipage app", cell(f"approximately {pages_str} page(s)")])

    interactive = data.get("interactive_plots")
    num_ip_val = data.get("num_interactive_plots")
    if interactive:
        ip_str = str(num_ip_val) if num_ip_val not in (None, "", 0) else "unknown number of"
        tech_data.append(["Interactive plots", cell(f"{ip_str} interactive plot(s)")])

    assessments = data.get("assessments_included")
    num_q_val = data.get("num_assessment_questions")
    if assessments:
        q_str = str(num_q_val) if num_q_val not in (None, "", 0) else "unknown number of"
        tech_data.append(["Assessments", cell(f"{q_str} question(s)")])

    videos = data.get("videos_included")
    num_vid_val = data.get("num_videos")
    if videos:
        v_str = str(num_vid_val) if num_vid_val not in (None, "", 0) else "unknown number of"
        tech_data.append(["Videos", cell(f"{v_str} video(s)")])

    # ✅ Only render the section if we have at least one row
    if tech_data:
        add_section("Technical details")

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



    # ============================================================
    # 4. EDUCATIONAL FIT (TABLE) — render only if something exists
    # ============================================================

    edu_data = []

    time_required = safe_str(data.get("time_required")).strip()
    if time_required:
        edu_data.append(["Time required", cell(time_required)])

    prereq = safe_str(data.get("prerequisites")).strip()
    if prereq:
        edu_data.append(["Prerequisites", cell(prereq)])

    # fit_for_text is computed in Section 2.
    # Only include it if it’s not empty and not the placeholder "—".
    if fit_for_text and fit_for_text != "—":
        edu_data.append(["Best suited for", cell(fit_for_text)])

    # ✅ Only render the section if we have at least one row
    if edu_data:
        add_section("Educational fit")

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


    # ============================================================
    # AUTHORS & REFERENCES — render only if something exists
    # ============================================================

    authors_list = [a for a in (data.get("authors") or []) if isinstance(a, dict)]
    refs = as_list(data.get("references"))

    has_authors = bool(authors_list)
    has_refs = bool([r for r in refs if safe_str(r).strip()])

    if has_authors or has_refs:
        add_section("Authors & references")

        if has_authors:
            story.append(Paragraph("<b>Authors</b>", label_style))
            for a in authors_list:
                name = safe_str(a.get("name")).strip() or "Unknown"
                aff = safe_str(a.get("affiliation")).strip()
                line = name + (f" ({aff})" if aff else "")
                story.append(Paragraph(f"• {line}", styles["Normal"]))
            story.append(Spacer(1, 4))

        if has_refs:
            story.append(Paragraph("<b>References</b>", label_style))
            for r in refs:
                r_txt = safe_str(r).strip()
                if r_txt:
                    story.append(Paragraph(f"– {r_txt}", styles["Normal"]))
            story.append(Spacer(1, 8))

    # ============================================================
    # 6. FIGURES & ILLUSTRATIONS
    # ============================================================
    figures_info = data.get("figures")
    if not isinstance(figures_info, list):
        figures_info = []

    uploaded_figures = uploaded_figures or []

    if uploaded_figures:
        add_section("Figures and illustrations")
        story.append(Spacer(1, 4))

        for idx, fig_file in enumerate(uploaded_figures, start=1):
            # Optional figure metadata from YAML (caption/type)
            info = figures_info[idx - 1] if idx - 1 < len(figures_info) else {}

            ftype = safe_str(info.get("type")).strip()
            fcap = safe_str(info.get("caption")).strip()

            base_caption = fcap if fcap else f"Uploaded image {idx}"
            media_suffix = f" ({ftype})" if ftype else ""
            caption_text = f"Figure {idx}. {base_caption}{media_suffix}"

            try:
                img = Image(BytesIO(fig_file.getvalue()))

                #  HERE:
                # - Adjust max figure size (width, height)
                img._restrictSize(160 * mm, 90 * mm)

                #  HERE:
                # - figure layout (image + caption) is controlled by this mini-table
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
                # If image fails, still show caption
                story.append(Paragraph(caption_text, caption_style))

            story.append(Spacer(1, 10))

    # ============================================================
    # HEADER / FOOTER DRAWING (CANVAS-LEVEL)
    # ============================================================
    #  HERE:
    # - Header/footer band size is controlled by "15 * mm"
    # - Logo placement: x/y values
    # - Footer banner image size + placement
    # - Footer text font size and justification
    def add_header_footer(canvas, doc_):
        page_num = canvas.getPageNumber()
        width, height = A4
        margin = 20 * mm

        # =========================
        # HEADER (15mm band)
        # =========================
        header_y = height - 15 * mm  # : moves header band up/down
        canvas.setFont("Helvetica", 9)

        # Logo ( x/y/height)
        try:
            canvas.drawImage(
                "FIGS/iNUX_wLogo.png",
                margin - 8 * mm,     # x (move left/right)
                header_y - 4 * mm,   # y (move up/down)
                height=12 * mm,      # logo height
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

        # Header text ( x/y or replace with drawCentredString if desired)
        canvas.drawString(margin, header_y, "iNUX Groundwater – An Erasmus+ Project")

        # Header separator line ( y position)
        canvas.setLineWidth(0.5)
        canvas.line(margin, header_y - 2 * mm, width - margin, header_y - 2 * mm)

        # =========================
        # FOOTER (15mm band)
        # =========================
        band_h = 15 * mm  # : footer band height
        canvas.setLineWidth(0.5)
        canvas.line(margin, band_h, width - margin, band_h)  # top border of footer band

        # Footer image (EU banner) placement + size
        img_w, img_h = 28 * mm, 11 * mm
        img_x, img_y = margin, 2 * mm  # : move image inside footer band

        try:
            canvas.drawImage(
                "FIGS/EN_Co-fundedbytheEU_RGB_Monochrome.png",
                img_x,
                img_y,
                width=img_w,
                height=img_h,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

        # Page number bottom-right ( y position "3 * mm")
        page_zone_w = 18 * mm  # reserved space so footer text does not collide with page number
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(width - margin, 3 * mm, str(page_num))

        # Footer justified text (uses remaining width between image and page number)
        from reportlab.platypus import Paragraph, Table, TableStyle
        from reportlab.lib.styles import ParagraphStyle

        footer_style = ParagraphStyle(
            "FooterJustified",
            fontName="Helvetica",
            fontSize=6.8,   # : footer text size
            leading=7.6,    # : footer line spacing
            alignment=4,    # JUSTIFY
        )

        eu_text = (
            "This project is co-funded by the European Union. However, the views and opinions expressed "
            "are solely those of the author(s) and do not necessarily reflect those of the European Union "
            "or the National Agency DAAD. Neither the European Union nor the granting authority can be held "
            "responsible for them."
        )

        text_x = img_x + img_w + 5 * mm  # : gap between image and text
        text_w = (width - margin - page_zone_w) - text_x  # available width for footer text

        # The Table+Paragraph trick is used so justify works reliably in the footer band
        t = Table([[Paragraph(eu_text, footer_style)]], colWidths=[text_w], rowHeights=[band_h])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        t.wrapOn(canvas, text_w, band_h)
        t.drawOn(canvas, text_x, 0)  # : move text up/down inside band

    # ============================================================
    # BUILD PDF
    # ============================================================
    doc.build(
        story,
        onFirstPage=add_header_footer,   # header/footer also on page 1
        onLaterPages=add_header_footer,
    )

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# ============================================================
# STREAMLIT FRONTEND: STANDALONE YAML → PDF TOOL
# ============================================================

#  HERE:
# - Page title/icon/layout in Streamlit (not PDF)
st.set_page_config(page_title="YAML → PDF Resource Sheet", page_icon="📄", layout="centered")

st.title("YAML ➜ PDF generator 📄")
st.write(
    """
Upload a YAML file describing an iNUX resource, optionally add figures,  
and this tool will generate the **resource description sheet** as a PDF.
"""
)

# Upload YAML
uploaded_yaml = st.file_uploader(
    "Upload YAML file",
    type=["yaml", "yml", "txt"],
    accept_multiple_files=False,
)

# Choose language label for the PDF header
language_label = st.selectbox(
    "Language shown in the PDF",
    ["English", "German", "French", "Italian", "Swedish", "Hindi", "Polish", "Dutch"],
    index=0,
)

# Upload figures (optional)
uploaded_figures = st.file_uploader(
    "Upload figure images (optional, multiple allowed)",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
)

if uploaded_yaml:
    st.markdown("### YAML preview")
    raw_yaml_bytes = uploaded_yaml.read()

    #  HERE:
    # - Change decoding strategy if your YAML files come in other encodings
    try:
        yaml_text = raw_yaml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        yaml_text = raw_yaml_bytes.decode("latin-1")

    st.code(yaml_text, language="yaml")

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
