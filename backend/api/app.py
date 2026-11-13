import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api.operations import Operations
from backend.api.schemas import (
    Answer,
    CreateProject,
    DocumentView,
    GenerateQuestions,
    IndexResult,
    Message,
    Operation,
    Project,
    Question,
    SavedQuestions,
    SaveSettings,
    SettingsView,
    UploadResult,
)
from backend.api.security import RequestSizeLimit
from backend.models import AISettings, AppError
from backend.services.application import create_application
from backend.services.recommendation_service import PRESET_QUESTIONS
from backend.storage.files import MAX_BYTES

ROOT = Path(__file__).resolve().parents[2]


def create_api(application=None, frontend=None, port=None):
    port = port or int(os.environ.get("PROJECT_REVISIT_PORT", "8765"))
    origins = [f"http://{host}:{p}" for host in ("127.0.0.1", "localhost") for p in (port, 5173)]
    dist = Path(frontend) if frontend is not None else ROOT / "frontend" / "dist"
    operations = Operations()

    @asynccontextmanager
    async def lifespan(api):
        # No data or keyring access merely by importing this module.
        api.state.services = application or create_application()
        yield

    api = FastAPI(title="ProjectRevisit", lifespan=lifespan, docs_url=None, redoc_url=None)
    api.add_middleware(RequestSizeLimit)
    api.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @api.middleware("http")
    async def local_boundary(request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if (origin and origin not in origins) or request.headers.get(
                "sec-fetch-site"
            ) == "cross-site":
                return JSONResponse({"error": "仅允许本机应用页面访问接口。"}, status_code=403)
            if request.method not in ("GET", "HEAD", "OPTIONS") and origin not in origins:
                return JSONResponse({"error": "写入操作必须来自本机应用页面。"}, status_code=403)
            try:
                if int(request.headers.get("content-length", "0")) > 12 * 1024 * 1024:
                    return JSONResponse({"error": "请求超过 12 MB 限制。"}, status_code=413)
            except ValueError:
                return JSONResponse({"error": "无效的请求长度。"}, status_code=400)
        try:
            response = await call_next(request)
        except Exception:
            return JSONResponse(
                {"error": "操作失败，资料已保留。请检查本机权限或依赖后重试。"}, status_code=500
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @api.exception_handler(AppError)
    async def business_error(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @api.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @api.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never echo invalid input: a malformed settings request may contain a key.
        return JSONResponse({"error": "请求格式或参数无效，请检查输入。"}, status_code=422)

    def services():
        return api.state.services

    def consent(body):
        if not body.confirmed:
            raise HTTPException(400, "请明确确认此操作及可能产生的 API 费用。")

    @api.get("/api/health")
    def health():
        return {"status": "ok"}

    @api.get("/api/projects", response_model=list[Project])
    def projects():
        return services().projects.list()

    @api.post("/api/projects", response_model=Project, status_code=201)
    def create_project(body: CreateProject):
        project_id = services().projects.create(body.name)
        return next(p for p in services().projects.list() if p["id"] == project_id)

    @api.get("/api/projects/{project_id}/documents", response_model=list[DocumentView])
    def documents(project_id: UUID):
        return services().documents.list(str(project_id))

    @api.post("/api/projects/{project_id}/documents", response_model=UploadResult)
    async def upload(project_id: UUID, file: UploadFile):
        try:
            content = await file.read(MAX_BYTES + 1)
            return await run_in_threadpool(
                services().documents.upload, str(project_id), file.filename or "", content
            )
        finally:
            await file.close()

    @api.post(
        "/api/projects/{project_id}/documents/{document_id}/index", response_model=IndexResult
    )
    def index(project_id: UUID, document_id: UUID, body: Operation):
        consent(body)
        return operations.run(
            str(project_id),
            body.request_id,
            lambda: services().documents.index(str(project_id), str(document_id), confirmed=True),
        )

    @api.get("/api/projects/{project_id}/messages", response_model=list[Message])
    def messages(project_id: UUID):
        return services().qa.history(str(project_id))

    @api.post("/api/projects/{project_id}/questions", response_model=Answer)
    def question(project_id: UUID, body: Question):
        consent(body)
        return operations.run(
            str(project_id),
            body.request_id,
            lambda: services().qa.ask(str(project_id), body.question),
        )

    @api.delete("/api/projects/{project_id}/messages")
    def clear(project_id: UUID, body: Operation):
        if not body.confirmed:
            raise HTTPException(400, "清空聊天需要确认。")
        operations.run(
            str(project_id),
            body.request_id,
            lambda: services().qa.clear(str(project_id), confirmed=True),
        )
        return {"status": "ok"}

    @api.get("/api/recommendations/presets", response_model=dict[str, list[str]])
    def presets():
        return PRESET_QUESTIONS

    @api.get("/api/projects/{project_id}/recommendations", response_model=SavedQuestions | None)
    def recommendations(project_id: UUID):
        return services().recommendations.load(str(project_id))

    @api.post("/api/projects/{project_id}/recommendations", response_model=SavedQuestions)
    def generate(project_id: UUID, body: GenerateQuestions):
        consent(body)
        return operations.run(
            str(project_id),
            body.request_id,
            lambda: services().recommendations.generate(
                str(project_id), body.description, body.target_role, confirmed=True
            ),
        )

    @api.get("/api/settings", response_model=SettingsView)
    def settings():
        warning = None
        try:
            current = services().settings.load()
        except AppError:
            current = AISettings()
            warning = "本地配置无效，已显示默认值供修复；保存前不会覆盖原配置。"
        return {
            "settings": current.to_dict(),
            "key_status": services().settings.key_status(current),
            "warning": warning,
        }

    @api.put("/api/settings", response_model=SettingsView)
    def save_settings(body: SaveSettings):
        consent(body)
        services().settings.save(
            AISettings(**body.settings.model_dump()), body.api_key.get_secret_value().strip()
        )
        return settings()

    @api.post("/api/settings/test")
    def connection_test(body: Operation):
        consent(body)
        return {
            "message": operations.run(
                "settings",
                body.request_id,
                lambda: services().settings.test_connection(confirmed=True),
            )
        }

    @api.get("/api/settings/data-location")
    def data_location():
        return {"path": services().data_path}

    @api.get("/{path:path}", include_in_schema=False)
    def frontend_file(path: str):
        if path.startswith("api/") or path == "api":
            raise HTTPException(404, "接口不存在。")
        resolved = (dist / path).resolve()
        if dist.resolve() not in resolved.parents and resolved != dist.resolve():
            raise HTTPException(404, "页面不存在。")
        if resolved.is_file():
            return FileResponse(resolved)
        if "." in Path(path).name:
            raise HTTPException(404, "资源不存在。")
        if not (dist / "index.html").is_file():
            raise HTTPException(
                503, "前端尚未构建，请在 frontend 目录执行 npm install 和 npm run build。"
            )
        return FileResponse(dist / "index.html")

    return api
