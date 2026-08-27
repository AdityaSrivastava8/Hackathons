import sys
import os

# 1. Update system path FIRST
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
import pandas as pd
from fpdf import FPDF
from agent.analyzer import DetectiveAgent

# Initialize Session State Variables
if "evals_left" not in st.session_state:
    st.session_state.evals_left = 25
if "latest_results" not in st.session_state:
    st.session_state.latest_results = None
if "show_pricing" not in st.session_state:
    st.session_state.show_pricing = False

@st.cache_resource
def load_agent():
    return DetectiveAgent()

agent = load_agent()

# Page Configuration
st.set_page_config(
    page_title="Detective Agentic AI - Criminal Profiler",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# Helper Function: Generate PDF Executive Summary
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
    pdf.multi_cell(0, 6, behaviors)
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

# Header
st.title("🕵️‍♂️ Detective Agentic AI & RAG Profiling System")
st.markdown("Automated criminal pattern recognition, risk evaluation, and precedent retrieval engine.")
st.divider()

# Sidebar: Web Admin Case JSON Uploader
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

# Dynamic B2B Agency Plan Sidebar Widget
st.sidebar.markdown("### B2B Agency Plan")
st.sidebar.info(f"**Current Tier:** Pro Agency Trial\n\n**Evaluations Remaining:** {st.session_state.evals_left}/25")

if st.session_state.evals_left <= 0:
    st.sidebar.error("⚠️ Trial Limit Reached")

if st.sidebar.button("💳 Upgrade / Billing Portal", use_container_width=True):
    st.session_state.show_pricing = not st.session_state.show_pricing

# Reset Quota & Clear Session Button
if st.sidebar.button("🔄 Reset Demo & Clear Cache", use_container_width=True):
    st.session_state.evals_left = 25
    st.session_state.latest_results = None
    st.session_state.show_pricing = False
    st.rerun()

# B2B SaaS Pricing Window (Displays when redirected)
if st.session_state.show_pricing:
    st.warning("🔗 **Redirected to Secure B2B Billing Portal**")
    st.subheader("Select an Enterprise Subscription Tier")
    
    p_col1, p_col2, p_col3 = st.columns(3)
    
    with p_col1:
        st.markdown("### 🥉 Starter Agency")
        st.markdown("**$99 / month**")
        st.markdown("* 100 Evaluations / mo\n* Standard RAG Precedent Search\n* Basic PDF Export")
        if st.button("Select Starter"):
            st.session_state.evals_left += 100
            st.session_state.show_pricing = False
            st.success("Plan updated! +100 evaluations added.")
            st.rerun()
            
    with p_col2:
        st.markdown("### 🥈 Pro Agency")
        st.markdown("**$299 / month**")
        st.markdown("* 500 Evaluations / mo\n* Fast ChromaDB Vector Search\n* Custom JSON File Indexer")
        if st.button("Select Pro Plan"):
            st.session_state.evals_left += 500
            st.session_state.show_pricing = False
            st.success("Plan updated! +500 evaluations added.")
            st.rerun()

    with p_col3:
        st.markdown("### 🥇 Enterprise SaaS")
        st.markdown("**$799 / month**")
        st.markdown("* Unlimited Evaluations\n* Private Vector Database\n* Dedicated API & Priority Support")
        if st.button("Select Enterprise"):
            st.session_state.evals_left = 99999
            st.session_state.show_pricing = False
            st.success("Enterprise Plan activated! Unlimited evaluations enabled.")
            st.rerun()
            
    st.divider()

# Main Profiling Form
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Suspect Information & Observations")
    with st.form(key="suspect_form", clear_on_submit=False):
        suspect_name = st.text_input("Suspect Name / Alias", placeholder="John Doe")
        age = st.text_input("Age", placeholder="34")
        behaviors = st.text_area(
            "Observed Behaviors, MO, & Traits",
            height=180,
            placeholder="Entering residential premises during late hours, targeting locked cabinets, using toxic chemicals..."
        )
        submit_btn = st.form_submit_button("Run Intelligence Analysis", type="primary", use_container_width=True)

with col2:
    st.subheader("Analysis & Precedent Results")
    
    # Process Analysis inside st.form to eliminate rerun freeze loops
    if submit_btn:
        if not behaviors.strip():
            st.warning("Please enter observed behaviors to analyze.")
        elif st.session_state.evals_left <= 0:
            st.error("🚫 Evaluation Quota Exceeded! You have reached your 25 trial limit. Click 'Upgrade / Billing Portal' in the sidebar.")
        else:
            with st.spinner("Analyzing traits against ChromaDB precedent vectors..."):
                try:
                    name_str = suspect_name if suspect_name else "Unnamed Suspect"
                    res = agent.evaluate_suspect(
                        name=name_str,
                        behavior=behaviors,
                        mo_suspected=behaviors,
                        personality_notes="Observed via profiling dashboard."
                    )
                    st.session_state.evals_left -= 1
                    
                    st.session_state.latest_results = {
                        "name": name_str,
                        "age": age,
                        "behaviors": behaviors,
                        "tendency_score": res.get("tendency_score", "0%"),
                        "risk_level": res.get("risk_level", "UNKNOWN"),
                        "matched_cases": res.get("similar_cases", []),
                        "summary_text": res.get("summary", "")
                    }
                except Exception as err:
                    st.error(f"Analysis failed: {err}")

    # Render Stored Results
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

        pdf_bytes = generate_pdf_report(
            res["name"],
            res["age"],
            res["tendency_score"],
            res["risk_level"],
            res["behaviors"],
            res["matched_cases"]
        )

        st.download_button(
            label="📥 Download Executive PDF Report",
            data=pdf_bytes,
            file_name=f"Profile_Report_{res['name'].replace(' ', '_')}.pdf",
            mime="application/pdf",
            use_container_width=True
        ) 