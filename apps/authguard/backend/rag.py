from __future__ import annotations

from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class PolicyRAG:
    def __init__(self, knowledge_dir: str | Path | None = None) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.knowledge_dir = Path(knowledge_dir or project_root / "data" / "knowledge")
        self.documents: list[dict[str, str]] = []
        self._load()

    def _load(self) -> None:
        self.documents.clear()
        for path in sorted(self.knowledge_dir.glob("*.txt")):
            text = path.read_text(encoding="utf-8")
            chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
            for index, chunk in enumerate(chunks):
                self.documents.append({
                    "source": path.name,
                    "chunk_id": f"{path.stem}-{index + 1}",
                    "text": chunk,
                })
        corpus = [item["text"] for item in self.documents] or ["No policy documents loaded."]
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self.matrix = self.vectorizer.fit_transform(corpus)

    def retrieve(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        if not self.documents:
            return []
        query_vector = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vector, self.matrix)[0]
        ranked = scores.argsort()[::-1][:top_k]
        results: list[dict[str, Any]] = []
        for index in ranked:
            if scores[index] <= 0:
                continue
            row = dict(self.documents[int(index)])
            row["score"] = round(float(scores[index]), 4)
            results.append(row)
        return results
