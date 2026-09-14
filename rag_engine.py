"""
Amethyst RAG Engine — Retrieval-Augmented Generation
=====================================================
Uses LangChain + ChromaDB + Ollama Embeddings to maintain
a persistent, local vector database of ingested documents.

Key features:
  - Ingests PDFs, text, code, and markdown files
  - Chunks documents intelligently for semantic search
  - Deduplicates re-ingested files automatically
  - Queries top-K relevant chunks for any user prompt
  - Fully offline via Ollama nomic-embed-text
  - Relevance scoring: only injects context above a similarity threshold
"""

import os
import hashlib
import logging
import re
from typing import List, Optional, Tuple

log = logging.getLogger("amethyst.rag")

# Words that indicate the user is making casual chat, not a document query.
# These are checked BEFORE hitting the vector database.
_CASUAL_PATTERNS = re.compile(
    r"^(hi|hey|hello|yo|sup|ok|okay|yes|no|yeah|nah|hm+|lol|lmao|"
    r"what\??|huh\??|why\??|\?\??|thanks?|bye|good|nice|cool|bruh|bro)$",
    re.IGNORECASE
)


class RAGEngine:
    """
    Retrieval-Augmented Generation using LangChain and ChromaDB.
    Maintains a persistent vector database of ingested documents.
    """

    def __init__(self):
        if "AMETHYST_HOME" in os.environ:
            amethyst_dir = os.environ["AMETHYST_HOME"]
        else:
            amethyst_dir = os.path.join(os.path.expanduser("~"), ".amethyst")
        self._db_dir = os.path.join(amethyst_dir, "chroma_db")
        self._embeddings = None
        self._vector_db = None
        self._ready = False

    def initialize(self):
        """Lazy-init the embeddings and vector database (heavy imports)."""
        if self._ready:
            return

        try:
            # Use the updated, non-deprecated packages
            from langchain_ollama import OllamaEmbeddings
            from langchain_chroma import Chroma

            log.info("Loading Ollama Embeddings (nomic-embed-text)...")
            self._embeddings = OllamaEmbeddings(model="nomic-embed-text")

            log.info("Initializing ChromaDB...")
            os.makedirs(self._db_dir, exist_ok=True)
            self._vector_db = Chroma(
                embedding_function=self._embeddings,
                persist_directory=self._db_dir
            )
            self._ready = True
            count = self._vector_db._collection.count()
            log.info(f"RAG Engine ready. {count} chunks in database at {self._db_dir}")
        except Exception as e:
            log.error(f"Failed to initialize RAG database. Running without RAG. Error: {e}")
            self._ready = False

    # ── Ingestion ─────────────────────────────────────────────────────────

    @staticmethod
    def _file_hash(filepath: str) -> str:
        """Compute SHA256 hash of a file for deduplication."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()

    def _remove_source(self, filepath: str):
        """Remove all existing chunks from a specific source file."""
        if not self._ready:
            return
        try:
            # Normalize the path for matching
            norm_path = os.path.normpath(filepath)
            collection = self._vector_db._collection
            # Get all documents with this source
            results = collection.get(where={"source": norm_path})
            if results and results["ids"]:
                collection.delete(ids=results["ids"])
                log.info(f"Removed {len(results['ids'])} old chunks from {os.path.basename(filepath)}")
        except Exception as e:
            # If metadata filtering fails, just log and continue
            log.debug(f"Could not remove old chunks: {e}")

    def ingest_document(self, filepath: str) -> int:
        """
        Reads a document, chunks it, and adds the vectors to ChromaDB.
        Automatically removes old chunks if the same file was previously ingested.
        Returns the number of chunks added.
        """
        if not self._ready:
            self.initialize()
            if not self._ready:
                return 0

        if not os.path.exists(filepath):
            log.error(f"File not found: {filepath}")
            return 0

        try:
            from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            ext = os.path.splitext(filepath)[1].lower()

            # 1. Load
            if ext == ".pdf":
                loader = PyMuPDFLoader(filepath)
            else:
                loader = TextLoader(filepath, encoding='utf-8')

            docs = loader.load()

            # 2. Remove old chunks from same file (deduplication)
            self._remove_source(filepath)

            # 3. Chunk
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=700,
                chunk_overlap=100,
                separators=["\n\n", "\n", ".", " ", ""]
            )
            chunks = splitter.split_documents(docs)

            if not chunks:
                return 0

            # Cap chunks to prevent indefinite server freezing on massive books
            MAX_CHUNKS = 400
            total_chunks = len(chunks)
            truncated = False
            if total_chunks > MAX_CHUNKS:
                log.warning(
                    f"Document has {total_chunks} chunks — capping at {MAX_CHUNKS} "
                    f"({total_chunks - MAX_CHUNKS} chunks from later pages were dropped)."
                )
                chunks = chunks[:MAX_CHUNKS]
                truncated = True

            # 4. Add file hash to metadata for future dedup tracking
            file_hash = self._file_hash(filepath)
            for chunk in chunks:
                chunk.metadata["file_hash"] = file_hash
                if truncated:
                    chunk.metadata["truncated"] = True
                    chunk.metadata["original_chunk_count"] = total_chunks

            # 5. Add to DB
            self._vector_db.add_documents(chunks)
            log.info(f"Ingested {os.path.basename(filepath)}: {len(chunks)} chunks added"
                     f"{f' (truncated from {total_chunks})' if truncated else ''}.")
            return len(chunks)

        except Exception as e:
            log.error(f"Error ingesting document {filepath}: {e}")
            return 0

    # ── Querying ──────────────────────────────────────────────────────────

    def query(self, prompt: str, k: int = 4) -> str:
        """
        Searches the vector database for the top K chunks related to the prompt.
        Returns a formatted context string, or empty string if nothing found.

        Includes a relevance filter: chunks with very low similarity scores
        are discarded to prevent injecting unrelated document noise.
        """
        if not self._ready:
            self.initialize()
            if not self._ready:
                return ""

        stripped = prompt.strip()

        # Skip RAG for casual chat messages (regex-based, not arbitrary length)
        if _CASUAL_PATTERNS.match(stripped):
            return ""

        # Skip extremely short messages (covers edge cases the regex misses)
        if len(stripped) < 8:
            return ""

        try:
            if self._vector_db._collection.count() == 0:
                return ""

            # Use similarity_search_with_score for relevance filtering
            results_with_scores = self._vector_db.similarity_search_with_score(prompt, k=k)
            if not results_with_scores:
                return ""

            # Filter by relevance: Chroma returns L2 distance (lower = more similar).
            # Typical good matches are < 1.0; anything > 1.5 is usually noise.
            RELEVANCE_THRESHOLD = 1.5
            context_pieces = []
            for doc, score in results_with_scores:
                if score > RELEVANCE_THRESHOLD:
                    log.debug(f"RAG chunk dropped (score={score:.2f} > threshold={RELEVANCE_THRESHOLD})")
                    continue

                source = os.path.basename(doc.metadata.get("source", "Unknown"))
                page = doc.metadata.get("page", "")
                page_info = f" (Page {page})" if page != "" else ""

                content = doc.page_content.strip()
                context_pieces.append(f"[Source: {source}{page_info}]\n{content}")

            if not context_pieces:
                return ""

            full_context = "\n\n".join(context_pieces)
            return full_context

        except Exception as e:
            log.error(f"RAG search error: {e}")
            return ""

    # ── Database Management ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return stats about the current vector database."""
        if not self._ready:
            self.initialize()
            if not self._ready:
                return {"total_chunks": 0, "sources": []}

        try:
            collection = self._vector_db._collection
            count = collection.count()

            # Try to get unique sources
            sources = set()
            if count > 0:
                results = collection.get(include=["metadatas"])
                if results and results["metadatas"]:
                    for meta in results["metadatas"]:
                        src = meta.get("source", "")
                        if src:
                            sources.add(os.path.basename(src))

            return {"total_chunks": count, "sources": sorted(sources)}
        except Exception as e:
            log.error(f"Error getting DB stats: {e}")
            return {"total_chunks": 0, "sources": []}

    def clear_database(self):
        """Wipe the entire vector database."""
        if not self._ready:
            self.initialize()
            if not self._ready:
                return

        try:
            collection = self._vector_db._collection
            count = collection.count()
            if count > 0:
                # Delete all
                all_ids = collection.get()["ids"]
                collection.delete(ids=all_ids)
            log.info(f"Cleared vector database ({count} chunks removed).")
        except Exception as e:
            log.error(f"Error clearing database: {e}")

    @property
    def is_ready(self) -> bool:
        return self._ready

    @property
    def chunk_count(self) -> int:
        if not self._ready:
            return 0
        try:
            return self._vector_db._collection.count()
        except Exception:
            return 0
