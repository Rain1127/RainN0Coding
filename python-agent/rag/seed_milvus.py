"""Deprecated compatibility entrypoint; use rag/seed_vector_store.py."""

import warnings

from rag.seed_vector_store import main, seed_collection


if __name__ == "__main__":
    warnings.warn(
        "seed_milvus.py is deprecated; use seed_vector_store.py",
        DeprecationWarning,
        stacklevel=1,
    )
    main()
