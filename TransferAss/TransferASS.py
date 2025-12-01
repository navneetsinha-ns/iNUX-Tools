import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET
import uuid
from typing import Dict, Any, List
from xml.dom.minidom import Document
import streamlit as st
import subprocess
from io import BytesIO
import tempfile
import os

# ============================================================
# MD/WORD PART
# ============================================================

def questions_to_markdown(questions: list[dict],
                          strip_prefixes_for_docx: bool = True) -> str:
    """
    Student version:
    - Question
    - Options (A/B/C/...)
    """
    md = []

    for idx, q in enumerate(questions, start=1):
        # Ensure q is a dict and has a question
        if not isinstance(q, dict):
            continue

        question_text = str(q.get("question", "")).strip()
        if not question_text:
            # skip items without a question field
            continue

        options = q.get("options", {})
        if not isinstance(options, dict) or not options:
            # no options -> skip or leave a placeholder if you prefer
            continue

        # Question title
        md.append(f"**{idx}. {question_text}**")
        md.append("")  # blank line before options

        # Options (A, B, C…)
        for j, (opt_text, _) in enumerate(options.items()):
            letter = chr(ord("A") + j)

            display_text = clean_option_text(
                str(opt_text),
                strip_prefixes=strip_prefixes_for_docx,
                convert_math=False,
            )

            # Two spaces at the end: hard line break in Markdown
            md.append(f"**{letter}.** {display_text}  ")

        md.append("")  # extra blank line after each question

    return "\n".join(md)


def questions_to_markdown_full(questions: list[dict],
                               strip_prefixes_for_docx: bool = True) -> str:
    """
    Teacher version:
    - Question
    - Options with TRUE/FALSE indication
    - Success and error feedback (each on its own paragraph)
    """
    md = []

    for idx, q in enumerate(questions, start=1):
        # Ensure q is a dict and has a question
        if not isinstance(q, dict):
            continue

        question_text = str(q.get("question", "")).strip()
        if not question_text:
            continue

        options = q.get("options", {})
        if not isinstance(options, dict) or not options:
            continue

        md.append(f"**{idx}. {question_text}**")
        md.append("")

        # Options with TRUE/FALSE
        for j, (opt_text, is_true) in enumerate(options.items()):
            letter = chr(ord("A") + j)
            display_text = clean_option_text(
                str(opt_text),
                strip_prefixes=strip_prefixes_for_docx,
                convert_math=False,
            )
            status = "TRUE" if is_true else "FALSE"
            md.append(f"**{letter}.** {display_text} — **{status}**  ")
            md.append("")

        # Feedback texts
        success_fb = (q.get("success") or "").strip()
        error_fb   = (q.get("error")   or "").strip()

        if success_fb:
            md.append(f"*Feedback for correct answers:*")
            md.append(f"{success_fb}  ")
            md.append("")   # empty line = new paragraph

        if error_fb:
            md.append(f"*Feedback for incorrect/partial answers:*")
            md.append(f"{error_fb}  ")
            md.append("")

        md.append("")  # extra space between questions

    return "\n".join(md)

def markdown_to_docx(md_text: str) -> BytesIO:
    """
    Convert a Markdown string into DOCX using Pandoc.
    Returns a BytesIO buffer (ready for Streamlit download).
    """
    # Temporary markdown file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as f_md:
        f_md.write(md_text.encode("utf-8"))
        md_path = f_md.name

    # Output file path
    docx_path = md_path.replace(".md", ".docx")

    # Build Pandoc command
    cmd = ["pandoc", md_path, "-o", docx_path]

    # Optional reference docx: only add if it exists
    ref_doc = Path("custom-reference.docx")
    if ref_doc.exists():
        cmd.extend(["--reference-doc", str(ref_doc)])

    # Run Pandoc and capture output for nicer error reporting
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        # Clean up temp files on failure
        try:
            os.remove(md_path)
        except FileNotFoundError:
            pass
        try:
            if os.path.exists(docx_path):
                os.remove(docx_path)
        except FileNotFoundError:
            pass

        # Show Pandoc's error message in Streamlit
        st.error(f"Pandoc failed (exit code {result.returncode}):\n\n{result.stderr}")
        raise RuntimeError("Pandoc conversion failed")

    # Read DOCX into memory
    with open(docx_path, "rb") as f:
        buffer = BytesIO(f.read())

    # Clean temp files
    os.remove(md_path)
    os.remove(docx_path)

    buffer.seek(0)
    return buffer

