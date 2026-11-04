"""Tiny in-memory daily cap so a public link cannot burn the whole API quota."""
from __future__ import annotations

import threading
from datetime import date
from typing import Callable


class DailyCounter:
    def __init__(self, limit: int, today: Callable[[], date] = date.today):
        self.limit = limit
        self._today = today
        self._day = today()
        self._count = 0
        self._lock = threading.Lock()

    def try_consume(self) -> bool:
        with self._lock:
            if self._today() != self._day:
                self._day, self._count = self._today(), 0
            if self._count >= self.limit:
                return False
            self._count += 1
            return True
