"""Filesystem watcher: debounced auto-conversion of new/changed files.

Wraps watchdog's Observer with a per-path debounce timer, so a burst of
rapid write events for the same file (common while it's still being
written or copied) collapses into a single callback once things settle,
rather than converting a half-written file or firing repeatedly.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from dnude.core.engine import SUPPORTED_EXTENSIONS


class _DebounceHandler(FileSystemEventHandler):
    def __init__(self, on_event: Callable[[str], None]):
        self._on_event = on_event

    def on_created(self, event):
        if not event.is_directory:
            self._on_event(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._on_event(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._on_event(event.dest_path)


class DirectoryWatcher:
    """Watches a directory and calls `callback(path)` once per settled change.

    "Settled" means no further create/modify/move events for that path
    arrived within `debounce_seconds`. Only paths with a supported
    extension (.pdf/.docx/.xml) trigger the callback.
    """

    def __init__(
        self,
        directory: str | Path,
        callback: Callable[[str], None],
        debounce_seconds: float = 1.0,
        recursive: bool = True,
    ):
        self.directory = str(directory)
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.recursive = recursive
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._observer = Observer()

    def _handle_event(self, path: str) -> None:
        if Path(path).suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        with self._lock:
            existing = self._timers.get(path)
            if existing:
                existing.cancel()
            timer = threading.Timer(self.debounce_seconds, self._fire, args=(path,))
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _fire(self, path: str) -> None:
        with self._lock:
            self._timers.pop(path, None)
        if Path(path).is_file():
            self.callback(path)

    def start(self) -> None:
        handler = _DebounceHandler(self._handle_event)
        self._observer.schedule(handler, self.directory, recursive=self.recursive)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join(timeout=5)
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()

    def run_forever(self, poll_interval: float = 0.5) -> None:
        """Block until interrupted (Ctrl+C), then stop cleanly."""
        self.start()
        try:
            while True:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()
