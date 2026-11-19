"""Check the maintained architecture without starting services or touching private data."""

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_backend_dependency_direction_and_single_ui():
    for path in (ROOT / "backend").rglob("*.py"):
        for module in imports(path):
            assert module.split(".")[0] not in {"ui", "streamlit", "frontend"}, path
            if "api" not in path.relative_to(ROOT / "backend").parts:
                assert not module.startswith(("fastapi", "backend.api")), path
            else:
                assert not module.startswith(("backend.storage", "backend.rag")), path
            if path.parent.name == "storage":
                assert not module.startswith(("backend.services", "backend.rag")), path
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["tool"]["setuptools"]["packages"]["find"]["include"] == ["backend*"]
    assert not any(
        "streamlit" in dependency.lower() for dependency in project["project"]["dependencies"]
    )


def test_settings_view_is_service_owned_and_does_not_rewrite_corrupt_config(configured):
    app, *_ = configured
    app.settings.path.write_text("synthetic invalid JSON", encoding="utf-8")
    view = app.settings.view()
    assert view["warning"] and "api_key" not in view["settings"]
    assert app.settings.path.read_text(encoding="utf-8") == "synthetic invalid JSON"