# ============================================================
# QTI PART
# ============================================================

# -------------------------------
# QTI namespaces and registration
# -------------------------------
NS_QTI   = "http://www.imsglobal.org/xsd/imsqti_v2p1"
NS_IMSCP = "http://www.imsglobal.org/xsd/imscp_v1p1"
NS_XSI   = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace('',   NS_QTI)
ET.register_namespace('xsi', NS_XSI)

# -------------------------------
# Text transforms
# -------------------------------
#_opt_prefix = re.compile(r"^\s*[A-Z][\)\.\:]\s+")
_opt_prefix = re.compile(r"^\s*([A-Za-z0-9]+)[\)\.\:]\s+")
_inline_math = re.compile(r"\$(?!\$)(.+?)\$(?!\$)")  # convert single-$ inline math to $$...$$

def to_double_dollar_math(s: str) -> str:
    # Convert $...$ to $$...$$, leave $$...$$ as-is
    return _inline_math.sub(r"$$\1$$", s)

def clean_option_text(s: str, strip_prefixes=True, convert_math=True) -> str:
    text = s
    if strip_prefixes:
        text = _opt_prefix.sub("", text)
    if convert_math:
        text = to_double_dollar_math(text)
    return text

def clean_general_text(s: str, convert_math=True) -> str:
    return to_double_dollar_math(s) if convert_math else s

