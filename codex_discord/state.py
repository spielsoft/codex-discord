import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Union


class RoutingState:
    """Process-safe, atomically persisted session routing."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(f"{self.path.name}.lock")

    @contextmanager
    def locked_routes(self) -> Iterator[Dict[str, str]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            routes = self._read()
            original = routes.copy()
            try:
                yield routes
                if routes != original:
                    self._write(routes)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _read(self) -> Dict[str, str]:
        try:
            raw_state = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        if not raw_state.strip():
            return {}

        state = json.loads(raw_state)
        if not isinstance(state, dict):
            raise ValueError("routing state must be a JSON object")
        routes = state.get("routes")
        if not isinstance(routes, dict) or not all(
            isinstance(session_id, str) and isinstance(thread_id, str)
            for session_id, thread_id in routes.items()
        ):
            raise ValueError("routing state contains invalid routes")
        return routes

    def _write(self, routes: Dict[str, str]) -> None:
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
                json.dump({"routes": routes}, temporary_file, sort_keys=True)
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
