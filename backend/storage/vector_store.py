from uuid import uuid4


class VectorStore:
    def __init__(self, root):
        self.path = str(root / "chroma")

    def _open(self, name, embeddings=None, create=False):
        # Heavy optional initialization stays out of app startup.
        from chromadb.config import Settings
        from langchain_chroma import Chroma

        return Chroma(
            collection_name=name,
            persist_directory=self.path,
            embedding_function=embeddings,
            collection_metadata={"hnsw:space": "cosine"},
            client_settings=Settings(anonymized_telemetry=False),
            create_collection_if_not_exists=create,
        )

    def stage(self, project_id, chunks, embeddings):
        name = f"p_{project_id.replace('-', '')}_{uuid4().hex}"
        store = self._open(name, embeddings, create=True)
        try:
            # Stage in manageable batches. SQLite never points at partially written generations.
            for offset in range(0, len(chunks), 50):
                batch = chunks[offset : offset + 50]
                store.add_documents(batch, ids=[c.metadata["chunk_id"] for c in batch])
            actual = store.get(include=[])["ids"]
            if len(actual) != len(chunks):
                raise ValueError("Incomplete index")
        except Exception:
            try:
                store.delete_collection()
            except Exception:
                pass
            raise
        return name

    def search(self, collection, project_id, vector, k):
        return self._open(collection).similarity_search_by_vector_with_relevance_scores(
            vector,
            k=k,
            filter={"project_id": project_id},
        )

    def delete(self, collection):
        self._open(collection).delete_collection()
