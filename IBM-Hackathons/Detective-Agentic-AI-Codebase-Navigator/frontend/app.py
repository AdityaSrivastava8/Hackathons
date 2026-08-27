import streamlit as st
import os
from code_parser.parser import deep_codebase_search
from rag.vector_search import build_simple_rag_index, query_rag_engine
from agent.agent_engine import generate_agent_response

st.set_page_config(page_title="Detective Agentic AI", page_icon="🕵️‍♂️", layout="wide")

st.title("🕵️‍♂️ Detective Agentic AI Codebase Navigator")
st.write("Welcome! Search filenames, functions, classes, or raw code logic across your project.")

query = st.text_input("Enter search query (e.g., function name, class, or keyword):")

if st.button("Run Agentic Search"):
    if query:
        with st.spinner("Agent is analyzing codebase..."):
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            
            # 1. Fetch AST Matches
            ast_matches = deep_codebase_search(project_root, query.strip())
            
            # 2. Fetch RAG Matches
            docs = build_simple_rag_index(project_root)
            rag_matches = query_rag_engine(docs, query.strip())
            
            # 3. Generate Agent Synthesis
            agent_output = generate_agent_response(query.strip(), ast_matches, rag_matches)
            
            st.markdown(agent_output)
    else:
        st.warning("Please enter a search query first.")