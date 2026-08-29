"""
core/relationship_engine/isolation/memory_isolator.py — Thread-safe per-network memory isolation.
Each network has its own training buffer. Cross-reading raises PermissionError.
"""

from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional
from collections import defaultdict


class MemoryIsolator:
    """Manages isolated, thread-safe training buffers per network type.

    Each network type has its own buffer that is completely independent.
    Attempting to read from a different network's buffer raises PermissionError.
    """

    def __init__(self):
        self._buffers: Dict[str, List[Any]] = defaultdict(list)
        self._locks: Dict[str, threading.Lock] = {}
        self._owner: Dict[str, str] = {}  # buffer_name -> owner_network
        self._global_lock = threading.Lock()

    def create_buffer(self, name: str, owner_network: str) -> None:
        """Create a new isolated buffer owned by a specific network."""
        with self._global_lock:
            if name in self._buffers:
                raise ValueError(f"Buffer '{name}' already exists")
            self._buffers[name] = []
            self._locks[name] = threading.Lock()
            self._owner[name] = owner_network

    def write(self, buffer_name: str, owner_network: str, data: Any) -> None:
        """Write data to a buffer. Only the owning network can write."""
        if buffer_name not in self._owner:
            raise KeyError(f"Buffer '{buffer_name}' does not exist")
        if self._owner[buffer_name] != owner_network:
            raise PermissionError(
                f"Network '{owner_network}' cannot write to buffer '{buffer_name}' "
                f"(owned by '{self._owner[buffer_name]}')"
            )
        with self._locks[buffer_name]:
            self._buffers[buffer_name].append(data)

    def read(self, buffer_name: str, requester_network: str) -> List[Any]:
        """Read all data from a buffer. Only the owning network can read."""
        if buffer_name not in self._owner:
            raise KeyError(f"Buffer '{buffer_name}' does not exist")
        if self._owner[buffer_name] != requester_network:
            owner = self._owner[buffer_name]
            raise PermissionError(
                f"Network '{requester_network}' cannot read buffer '{buffer_name}' "
                f"(owned by '{owner}')"
            )
        with self._locks[buffer_name]:
            return list(self._buffers[buffer_name])

    def read_cross(self, buffer_name: str, requester_network: str) -> None:
        """Explicitly block cross-network reads."""
        if buffer_name not in self._owner:
            raise KeyError(f"Buffer '{buffer_name}' does not exist")
        if self._owner[buffer_name] != requester_network:
            raise PermissionError(
                f"Cross-network read blocked: '{requester_network}' "
                f"attempted to read buffer '{buffer_name}' "
                f"(owned by '{self._owner[buffer_name]}')"
            )

    def clear(self, buffer_name: str, owner_network: str) -> None:
        """Clear a buffer. Only the owning network can clear."""
        if buffer_name not in self._owner:
            raise KeyError(f"Buffer '{buffer_name}' does not exist")
        if self._owner[buffer_name] != owner_network:
            raise PermissionError(
                f"Network '{owner_network}' cannot clear buffer '{buffer_name}'"
            )
        with self._locks[buffer_name]:
            self._buffers[buffer_name].clear()

    def size(self, buffer_name: str) -> int:
        """Get buffer size (no ownership check for monitoring)."""
        with self._locks.get(buffer_name, threading.Lock()):
            return len(self._buffers.get(buffer_name, []))

    def list_buffers(self) -> Dict[str, str]:
        """List all buffers and their owners."""
        return dict(self._owner)



















