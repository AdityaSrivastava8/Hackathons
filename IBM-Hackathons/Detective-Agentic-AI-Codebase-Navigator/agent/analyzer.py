import sys
import os

# 1. Update system path FIRST so Python can locate internal modules on Streamlit Cloud
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st
import json
import pandas as pd
from fpdf import FPDF
from agent.analyzer import DetectiveAgent

# Initialize Detective Agent
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
        # Save to cases directory
        cases_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cases"))
        os.makedirs(cases_dir, exist_ok=True)
        save_path = os.path.join(cases_dir, uploaded_file.name)
        
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(case_data, f, indent=4)
            
        st.sidebar.success(f"Successfully uploaded & indexed '{uploaded_file.name}'!")
    except Exception as e:
        st.sidebar.error(f"Failed to upload case JSON: {e}")

st.sidebar.divider()
st.sidebar.markdown("### B2B Agency Plan")
st.sidebar.info("**Current Tier:** Pro Agency Trial\n\n**Evaluations Remaining:** 25/25")

# Main Profiling Form
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Suspect Information & Observations")
    suspect_name = st.text_input("Suspect Name / Alias", placeholder="John Doe")
    age = st.text_input("Age", placeholder="34")
    behaviors = st.text_area(
        "Observed Behaviors, MO, & Traits",
        height=180,
        placeholder="Entering residential premises during late hours, targeting locked cabinets, using toxic chemicals..."
    )
    analyze_btn = st.button("Run Intelligence Analysis", type="primary", use_container_width=True)

with col2:
    st.subheader("Analysis & Precedent Results")
    
    if analyze_btn and behaviors.strip():
        with st.spinner("Analyzing traits against ChromaDB precedent vectors..."):
            try:
                # Call agent's evaluate_suspect with required arguments
                name_str = suspect_name if suspect_name else "Unnamed Suspect"
                results = agent.evaluate_suspect(
                    name=name_str,
                    behavior=behaviors,
                    mo_suspected=behaviors,
                    personality_notes="Observed via profiling dashboard."
                )
                
                tendency_score = results.get("tendency_score", "0%")
                risk_level = results.get("risk_level", "UNKNOWN")
                matched_cases = results.get("similar_cases", [])
                summary_text = results.get("summary", "")

                # Display Risk Indicators
                m_col1, m_col2 = st.columns(2)
                m_col1.metric("Tendency Score", str(tendency_score))
                m_col2.metric("Risk Level", risk_level)

                st.info(summary_text)

                st.markdown("#### Matched Precedents")
                if matched_cases:
                    for case in matched_cases:
                        with st.expander(f"📌 {case.get('case_title', 'Historical Precedent')} ({case.get('location', 'Global')})"):
                            st.write(f"**Case ID:** {case.get('case_id', 'N/A')}")
                            st.write(f"**Details:** {case.get('summary', case.get('snippet', 'No detailed snippet available.'))}")
                else:
                    st.info("No close precedent matches found above threshold.")

                # PDF Download Button
                pdf_bytes = generate_pdf_report(
                    name_str,
                    age,
                    tendency_score,
                    risk_level,
                    behaviors,
                    matched_cases
                )

                st.download_button(
                    label="📥 Download Executive PDF Report",
                    data=pdf_bytes,
                    file_name=f"Profile_Report_{name_str.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as err:
                st.error(f"Analysis failed: {err}")
    elif analyze_btn:
        st.warning("Please enter observed behaviors to analyze.") 