"""Bounded in-process sharing of an immutable in-flight result."""
from dataclasses import dataclass, field
from threading import Event, Lock

from prometheus_client import Counter


_events = Counter('ai_rag_singleflight_total',
                  'RAG in-flight sharing events, separate from Redis cache hits',
                  ['phase', 'channel', 'status'])


def record_singleflight(phase, channel, status):
    _events.labels(phase=phase, channel=channel, status=status).inc()


@dataclass
class _Flight:
    done: Event = field(default_factory=Event)
    value: str | None = None
    error: BaseException | None = None


class SingleFlight:
    def __init__(self, wait_timeout=1.0, max_pending=256):
        self.wait_timeout = wait_timeout
        self.max_pending = max_pending
        self._lock = Lock()
        self._pending = {}

    @property
    def pending_count(self):
        with self._lock:
            return len(self._pending)

    def run(self, key, loader, on_event=lambda _status: None):
        with self._lock:
            flight = self._pending.get(key)
            owner = flight is None
            if owner and len(self._pending) < self.max_pending:
                flight = _Flight()
                self._pending[key] = flight

        if flight is None:
            on_event('capacity_bypass')
            return loader()
        if not owner:
            on_event('joined')
            if not flight.done.wait(self.wait_timeout):
                on_event('timeout')
                return loader()
            if flight.error is not None:
                raise flight.error
            return flight.value

        try:
            flight.value = loader()
            return flight.value
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            with self._lock:
                flight.done.set()
                if self._pending.get(key) is flight:
                    del self._pending[key]
