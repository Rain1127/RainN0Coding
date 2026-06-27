"""单元测试：P2 反馈追踪器"""
import pytest
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a temporary DB for testing
os.environ["CODE_STORE_DIR"] = tempfile.mkdtemp(prefix="test_feedback_")

from rag.feedback_tracker import FeedbackTracker


@pytest.fixture
def tracker():
    """创建独立的 FeedbackTracker 实例用于测试"""
    t = FeedbackTracker()
    t.connect()
    t.init_tables()
    yield t
    # Cleanup
    t._conn.execute("DELETE FROM rag_quality")
    t._conn.execute("DELETE FROM rag_retrieval_log")
    t._conn.commit()
    t.close()


class TestFeedbackTracker:

    def test_record_ingestion(self, tracker):
        """入库后能查到初始质量分"""
        tracker.record_ingestion("app_001", "src/App.vue", review_score=85)
        score = tracker.get_quality_score("app_001", "src/App.vue")
        assert score is not None
        assert score == 85.0  # review_score 优先

    def test_record_ingestion_default_score(self, tracker):
        """未提供 review_score 时使用默认值"""
        tracker.record_ingestion("app_002", "main.py")
        score = tracker.get_quality_score("app_002", "main.py")
        assert score is not None
        assert score > 0

    def test_get_quality_score_missing(self, tracker):
        """无记录的条目返回 None"""
        score = tracker.get_quality_score("nonexistent", "file.py")
        assert score is None

    def test_record_to_session_self_reference_filtered(self, tracker):
        """自引用被过滤（gen_app_id == rag_app_id）"""
        tracker.record_to_session("app_001", "app_001", "src/App.vue")
        # Session 应为空（自引用不记录）
        assert "app_001" not in tracker._pending_sessions

    def test_record_to_session_cross_reference(self, tracker):
        """跨应用引用被记录"""
        tracker.record_to_session("app_002", "app_001", "src/Button.vue")
        assert "app_002" in tracker._pending_sessions
        assert ("app_001", "src/Button.vue") in tracker._pending_sessions["app_002"]

    def test_record_to_session_empty_params(self, tracker):
        """空参数不记录"""
        tracker.record_to_session("", "app_001", "file.py")
        tracker.record_to_session("app_001", "", "file.py")
        tracker.record_to_session("app_001", "app_002", "")
        assert len(tracker._pending_sessions) == 0

    def test_apply_feedback_success_boost(self, tracker):
        """构建成功 → 质量分增加"""
        # 先入库
        tracker.record_ingestion("app_A", "file.py", review_score=70)
        # 记录检索引用
        tracker.record_to_session("app_B", "app_A", "file.py")
        # 应用反馈（构建成功）
        tracker.apply_feedback("app_B", build_success=True)

        score = tracker.get_quality_score("app_A", "file.py")
        assert score is not None
        assert score >= 70.0  # 应该被加分了
        assert score <= 100.0  # 不能超过 100

    def test_apply_feedback_failure_penalty(self, tracker):
        """构建失败 → 质量分减少"""
        tracker.record_ingestion("app_A", "file.py", review_score=70)
        tracker.record_to_session("app_B", "app_A", "file.py")
        tracker.apply_feedback("app_B", build_success=False)

        score = tracker.get_quality_score("app_A", "file.py")
        assert score is not None
        assert score <= 70.0  # 应该被扣分了
        assert score >= 0.0   # 不能低于 0

    def test_apply_feedback_score_clamped_0_100(self, tracker):
        """质量分钳制在 [0, 100]"""
        # 测试上限：多次加分不应超过 100
        tracker.record_ingestion("app_C", "high.py", review_score=99)
        for i in range(5):
            gen_id = f"app_boost_{i}"
            tracker.record_to_session(gen_id, "app_C", "high.py")
            tracker.apply_feedback(gen_id, build_success=True)
        score = tracker.get_quality_score("app_C", "high.py")
        assert score <= 100.0

        # 测试下限：多次扣分不应低于 0
        tracker.record_ingestion("app_G", "low.py", review_score=5)
        for i in range(10):
            gen_id = f"app_penalty_{i}"
            tracker.record_to_session(gen_id, "app_G", "low.py")
            tracker.apply_feedback(gen_id, build_success=False)
        score = tracker.get_quality_score("app_G", "low.py")
        assert score >= 0.0

    def test_apply_feedback_empty_session(self, tracker):
        """空会话不抛异常"""
        tracker.apply_feedback("nonexistent_session", build_success=True)

    def test_get_low_quality_entries(self, tracker):
        """查询低质量条目"""
        tracker.record_ingestion("app_X", "good.py", review_score=80)
        tracker.record_ingestion("app_Y", "bad.py", review_score=20)

        # 手动修改 updated_at 为很久以前（模拟旧数据）
        old_ts = "2020-01-01T00:00:00"
        with tracker._lock:
            tracker._conn.execute(
                "UPDATE rag_quality SET updated_at = ? WHERE app_id = ? AND file_path = ?",
                (old_ts, "app_Y", "bad.py"),
            )
            tracker._conn.commit()

        entries = tracker.get_low_quality_entries(threshold=30.0, min_age_days=30)
        assert any(e["app_id"] == "app_Y" for e in entries)
        assert not any(e["app_id"] == "app_X" for e in entries)  # 高质量不被返回

    def test_delete_entry(self, tracker):
        """删除条目后查询返回 None"""
        tracker.record_ingestion("app_Z", "to_delete.py", review_score=50)
        assert tracker.get_quality_score("app_Z", "to_delete.py") is not None

        tracker.delete_entry("app_Z", "to_delete.py")
        assert tracker.get_quality_score("app_Z", "to_delete.py") is None

    def test_record_ingestion_upsert(self, tracker):
        """重复入库不会创建重复记录，且质量分取最高值"""
        tracker.record_ingestion("app_U", "dup.py", review_score=60)
        tracker.record_ingestion("app_U", "dup.py", review_score=80)
        score = tracker.get_quality_score("app_U", "dup.py")
        assert score == 80.0  # 取最高值
