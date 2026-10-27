from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter


def split_document(text, project_id, document_id, source, settings, generation):
    if source.lower().endswith(".md"):
        sections = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        ).split_text(text)
    else:
        sections = [Document(page_content=text)]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "。", "；", " ", ""],
    )
    chunks = splitter.split_documents(sections)
    for i, chunk in enumerate(chunks):
        heading = " / ".join(
            chunk.metadata.get(k, "") for k in ("h1", "h2", "h3") if chunk.metadata.get(k)
        )
        chunk.metadata = dict(
            project_id=project_id,
            document_id=document_id,
            source=source,
            chunk_id=f"{document_id}:{generation}:{i}",
            heading=heading,
        )
    return chunks
