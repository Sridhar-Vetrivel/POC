"""Command line for the local embedding model (decision 0013): `fetch` and `status`.

    python -m ingenus_mcp.embeddings fetch    # the ONLY place a model is downloaded (into INGENUS_EMBED_DIR)
    python -m ingenus_mcp.embeddings status   # what is configured, and whether the model loads

The server itself never downloads a model: it loads files that are already on disk (core/embeddings.py).
"""

from __future__ import annotations

import argparse
import hashlib
import sys

from ingenus_mcp.core.config import Settings, load_env_file, load_settings
from ingenus_mcp.core.embeddings import (
    ALIASES,
    KNOWN,
    EmbedderUnavailable,
    get_embedder,
    resolve_name,
)


def fetch(settings: Settings) -> int:
    name = resolve_name(settings.embed_model)
    if name not in KNOWN:
        print(
            f"Set INGENUS_EMBED_MODEL to one of: {', '.join(ALIASES)} (or the full names: {', '.join(KNOWN)})",
            file=sys.stderr,
        )
        return 1
    try:
        from fastembed import TextEmbedding
    except ImportError:
        print("The `fastembed` package is not installed (pip install fastembed).", file=sys.stderr)
        return 1
    TextEmbedding(name, cache_dir=str(settings.embed_dir))
    print(f"Model {name} is in {settings.embed_dir}")
    for f in sorted(settings.embed_dir.rglob("*.onnx")):
        print(
            f"  {hashlib.sha256(f.read_bytes()).hexdigest()[:16]}  {f.stat().st_size // 1024} KB  {f.name}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ingenus_mcp.embeddings", description=__doc__)
    parser.add_argument("command", choices=["fetch", "status"])
    args = parser.parse_args(argv)
    load_env_file()
    settings = load_settings()
    if args.command == "fetch":
        return fetch(settings)
    name = resolve_name(settings.embed_model) or "(not set: meaning search is off)"
    print(f"INGENUS_EMBED_MODEL = {name}\nINGENUS_EMBED_DIR   = {settings.embed_dir}")
    try:
        embedder = get_embedder(settings)
        if embedder is not None:
            print(f"Loaded: {len(embedder.embed_query('test'))} numbers per passage")
    except EmbedderUnavailable as exc:
        print(f"Not available: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
