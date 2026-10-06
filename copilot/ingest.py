"""STEP 3 — Embed the docs/ corpus and store it in Postgres (pgvector).

What this does, in order:
1. Chunk docs/*.md into ~500-char titled pieces (copilot/chunk_docs.py).
2. Encode every chunk with the LOCAL model `all-MiniLM-L6-v2`
   -> a 384-number "fingerprint" per chunk (numpy vector).
3. Create table rag_documents(id, title, content, embedding vector(384)).
4. Insert all chunks + vectors, print the final stored count.

Run: ./venv/Scripts/python.exe copilot/ingest.py
"""

from sqlalchemy import text

from copilot.chunk_docs import build_corpus
from copilot.db import get_engine

MODEL_NAME = "all-MiniLM-L6-v2"


def main() -> None:
    chunks = build_corpus()
    print(f"Chunked {len(chunks)} pieces from docs/")

    # Lazy import: importing sentence_transformers pulls in torch (slow).
    from sentence_transformers import SentenceTransformer

    print(f"Loading local model {MODEL_NAME} (downloads once on first run)...")
    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        [c["content"] for c in chunks],
        normalize_embeddings=True,  # cosine similarity via pgvector <=>
    )
    print(f"Encoded {len(embeddings)} vectors of dim {embeddings.shape[1]}")

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS rag_documents"))
        conn.execute(text(
            "CREATE TABLE rag_documents ("
            "id integer PRIMARY KEY,"
            "title text NOT NULL,"
            "content text NOT NULL,"
            "embedding vector(384) NOT NULL)"
        ))
        for c, emb in zip(chunks, embeddings):
            vec = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
            conn.execute(
                text(
                    "INSERT INTO rag_documents (id, title, content, embedding) "
                    "VALUES (:id, :title, :content, CAST(:emb AS vector))"
                ),
                {"id": c["chunk_id"], "title": c["label"],
                 "content": c["content"], "emb": vec},
            )

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM rag_documents")).scalar()
    print(f"Stored chunks in rag_documents: {count}")


if __name__ == "__main__":
    main()
