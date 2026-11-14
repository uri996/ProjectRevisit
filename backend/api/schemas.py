from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateProject(Contract):
    name: str = Field(min_length=1, max_length=100)


class Project(Contract):
    id: str
    name: str
    created_at: str
    document_count: int
    indexed_count: int


class Operation(Contract):
    request_id: UUID
    confirmed: StrictBool = False


class Question(Operation):
    question: str = Field(min_length=1, max_length=8000)


class GenerateQuestions(Operation):
    description: str = Field(min_length=1, max_length=8000)
    target_role: str = Field(min_length=1, max_length=100)


class Settings(Contract):
    provider: str
    base_url: str = Field(max_length=2048)
    llm_model: str = Field(min_length=1, max_length=200)
    embedding_model: str = Field(min_length=1, max_length=200)
    dimensions: int = Field(ge=1, le=4096)
    chunk_size: int = Field(ge=200, le=4000)
    chunk_overlap: int = Field(ge=0, le=3999)
    top_k: int = Field(ge=1, le=10)
    history_messages: int = Field(ge=0, le=20)
    history_chars: int = Field(ge=0, le=20000)
    max_distance: float = Field(ge=0, le=2)


class SaveSettings(Contract):
    settings: Settings
    api_key: SecretStr = SecretStr("")
    confirmed: StrictBool = False


class SettingsView(Contract):
    settings: Settings
    key_status: str
    warning: str | None = None


class DocumentView(BaseModel):
    # Intentionally omit private disk paths, hashes, and vector collection names.
    id: str
    project_id: str
    name: str
    status: str
    error: str
    chunk_count: int
    index_config: str | None
    created_at: str


class UploadResult(Contract):
    document_id: str
    action: Literal["created", "updated", "duplicate"]


class IndexResult(Contract):
    document_id: str
    chunk_count: int
    status: str


class Citation(BaseModel):
    source: str
    chunk_id: str
    document_id: str
    heading: str
    text: str
    distance: float
    cited: bool = False
    reference: int | None = None
    analysis_basis: bool = False
    supporting_quotes: list[str] = Field(default_factory=list)


class Message(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    status: str
    citations: list[Citation]


class Answer(Contract):
    answer: str
    citations: list[Citation]
    status: str


class RecommendedQuestion(Contract):
    question: str
    direction: str
    reason: str


class SavedQuestions(Contract):
    project_id: str
    description: str
    target_role: str
    questions: list[RecommendedQuestion]
    updated_at: str
