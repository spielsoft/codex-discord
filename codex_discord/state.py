import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, MutableMapping, Union


MAX_DELIVERED_EVENTS = 256


class RoutingStateTimeout(TimeoutError):
    """The routing-state lock could not be acquired within its time budget."""


class RoutingState:
    """Process-safe, atomically persisted routing and delivery identity."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    def inspect(self) -> Dict[str, object]:
        """Read a credential-free summary without creating or changing state."""

        state = self._read_state()
        routes = state["routes"]
        delivered_events = state["delivered_events"]
        assert isinstance(routes, dict)
        assert isinstance(delivered_events, list)
        return {
            "route_count": len(routes),
            "delivered_event_count": len(delivered_events),
        }

    @contextmanager
    def locked_state(
        self, timeout_seconds: float = 6.0
    ) -> Iterator[MutableMapping[str, object]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    fcntl.flock(
                        lock_file.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                    break
                except BlockingIOError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise RoutingStateTimeout(
                            "routing-state lock acquisition timed out"
                        )
                    time.sleep(min(0.01, remaining))
            state = self._read_state()
            original = {
                "routes": dict(state["routes"]),
                "delivered_events": list(state["delivered_events"]),
            }
            try:
                yield state
                if state != original:
                    self._write_state(state)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def locked_routes(
        self, timeout_seconds: float = 6.0
    ) -> Iterator[Dict[str, str]]:
        """Compatibility view used by callers that only need session routes."""

        with self.locked_state(timeout_seconds=timeout_seconds) as state:
            routes = state["routes"]
            assert isinstance(routes, dict)
            yield routes

    def _read_state(self) -> MutableMapping[str, object]:
        try:
            raw_state = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"routes": {}, "delivered_events": []}
        if not raw_state.strip():
            return {"routes": {}, "delivered_events": []}

        state = json.loads(raw_state)
        if not isinstance(state, dict):
            raise ValueError("routing state must be a JSON object")
        routes = state.get("routes")
        if not isinstance(routes, dict) or not all(
            isinstance(session_id, str) and isinstance(thread_id, str)
            for session_id, thread_id in routes.items()
        ):
            raise ValueError("routing state contains invalid routes")
        delivered_events = state.get("delivered_events", [])
        if not isinstance(delivered_events, list) or not all(
            isinstance(event_id, str) and event_id
            for event_id in delivered_events
        ):
            raise ValueError("routing state contains invalid delivered events")
        return {
            "routes": routes,
            "delivered_events": delivered_events[-MAX_DELIVERED_EVENTS:],
        }

    def _write_state(self, state: MutableMapping[str, object]) -> None:
        routes = state.get("routes")
        delivered_events = state.get("delivered_events")
        if not isinstance(routes, dict) or not isinstance(delivered_events, list):
            raise ValueError("routing state is invalid")
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    {
                        "routes": routes,
                        "delivered_events": delivered_events[
                            -MAX_DELIVERED_EVENTS:
                        ],
                    },
                    temporary_file,
                    sort_keys=True,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
