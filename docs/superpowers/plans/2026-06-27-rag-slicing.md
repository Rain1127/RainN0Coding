# RAG Seed Slicing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slice oversized `component_library` seed entries into semantic chunks before embedding and Milvus insertion, while leaving already-small seed collections unchanged.

**Architecture:** Add a small pure chunking helper in `python-agent/rag/` that splits long component snippets on paragraph/code-block boundaries and emits chunked records using the existing Milvus schema. Wire that helper into `seed_milvus.py` so the seeding path keeps short entries intact and only expands `component_library` rows that exceed the chunk threshold.

**Tech Stack:** Python 3.12, pytest, Milvus client wrapper, existing `rag.seed_data` fixtures.

---

### Task 1: Add chunking helper and tests

**Files:**
- Create: `python-agent/rag/seed_chunking.py`
- Create: `python-agent/tests/test_seed_chunking.py`

- [ ] **Step 1: Write the failing test**

```python
from rag.seed_chunking import expand_seed_record


def test_expand_seed_record_keeps_short_component_as_one_record():
    item = {
        "component_name": "SearchFilter",
        "code_snippet": "<template>...</template>",
        "framework": "vue3",
        "use_count": 1,
    }

    records = expand_seed_record(
        item,
        name_field="component_name",
        content_field="code_snippet",
        max_chars=1200,
    )

    assert len(records) == 1
    assert records[0]["component_name"] == "SearchFilter"
    assert records[0]["code_snippet"] == "<template>...</template>"


def test_expand_seed_record_splits_long_component_into_chunked_records():
    item = {
        "component_name": "BigForm",
        "code_snippet": (
            "section-a\n" + ("a" * 700) + "\n\n"
            "section-b\n" + ("b" * 700) + "\n\n"
            "section-c\n" + ("c" * 700)
        ),
        "framework": "vue3",
        "use_count": 1,
    }

    records = expand_seed_record(
        item,
        name_field="component_name",
        content_field="code_snippet",
        max_chars=1200,
    )

    assert len(records) >= 2
    assert all(len(record["code_snippet"]) <= 1200 for record in records)
    assert records[0]["component_name"].startswith("BigForm")
    assert records[-1]["component_name"].startswith("BigForm")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_seed_chunking.py -v`
Expected: FAIL because `rag.seed_chunking` and `expand_seed_record` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
def expand_seed_record(item, name_field, content_field, max_chars=1200):
    # Return the original record when it is already small.
    # Split long content on blank-line boundaries, then hard-wrap oversize blocks.
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_seed_chunking.py -v`
Expected: PASS.

### Task 2: Wire chunking into component seeding

**Files:**
- Modify: `python-agent/rag/seed_milvus.py`
- Modify: `python-agent/rag/seed_data.py` if any component seed needs a shorter inline example for clarity

- [ ] **Step 1: Write the failing test**

```python
from rag.seed_chunking import expand_seed_record


def test_component_library_seeding_expands_only_long_records():
    short_item = {
        "component_name": "CardGrid",
        "code_snippet": "<div class=\"grid\">...</div>",
        "framework": "vue3",
        "use_count": 1,
    }
    long_item = {
        "component_name": "MegaEditor",
        "code_snippet": ("section\n" + ("x" * 1300)),
        "framework": "vue3",
        "use_count": 1,
    }

    short_records = expand_seed_record(
        short_item,
        name_field="component_name",
        content_field="code_snippet",
        max_chars=1200,
    )
    long_records = expand_seed_record(
        long_item,
        name_field="component_name",
        content_field="code_snippet",
        max_chars=1200,
    )

    assert len(short_records) == 1
    assert len(long_records) > 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_seed_chunking.py -v`
Expected: FAIL until `seed_milvus.py` uses the helper in the real seeding path.

- [ ] **Step 3: Write minimal implementation**

```python
from rag.seed_chunking import expand_seed_record


def seed_collection(collection_name: str, data: list[dict], text_field: str):
    ...
    for item in data:
        for record in expand_seed_record(
            item,
            name_field="component_name" if collection_name == "component_library" else None,
            content_field=text_field,
            max_chars=1200,
        ):
            ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/test_seed_chunking.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python-agent/rag/seed_chunking.py python-agent/rag/seed_milvus.py python-agent/tests/test_seed_chunking.py
git commit -m "feat: chunk large rag component seeds"
```

