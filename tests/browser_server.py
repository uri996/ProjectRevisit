"""Offline E2E server. Never used by the production launcher.

The supervisor owns the temporary directory and cleans it after the worker exits,
including on Windows where Chroma holds files open for the worker's lifetime.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def worker(directory):
    import uvicorn
    from conftest import FakeProvider, MemoryKeys

    from backend.api.app import create_api
    from backend.models import AISettings
    from backend.services.application import create_application

    counts = {"llm": 0, "embedding": 0, "fail_next": False}

    class Provider(FakeProvider):
        def embed_documents(self, texts):
            counts["embedding"] += 1
            return super().embed_documents(texts)

        def complete(self, system, payload):
            counts["llm"] += 1
            time.sleep(0.8)
            if counts["fail_next"] and "evidence" in payload:
                counts["fail_next"] = False
                raise RuntimeError("synthetic-private-provider-error")
            return super().complete(system, payload)

    app = create_application(Path(directory), MemoryKeys(), Provider)
    app.settings.save(AISettings(), "synthetic-browser-test-key")
    api = create_api(app, port=18765)
    server = uvicorn.Server(
        uvicorn.Config(
            api,
            host="127.0.0.1",
            port=18765,
            access_log=False,
            use_colors=False,
            log_level="warning",
        )
    )

    @api.get("/__test__/counts")
    def counters():
        return counts

    @api.post("/__test__/fail-next")
    def fail_next():
        counts["fail_next"] = True
        return {"status": "ok"}

    @api.post("/__test__/long-history/{project_id}")
    def long_history(project_id: str):
        for i in range(40):
            app.qa.db.add_message(
                project_id, "user", f"虚构复盘问题 {i}：" + "目录编号与分类校验。" * 20
            )
            app.qa.db.add_message(
                project_id, "assistant", "虚构的长回答，仅用于测试滚动布局。" * 30
            )
        return {"status": "ok"}

    @api.post("/__test__/stop")
    def stop():
        server.should_exit = True
        return {"status": "ok"}

    # Keep the production SPA fallback after these test-only routes.
    fallback = next(route for route in api.router.routes if route.path == "/{path:path}")
    api.router.routes.remove(fallback)
    api.router.routes.append(fallback)
    server.run()


if __name__ == "__main__":
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
    else:
        with tempfile.TemporaryDirectory(prefix="projectrevisit-browser-") as directory:
            process = subprocess.Popen(
                [sys.executable, __file__, "--worker", directory],
                env=dict(os.environ, PROJECT_RAG_DATA_DIR=directory),
            )
            try:
                process.wait()
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
