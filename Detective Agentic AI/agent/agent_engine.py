def generate_agent_response(query, ast_results, rag_results):
    """Synthesizes AST parser data and RAG content results into an AI agent report."""
    if not ast_results and not rag_results:
        return f"🕵️‍♂️ *Detective Agent:* I searched the codebase for *'{query}'*, but found no structural definitions or matching code snippets."
    
    report = [f"🕵️‍♂️ *Detective Agent Analysis for:* {query}\n"]
    
    if ast_results:
        report.append("### 🧩 Code Structure Summary")
        for res in ast_results:
            report.append(f"- *Type:* {res['type'].upper()} | *Details:* {res['details']}\n  - *File:* {res['path']}")
    
    if rag_results:
        report.append("\n### 📄 Relevant Code Snippets")
        for res in rag_results:
            report.append(f"- *File:* {res['path']}\n  - Context: {res['snippet']}")
            
    report.append("\n---\n💡 *Insight:* The query matches your core codebase logic. You can navigate directly to the paths specified above.")
    return "\n".join(report)