import re
import subprocess
import tempfile
from pathlib import Path


def test_gitignore_private_data_and_public_source():
    root = Path(__file__).resolve().parents[1]
    protected = [
        "AGENTS.md",
        "ui/AGENTS.md",
        "examples/AGENTS.md",
        "nested/deeper/AGENTS.md",
        ".env",
        ".env.local",
        "notes.md",
        "notes.txt",
        "metadata.sqlite3",
        "metadata.sqlite3-wal",
        "metadata.db",
        "chroma/index.bin",
        "uploads/private.md",
        "settings.json",
        "settings.json.tmp",
        "settings.json.lock",
        ".venv/pyvenv.cfg",
        ".tools/runtime.exe",
        ".cache/raw-data",
        ".pytest_cache/cache.json",
        ".ruff_cache/cache.bin",
        "logs/private.log",
        "test-results/report.txt",
        "private/data.json",
        "data/private.json",
        "originals/revision.utf8",
        "chunks/chunk.json",
        "chunk_cache/text.json",
        "chat_history/messages.json",
        "conversations/messages.json",
        "runtime/session.json",
        "export.jsonl",
        "vectors.npy",
        "vectors.npz",
        "cache.pkl",
        "cache.pickle",
        ".streamlit/secrets.toml",
        "backend/__pycache__/models.pyc",
        "project_rag_assistant.egg-info/PKG-INFO",
        "examples/personal_notes.md",
        "examples/new_sample.txt",
        "private/README.md",
        "private/.env.example",
        "docs/DELIVERY.md",
        "docs/new-note.txt",
        "docs/new-note.json",
        "docs/new-script.py",
        "docs/nested/future.toml",
        "docs/README.md",
        "docs/AGENTS.md",
        "docs/.env.example",
        "docs/examples/demo_project_alpha.md",
    ]
    public = [
        "backend/models.py",
        "ui/app.py",
        "tests/test_privacy.py",
        "scripts/smoke_runtime.py",
        "README.md",
        "examples/demo_project_alpha.md",
        "examples/demo_project_beta.md",
        ".env.example",
        ".gitignore",
        "pyproject.toml",
        "requirements-lock.txt",
        ".streamlit/config.toml",
        "start.bat",
    ]
    # Only this newly created, disposable directory is initialized as a Git repository.
    with tempfile.TemporaryDirectory(prefix="rag-ignore-check-") as directory:
        temporary = Path(directory)
        (temporary / ".gitignore").write_bytes((root / ".gitignore").read_bytes())
        subprocess.run(["git", "init", "--quiet", directory], check=True, capture_output=True)
        for relative in protected + public:
            path = temporary / relative
            if relative == ".gitignore":
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Synthetic privacy test data only.", encoding="utf-8")
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.excludesFile=NUL",
                "-C",
                directory,
                "check-ignore",
                "--no-index",
                "--stdin",
                "-z",
            ],
            input=("\0".join(protected + public) + "\0").encode("utf-8"),
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
        assert set(result.stdout.decode("utf-8").rstrip("\0").split("\0")) == set(protected)


def test_public_files_do_not_link_internal_records():
    root = Path(__file__).resolve().parents[1]
    candidates = [
        root / "README.md",
        root / ".env.example",
        root / "pyproject.toml",
        root / "requirements-lock.txt",
        root / "start.bat",
    ]
    for folder in ("backend", "ui", "tests", "examples", "scripts", ".streamlit"):
        candidates.extend(
            path
            for path in (root / folder).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
    internal_link = re.compile(
        r"(?:\]\(\s*<?|^\s*\[[^\]]+\]:\s*<?)(?:\.\.?/|/)*docs[/\\]",
        re.IGNORECASE | re.MULTILINE,
    )
    for path in candidates:
        assert not internal_link.search(path.read_text(encoding="utf-8-sig")), path.name
