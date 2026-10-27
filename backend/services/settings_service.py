import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout

from backend.models import AISettings, AppError
from backend.rag.provider import BailianProvider


class SecureKeys:
    SERVICE = "ProjectRAGAssistant.v0.1"

    def _backend(self):
        import keyring

        backend = keyring.get_keyring()
        # Explicit OS implementations only: no plaintext, null, or third-party fallback.
        if not type(backend).__module__.startswith(
            ("keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService")
        ):
            raise AppError("当前系统没有受支持的安全凭据存储，密钥不会保存为明文。")
        return backend

    def get(self, account):
        try:
            return self._backend().get_password(self.SERVICE, account)
        except Exception:
            raise AppError("无法读取操作系统安全凭据；仍可使用项目管理与历史记录。") from None

    def set(self, account, key):
        try:
            self._backend().set_password(self.SERVICE, account, key)
        except Exception:
            raise AppError("无法保存到操作系统安全凭据，未进行明文保存。") from None


class SettingsService:
    def __init__(self, root, db, keys=None, provider_factory=None):
        self.path = root / "settings.json"
        self.db = db
        self.keys = keys if keys is not None else SecureKeys()
        self.provider_factory = provider_factory or BailianProvider

    def load(self):
        if not self.path.exists():
            return AISettings()
        try:
            settings = AISettings(**json.loads(self.path.read_text(encoding="utf-8")))
            settings.validate()
            return settings
        except Exception:
            raise AppError("本地 AI 配置无效。请在设置页面重新保存。") from None

    @staticmethod
    def account(settings):
        return hashlib.sha256(settings.base_url.rstrip("/").encode()).hexdigest()

    def key_status(self, settings):
        try:
            return "已保存" if self.keys.get(self.account(settings)) else "未配置"
        except AppError:
            return "安全凭据不可用"

    def save(self, settings, key=""):
        try:
            with FileLock(str(self.path) + ".lock", timeout=0):
                self._save(settings, key)
        except Timeout:
            raise AppError("其他窗口正在保存设置，请稍后重试。") from None

    def _save(self, settings, key):
        settings.validate()
        if key:
            self.keys.set(self.account(settings), key)
        temp = Path(str(self.path) + ".tmp")
        temp.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp.replace(self.path)
        # Preserve actual model + dimensions per document; do not delete old collections.
        self.db.execute(
            "UPDATE documents SET status='needs_reindex' WHERE collection IS NOT NULL AND signature != ?",
            (settings.signature,),
        )

    @contextmanager
    def provider(self, settings=None):
        settings = settings or self.load()
        settings.validate()
        key = self.keys.get(self.account(settings))
        if not key:
            raise AppError("请先在 AI 设置中保存此目标地址的 API Key。")
        provider = self.provider_factory(settings, key)
        try:
            yield provider
        finally:
            close = getattr(provider, "close", None)
            if close:
                close()

    def test_connection(self, confirmed=False):
        if not confirmed:
            raise AppError("请确认连接测试会向已保存的地址发送合成文本并可能产生费用。")
        with self.provider() as provider:
            provider.embed_query("Synthetic connection test; no private project data.")
            result = provider.complete(
                'Return JSON: {"ok": true}',
                {"test": "Synthetic connection test"},
            )
            if result.get("ok") is not True:
                raise AppError("LLM 测试未返回预期结果；Embedding 请求已完成。")
        return "Embedding 与 LLM 连接测试均成功（仅合成文本）。"
