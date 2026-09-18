"""Verify live retrieval; seed SQLite only when explicitly initializing a new index."""
import argparse
from rag.embedding_service import embedding_service
from rag.vector_store import vector_store
from rag.sqlite_store import sqlite_store
from rag.seed_data import FRAMEWORK_API_SEEDS, COMPONENT_LIBRARY_SEEDS, ERROR_PATTERN_SEEDS

parser = argparse.ArgumentParser()
parser.add_argument('--seed-sqlite', action='store_true')
args = parser.parse_args()

vector = embedding_service.embed('Vue 3 响应式状态 ref 和 computed')
assert len(vector) == 512
hits = vector_store.search('framework_api', vector, limit=3)
assert hits, 'Live Qdrant search returned no results'
print('EMBEDDING_DIMENSION', len(vector), 'QDRANT_HITS', len(hits))
for collection in ['framework_api', 'component_library', 'design_pattern', 'error_pattern', 'code_store']:
    print('QDRANT_COUNT', collection, vector_store.count(collection))
if args.seed_sqlite:
    sqlite_store.seed_all(FRAMEWORK_API_SEEDS, COMPONENT_LIBRARY_SEEDS, ERROR_PATTERN_SEEDS)
exact = sqlite_store.search_framework_api(['ref'], limit=3)
assert exact, 'SQLite exact search returned no results'
print('SQLITE_SEARCH_HITS', len(exact))
print('RAG_CHECK_PASS')