# -------------------------------
# QTI builders
# -------------------------------
def make_item_xml(
    title: str,
    stem: str,
    choices: list[tuple[str, str]],          # [(choice_id, text), ...]
    correct_ids: list[str],
    success_text: str,
    error_text: str,
    shuffle: bool = True
    ):
    """
    Build a QTI 2.1 assessmentItem that matches the LMS sample wiring.
    """
    item_id = f"item-{uuid.uuid4()}"
    item = ET.Element(ET.QName(NS_QTI, "assessmentItem"), {
        ET.QName(NS_XSI, "schemaLocation"):
            "http://www.imsglobal.org/xsd/imsqti_v2p1 "
            "http://www.imsglobal.org/xsd/qti/qtiv2p1/imsqti_v2p1p1.xsd",
        "identifier": item_id,
        "title": title,
        "adaptive": "false",
        "timeDependent": "false"
    })

    # responseDeclaration
    rd = ET.SubElement(item, ET.QName(NS_QTI, "responseDeclaration"),
                       {"identifier": "RESPONSE_1", "cardinality": "multiple", "baseType": "identifier"})
    cr = ET.SubElement(rd, ET.QName(NS_QTI, "correctResponse"))
    for cid in correct_ids:
        v = ET.SubElement(cr, ET.QName(NS_QTI, "value"))
        v.text = cid

    # outcomes
    for ident, baseType, default in [
        ("SCORE", "float", "0"),
        ("MAXSCORE", "float", "1"),
        ("MINSCORE", "float", "0"),
        ("FEEDBACKBASIC", "identifier", "empty"),
    ]:
        od = ET.SubElement(item, ET.QName(NS_QTI, "outcomeDeclaration"),
                           {"identifier": ident, "cardinality": "single", "baseType": baseType})
        dv = ET.SubElement(od, ET.QName(NS_QTI, "defaultValue"))
        ET.SubElement(dv, ET.QName(NS_QTI, "value")).text = default

    ET.SubElement(item, ET.QName(NS_QTI, "outcomeDeclaration"),
                  {"identifier": "FEEDBACKMODAL", "cardinality": "multiple", "baseType": "identifier", "view": "testConstructor"})

    # itemBody
    body = ET.SubElement(item, ET.QName(NS_QTI, "itemBody"))
    ET.SubElement(body, ET.QName(NS_QTI, "p")).text = stem
    ci = ET.SubElement(body, ET.QName(NS_QTI, "choiceInteraction"),
                       {"responseIdentifier": "RESPONSE_1", "shuffle": "true" if shuffle else "false", "maxChoices": "0"})
    for cid, text in choices:
        sc = ET.SubElement(ci, ET.QName(NS_QTI, "simpleChoice"), {"identifier": cid})
        ET.SubElement(sc, ET.QName(NS_QTI, "p")).text = text

    # modalFeedback nodes
    fb_ok_id  = f"id-{uuid.uuid4()}"
    fb_err_id = f"id-{uuid.uuid4()}"
    for fid, txt in [(fb_ok_id, success_text), (fb_err_id, error_text)]:
        mf = ET.SubElement(item, ET.QName(NS_QTI, "modalFeedback"),
                           {"identifier": fid, "outcomeIdentifier": "FEEDBACKMODAL", "showHide": "show"})
        ET.SubElement(mf, ET.QName(NS_QTI, "p")).text = txt

    # responseProcessing (matches your working LMS example)
    rp = ET.SubElement(item, ET.QName(NS_QTI, "responseProcessing"))

    # 0) If empty -> FEEDBACKBASIC = empty
    rc0 = ET.SubElement(rp, ET.QName(NS_QTI, "responseCondition"))
    rif0 = ET.SubElement(rc0, ET.QName(NS_QTI, "responseIf"))
    isnull = ET.SubElement(rif0, ET.QName(NS_QTI, "isNull"))
    ET.SubElement(isnull, ET.QName(NS_QTI, "variable"), {"identifier": "RESPONSE_1"})
    act0 = ET.SubElement(rif0, ET.QName(NS_QTI, "setOutcomeValue"), {"identifier": "FEEDBACKBASIC"})
    ET.SubElement(act0, ET.QName(NS_QTI, "baseValue"), {"baseType": "identifier"}).text = "empty"

    # 1) Exact match -> SCORE = SCORE + MAXSCORE; FEEDBACKBASIC = correct
    rc1 = ET.SubElement(rp, ET.QName(NS_QTI, "responseCondition"))
    rif1 = ET.SubElement(rc1, ET.QName(NS_QTI, "responseIf"))
    match = ET.SubElement(rif1, ET.QName(NS_QTI, "match"))
    ET.SubElement(match, ET.QName(NS_QTI, "variable"), {"identifier": "RESPONSE_1"})
    ET.SubElement(match, ET.QName(NS_QTI, "correct"), {"identifier": "RESPONSE_1"})
    so1 = ET.SubElement(rif1, ET.QName(NS_QTI, "setOutcomeValue"), {"identifier": "SCORE"})
    summ = ET.SubElement(so1, ET.QName(NS_QTI, "sum"))
    ET.SubElement(summ, ET.QName(NS_QTI, "variable"), {"identifier": "SCORE"})
    ET.SubElement(summ, ET.QName(NS_QTI, "variable"), {"identifier": "MAXSCORE"})
    so2 = ET.SubElement(rif1, ET.QName(NS_QTI, "setOutcomeValue"), {"identifier": "FEEDBACKBASIC"})
    ET.SubElement(so2, ET.QName(NS_QTI, "baseValue"), {"baseType": "identifier"}).text = "correct"

    # 2) Else -> SCORE = 0; FEEDBACKBASIC = incorrect
    relse = ET.SubElement(rc1, ET.QName(NS_QTI, "responseElse"))
    so3 = ET.SubElement(relse, ET.QName(NS_QTI, "setOutcomeValue"), {"identifier": "SCORE"})
    ET.SubElement(so3, ET.QName(NS_QTI, "baseValue"), {"baseType": "float"}).text = "0"
    so4 = ET.SubElement(relse, ET.QName(NS_QTI, "setOutcomeValue"), {"identifier": "FEEDBACKBASIC"})
    ET.SubElement(so4, ET.QName(NS_QTI, "baseValue"), {"baseType": "identifier"}).text = "incorrect"

    # 3) FEEDBACKBASIC == correct -> add correct modal id
    rc2 = ET.SubElement(rp, ET.QName(NS_QTI, "responseCondition"))
    rif2 = ET.SubElement(rc2, ET.QName(NS_QTI, "responseIf"))
    match2 = ET.SubElement(rif2, ET.QName(NS_QTI, "match"))
    ET.SubElement(match2, ET.QName(NS_QTI, "baseValue"), {"baseType": "identifier"}).text = "correct"
    ET.SubElement(match2, ET.QName(NS_QTI, "variable"), {"identifier": "FEEDBACKBASIC"})
    so5 = ET.SubElement(rif2, ET.QName(NS_QTI, "setOutcomeValue"), {"identifier": "FEEDBACKMODAL"})
    mult_ok = ET.SubElement(so5, ET.QName(NS_QTI, "multiple"))
    ET.SubElement(mult_ok, ET.QName(NS_QTI, "variable"), {"identifier": "FEEDBACKMODAL"})
    ET.SubElement(mult_ok, ET.QName(NS_QTI, "baseValue"), {"baseType": "identifier"}).text = fb_ok_id

    # 4) FEEDBACKBASIC == incorrect -> add incorrect modal id
    rc3 = ET.SubElement(rp, ET.QName(NS_QTI, "responseCondition"))
    rif3 = ET.SubElement(rc3, ET.QName(NS_QTI, "responseIf"))
    match3 = ET.SubElement(rif3, ET.QName(NS_QTI, "match"))
    ET.SubElement(match3, ET.QName(NS_QTI, "baseValue"), {"baseType": "identifier"}).text = "incorrect"
    ET.SubElement(match3, ET.QName(NS_QTI, "variable"), {"identifier": "FEEDBACKBASIC"})
    so6 = ET.SubElement(rif3, ET.QName(NS_QTI, "setOutcomeValue"), {"identifier": "FEEDBACKMODAL"})
    mult_bad = ET.SubElement(so6, ET.QName(NS_QTI, "multiple"))
    ET.SubElement(mult_bad, ET.QName(NS_QTI, "variable"), {"identifier": "FEEDBACKMODAL"})
    ET.SubElement(mult_bad, ET.QName(NS_QTI, "baseValue"), {"baseType": "identifier"}).text = fb_err_id

    return item_id, item

