def retrieve(vectors, documents, project_id, query_vector, settings):
    matches = []
    for document in documents:
        for chunk, distance in vectors.search(
            document["collection"], project_id, query_vector, settings.top_k
        ):
            metadata = chunk.metadata
            # Enforce scope twice, even if vector store filtering regresses.
            if (
                metadata.get("project_id") != project_id
                or metadata.get("document_id") != document["id"]
                or distance > settings.max_distance
            ):
                continue
            matches.append(
                dict(
                    source=metadata["source"],
                    chunk_id=metadata["chunk_id"],
                    document_id=document["id"],
                    heading=metadata.get("heading", ""),
                    text=chunk.page_content,
                    distance=float(distance),
                )
            )
    return sorted(matches, key=lambda item: item["distance"])[: settings.top_k]
