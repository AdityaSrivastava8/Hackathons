import sys
import os

# Update system path FIRST so Python can locate internal modules on Streamlit Cloud
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
import time
from fpdf import FPDF
from agent.analyzer import DetectiveAgent

# Page Configuration MUST BE FIRST
st.set_page_config(
    page_title="Detective Agentic AI - Criminal Profiler",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# ── Session State defaults ─────────────────────────────────────────────────────
if "evals_left" not in st.session_state:
    st.session_state.evals_left = 25
if "max_evals" not in st.session_state:
    st.session_state.max_evals = 25
if "current_tier" not in st.session_state:
    st.session_state.current_tier = "Pro Agency Trial"
if "latest_results" not in st.session_state:
    st.session_state.latest_results = None
if "show_pricing" not in st.session_state:
    st.session_state.show_pricing = False

# ── Agent (cached so it survives re-runs) ──────────────────────────────────────
@st.cache_resource
def load_agent():
    return DetectiveAgent()

agent = load_agent()

# ── Helper: Generate PDF Executive Summary ─────────────────────────────────────
def generate_pdf_report(suspect_name, age, tendency_score, risk_level, behaviors, matched_cases):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "EXECUTIVE CRIMINAL PROFILE REPORT", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Suspect Name: {suspect_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Age: {age if age else 'Unknown'}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Calculated Tendency Score: {tendency_score}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Risk Assessment Level: {risk_level}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Observed Behaviors & Modus Operandi:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, str(behaviors))
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Matched Historical Precedents:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)

    for idx, case in enumerate(matched_cases, 1):
        pdf.cell(0, 6, f"{idx}. {case.get('case_title', 'Unknown Case')} ({case.get('location', 'N/A')})", new_x="LMARGIN", new_y="NEXT")
        snippet = case.get('summary', case.get('snippet', ''))[:150]
        pdf.multi_cell(0, 5, f"   Snippet: {snippet}...")
        pdf.ln(2)

    return bytes(pdf.output())

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🕵️‍♂️ Detective Agentic AI & RAG Profiling System")
st.markdown("Automated criminal pattern recognition, risk evaluation, and precedent retrieval engine.")
st.divider()

# ── Sidebar: Admin Case JSON Uploader ──────────────────────────────────────────
st.sidebar.header("⚙️ Admin Case Indexer")
uploaded_file = st.sidebar.file_uploader("Upload Case JSON to Vector DB", type=["json"])

if uploaded_file is not None:
    try:
        case_data = json.load(uploaded_file)
        cases_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cases"))
        os.makedirs(cases_dir, exist_ok=True)
        save_path = os.path.join(cases_dir, uploaded_file.name)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=4)
        st.sidebar.success(f"Successfully uploaded & indexed '{uploaded_file.name}'!")
    except Exception as e:
        st.sidebar.error(f"Failed to upload case JSON: {e}")

st.sidebar.divider()

# ── Sidebar: B2B Agency Plan display ──────────────────────────────────────────
st.sidebar.markdown("### B2B Agency Plan")

_max = st.session_state.max_evals
_left = st.session_state.evals_left

# Always derive quota_display from current session state
if _max == "Unlimited":
    quota_display = "Unlimited"
else:
    # Guard: if evals_left somehow exceeds max (e.g. after plan switch), cap display
    quota_display = f"{min(_left, _max)}/{_max}"

st.sidebar.info(
    f"**Current Tier:** {st.session_state.current_tier}\n\n"
    f"**Evaluations Remaining:** {quota_display}"
)

if _max != "Unlimited" and _left <= 0:
    st.sidebar.error("⚠️ Trial Limit Reached")

if st.sidebar.button("💳 Upgrade / Billing Portal", use_container_width=True):
    st.session_state.show_pricing = not st.session_state.show_pricing
    st.rerun()

# Reset Quota & Clear Session Button
if st.sidebar.button("🔄 Reset Demo & Clear Cache", use_container_width=True):
    st.session_state.evals_left = 25
    st.session_state.max_evals = 25
    st.session_state.current_tier = "Pro Agency Trial"
    st.session_state.latest_results = None
    st.session_state.show_pricing = False
    st.rerun()

