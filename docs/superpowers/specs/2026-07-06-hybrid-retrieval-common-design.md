# Hybrid Engine Shared Retrieval Common Design

## Background

`python-agent/rag/hybrid_engine.py` currently lazily imports `RetrievalResult`, `PostProcessor`, and `RetrievalContext` from `python-agent/rag/retrieval_engine.py`:

```python
from rag.retrieval_engine import RetrievalResult, PostProcessor, RetrievalContext
```

This creates an unhealthy dependency direction. `hybrid_engine` depends on `retrieval_engine` not only for behavior, but also for shared data models and post-processing. `semantic_engine.py` also imports `RetrievalResult` from `retrieval_engine.py`, which makes `retrieval_engine.py` the de facto base module for unrelated retrieval implementations.

The goal is to decouple these shared pieces into a common module while preserving the existing `retrieval_engine.py` API and behavior.

## Goals

- Extract shared retrieval models and post-processing into a dedicated common module.
- Make `hybrid_engine.py` depend on the common module instead of `retrieval_engine.py`.
- Make `semantic_engine.py` depend on the common module instead of `retrieval_engine.py`.
- Preserve existing imports from `rag.retrieval_engine` for compatibility.
- Avoid changing retrieval flow logic unless required for the decoupling.

## Non-Goals

- Rewriting retrieval strategies in `retrieval_engine.py`.
- Changing Milvus, SQLite, or cache behavior.
- Refactoring unrelated RAG modules.
- Changing external call signatures such as `RetrievalEngine.retrieve(ctx)`.

## Proposed Design

### 1. Add a new common module

Create `python-agent/rag/retrieval_common.py` containing:

- `RetrievalResult`
- `RetrievalContext`
- `PostProcessor`

This module becomes the single source of truth for retrieval-shared types and formatting/reranking/dedup behavior.

### 2. Preserve compatibility in `retrieval_engine.py`

Update `python-agent/rag/retrieval_engine.py` to import the shared classes from `retrieval_common.py` and continue exposing them under the same names.

Expected compatibility outcome:

```python
from rag.retrieval_engine import RetrievalResult, PostProcessor, RetrievalContext
```

continues to work without any caller changes.

`retrieval_engine.py` should remain the home of:

- `IntentDirectedRetriever`
- `GlobalVectorRetriever`
- `RetrievalEngine`
- `retrieval_engine` singleton

but no longer define the shared dataclasses or post-processing inline.

### 3. Update `hybrid_engine.py`

Replace the lazy import of shared models from `retrieval_engine.py` with direct imports from `retrieval_common.py`.

This changes the dependency direction from:

- `hybrid_engine -> retrieval_engine`

to:

- `hybrid_engine -> retrieval_common`

`hybrid_engine.py` may still keep a lazy import for `semantic_retriever` if that remains useful for optional Milvus availability, but it should not need fallback copies of shared retrieval models anymore.

### 4. Update `semantic_engine.py`

Replace:

```python
from rag.retrieval_engine import RetrievalResult
```

with:

```python
from rag.retrieval_common import RetrievalResult
```

This ensures all retrieval implementations use the same shared model source.

## File-Level Changes

### New file

- `python-agent/rag/retrieval_common.py`

### Updated files

- `python-agent/rag/retrieval_engine.py`
- `python-agent/rag/hybrid_engine.py`
- `python-agent/rag/semantic_engine.py`

## Dependency Direction After Change

Before:

- `hybrid_engine -> retrieval_engine`
- `semantic_engine -> retrieval_engine`

After:

- `retrieval_engine -> retrieval_common`
- `hybrid_engine -> retrieval_common`
- `semantic_engine -> retrieval_common`

This makes `retrieval_common.py` the shared base and removes the architectural pressure on `retrieval_engine.py` to act as a utility module.

## Migration Strategy

1. Move the shared definitions into `retrieval_common.py`.
2. Update `retrieval_engine.py` to import and re-export those definitions.
3. Update `hybrid_engine.py` to import the shared definitions directly.
4. Update `semantic_engine.py` to import `RetrievalResult` directly from the common module.
5. Run targeted verification on imports and retrieval execution paths.

## Testing and Verification

The change should be validated with targeted checks:

- Import compatibility:
  - `from rag.retrieval_engine import RetrievalResult, PostProcessor, RetrievalContext`
  - `from rag.retrieval_common import RetrievalResult, PostProcessor, RetrievalContext`
- `hybrid_engine.py` imports successfully without pulling shared types from `retrieval_engine.py`.
- `semantic_engine.py` imports successfully with the new source.
- A basic retrieval path in `retrieval_engine` still constructs, deduplicates, reranks, and formats results correctly.
- A basic retrieval path in `hybrid_engine` still completes formatting correctly.

If automated coverage is missing, add a focused regression test around import compatibility and/or serializer-deserializer behavior for `RetrievalResult`.

## Risks

### Import regression

If any external or internal module relies on importing shared classes from `rag.retrieval_engine`, moving definitions without re-exporting them would break callers.

Mitigation:

- Keep the names available from `retrieval_engine.py`.

### Behavior drift in `PostProcessor`

Moving `PostProcessor` into a new file could accidentally change logic during copy/move.

Mitigation:

- Move the implementation with minimal edits.
- Verify dedup, rerank, and format behavior before and after.

### Hidden coupling

Some modules may depend on implementation details rather than public types.

Mitigation:

- Search for all imports and references before editing.
- Keep the public surface unchanged unless a caller is updated deliberately.

## Recommendation

Implement the decoupling through `retrieval_common.py` now, because it gives the clearest architecture improvement with the smallest behavioral risk. It removes the strongest structural coupling while preserving `retrieval_engine.py` as a stable compatibility entry point.
