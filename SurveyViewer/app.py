import streamlit as st
import pandas as pd
import altair as alt
import re

from utils import (
    make_bar_png_from_plot_df,
    generate_all_graphs_pdf_cached,
    generate_all_text_answers_pdf_cached,
)

def strip_html_br(text: str) -> str:
    text = str(text)
    text = (
        text.replace("<br>", " ")
            .replace("<br/>", " ")
            .replace("<br />", " ")
    )
    # optional: remove any other HTML tags
    text = re.sub(r"<.*?>", " ", text)
    return " ".join(text.split())  # collapse extra spaces

st.set_page_config(page_title="iNUX Survey Explorer", layout="centered")
st.title("📊 SurvEye - The iNUX Survey Results Viewer")

st.markdown("This module loads iNUX SoSci survey data and plot (ordinal and nominal) or show you text answers. " \
"You need three files; **Dataset**, **Variables Overview** and **Response Code Listing**. You should not *Include variable labels* "
"in your **Dataset** as a setting when you download data from SoSci.")

# --- File uploaders ---
# ---------- LOAD SURVEY CSV ----------
survey_file = st.file_uploader("Upload survey CSV (1 header row)", type=["csv"])

df = None          # survey data

if survey_file is not None:
    df = pd.read_csv(survey_file, sep=';', encoding="utf-16", engine="python")
    st.success("Survey data loaded!")
    # st.write("Survey data preview:")
    # st.dataframe(df.head())


# ---------- LOAD CODEBOOK ----------
codebook_file = st.file_uploader(
    "Upload response code CSV (columns: VAR, RESPONSE, MEANING)", type=["csv"]
)

df_codebook = None # response codes

if codebook_file is not None:
    df_codebook = pd.read_csv(codebook_file, sep=';', encoding="utf-16", engine="python")

    st.success("Codebook loaded!")
    # st.write("Codebook preview:")
    # st.dataframe(df_codebook.head())


# ---------- LOAD METADATA ----------
meta_file = st.file_uploader(
    "Upload metadata CSV (columns: VAR, QUESTION, TYPE)", type=["csv"]
)

df_meta = None     # question metadata

if meta_file is not None:
    df_meta = pd.read_csv(meta_file, sep=';', encoding="utf-16", engine="python")

    df_meta = df_meta.loc[df_meta["INPUT"] != "SYSTEM"][["VAR", "TYPE", "QUESTION"]]

    # Normalize TYPE
    if "TYPE" in df_meta.columns:
        df_meta["TYPE"] = df_meta["TYPE"].astype(str).str.upper().str.strip()

    st.success("Metadata loaded!")
    # st.write("Metadata preview:")
    # st.dataframe(df_meta.head())