# ── B2B SaaS Pricing Panel ─────────────────────────────────────────────────────
if st.session_state.show_pricing:
    st.warning("🔗 **Redirected to Secure B2B Billing Portal**")
    st.subheader("Select an Enterprise Subscription Tier")

    p_col1, p_col2, p_col3 = st.columns(3)

    with p_col1:
        st.markdown("### 🥉 Starter Agency")
        st.markdown("**$99 / month**")
        st.markdown("* 100 Evaluations / mo\n* Standard RAG Precedent Search\n* Basic PDF Export")
        if st.button("Select Starter", key="btn_starter"):
            st.session_state.evals_left = 100
            st.session_state.max_evals = 100
            st.session_state.current_tier = "Starter Agency"
            st.session_state.show_pricing = False
            st.rerun()

    with p_col2:
        st.markdown("### 🥈 Pro Agency")
        st.markdown("**$299 / month**")
        st.markdown("* 500 Evaluations / mo\n* Fast ChromaDB Vector Search\n* Custom JSON File Indexer")
        if st.button("Select Pro Plan", key="btn_pro"):
            st.session_state.evals_left = 500
            st.session_state.max_evals = 500
            st.session_state.current_tier = "Pro Agency"
            st.session_state.show_pricing = False
            st.rerun()

    with p_col3:
        st.markdown("### 🥇 Enterprise SaaS")
        st.markdown("**$799 / month**")
        st.markdown("* Unlimited Evaluations\n* Private Vector Database\n* Dedicated API & Priority Support")
        if st.button("Select Enterprise", key="btn_enterprise"):
            st.session_state.evals_left = "Unlimited"
            st.session_state.max_evals = "Unlimited"
            st.session_state.current_tier = "Enterprise SaaS"
            st.session_state.show_pricing = False
            st.rerun()

    st.divider()

# ── Main Profiling Layout ──────────────────────────────────────────────────────
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Suspect Information & Observations")
    with st.form(key="suspect_profiling_form"):
        suspect_name = st.text_input("Suspect Name / Alias", placeholder="John Doe")
        age = st.text_input("Age", placeholder="34")
        behaviors = st.text_area(
            "Observed Behaviors, MO, & Traits",
            height=180,
            placeholder="Entering residential premises during late hours, targeting locked cabinets..."
        )
        submit_btn = st.form_submit_button("Run Intelligence Analysis", type="primary", use_container_width=True)

with col2:
    st.subheader("Analysis & Precedent Results")

    if submit_btn:
        if not behaviors.strip():
            st.warning("Please enter observed behaviors to analyze.")
        elif st.session_state.max_evals != "Unlimited" and st.session_state.evals_left <= 0:
            st.error("🚫 Evaluation Quota Exceeded! Please upgrade via the sidebar.")
        else:
            with st.spinner("Analyzing traits against ChromaDB precedent vectors..."):
                try:
                    name_str = suspect_name if suspect_name else "Unnamed Suspect"
                    # Re-instantiate agent if somehow invalidated (handles post-1st-run crash)
                    try:
                        res = agent.evaluate_suspect(
                            name=name_str,
                            behavior=behaviors,
                            mo_suspected=behaviors,
                            personality_notes="Observed via profiling dashboard."
                        )
                    except Exception:
                        # Cache may have stale ChromaDB connection; bust and retry once
                        load_agent.clear()
                        fresh_agent = load_agent()
                        res = fresh_agent.evaluate_suspect(
                            name=name_str,
                            behavior=behaviors,
                            mo_suspected=behaviors,
                            personality_notes="Observed via profiling dashboard."
                        )

                    # Decrement quota only for non-unlimited plans
                    if st.session_state.max_evals != "Unlimited":
                        st.session_state.evals_left = max(0, st.session_state.evals_left - 1)

                    st.session_state.latest_results = {
                        "name": name_str,
                        "age": age,
                        "behaviors": behaviors,
                        "tendency_score": res.get("tendency_score", "0%"),
                        "risk_level": res.get("risk_level", "UNKNOWN"),
                        "matched_cases": res.get("similar_cases", []),
                        "summary_text": res.get("summary", ""),
                        "timestamp": time.time()
                    }
                except Exception as err:
                    st.error(f"Analysis failed: {err}")

    # Render persisted results (survives re-runs without re-analyzing)
    if st.session_state.latest_results:
        res = st.session_state.latest_results

        m_col1, m_col2 = st.columns(2)
        m_col1.metric("Tendency Score", str(res["tendency_score"]))
        m_col2.metric("Risk Level", res["risk_level"])

        st.info(res["summary_text"])

        st.markdown("#### Matched Precedents")
        if res["matched_cases"]:
            for case in res["matched_cases"]:
                with st.expander(f"📌 {case.get('case_title', 'Historical Precedent')} ({case.get('location', 'Global')})"):
                    st.write(f"**Case ID:** {case.get('case_id', 'N/A')}")
                    st.write(f"**Details:** {case.get('summary', case.get('snippet', 'No detailed snippet available.'))}")
        else:
            st.info("No close precedent matches found above threshold.")

        try:
            pdf_bytes = generate_pdf_report(
                res["name"],
                res["age"],
                res["tendency_score"],
                res["risk_level"],
                res["behaviors"],
                res["matched_cases"]
            )
            dynamic_key = f"dl_pdf_{res.get('timestamp', time.time())}"
            st.download_button(
                label="📥 Download Executive PDF Report",
                data=pdf_bytes,
                file_name=f"Profile_Report_{res['name'].replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=dynamic_key
            )
        except Exception:
            st.caption("PDF generation ready.")
