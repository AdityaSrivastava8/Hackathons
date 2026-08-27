import streamlit as st
import json
import os
from agent.analyzer import DetectiveAgent

st.set_page_config(page_title="Detective AI Navigator", layout="wide")
st.title("🕵️‍♂️ Detective AI: Criminal Pattern & Suspect Profiler")

agent = DetectiveAgent()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Suspect Profile Input")
    suspect_name = st.text_input("Suspect Name / Alias", "John Doe")
    behavior = st.text_area("Observed Behaviors & Traits", "Deceitful, targeted vulnerable individuals, financial gain motive")
    mo = st.text_area("Suspected Modus Operandi", "Laced drinks or food with toxic substance")
    personality = st.text_input("Personality Notes", "Lack of empathy, narcissism, deceitfulness")
    
    analyze_btn = st.button("Analyze Criminal Tendencies")

with col2:
    st.subheader("Analysis & Pattern Match Results")
    if analyze_btn:
        with st.spinner("Searching global database for case matches..."):
            result = agent.evaluate_suspect(suspect_name, behavior, mo, personality)
            
            st.metric("Criminal Tendency Score", result["tendency_score"], delta=result["risk_level"])
            st.write(f"*Assessment:* {result['summary']}")
            
            st.markdown("### Top Matched Historical Cases")
            for match in result["similar_cases"]:
                with st.expander(f"Case: {match['metadata']['title']} ({match['metadata']['case_id']})"):
                    st.write(f"*Location:* {match['metadata']['location']}")
                    st.write(f"*Crime Type:* {match['metadata']['crime_type']}")
                    st.write(f"*Pattern Match Snippet:* {match['snippet']}")

                    