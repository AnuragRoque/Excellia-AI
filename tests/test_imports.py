"""Architecture smoke tests: the package imports, and core stays pure."""

import ast
import pathlib

import excellia
from excellia.core import Flag, Issue, Profile, ReconcileResult

CORE_DIR = pathlib.Path(excellia.__file__).parent / "core"
FORBIDDEN_IN_CORE = {"fastapi", "flask", "mcp", "requests", "uvicorn", "httpx"}


def test_version():
    assert excellia.__version__


def test_models_importable():
    assert Issue and Flag and Profile and ReconcileResult


def test_core_never_imports_outer_layers():
    """core/ must not import HTTP frameworks or the MCP SDK, and must
    never import from api/, mcp_server/, or local_agent/."""
    for py in CORE_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                assert root not in FORBIDDEN_IN_CORE, f"{py.name} imports {name}"
                if root == "excellia":
                    assert name.startswith("excellia.core"), (
                        f"{py.name} imports outer layer: {name}"
                    )
