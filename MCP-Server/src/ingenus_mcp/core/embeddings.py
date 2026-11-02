"""Local embedding model for meaning search (decision 0013).

An embedding model turns a passage into a list of numbers so that passages with a similar meaning get
similar numbers. It runs here, on this machine, in-process (ONNX, CPU): no contract text goes to a service.

The server NEVER downloads a model while it runs. `get_embedder` loads files that are already on disk
(`INGENUS_EMBED_DIR`); fetching a model is an explicit act:

    python -m ingenus_mcp.embeddings fetch      # downloads INGENUS_EMBED_MODEL into INGENUS_EMBED_DIR
    python -m ingenus_mcp.embeddings status     # says what is configured and whether the files are there

(The command line is `ingenus_mcp/embeddings.py`; server code must not print to stdout.)

Meaning search is OFF unless `INGENUS_EMBED_MODEL` is set. If the model cannot be loaded, search falls back to
keyword only and says so.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ingenus_mcp.core.config import Settings

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


class EmbedderUnavailable(RuntimeError):
    """The model is not configured, not installed or not downloaded. Search then uses keywords only."""


@dataclass(frozen=True)
class ModelSpec:
    name: str
    dim: int
    query_prefix: str = ""
    doc_prefix: str = ""
    min_similarity: float = 0.5  # cosine similarity below this is not shown as a meaning hit


# Measured on the synthetic contracts on 2 Nov 2026 (docs/decisions/0013): real questions scored 0.64 or
# more against their best passage, unrelated ones 0.53 or less. On Chain A's real passages (2 Nov) "retrospective
# discount" scored 0.58 and "volume rebate" 0.68, so the nomic cut-off is 0.55: just above the unrelated
# questions. MiniLM (2 Nov): real questions 0.39 to 0.78, unrelated 0.16 or less, so 0.30. A topic that is simply absent can still score 0.6 ("which law applies"): a hit is a pointer only.
KNOWN: dict[str, ModelSpec] = {
    "nomic-ai/nomic-embed-text-v1.5-Q": ModelSpec(
        "nomic-ai/nomic-embed-text-v1.5-Q", 768, "search_query: ", "search_document: ", 0.55
    ),
    "BAAI/bge-small-en-v1.5": ModelSpec(
        "BAAI/bge-small-en-v1.5",
        384,
        "Represent this sentence for searching relevant passages: ",
        "",
        0.55,
    ),
    "sentence-transformers/all-MiniLM-L6-v2": ModelSpec(
        "sentence-transformers/all-MiniLM-L6-v2", 384, "", "", 0.30
    ),
}
# Short names for INGENUS_EMBED_MODEL, so that a model can be chosen in .env with one word.
ALIASES = {
    "nomic": "nomic-ai/nomic-embed-text-v1.5-Q",
    "bge": "BAAI/bge-small-en-v1.5",
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
}


def resolve_name(name: str) -> str:
    """The full model name for a short name (nomic, bge, minilm); anything else is returned as given."""
    return ALIASES.get(name.strip().lower(), name.strip())


TEST_MODEL = "test-hash"  # a stand-in for the tests: words hashed into 64 numbers, no model files


class Embedder(Protocol):
    spec: ModelSpec

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class HashEmbedder:
    """Tests only: bag of words hashed into 64 buckets. Shares words, not meaning."""

    spec = ModelSpec(TEST_MODEL, 64, min_similarity=0.3)

    def _one(self, text: str) -> list[float]:
        out = [0.0] * 64
        for word in re.findall(r"[a-z0-9]+", text.casefold()):
            digest = hashlib.sha256(word.encode()).digest()
            out[digest[0] % 64] += 1.0 if digest[1] % 2 else -1.0
            out[digest[2] % 64] += 0.5
        return _unit(out)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._one(text)


class FastEmbedder:
    """The real model, through the `fastembed` package (ONNX runtime, no PyTorch). Loaded on first use."""

    def __init__(self, spec: ModelSpec, cache_dir: Path) -> None:
        self.spec = spec
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    from fastembed import TextEmbedding
                except ImportError as exc:
                    raise EmbedderUnavailable("the `fastembed` package is not installed") from exc
                try:
                    self._model = TextEmbedding(
                        self.spec.name, cache_dir=str(self._cache_dir), local_files_only=True
                    )
                except Exception as exc:  # noqa: BLE001 - a missing or damaged model is one condition
                    raise EmbedderUnavailable(
                        f"model {self.spec.name} is not in {self._cache_dir} "
                        "(run: python -m ingenus_mcp.embeddings fetch)"
                    ) from exc
            return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        model = self._load()
        return [
            _unit([float(x) for x in v])
            for v in model.embed([self.spec.doc_prefix + t for t in texts])
        ]

    def embed_query(self, text: str) -> list[float]:
        model = self._load()
        return _unit([float(x) for x in next(iter(model.embed([self.spec.query_prefix + text])))])


_CACHE: dict[tuple[str, str], Embedder] = {}
_CACHE_LOCK = threading.Lock()


def get_embedder(settings: Settings) -> Embedder | None:
    """The configured embedder, or None when meaning search is off (INGENUS_EMBED_MODEL unset or "off")."""
    name = resolve_name(settings.embed_model)
    if not name or name.lower() == "off":
        return None
    key = (name, str(settings.embed_dir))
    with _CACHE_LOCK:
        if key not in _CACHE:
            if name == TEST_MODEL:
                _CACHE[key] = HashEmbedder()
            elif name in KNOWN:
                _CACHE[key] = FastEmbedder(KNOWN[name], settings.embed_dir)
            else:
                raise EmbedderUnavailable(
                    f"model {name!r} is not one we have measured; known: {', '.join(KNOWN)}"
                )
        return _CACHE[key]


def min_similarity(settings: Settings, embedder: Embedder) -> float:
    return settings.embed_min_similarity or embedder.spec.min_similarity


def vector_text(vector: list[float]) -> str:
    """The text form pgvector reads: [0.1,0.2,...]."""
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
