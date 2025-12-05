import pandas as pd
from io import BytesIO
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import streamlit as st
import textwrap

# ----------------------
#  PLOT HELPERS
# ----------------------

def wrap_text_to_width(text, canvas_obj, max_width, font_name="Helvetica", font_size=10):
    """
    Split `text` into a list of lines that fit within `max_width` (in points)
    using ReportLab's stringWidth for accurate measurement.
    """
    words = str(text).split()
    if not words:
        return [""]

    lines = []
    current_line = words[0]

    for word in words[1:]:
        test_line = current_line + " " + word
        w = canvas_obj.stringWidth(test_line, font_name, font_size)
        if w <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word

    lines.append(current_line)
    return lines

def make_bar_png_from_plot_df(plot_df, question_text, n_responses,
                              title_char_width=60, label_char_width=12):
    """
    plot_df: must contain 'MEANING' and 'count'
    question_text: full question string
    n_responses: integer
    title_char_width: approx chars per line before wrapping title
    label_char_width: approx chars per line for x labels
    """
    # --- Wrap question text into multiple lines ---
    wrapped_question_lines = textwrap.wrap(str(question_text), width=title_char_width)
    wrapped_question = "\n".join(wrapped_question_lines)
    title_str = f"{wrapped_question}\n(n = {n_responses})"

    # --- Prepare x and y ---
    x_raw = plot_df["MEANING"].astype(str).tolist()

    # Clean HTML breaks and extra whitespace
    x_clean = [lbl.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ").strip()
            for lbl in x_raw]

    y = plot_df["count"].tolist()

    # Wrap x labels as well, so long categories break into 2–3 lines
    x_wrapped = ["\n".join(textwrap.wrap(lbl, width=label_char_width)) for lbl in x_clean]

    # Taller figure to give more room for labels
    fig, ax = plt.subplots(figsize=(9, 6))

    ax.bar(range(len(x_wrapped)), y)
    ax.set_xticks(range(len(x_wrapped)))
    ax.set_xticklabels(x_wrapped, rotation=45, ha="right")
    ax.set_ylabel("Count")

    ax.set_title(title_str, pad=20, fontsize=10)

    # Leave extra room at bottom for x labels, and at top for title
    fig.subplots_adjust(left=0.15, right=0.98, top=0.80, bottom=0.30)

    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf

# ----------------------
#  PDF GENERATORS
# ----------------------

def generate_all_graphs_pdf(df, df_codebook, df_meta):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 40

    question_map = df_meta.set_index("VAR")["QUESTION"].to_dict()
    type_map = df_meta.set_index("VAR")["TYPE"].to_dict()

    vars_in_survey = set(df.columns)
    vars_in_meta = set(df_meta["VAR"])
    available_vars = sorted(vars_in_survey & vars_in_meta)

    for var in available_vars:
        q_type = str(type_map.get(var, "")).upper()
        if q_type not in ("ORDINAL", "NOMINAL"):
            continue

        series = df[var]
        n_responses = series.notna().sum()
        question_text = str(question_map.get(var, var))

        cb_subset = df_codebook[df_codebook["VAR"] == var]
        if cb_subset.empty:
            continue

        counts = (
            series.dropna()
            .value_counts()
            .rename_axis("RESPONSE")
            .reset_index(name="count")
        )
        counts["RESPONSE"] = pd.to_numeric(counts["RESPONSE"], errors="coerce").astype("Int32")

        cb_small = cb_subset[["RESPONSE", "MEANING"]].drop_duplicates()
        cb_small["RESPONSE"] = cb_small["RESPONSE"].astype("Int32")

        plot_df = cb_small.merge(counts, on="RESPONSE", how="left")
        plot_df["count"] = plot_df["count"].fillna(0).astype(int)

        # (Optional ordering of MEANING goes here)

        # --- Use wrapped-title helper ---
        img_buf = make_bar_png_from_plot_df(plot_df, question_text, n_responses)
        img = ImageReader(img_buf)

        img_w, img_h = img.getSize()
        scale = min((width - 2 * margin) / img_w, (height - 2 * margin) / img_h)
        new_w = img_w * scale
        new_h = img_h * scale

        c.drawImage(img, margin, height - margin - new_h, width=new_w, height=new_h)
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()

def generate_all_text_answers_pdf(df, df_meta):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 40
    line_height = 14

    question_map = df_meta.set_index("VAR")["QUESTION"].to_dict()
    type_map = df_meta.set_index("VAR")["TYPE"].to_dict()

    vars_in_survey = set(df.columns)
    vars_in_meta = set(df_meta["VAR"])
    available_vars = sorted(vars_in_survey & vars_in_meta)

    max_text_width = width - 2 * margin  # usable width in points

    for var in available_vars:
        q_type = str(type_map.get(var, "")).upper()
        if q_type != "TEXT":
            continue

        series = df[var].dropna().astype(str)
        if series.empty:
            continue

        question_text = str(question_map.get(var, var))
        n_responses = len(series)

        # --- Start a new page for this question ---
        c.setFont("Helvetica-Bold", 11)
        y = height - margin

        header = f"{var} - {question_text} (n = {n_responses})"

        header_lines = wrap_text_to_width(
            header,
            canvas_obj=c,
            max_width=max_text_width,
            font_name="Helvetica-Bold",
            font_size=11,
        )

        for hline in header_lines:
            c.drawString(margin, y, hline)
            y -= line_height

        y -= line_height  # extra space before answers

        c.setFont("Helvetica", 10)

        # --- Answers ---
        for ans in series:
            answer_lines = wrap_text_to_width(
                f"- {ans}",
                canvas_obj=c,
                max_width=max_text_width,
                font_name="Helvetica",
                font_size=10,
            )

            for line in answer_lines:
                if y < margin:
                    c.showPage()
                    c.setFont("Helvetica", 10)
                    y = height - margin

                c.drawString(margin, y, line)
                y -= line_height

        c.showPage()  # finish this question's page(s)

    c.save()
    buf.seek(0)
    return buf.getvalue()

@st.cache_data
def generate_all_graphs_pdf_cached(df, df_codebook, df_meta):
    return generate_all_graphs_pdf(df, df_codebook, df_meta)

@st.cache_data
def generate_all_text_answers_pdf_cached(df, df_meta):
    return generate_all_text_answers_pdf(df, df_meta)