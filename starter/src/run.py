"""Suggested pipeline entry point; orchestrates ingestion, chunking, embedding, storage, and evaluation."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .models import Chunk, DocumentPage
from .store import PgVectorStore

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _build_strategy_chunks(pages: list[DocumentPage], strategy: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        if strategy == "A_fixed":
            chunks.extend(fixed_size(page, size=500, overlap=80))
        elif strategy in {"B_paragraph", "C_paragraph_filter"}:
            chunks.extend(by_paragraph(page, max_size=400))
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    return chunks


def main() -> None:
    """Run the default retrieval pipeline against the local corpus and benchmark."""
    base_dir = Path(__file__).resolve().parents[1]
    corpus_path = base_dir / "data" / "corpus.json"
    benchmark_path = base_dir / "data" / "benchmark.json"
    results_dir = base_dir / "results"
    results_dir.mkdir(exist_ok=True)

    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")
    if not benchmark_path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {benchmark_path}")

    with benchmark_path.open("r", encoding="utf-8") as handle:
        benchmark = json.load(handle)
    with corpus_path.open("r", encoding="utf-8") as handle:
        corpus = json.load(handle)

    pages: list[DocumentPage] = []
    for item in corpus.get("pages", []):
        pages.append(
            DocumentPage(
                document_id=corpus.get("document_id", "demo_document"),
                source=corpus.get("source", "demo_source"),
                page=int(item["page"]),
                text=item["text"],
                metadata={k: v for k, v in item.items() if k not in {"page", "text"}},
            )
        )

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL is missing. Copy starter/.env.example to starter/.env and set the DB URL.")

    model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedder = MyEmbedder(model_name)

    strategies = ["A_fixed", "B_paragraph", "C_paragraph_filter"]
    all_traces: list[dict[str, object]] = []

    for strategy in strategies:
        chunks = _build_strategy_chunks(pages, strategy)
        if not chunks:
            continue
        vectors = embedder.embed_documents([chunk.text for chunk in chunks])
        store = PgVectorStore(database_url, dimensions=len(vectors[0]))
        store.create_schema()
        store.upsert(strategy, chunks, vectors)

        for question in benchmark["questions"]:
            query_vector = embedder.embed_query(question["question"])
            filters = question.get("filter") if strategy == "C_paragraph_filter" else None
            hits = store.search(strategy, query_vector, top_k=3, filters=filters)
            result = evaluate_query(question, hits)
            trace = {
                "strategy": strategy,
                "split": question["split"],
                "question_id": question["id"],
                "question": question["question"],
                "filter": filters,
                "result": result,
                "top_hits": hits,
            }
            all_traces.append(trace)

    summary = summarize(
        [{"strategy": trace["strategy"], "split": trace["split"], "result": trace["result"]} for trace in all_traces]
    )

    (results_dir / "trace_top3.json").write_text(json.dumps(all_traces, ensure_ascii=False, indent=2), encoding="utf-8")
    (results_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
