from dataclasses import dataclass

from backend.config import data_directory
from backend.services.document_service import DocumentService
from backend.services.project_service import ProjectService
from backend.services.qa_service import QAService
from backend.services.settings_service import SettingsService
from backend.storage.database import Database
from backend.storage.files import FileStore
from backend.storage.vector_store import VectorStore


@dataclass
class Application:
    projects: ProjectService
    documents: DocumentService
    qa: QAService
    settings: SettingsService
    data_path: str


def create_application(root=None, keys=None, provider_factory=None):
    root = root if root is not None else data_directory()
    db = Database(root)
    settings = SettingsService(root, db, keys, provider_factory)
    vectors = VectorStore(root)
    return Application(
        ProjectService(db),
        DocumentService(root, db, FileStore(root), vectors, settings),
        QAService(root, db, vectors, settings),
        settings,
        str(root),
    )