# ---------- MAIN INTERACTION ----------
if df is not None and df_meta is not None:

    # Only keep VARs that exist in both survey and metadata
    vars_in_survey = set(df.columns)
    vars_in_meta = set(df_meta["VAR"])
    available_vars = sorted(vars_in_survey & vars_in_meta)

    if not available_vars:
        st.warning("No overlapping VAR codes between survey and metadata.")
    else:
        # Maps from metadata
        question_map = df_meta.set_index("VAR")["QUESTION"].to_dict()
        type_map = df_meta.set_index("VAR")["TYPE"].to_dict()

        # Build dropdown labels: "VAR (TYPE) QUESTION"
        var_to_label = {}

        for var in available_vars:
            q_text = str(question_map.get(var, var)).strip()
            q_type = str(type_map.get(var, "")).strip().upper()

            # Construct the label
            label = f"{var} ({q_type}): {q_text}"
            var_to_label[var] = label

        labels = list(var_to_label.values())
        label_to_var = {label: var for var, label in var_to_label.items()}

        st.markdown("### Select a question")
        selected_label = st.selectbox("Choose a question", labels)

        selected_var = label_to_var[selected_label]

        question_text = str(question_map.get(selected_var, selected_var)).strip()
        q_type = type_map.get(selected_var, "ORDINAL")  # default

        # st.write(f"**Selected VAR:** `{selected_var}`")
        # st.write(f"**Question type:** {q_type}")
        st.write(f"**Question text:** {question_text}")

        series = df[selected_var]

        # Number of non-missing responses
        n_responses = series.notna().sum()
        title_text = [question_text, f"n = {n_responses}"]

        # ---------- TEXT QUESTIONS ----------
        if q_type == "TEXT":
            st.markdown("### Text responses")

            text_answers = series.dropna().astype(str)
            st.write(f"Number of text responses: **{n_responses}**")

            # Frequency table
            freq = (
                text_answers
                .value_counts()
                .rename_axis("response")
                .reset_index(name="count")
            )

            st.markdown("#### Most frequent responses")
            st.dataframe(freq)

            st.markdown("#### All responses")
            st.dataframe(text_answers.to_frame(name="response"))
            
            # For plot
            show_graph = False

        # ---------- ORDINAL / NOMINAL (CODED) QUESTIONS ----------
        else:
            # For plot
            show_graph = True

            if df_codebook is not None and "VAR" in df_codebook.columns:
                cb_subset = df_codebook[df_codebook["VAR"] == selected_var]
                cb_subset["RESPONSE"] = cb_subset["RESPONSE"].astype("Int32")

                # st.markdown("#### Response codes for this question")
                # st.dataframe(cb_subset)

                # 1. Count observed responses
                counts = (
                    series.dropna()
                    .value_counts()
                    .rename_axis("RESPONSE")
                    .reset_index(name="count")
                )

                # Align dtype with codebook
                counts["RESPONSE"] = pd.to_numeric(
                    counts["RESPONSE"], errors="coerce"
                ).astype("Int32")

                # 2. All possible RESPONSE + MEANING from codebook for this VAR
                cb_small = cb_subset[["RESPONSE", "MEANING"]].drop_duplicates()

                # 3. Left join counts onto full list of response options
                plot_df = cb_small.merge(counts, on="RESPONSE", how="left")
                plot_df["count"] = plot_df["count"].fillna(0).astype(int)

                # ---- Optional: apply ordered scales for common Likert types ----
                order = ["Excellent", "Good", "Neutral", "Poor", "Very poor", "Not answered"]
                order_2 = [
                    "Strongly agree", "Agree", "Neutral",
                    "Disagree", "Strongly disagree",
                    "Not relevant", "Not answered",
                ]

                meanings_present = set(plot_df["MEANING"].dropna().unique())

                if meanings_present.issubset(set(order)):
                    plot_df["MEANING"] = pd.Categorical(
                        plot_df["MEANING"], categories=order, ordered=True
                    )
                elif meanings_present.issubset(set(order_2)):
                    plot_df["MEANING"] = pd.Categorical(
                        plot_df["MEANING"], categories=order_2, ordered=True
                    )

                # Cleaned label column
                plot_df["MEANING_CLEAN"] = plot_df["MEANING"].apply(strip_html_br)

                # ---------- PLOT ----------
                st.markdown("### Response distribution")

                chart = (
                    alt.Chart(plot_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("MEANING_CLEAN:N", title="Response", sort=None),
                        y=alt.Y("count:Q", title="Count"),
                        tooltip=["RESPONSE", "MEANING_CLEAN", "count"],
                    )
                    .properties(
                        title={
                            "text": title_text,
                            "anchor": "middle",
                        }
                    )
                )

                st.altair_chart(chart, use_container_width=True)

            else:
                st.warning("No codebook available – plotting raw values instead.")

                counts = (
                    series.dropna()
                    .value_counts()
                    .rename_axis("value")
                    .reset_index(name="count")
                )

                chart = (
                    alt.Chart(counts)
                    .mark_bar()
                    .encode(
                        x=alt.X("value:N", title="Response"),
                        y=alt.Y("count:Q", title="Count"),
                        tooltip=["value", "count"],
                    )
                    .properties(
                        title={
                            "text": title_text,
                            "anchor": "middle",
                        }
                    )
                )
                st.altair_chart(chart, use_container_width=True)

elif df is not None and df_meta is None:
    st.info("Upload the metadata CSV (VAR / QUESTION / TYPE) to enable question selection.")
elif df_meta is not None and df is None:
    st.info("Upload the survey CSV to enable analysis.")

if df is not None and df_codebook is not None and df_meta is not None:
    if "pdf_graphs" not in st.session_state:
        st.session_state["pdf_graphs"] = None
    if "pdf_text" not in st.session_state:
        st.session_state["pdf_text"] = None

    # Columns for download buttons at the end
    col1, col2, col3, col4 = st.columns(4)

    # --- Generate ALL downloads button ---
    with col1:
        if st.button("⚙️ Generate ALL downloads"):
            with st.spinner("Generating PDFs…"):
                st.session_state["pdf_graphs"] = generate_all_graphs_pdf_cached(
                    df, df_codebook, df_meta
                )
                st.session_state["pdf_text"] = generate_all_text_answers_pdf_cached(
                    df, df_meta
                )

    # --- Current graph PNG ---
    with col2:
        if show_graph:
            png_buf = make_bar_png_from_plot_df(plot_df, question_text, n_responses)
            png_bytes = png_buf.getvalue()

            st.download_button(
                "📥 Download current graph (PNG)",
                png_bytes,
                f"{selected_var}.png",
                "image/png",
            )
        else:
            st.info("Cannot export text answers as figure.")

    # --- Download ALL graphs (PDF) ---
    with col3:
        if st.session_state["pdf_graphs"] is not None:
            st.download_button(
                "📥 Download ALL graphs (PDF)",
                st.session_state["pdf_graphs"],
                "all_graphs.pdf",
                mime="application/pdf",
            )

    # --- Download ALL text answers (PDF) ---
    with col4:
        if st.session_state["pdf_text"] is not None:
            st.download_button(
                "📥 Download ALL text answers (PDF)",
                st.session_state["pdf_text"],
                "all_text_answers.pdf",
                mime="application/pdf",
            )
