import ast
import os


def parse_python_file(file_path):
    """
    Parse a Python file and return its basic code structure.

    The existing functions/classes output is preserved because other parts
    of the project may already depend on this structure.

    Additional information:
    - imports are collected so the navigator can understand file dependencies
    - methods are identified through their class name
    """

    # Only Python files are handled by this parser.
    if not file_path.endswith(".py"):
        return None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()

        # Convert source code into a Python Abstract Syntax Tree.
        tree = ast.parse(code, filename=file_path)

        structure = {
            "functions": [],
            "classes": [],
            "imports": [],       # Added: helps understand file dependencies
        }

        # Walk through the complete syntax tree.
        for node in ast.walk(tree):

            # Detect normal functions and class methods.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                structure["functions"].append({
                    "name": node.name,
                    "line": node.lineno,
                    # Added: records the class when this function is a method.
                    "parent_class": None,
                })

            # Detect classes.
            elif isinstance(node, ast.ClassDef):
                structure["classes"].append({
                    "name": node.name,
                    "line": node.lineno,
                })

            # Detect "import module" statements.
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    structure["imports"].append(alias.name)

            # Detect "from module import something" statements.
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    structure["imports"].append(node.module)

        # Build a more accurate parent-class relationship for methods.
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for function in structure["functions"]:
                            if (
                                function["name"] == child.name
                                and function["line"] == child.lineno
                            ):
                                function["parent_class"] = node.name
                                break

        return structure

    # Do not crash the complete codebase scan because one file is invalid.
    # Returning None preserves the previous behaviour while avoiding
    # unnecessary failure of the rest of the project.
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def deep_codebase_search(target_dir, search_term):
    """
    Search a codebase for:
    - matching filenames
    - matching function names
    - matching class names
    - matching imports
    - matching text inside Python source files

    Existing result fields (type/path/details) are preserved so the
    agent engine can continue consuming the results.
    """

    results = []
    search_lower = search_term.lower()

    # Walk through every directory and file under the target directory.
    for root, _, files in os.walk(target_dir):

        for file in files:
            file_path = os.path.join(root, file)

            # Search filenames.
            if search_lower in file.lower():
                results.append({
                    "type": "file",
                    "path": file_path,
                    "details": "Filename match",
                })

            # Parse Python files for structural information.
            if file.endswith(".py"):
                parsed = parse_python_file(file_path)

                if parsed:

                    # Search function names.
                    for func in parsed["functions"]:
                        if search_lower in func["name"].lower():
                            parent = func.get("parent_class")

                            if parent:
                                details = (
                                    f"Method '{func['name']}' "
                                    f"in class '{parent}' "
                                    f"(Line {func['line']})"
                                )
                            else:
                                details = (
                                    f"Function '{func['name']}' "
                                    f"(Line {func['line']})"
                                )

                            results.append({
                                "type": "function",
                                "path": file_path,
                                "details": details,
                            })

                    # Search class names.
                    for cls in parsed["classes"]:
                        if search_lower in cls["name"].lower():
                            results.append({
                                "type": "class",
                                "path": file_path,
                                "details": (
                                    f"Class '{cls['name']}' "
                                    f"(Line {cls['line']})"
                                ),
                            })

                    # Search imported modules.
                    for imported_module in parsed["imports"]:
                        if search_lower in imported_module.lower():
                            results.append({
                                "type": "import",
                                "path": file_path,
                                "details": (
                                    f"Import '{imported_module}'"
                                ),
                            })

                # Search the actual source-code text.
                # This allows the navigator to find logic that isn't part
                # of a function/class/import name.
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source = f.read()

                    if search_lower in source.lower():
                        results.append({
                            "type": "code",
                            "path": file_path,
                            "details": "Code content match",
                        })

                except (UnicodeDecodeError, OSError):
                    # Ignore files that cannot be safely read.
                    continue

    return results 