def make_manifest_xml(item_filenames: list[str]) -> ET.Element:
    ET.register_namespace('', NS_IMSCP)
    ET.register_namespace('xsi', NS_XSI)
    manifest = ET.Element(ET.QName(NS_IMSCP, "manifest"), {
        ET.QName(NS_XSI, "schemaLocation"):
            "http://www.imsglobal.org/xsd/imscp_v1p1 "
            "http://www.imsglobal.org/xsd/imscp_v1p1.xsd "
            "http://www.imsglobal.org/xsd/imsqti_v2p1 "
            "http://www.imsglobal.org/xsd/qti/qtiv2p1/imsqti_v2p1p1.xsd",
        "identifier": "manifestID"
    })
    metadata = ET.SubElement(manifest, ET.QName(NS_IMSCP, "metadata"))
    ET.SubElement(metadata, "schema").text = "QTIv2.1 Package"
    ET.SubElement(metadata, "schemaversion").text = "1.0.0"
    ET.SubElement(manifest, ET.QName(NS_IMSCP, "organizations"))
    resources = ET.SubElement(manifest, ET.QName(NS_IMSCP, "resources"))
    for fname in item_filenames:
        rid = "res_" + Path(fname).stem.replace('-', '_')
        res = ET.SubElement(resources, ET.QName(NS_IMSCP, "resource"), {
            "identifier": rid,
            "type": "imsqti_item_xmlv2p1",
            "href": fname
        })
        ET.SubElement(res, ET.QName(NS_IMSCP, "file"), {"href": fname})
    return manifest

def json_to_qti_zip(
    json_bytes: bytes,
    strip_prefixes=True,
    convert_math=True,
    shuffle=True,
    item_prefix: str = "Item",
) -> bytes:
    """
    Convert a JSON (array of items) into a QTI 2.1 zip (in-memory).
    """
    items = json.loads(json_bytes.decode("utf-8"))

    buf = BytesIO()
    zf = ZipFile(buf, "w", ZIP_DEFLATED)

    item_filenames = []

    for idx, q in enumerate(items, start=1):
        # Build choices & correct set
        choices_text = list(q["options"].keys())
        choices_bools = list(q["options"].values())
        choice_ids = [f"ID_{i+1}" for i in range(len(choices_text))]
        # Apply transforms
        stem = clean_general_text(q["question"], convert_math=convert_math)
        choices = [(cid, clean_option_text(txt, strip_prefixes=strip_prefixes, convert_math=convert_math))
                   for cid, txt in zip(choice_ids, choices_text)]
        correct_ids = [cid for cid, ok in zip(choice_ids, choices_bools) if ok]

        # Build item
        title = f"{item_prefix}_{idx:02d}"
        success_text = clean_general_text(q.get("success",""), convert_math=convert_math)
        error_text   = clean_general_text(q.get("error",""),   convert_math=convert_math)
        item_id, item_xml = make_item_xml(title, stem, choices, correct_ids, success_text, error_text, shuffle=shuffle)

        # Write item XML into zip
        item_filename = f"{item_id}.xml"
        item_filenames.append(item_filename)
        xml_bytes = ET.tostring(item_xml, encoding="utf-8", xml_declaration=True)
        zf.writestr(item_filename, xml_bytes)

    # Manifest
    manifest_xml = make_manifest_xml(item_filenames)
    manifest_bytes = ET.tostring(manifest_xml, encoding="utf-8", xml_declaration=True)
    zf.writestr("imsmanifest.xml", manifest_bytes)
    zf.close()
    return buf.getvalue()

