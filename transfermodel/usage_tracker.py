import threading
import time


class UsageSnapshot:
    __slots__ = (
        "provider", "model", "api_type", "active", "started_at",
        "input_tokens", "output_tokens", "cache_read", "cache_write",
        "response_text",
    )

    def __init__(self):
        self.provider = ""
        self.model = ""
        self.api_type = ""
        self.active = False
        self.started_at = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read = 0
        self.cache_write = 0
        self.response_text = ""


class UsageTracker:
    """Thread-safe tracker for LLM token usage and response text.

    The proxy (running in QThread) calls methods here.
    The dashboard (main Qt thread) reads via get_snapshot() / get_totals().
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current = UsageSnapshot()
        self._total_input = 0
        self._total_output = 0
        self._total_cache_read = 0
        self._total_cache_write = 0
        self._request_count = 0

    def start_request(self, provider: str, model: str, api_type: str):
        with self._lock:
            self._current = UsageSnapshot()
            self._current.provider = provider
            self._current.model = model
            self._current.api_type = api_type
            self._current.active = True
            self._current.started_at = time.monotonic()

    def set_input_tokens(self, n: int, cache_read: int = 0, cache_write: int = 0):
        with self._lock:
            self._current.input_tokens = n
            self._current.cache_read = cache_read
            self._current.cache_write = cache_write

    def set_output_tokens(self, n: int):
        with self._lock:
            self._current.output_tokens = n

    def append_text(self, text: str):
        with self._lock:
            self._current.response_text += text

    def end_request(self):
        with self._lock:
            self._current.active = False
            self._total_input += self._current.input_tokens
            self._total_output += self._current.output_tokens
            self._total_cache_read += self._current.cache_read
            self._total_cache_write += self._current.cache_write
            self._request_count += 1

    def get_snapshot(self) -> UsageSnapshot:
        with self._lock:
            # Return a copy
            snap = UsageSnapshot()
            snap.provider = self._current.provider
            snap.model = self._current.model
            snap.api_type = self._current.api_type
            snap.active = self._current.active
            snap.started_at = self._current.started_at
            snap.input_tokens = self._current.input_tokens
            snap.output_tokens = self._current.output_tokens
            snap.cache_read = self._current.cache_read
            snap.cache_write = self._current.cache_write
            snap.response_text = self._current.response_text
            return snap

    def get_totals(self) -> dict:
        with self._lock:
            return {
                "total_input": self._total_input,
                "total_output": self._total_output,
                "total_cache_read": self._total_cache_read,
                "total_cache_write": self._total_cache_write,
                "request_count": self._request_count,
            }

    def reset_totals(self):
        with self._lock:
            self._total_input = 0
            self._total_output = 0
            self._total_cache_read = 0
            self._total_cache_write = 0
            self._request_count = 0


_tracker: UsageTracker | None = None


def get_tracker() -> UsageTracker:
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
