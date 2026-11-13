import argparse
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description="ProjectRevisit local Vue + FastAPI application")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--api-only", action="store_true", help="Development API for Vite")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    if not args.api_only and not (ROOT / "frontend/dist/index.html").is_file():
        print("Frontend build missing. In frontend run: npm install, then npm run build.")
        return 1
    os.chdir(ROOT)
    os.environ["NO_COLOR"] = "1"
    os.environ["TERM"] = "dumb"
    os.environ["CLICOLOR"] = "0"
    os.environ.pop("FORCE_COLOR", None)
    os.environ.pop("CLICOLOR_FORCE", None)
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    import uvicorn

    from backend.api.app import create_api

    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser and not args.api_only:

        def open_when_ready():
            opener = build_opener(ProxyHandler({}))
            for _ in range(100):
                try:
                    with opener.open(url + "/api/health", timeout=0.5) as response:
                        if response.status == 200:
                            webbrowser.open(url)
                            return
                except (URLError, OSError):
                    time.sleep(0.2)

        threading.Thread(target=open_when_ready, daemon=True).start()
    print(f"ProjectRevisit: {url} (local only). Press Ctrl+C to stop.", flush=True)
    try:
        uvicorn.run(
            create_api(port=args.port),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
            use_colors=False,
        )
    except KeyboardInterrupt:
        pass
    except Exception:
        print("Startup failed. Check dependencies, port availability and local data permissions.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