# ============================================================
# MOODLE PART
# ============================================================

# ---------- Helpers (ONE <text> child only) ----------
def wrap_p(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    return s if s.lstrip().startswith("<") else f"<p>{s}</p>"

def fractions_from_options(options: Dict[str, bool], single: bool) -> Dict[str, str]:
    """
    Return fraction values as strings in percent.
    - single=True:
        correct = 100.000000, wrong = 0
    - single=False (multi-select):
        each correct = 100 / C
        each wrong   = -100 / W
    """
    keys = list(options.keys())
    correct_keys = [k for k in keys if options[k] is True]
    wrong_keys   = [k for k in keys if options[k] is not True]

    if single:
        return {k: ("100.000000" if k in correct_keys[:1] else "0") for k in keys}

    # Multi-select:
    out: Dict[str, str] = {k: "0" for k in keys}
    C = len(correct_keys)
    W = len(wrong_keys)

    if C > 0:
        share_c = f"{(100.0 / C):.6f}"
        for k in correct_keys:
            out[k] = share_c
    if W > 0:
        share_w = f"{(-100.0 / W):.6f}"
        for k in wrong_keys:
            out[k] = share_w
    return out

def add_scalar(doc: Document, parent, tag: str, text: str):
    el = doc.createElement(tag)
    el.appendChild(doc.createTextNode(text))
    parent.appendChild(el)
    return el

def set_cdata_text(doc: Document, parent, html_text: str):
    t = doc.createElement("text")
    t.appendChild(doc.createCDATASection(html_text))
    parent.appendChild(t)
    return t

def set_plain_text(doc: Document, parent, plain: str):
    t = doc.createElement("text")
    t.appendChild(doc.createTextNode(plain))
    parent.appendChild(t)
    return t

def build_multichoice(doc: Document, idx: int, q: Dict[str, Any],
                      name_prefix: str, defaultgrade: float, penalty: float,
                      shuffleanswers: bool, answernumbering: str, auto_single: bool):
    options = q.get("options", {})
    if not isinstance(options, dict) or not options:
        raise ValueError(f"Question {idx}: 'options' must be a non-empty dict.")

    num_true = sum(1 for v in options.values() if v is True)
    single = (num_true == 1) if auto_single else False
    fractions = fractions_from_options(options, single)

    question = doc.createElement("question")
    question.setAttribute("type", "multichoice")

    # <name><text>…</text></name>
    name = doc.createElement("name")
    question.appendChild(name)
    set_plain_text(doc, name, f"{name_prefix}{idx:03d}")

    # <questiontext format="html"><text><![CDATA[...]]></text></questiontext>
    qtext = doc.createElement("questiontext"); qtext.setAttribute("format", "html"); question.appendChild(qtext)

    raw_qtext = q.get("question", "")

    # Use global Moodle LaTeX setting if available
    try:
        use_convert_math = moodle_convert_math
    except NameError:
        use_convert_math = False

    if use_convert_math:
        raw_qtext = clean_general_text(raw_qtext, convert_math=True)

    set_cdata_text(doc, qtext, wrap_p(raw_qtext))


    # generalfeedback (empty – outcome feedback only)
    gf = doc.createElement("generalfeedback"); gf.setAttribute("format", "html"); question.appendChild(gf)
    set_cdata_text(doc, gf, "")

    # core fields
    add_scalar(doc, question, "defaultgrade", f"{float(defaultgrade):g}")
    add_scalar(doc, question, "penalty", f"{float(penalty):g}")
    add_scalar(doc, question, "hidden", "0")
    add_scalar(doc, question, "idnumber", "")
    add_scalar(doc, question, "single", "true" if single else "false")
    add_scalar(doc, question, "shuffleanswers", "true" if shuffleanswers else "false")
    add_scalar(doc, question, "answernumbering", answernumbering)
    add_scalar(doc, question, "showstandardinstruction", "0")

    # Outcome feedback:
    correct_fb = q.get("success", "") or "Your answer is correct."
    wrong_fb   = q.get("error", "")   or "Your answer is partially or wholly incorrect."

    cf = doc.createElement("correctfeedback"); cf.setAttribute("format","html"); question.appendChild(cf)
    set_cdata_text(doc, cf, wrap_p(correct_fb))
    pf = doc.createElement("partiallycorrectfeedback"); pf.setAttribute("format","html"); question.appendChild(pf)
    set_cdata_text(doc, pf, wrap_p(wrong_fb))
    inf = doc.createElement("incorrectfeedback"); inf.setAttribute("format","html"); question.appendChild(inf)
    set_cdata_text(doc, inf, wrap_p(wrong_fb))

    # <shownumcorrect/>
    question.appendChild(doc.createElement("shownumcorrect"))

    # answers with fractions
    for ans_text in options.keys():
        ans = doc.createElement("answer")
        ans.setAttribute("fraction", fractions[ans_text])
        ans.setAttribute("format", "html")
        question.appendChild(ans)

        # Use Moodle-specific strip option (global from Streamlit UI)
        try:
            use_strip = moodle_strip_prefixes
        except NameError:
            use_strip = True  # safe default if not defined

        try:
            use_convert_math = moodle_convert_math
        except NameError:
            use_convert_math = False

        display_text = clean_option_text(
            str(ans_text),
            strip_prefixes=use_strip,
            convert_math=use_convert_math,
        )

        set_cdata_text(doc, ans, wrap_p(display_text))

        fb = doc.createElement("feedback"); fb.setAttribute("format", "html"); ans.appendChild(fb)
        set_cdata_text(doc, fb, "")  # empty per-answer feedback

    return question

def build_quiz_xml(data: List[Dict[str, Any]],
                   name_prefix: str, defaultgrade: float, penalty: float,
                   shuffleanswers: bool, answernumbering: str, auto_single: bool) -> bytes:
    doc = Document()
    quiz = doc.createElement("quiz")
    doc.appendChild(quiz)
    for i, q in enumerate(data, start=1):
        quiz.appendChild(
            build_multichoice(doc, i, q, name_prefix, defaultgrade, penalty,
                              shuffleanswers, answernumbering, auto_single)
        )
    return doc.toprettyxml(indent="  ", encoding="UTF-8")

# ============================================================
# COMBINED STREAMLIT UI
# ============================================================

st.set_page_config(page_title="TRANSFER-ASS", page_icon="✨", layout="centered")

st.title("Transfer :blue[ASS] ✨")
st.subheader("🔄 Move your JSON assessments in QTI 2.1/MOODLE XML/DOCX format", divider = 'blue')
st.markdown("""
    This tool enables the conversion of JSON-based multiple-choice assessments into
    - QTI 2.1 import packages,
    - Moodle XML files, or
    - editable Word documents.
   
    To proceed and start the conversion, upload one **JSON** file containing the questions in the **iNUX-format**:
    """
    )
with st.expander("Click here to see the structure of the JSON file in iNUX-format"):
    st.markdown("""   
    ```json
    [
      {
        "question": "… (can include **markdown** and $$\\\\LaTeX$$) …",
        "options": {
          "Option text A": true,
          "Option text B": false,
          "Option text C": true
        },
        "success": "Feedback shown when *all* correct choices are selected.",
        "error":   "Feedback shown otherwise."
      }
    ]
    """
    )
    
st.subheader('Define file and transfer settings', divider = "blue")

st.markdown("""
    #### Select and :blue[**Upload**] JSON file
    
    Select the JSON file on your local computer, or drop the file here
    """)

uploaded = st.file_uploader("Upload JSON file", type=["json"])

# Derive a base prefix from uploaded filename (without .json)
if uploaded is not None:
    base_prefix = Path(uploaded.name).stem
else:
    base_prefix = "Item"   # fallback if nothing uploaded yet

# --- Select output

st.markdown("""
    #### Select Transfer :blue[**Formats**]
    
    You can activate the desired output format(s) with the following radio buttons. You can select to generate QTI, Moodle, and Word from the same JSON.
    """)
    
qti_selected = st.checkbox("Generate QTI 2.1 ZIP", value=True)
moodle_selected = st.checkbox("Generate Moodle XML", value=True)
word_selected = st.checkbox("Generate Word (.docx)", value=False)

# Word sub-options
if word_selected:
    word_clean_selected = st.checkbox(
        "Word: Questions & choices only (student version)",
        value=True,
    )
    word_full_selected = st.checkbox(
        "Word: With TRUE/FALSE + feedback (teacher version)",
        value=False,
    )
else:
    word_clean_selected = False
    word_full_selected = False

# Inform user if nothing selected
if not (qti_selected or moodle_selected or word_selected):
    st.warning("Please select at least one output format (QTI, Moodle, and/or Word).")

#---------- 3) Options for each converter (UI preserved) ----------
# Initial values
qti_prefix_ini = base_prefix
moodle_prefix_ini = base_prefix

if qti_selected:
    st.markdown("""
        #### Specific settings: :blue[**Options QTI**]
        
        Choose the options for the QTI 2.1 transfer file
        """)
    
    cq1, cq2 = st.columns(2)
    with cq1:
        qti_prefix = st.text_input("QTI item name prefix", value=qti_prefix_ini)
    with cq2:
        qti_strip_prefixes = st.checkbox("Strip prefixes like A) B) C) ... a) 1) in QTI",value=True)
        convert_math = st.checkbox("Convert LATEX codes in QTI", value=True)
        shuffle = st.checkbox("Shuffle answers in QTI", value=True)

if moodle_selected:
    st.markdown("""
        #### Specific settings: :blue[**Options MOODLE**]
        
        Choose the options for the MOODLE transfer file
        """)
    
    cm1, cm2 = st.columns((1,1))
    with cm1:
        if qti_selected:
            moodle_prefix = st.text_input("Question name prefix", value=qti_prefix)
        else:
            moodle_prefix = st.text_input("MOODLE item name prefix", value=moodle_prefix_ini)
    with cm2:
        moodle_strip_prefixes = st.checkbox("Strip prefixes like A) B) C) ... a) 1) in Moodle", value=True)
        moodle_convert_math = st.checkbox("Convert LATEX codes in Moodle", value=True)
        defaultgrade = st.number_input("Default grade", min_value=0.0, value=1.0, step=0.5, format="%.2f")
        penalty = st.number_input("Penalty (e.g., 0.3333333)", min_value=0.0, max_value=1.0, value=0.3333333, step=0.0000001, format="%.7f")
        answernumbering = st.selectbox("Answer numbering", ["abc", "ABCD", "123", "none"], index=0)
        auto_single = st.checkbox("Auto-detect single-correct (<single>true>)", value=True)
        shuffleanswers = st.checkbox("Shuffle answers in MOODLE", value=True)

st.subheader("Start the Conversion", divider = 'blue')
st.markdown("""
Click the following button to start the conversion. The converted file will be automatically downloaded.
        """)

convert_clicked = st.button(
    "Click here to Convert",
    type="primary",
    disabled=not (qti_selected or moodle_selected or word_selected)
)

if convert_clicked:
    if not (qti_selected or moodle_selected or word_selected):
        st.warning("Please select at least one output format (QTI and/or Moodle).")
    elif uploaded is None:
        st.error("Please upload a JSON file first.")
    else:
        try:
            raw_bytes = uploaded.read()
            data = json.loads(raw_bytes.decode("utf-8", errors="replace"))
        except Exception as e:
            st.error(f"Could not parse JSON: {e}")
            st.stop()

        # --- Normalize input to a plain list of question dicts ---
        if isinstance(data, dict) and "questions" in data:
            questions = data["questions"]
        elif isinstance(data, list):
            questions = data
        else:
            st.error("JSON must be a LIST of questions or an object with a 'questions' list.")
            st.stop()

        # Store once for later use (Word export etc.)
        st.session_state["questions"] = questions

        # For Moodle and QTI: use the same normalized list
        moodle_data = questions
        qti_json_bytes = json.dumps(questions).encode("utf-8")


        # Prepare result buffers
        qti_zip_bytes = None
        moodle_xml_bytes = None

        # ----- QTI -----
        if qti_selected:
            try:
                # Basic sanity check similar to original UI
                tmp_check = json.loads(qti_json_bytes.decode("utf-8"))
                assert isinstance(tmp_check, list), "Top level for QTI must be a JSON array of items."
                if tmp_check:
                    assert "question" in tmp_check[0] and "options" in tmp_check[0], \
                        "Each QTI item must have 'question' and 'options'."

                qti_zip_bytes = json_to_qti_zip(
                    qti_json_bytes,
                    strip_prefixes= qti_strip_prefixes,
                    convert_math=convert_math,
                    shuffle=shuffle,
                    item_prefix=qti_prefix,
                )
                st.success("QTI package created.")
            except Exception as e:
                st.error(f"QTI conversion failed: {e}")

        # ----- Moodle -----
        if moodle_selected:
            try:
                if not isinstance(moodle_data, list):
                    raise ValueError(
                        "JSON must be a LIST (array) of questions or an object with a 'questions' list for Moodle."
                    )
                moodle_xml_bytes = build_quiz_xml(
                    moodle_data,
                    moodle_prefix,
                    defaultgrade,
                    penalty,
                    shuffleanswers,
                    answernumbering,
                    auto_single,
                )
                st.success("Moodle XML generated.")
            except Exception as e:
                st.error(f"Moodle conversion failed: {e}")

        # ----- Word DOCX (clean + full) -----
        word_clean_bytes = None
        word_full_bytes = None

        if word_selected:
            try:
                if word_clean_selected:
                    md_clean = questions_to_markdown(
                        questions,
                        strip_prefixes_for_docx=True,
                    )
                    buf_clean = markdown_to_docx(md_clean)        # BytesIO
                    word_clean_bytes = buf_clean.getvalue()       # -> bytes
                    st.success("Word (questions only) generated.")
                
                if word_full_selected:
                    md_full = questions_to_markdown_full(
                        questions,
                        strip_prefixes_for_docx=True,
                    )
                    buf_full = markdown_to_docx(md_full)          # BytesIO
                    word_full_bytes = buf_full.getvalue()         # -> bytes
                    st.success("Word (with answers + feedback) generated.")
                

            except Exception as e:
                st.error(f"Word export failed: {e}")


        # ----- Collect all outputs for download -----
        outputs = []

        if qti_zip_bytes:
            outputs.append((
                "QTI package",
                f"{qti_prefix}_qti_mcq.zip",
                qti_zip_bytes,
                "application/zip",
                "qti"
            ))

        if moodle_xml_bytes:
            outputs.append((
                "Moodle XML",
                f"{moodle_prefix}_moodle_mcq.xml",
                moodle_xml_bytes,
                "application/xml",
                "moodle"
            ))

        if word_clean_bytes:
            outputs.append((
                "Word (questions only)",
                f"{base_prefix}_questions.docx",
                word_clean_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "word_clean"
            ))

        if word_full_bytes:
            outputs.append((
                "Word (answers + feedback)",
                f"{base_prefix}_questions_with_answers.docx",
                word_full_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "word_full"
            ))

        # ----- Download button(s) -----
        if not outputs:
            st.info("No downloadable file was created due to previous errors.")
        elif len(outputs) == 1:
            label, filename, data, mime, key_suffix = outputs[0]
            st.download_button(
                f"💾 Download {label}",
                data=data,
                file_name=filename,
                mime=mime,
                key=f"download_{key_suffix}",
            )
        else:
            combo_buf = BytesIO()
            with ZipFile(combo_buf, "w", ZIP_DEFLATED) as zf:
                for _, filename, data, _mime, _key in outputs:
                    zf.writestr(filename, data)
            combo_buf.seek(0)

            st.download_button(
                "💾 Download TRANSFER-ASS package (ZIP)",
                data=combo_buf.getvalue(),
                file_name=f"{base_prefix}_package.zip",
                mime="application/zip",
                key="download_package",
            )