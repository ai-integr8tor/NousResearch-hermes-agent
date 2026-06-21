import time

from agent.memory_manager import MemoryManager
from agent.memory_provider import MemoryProvider


class _SlowProvider(MemoryProvider):
    def __init__(self, name: str, delay: float = 0.5):
        self._name = name
        self._delay = delay
        self.sync_done = False
        self.prefetch_done = False

    @property
    def name(self) -> str:
        return self._name

    def initialize(self, session_id: str = "", **kwargs) -> None:
        pass

    def is_available(self) -> bool:
        return True

    def system_prompt_block(self) -> str:
        return ""

    def prefetch(self, query, *, session_id: str = "") -> str:
        time.sleep(self._delay)
        return f"result_from_{self._name}"

    def queue_prefetch(self, query, *, session_id: str = "") -> None:
        time.sleep(self._delay)
        self.prefetch_done = True

    def sync_turn(self, user_content, assistant_content, *, session_id="", messages=None):
        time.sleep(self._delay)
        self.sync_done = True

    def get_tool_schemas(self):
        return []


def test_prefetch_all_preserves_registration_order():
    mgr = MemoryManager()
    mgr.add_provider(_SlowProvider("builtin", 0.0))
    mgr.add_provider(_SlowProvider("external", 0.0))

    result = mgr.prefetch_all("hello")

    assert result == "result_from_builtin\n\nresult_from_external"


def test_background_sync_is_isolated_per_registered_provider():
    mgr = MemoryManager()
    builtin = _SlowProvider("builtin", 0.3)
    external = _SlowProvider("external", 0.3)
    mgr.add_provider(builtin)
    mgr.add_provider(external)

    t0 = time.time()
    mgr.sync_all("hello", "response")
    assert mgr.flush_pending(timeout=2) is True
    elapsed = time.time() - t0

    assert builtin.sync_done is True
    assert external.sync_done is True
    assert elapsed < 0.55


def test_background_prefetch_is_isolated_per_registered_provider():
    mgr = MemoryManager()
    builtin = _SlowProvider("builtin", 0.3)
    external = _SlowProvider("external", 0.3)
    mgr.add_provider(builtin)
    mgr.add_provider(external)

    t0 = time.time()
    mgr.queue_prefetch_all("hello")
    assert mgr.flush_pending(timeout=2) is True
    elapsed = time.time() - t0

    assert builtin.prefetch_done is True
    assert external.prefetch_done is True
    assert elapsed < 0.55
