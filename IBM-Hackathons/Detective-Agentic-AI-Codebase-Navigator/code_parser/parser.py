import ast
import os

def parse_python_file(file_path):
    if not file_path.endswith('.py'):
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        tree = ast.parse(code)
        structure = {"functions": [], "classes": []}
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                structure["functions"].append({
                    "name": node.name,
                    "line": node.lineno
                })
            elif isinstance(node, ast.ClassDef):
                structure["classes"].append({
                    "name": node.name,
                    "line": node.lineno
                })
        return structure
    except Exception:
        return None

def deep_codebase_search(target_dir, search_term):
    results = []
    for root, _, files in os.walk(target_dir):
        for file in files:
            file_path = os.path.join(root, file)
            if search_term.lower() in file.lower():
                results.append({"type": "file", "path": file_path, "details": "Filename match"})
            
            if file.endswith('.py'):
                parsed = parse_python_file(file_path)
                if parsed:
                    for func in parsed["functions"]:
                        if search_term.lower() in func["name"].lower():
                            results.append({"type": "function", "path": file_path, "details": f"Function '{func['name']}' (Line {func['line']})"})
                    for cls in parsed["classes"]:
                        if search_term.lower() in cls["name"].lower():
                            results.append({"type": "class", "path": file_path, "details": f"Class '{cls['name']}' (Line {cls['line']})"})
    return results