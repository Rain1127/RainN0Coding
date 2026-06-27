"""
熔断器 —— 基于滑动时间窗口的失败计数

状态机: CLOSED → OPEN (连续失败 N 次) → HALF_OPEN (冷却 T 秒后) → CLOSED (探测成功)

用法:
    cb = CircuitBreaker("deepseek-v4-pro", failure_threshold=3, cooldown_seconds=30)
    if cb.allow_request():
        try:
            ...
            cb.record_success()
        except Exception:
            cb.record_failure()
"""
import time
import threading
from enum import Enum


class State(Enum):
    CLOSED = "closed"          # 正常通行
    OPEN = "open"              # 熔断拒绝
    HALF_OPEN = "half_open"    # 探测恢复


class CircuitBreaker:
    """线程安全的轻量级熔断器。"""

    def __init__(self, name: str, failure_threshold: int = 3,
                 cooldown_seconds: int = 30, half_open_max_calls: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_max_calls = half_open_max_calls

        self._state = State.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    # ===== 公开 API =====

    def allow_request(self) -> bool:
        """判断当前是否允许通过请求。"""
        with self._lock:
            if self._state == State.CLOSED:
                return True
            if self._state == State.OPEN:
                if time.time() - self._last_failure_time >= self.cooldown_seconds:
                    self._state = State.HALF_OPEN
                    self._half_open_calls = 0
                    print(f"[CB] {self.name} OPEN → HALF_OPEN (冷却到期，开始探测)")
                    return True
                return False
            if self._state == State.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    return True
                return False
            return False

    def record_success(self):
        """记录成功，恢复闭合。"""
        with self._lock:
            if self._state == State.HALF_OPEN:
                self._state = State.CLOSED
                self._failure_count = 0
                print(f"[CB] {self.name} HALF_OPEN → CLOSED (探测成功)")
            self._failure_count = 0

    def record_failure(self):
        """记录失败，可能触发熔断。"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == State.HALF_OPEN:
                self._state = State.OPEN
                print(f"[CB] {self.name} HALF_OPEN → OPEN (探测失败)")
            elif (self._state == State.CLOSED and
                  self._failure_count >= self.failure_threshold):
                self._state = State.OPEN
                print(f"[CB] {self.name} CLOSED → OPEN (连续 {self._failure_count} 次失败，熔断 {self.cooldown_seconds}s)")

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def failure_count(self) -> int:
        return self._failure_count
