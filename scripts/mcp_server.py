import os
from fastmcp import FastMCP

mcp = FastMCP("SmartBugsScanner")

BASE_DATASET_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset"))

@mcp.tool()
def list_contracts() -> str:
    """Recursively lists all .sol files in the dataset subdirectories."""
    sol_files = []
    try:
        if not os.path.exists(BASE_DATASET_PATH):
            return f"ERROR: Dataset path not found at {BASE_DATASET_PATH}"

        for root, dirs, files in os.walk(BASE_DATASET_PATH):
            for file in files:
                if file.endswith(".sol"):
                    absolute_path = os.path.join(root, file)
                    relative_path = os.path.relpath(absolute_path, BASE_DATASET_PATH)
                    sol_files.append(relative_path)
        
        return ",".join(sol_files) if sol_files else ""
    except Exception as e:
        return f"ERROR_LISTING: {str(e)}"

@mcp.tool()
def read_contract(file_relative_path: str) -> str:
    """Reads contract content using its relative path."""
    try:
        # Security: Prevent directory traversal
        safe_filename = os.path.normpath(file_relative_path)
        full_path = os.path.join(BASE_DATASET_PATH, safe_filename)
        
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"ERROR_READING: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")