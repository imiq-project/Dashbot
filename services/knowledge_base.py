"""
RAG-based knowledge base for document search. Loads text files, creates semantic embeddings, and performs similarity search for relevant information.
"""

import numpy as np
from pathlib import Path
from typing import List, Dict, Optional


class KnowledgeBase:

    def __init__(self, knowledge_dir: str, embedder, chunk_size: int = 500,
                 chunk_overlap: int = 50, model_name: str = ""):
        self.knowledge_dir = knowledge_dir
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.model_name = model_name

        self.chunks = []
        self.chunk_embeddings = None

        self._load_documents()

    def _is_bge_model(self) -> bool:
        return "bge" in self.model_name.lower()

    def _load_documents(self):
        knowledge_path = Path(self.knowledge_dir)

        if not knowledge_path.exists():
            print(f"Warning: Knowledge directory not found: {self.knowledge_dir}")
            return

        txt_files = list(knowledge_path.glob("*.txt"))
        if not txt_files:
            print(f"Warning: No .txt files in {self.knowledge_dir}")
            return

        print(f"Loading {len(txt_files)} knowledge documents...")

        for file_path in txt_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                file_chunks = self._chunk_text(content, source=file_path.name)
                self.chunks.extend(file_chunks)
                print(f"   {file_path.name}: {len(file_chunks)} chunks")
            except Exception as e:
                print(f"   {file_path.name}: {e}")

        if self.chunks:
            print(f"Computing knowledge embeddings...")
            chunk_texts = [c["text"] for c in self.chunks]

            self.chunk_embeddings = self.embedder.encode(chunk_texts, normalize_embeddings=True)
            print(f"Knowledge base: {len(self.chunks)} chunks")

    def _chunk_text(self, text: str, source: str) -> List[Dict]:
        chunks = []
        text = text.strip()
        if not text:
            return chunks

        paragraphs = text.split('\n\n')
        current_chunk = ""
        chunk_id = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) > self.chunk_size and current_chunk:
                chunks.append({
                    "text": current_chunk.strip(),
                    "source": source,
                    "chunk_id": chunk_id
                })
                chunk_id += 1

                if self.chunk_overlap > 0:
                    words = current_chunk.split()
                    overlap_words = words[-self.chunk_overlap // 5:]
                    current_chunk = ' '.join(overlap_words) + ' ' + para
                else:
                    current_chunk = para
            else:
                current_chunk = current_chunk + '\n\n' + para if current_chunk else para

        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "source": source,
                "chunk_id": chunk_id
            })

        return chunks

    def search(self, query: str, top_k: int = 3, threshold: float = 0.20) -> List[Dict]:
        if not self.chunks or self.chunk_embeddings is None:
            return []

        if self._is_bge_model():
            query_text = f"Represent this sentence for searching relevant passages: {query}"
        else:
            query_text = query

        query_embedding = self.embedder.encode(query_text, normalize_embeddings=True)

        scores = np.dot(self.chunk_embeddings, query_embedding)

        results = []
        top_indices = np.argsort(scores)[::-1][:top_k]

        for idx in top_indices:
            if scores[idx] >= threshold:
                results.append({
                    "text": self.chunks[idx]["text"],
                    "source": self.chunks[idx]["source"],
                    "score": float(scores[idx])
                })

        return results

    def get_stats(self) -> Dict:
        sources = set(c["source"] for c in self.chunks) if self.chunks else set()
        return {
            "total_chunks": len(self.chunks),
            "total_documents": len(sources),
            "documents": sorted(list(sources))
        }

    def reload(self):
        self.chunks = []
        self.chunk_embeddings = None
        self._load_documents()


if __name__ == "__main__":
    from sentence_transformers import SentenceTransformer

    print("Loading embedding model...")
    embedder = SentenceTransformer('all-MiniLM-L6-v2')

    print("\nInitializing knowledge base...")
    kb = KnowledgeBase("knowledge", embedder, model_name="all-MiniLM-L6-v2")

    stats = kb.get_stats()
    print(f"\nKnowledge Base Stats:")
    print(f"   Total chunks: {stats['total_chunks']}")
    print(f"   Total documents: {stats['total_documents']}")
    print(f"   Documents: {', '.join(stats['documents'])}")

    query = "What is Magdeburg?"
    print(f"\nSearching for: '{query}'")
    results = kb.search(query, top_k=2)

    for i, result in enumerate(results, 1):
        print(f"\n{i}. [{result['source']}] (score: {result['score']:.3f})")
        print(f"   {result['text'][:150]}...")
