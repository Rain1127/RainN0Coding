import asyncio
import logging
from contextlib import asynccontextmanager

import config as config_module


logger = logging.getLogger("server")

_cleanup_task: asyncio.Task | None = None


def _config():
    return config_module.config


def get_cleanup_task() -> asyncio.Task | None:
    return _cleanup_task


@asynccontextmanager
async def lifespan(app):
    """Initialize and release runtime resources with FastAPI lifespan hooks."""
    global _cleanup_task

    try:
        from rag.sqlite_store import sqlite_store

        sqlite_store.connect()
        sqlite_store.init_tables()
        logger.info(f"SqliteStore initialized: {_config().SQLITE_DB_PATH}")
    except Exception as e:
        logger.warning(f"SqliteStore init failed (grep search disabled): {e}")

    try:
        import os

        os.makedirs(_config().CODE_STORE_DIR, exist_ok=True)
        logger.info(f"CodeStore directory ready: {_config().CODE_STORE_DIR}")
    except Exception as e:
        logger.warning(f"CodeStore directory create failed: {e}")

    try:
        from rag.feedback_tracker import feedback_tracker

        feedback_tracker.connect()
        feedback_tracker.init_tables()
        logger.info("FeedbackTracker initialized")
    except Exception as e:
        logger.warning(f"FeedbackTracker init failed: {e}")

    _cleanup_task = asyncio.create_task(_periodic_quality_cleanup())
    logger.info(
        f"Quality cleanup task started (interval={_config().QUALITY_CLEANUP_INTERVAL_HOURS}h, "
        f"min_age={_config().QUALITY_MIN_AGE_DAYS}d)"
    )
    logger.info(f"Search engine mode: {'Hybrid (grep+RAG)' if _config().USE_HYBRID_ENGINE else 'Vector-only (RAG)'}")

    try:
        yield
    finally:
        if _cleanup_task:
            _cleanup_task.cancel()
            try:
                await _cleanup_task
            except asyncio.CancelledError:
                _cleanup_task = None
            else:
                _cleanup_task = None
            logger.info("Quality cleanup task stopped")

        try:
            from rag.milvus_client import milvus_store

            milvus_store.close()
            logger.info("Milvus connection closed")
        except Exception:
            pass
        try:
            from rag.sqlite_store import sqlite_store

            sqlite_store.close()
            logger.info("SqliteStore connection closed")
        except Exception:
            pass
        try:
            from rag.feedback_tracker import feedback_tracker

            feedback_tracker.close()
            logger.info("FeedbackTracker connection closed")
        except Exception:
            pass


async def _periodic_quality_cleanup():
    """Background cleanup task for low quality code_store entries."""
    while True:
        await asyncio.sleep(_config().QUALITY_CLEANUP_INTERVAL_HOURS * 3600)
        try:
            from rag.code_grep import code_grep
            from rag.feedback_tracker import feedback_tracker
            from rag.milvus_client import milvus_store

            feedback_tracker.connect()
            feedback_tracker.init_tables()

            entries = feedback_tracker.get_low_quality_entries(
                threshold=30.0,
                min_age_days=_config().QUALITY_MIN_AGE_DAYS,
            )

            if not entries:
                logger.info("[QualityCleanup] no low-quality entries to clean")
                continue

            deleted_milvus = 0
            deleted_fs = 0
            for entry in entries:
                e_app_id = entry["app_id"]
                e_file_path = entry["file_path"]

                try:
                    milvus_store.connect()
                    expr = f'app_id == "{e_app_id}" && file_path == "{e_file_path}"'
                    count = milvus_store.delete_by_expr("code_store", expr)
                    deleted_milvus += count
                except Exception as e:
                    logger.warning(f"[QualityCleanup] Milvus delete failed {e_app_id}/{e_file_path}: {e}")

                try:
                    if code_grep.delete_code(e_app_id, e_file_path):
                        deleted_fs += 1
                except Exception as e:
                    logger.warning(f"[QualityCleanup] FS delete failed {e_app_id}/{e_file_path}: {e}")

                try:
                    feedback_tracker.delete_entry(e_app_id, e_file_path)
                except Exception:
                    pass

            logger.info(
                f"[QualityCleanup] cleaned: {len(entries)} entries, Milvus={deleted_milvus}, FS={deleted_fs}"
            )
        except Exception as e:
            logger.warning(f"[QualityCleanup] cleanup task error: {e}")
