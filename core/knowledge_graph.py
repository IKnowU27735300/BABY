"""
core/knowledge_graph.py — Neural Network-like Associative Memory System

A knowledge graph where all information is interconnected. When one piece of
information is recalled, related information is automatically surfaced based on:

1. **Entity Co-occurrence**: Things mentioned together become connected
2. **Temporal Proximity**: Recently discussed topics stay linked
3. **Frequency Weighting**: Frequently co-occurring entities have stronger bonds
4. **Semantic Similarity**: Related concepts (work → project → deadline) link

Architecture:
- Entities (nodes): People, places, projects, concepts, preferences, facts
- Edges (connections): Weighted relationships between entities
- Activation Spreading: Querying one entity activates related entities
- Decay: Unused connections weaken over time (like neural pruning)

This creates a "living memory" where mentioning "John" might surface:
- His email (entity: john_email)
- Your project with him (entity: project_alpha)
- His preference for morning meetings (entity: john_meeting_pref)
- The deadline next week (entity: alpha_deadline)
"""

from __future__ import annotations

import json
import math
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from loguru import logger


# ─── Storage ──────────────────────────────────────────────────────────────────

_KNOWLEDGE_GRAPH_FILE = Path("data/knowledge_graph.json")


@dataclass
class Entity:
    """A node in the knowledge graph."""
    id: str                          # Unique identifier (e.g., "person:john", "project:alpha")
    entity_type: str                 # Category: person, project, place, concept, preference, fact, etc.
    name: str                        # Display name
    attributes: dict = field(default_factory=dict)  # Key-value properties
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    importance: float = 1.0          # Base importance score (0.0 - 10.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "name": self.name,
            "attributes": self.attributes,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "importance": self.importance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Entity:
        return cls(
            id=data["id"],
            entity_type=data["entity_type"],
            name=data["name"],
            attributes=data.get("attributes", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_accessed=data.get("last_accessed", datetime.now().isoformat()),
            access_count=data.get("access_count", 0),
            importance=data.get("importance", 1.0),
        )


@dataclass
class Edge:
    """A weighted connection between two entities."""
    source_id: str                   # Source entity ID
    target_id: str                   # Target entity ID
    relationship: str                # Type of relationship (e.g., "works_with", "prefers", "located_in")
    weight: float = 1.0              # Connection strength (0.0 - 10.0)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_activated: str = field(default_factory=lambda: datetime.now().isoformat())
    activation_count: int = 0
    metadata: dict = field(default_factory=dict)  # Additional context

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship": self.relationship,
            "weight": self.weight,
            "created_at": self.created_at,
            "last_activated": self.last_activated,
            "activation_count": self.activation_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Edge:
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            relationship=data["relationship"],
            weight=data.get("weight", 1.0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_activated=data.get("last_activated", datetime.now().isoformat()),
            activation_count=data.get("activation_count", 0),
            metadata=data.get("metadata", {}),
        )


class KnowledgeGraph:
    """
    Neural network-like associative memory system.

    All information is interconnected. Querying one entity spreads activation
    to related entities, surfacing contextually relevant information.
    """

    def __init__(self):
        self._entities: dict[str, Entity] = {}
        self._edges: list[Edge] = []
        self._adjacency: dict[str, list[int]] = defaultdict(list)  # entity_id → [edge_indices]
        self._lock = threading.Lock()

        # Configuration
        self._MAX_ENTITIES = 10000
        self._MAX_EDGES = 50000
        self._DECAY_RATE = 0.95           # Weight decay per day without activation
        self._ACTIVATION_SPREAD = 0.7     # How much activation spreads (0.0 - 1.0)
        self._MIN_WEIGHT = 0.1            # Minimum edge weight before pruning
        self._IMPORTANCE_BOOST = 1.2      # Multiplier for frequently accessed entities

        # Load existing data
        self._load()

        logger.info(
            "[KnowledgeGraph] Loaded {} entities, {} edges",
            len(self._entities), len(self._edges)
        )

    # ─── Public API ───────────────────────────────────────────────────────────

    def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        attributes: Optional[dict] = None,
        importance: float = 1.0,
    ) -> Entity:
        """Add or update an entity in the knowledge graph."""
        with self._lock:
            if entity_id in self._entities:
                # Update existing entity
                entity = self._entities[entity_id]
                entity.name = name
                if attributes:
                    entity.attributes.update(attributes)
                entity.last_accessed = datetime.now().isoformat()
                entity.access_count += 1
                entity.importance = max(entity.importance, importance)
            else:
                # Create new entity
                entity = Entity(
                    id=entity_id,
                    entity_type=entity_type,
                    name=name,
                    attributes=attributes or {},
                    importance=importance,
                )
                self._entities[entity_id] = entity

                # Prune if at capacity
                if len(self._entities) > self._MAX_ENTITIES:
                    self._prune_entities()

            self._save()
            return entity

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        weight: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> Edge:
        """Add or strengthen a connection between two entities."""
        with self._lock:
            # Check if edge already exists
            for edge_idx in self._adjacency.get(source_id, []):
                edge = self._edges[edge_idx]
                if edge.target_id == target_id and edge.relationship == relationship:
                    # Strengthen existing edge
                    edge.weight = min(edge.weight + weight, 10.0)
                    edge.last_activated = datetime.now().isoformat()
                    edge.activation_count += 1
                    if metadata:
                        edge.metadata.update(metadata)
                    self._save()
                    return edge

            # Create new edge
            edge = Edge(
                source_id=source_id,
                target_id=target_id,
                relationship=relationship,
                weight=weight,
                metadata=metadata or {},
            )
            edge_idx = len(self._edges)
            self._edges.append(edge)
            self._adjacency[source_id].append(edge_idx)

            # Also add reverse edge for bidirectional traversal
            reverse_edge = Edge(
                source_id=target_id,
                target_id=source_id,
                relationship=f"reverse_{relationship}",
                weight=weight * 0.8,  # Slightly weaker reverse connection
                metadata=metadata or {},
            )
            self._edges.append(reverse_edge)
            self._adjacency[target_id].append(len(self._edges) - 1)

            # Prune if at capacity
            if len(self._edges) > self._MAX_EDGES:
                self._prune_edges()

            self._save()
            return edge

    def query(
        self,
        entity_id: str,
        max_depth: int = 2,
        min_weight: float = 0.3,
        max_results: int = 20,
    ) -> list[dict]:
        """
        Query an entity and spread activation to related entities.
        Returns activated entities sorted by relevance.
        """
        with self._lock:
            if entity_id not in self._entities:
                return []

            # Activate the source entity
            source = self._entities[entity_id]
            source.last_accessed = datetime.now().isoformat()
            source.access_count += 1

            # BFS activation spreading
            activated: dict[str, float] = {entity_id: 10.0}  # entity_id → activation_level
            queue = [(entity_id, 10.0, 0)]  # (entity_id, activation, depth)
            visited = {entity_id}

            while queue:
                current_id, current_activation, depth = queue.pop(0)

                if depth >= max_depth:
                    continue

                # Spread activation to neighbors
                for edge_idx in self._adjacency.get(current_id, []):
                    edge = self._edges[edge_idx]
                    if edge.weight < min_weight:
                        continue

                    neighbor_id = edge.target_id
                    if neighbor_id not in self._entities:
                        continue

                    # Calculate activation spread
                    spread_activation = current_activation * edge.weight * self._ACTIVATION_SPREAD / 10.0

                    if spread_activation < 0.1:
                        continue

                    if neighbor_id in activated:
                        activated[neighbor_id] = max(activated[neighbor_id], spread_activation)
                    else:
                        activated[neighbor_id] = spread_activation

                    if neighbor_id not in visited:
                        visited.add(neighbor_id)
                        queue.append((neighbor_id, spread_activation, depth + 1))

            # Remove source from results
            activated.pop(entity_id, None)

            # Sort by activation level
            sorted_results = sorted(activated.items(), key=lambda x: x[1], reverse=True)

            # Build result list
            results = []
            for eid, activation in sorted_results[:max_results]:
                entity = self._entities[eid]
                entity.last_accessed = datetime.now().isoformat()
                entity.access_count += 1

                # Get connecting edges
                connections = []
                for edge_idx in self._adjacency.get(entity_id, []):
                    edge = self._edges[edge_idx]
                    if edge.target_id == eid:
                        connections.append({
                            "relationship": edge.relationship,
                            "weight": edge.weight,
                        })

                results.append({
                    "entity": entity.to_dict(),
                    "activation": round(activation, 2),
                    "connections": connections,
                })

            self._save()
            return results

    def search(
        self,
        query: str,
        entity_type: Optional[str] = None,
        max_results: int = 10,
    ) -> list[dict]:
        """Search entities by name or attributes."""
        with self._lock:
            query_lower = query.lower()
            results = []

            for entity in self._entities.values():
                if entity_type and entity.entity_type != entity_type:
                    continue

                # Score based on name match
                score = 0.0
                if query_lower in entity.name.lower():
                    score += 10.0
                elif any(query_lower in word for word in entity.name.lower().split()):
                    score += 5.0

                # Score based on attribute match
                for key, value in entity.attributes.items():
                    if isinstance(value, str) and query_lower in value.lower():
                        score += 3.0

                if score > 0:
                    # Boost by importance and recency
                    recency_boost = self._recency_score(entity.last_accessed)
                    final_score = score * entity.importance * recency_boost
                    results.append({
                        "entity": entity.to_dict(),
                        "score": round(final_score, 2),
                    })

            # Sort by score
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:max_results]

    def get_entity(self, entity_id: str) -> Optional[dict]:
        """Get a single entity by ID."""
        with self._lock:
            entity = self._entities.get(entity_id)
            if entity:
                entity.last_accessed = datetime.now().isoformat()
                entity.access_count += 1
                self._save()
                return entity.to_dict()
            return None

    def get_all_entities(self, entity_type: Optional[str] = None) -> list[dict]:
        """Get all entities, optionally filtered by type."""
        with self._lock:
            results = []
            for entity in self._entities.values():
                if entity_type and entity.entity_type != entity_type:
                    continue
                results.append(entity.to_dict())
            return results

    def get_connections(self, entity_id: str) -> list[dict]:
        """Get all direct connections for an entity."""
        with self._lock:
            connections = []
            for edge_idx in self._adjacency.get(entity_id, []):
                edge = self._edges[edge_idx]
                target = self._entities.get(edge.target_id)
                if target:
                    connections.append({
                        "edge": edge.to_dict(),
                        "target": target.to_dict(),
                    })
            return connections

    def forget(self, entity_id: str) -> bool:
        """Remove an entity and all its connections."""
        with self._lock:
            if entity_id not in self._entities:
                return False

            del self._entities[entity_id]

            # Remove all edges involving this entity
            self._edges = [
                e for e in self._edges
                if e.source_id != entity_id and e.target_id != entity_id
            ]

            # Rebuild adjacency
            self._adjacency.clear()
            for idx, edge in enumerate(self._edges):
                self._adjacency[edge.source_id].append(idx)

            self._save()
            return True

    def decay(self, days: float = 1.0) -> int:
        """Apply temporal decay to all edge weights. Returns number of pruned edges."""
        with self._lock:
            pruned = 0
            new_edges = []

            for edge in self._edges:
                # Calculate decay
                time_since = (datetime.now() - datetime.fromisoformat(edge.last_activated)).days
                decay_factor = self._DECAY_RATE ** (time_since * days)
                edge.weight *= decay_factor

                if edge.weight >= self._MIN_WEIGHT:
                    new_edges.append(edge)
                else:
                    pruned += 1

            self._edges = new_edges

            # Rebuild adjacency
            self._adjacency.clear()
            for idx, edge in enumerate(self._edges):
                self._adjacency[edge.source_id].append(idx)

            self._save()
            return pruned

    # ─── Action Relationship Methods ──────────────────────────────────────────

    def store_action_relationship(
        self,
        action_a: str,
        action_b: str,
        relationship_type: str,
        explanation: str,
    ) -> Edge:
        """Store an action relationship as a graph edge.

        Args:
            action_a: First action description.
            action_b: Second action description.
            relationship_type: One of the 7 relationship types.
            explanation: Human-readable explanation.

        Returns:
            The created Edge.
        """
        entity_a_id = f"action:{action_a[:50].lower().replace(' ', '_')}"
        entity_b_id = f"action:{action_b[:50].lower().replace(' ', '_')}"

        self.add_entity(entity_a_id, "action", action_a[:100])
        self.add_entity(entity_b_id, "action", action_b[:100])

        return self.add_edge(
            source_id=entity_a_id,
            target_id=entity_b_id,
            relationship=f"action_{relationship_type.lower()}",
            weight=1.0,
            metadata={
                "relationship_type": relationship_type,
                "explanation": explanation,
                "action_a": action_a,
                "action_b": action_b,
            },
        )

    def get_related_actions(
        self,
        action: str,
        relationship_type: Optional[str] = None,
    ) -> list[dict]:
        """Get actions related to a given action.

        Args:
            action: The action description to search for.
            relationship_type: Optional filter by relationship type.

        Returns:
            List of related action dicts.
        """
        entity_id = f"action:{action[:50].lower().replace(' ', '_')}"
        if entity_id not in self._entities:
            return []

        results = []
        for edge_idx in self._adjacency.get(entity_id, []):
            edge = self._edges[edge_idx]
            if not edge.relationship.startswith("action_"):
                continue
            if relationship_type:
                expected = f"action_{relationship_type.lower()}"
                if edge.relationship != expected:
                    continue
            target = self._entities.get(edge.target_id)
            if target:
                results.append({
                    "action": target.name,
                    "relationship_type": edge.metadata.get("relationship_type", ""),
                    "explanation": edge.metadata.get("explanation", ""),
                    "weight": edge.weight,
                })
        return results

    # ─── Helper Methods ───────────────────────────────────────────────────────

    def _recency_score(self, last_accessed: str) -> float:
        """Calculate a recency score (higher = more recent)."""
        try:
            last = datetime.fromisoformat(last_accessed)
            days_ago = (datetime.now() - last).days
            return 1.0 / (1.0 + days_ago * 0.1)
        except Exception:
            return 1.0

    def _prune_entities(self):
        """Remove least important entities when at capacity."""
        if len(self._entities) <= self._MAX_ENTITIES:
            return

        # Sort by importance * recency
        entities_with_score = []
        for entity in self._entities.values():
            recency = self._recency_score(entity.last_accessed)
            score = entity.importance * recency * (1 + entity.access_count * 0.1)
            entities_with_score.append((entity.id, score))

        entities_with_score.sort(key=lambda x: x[1])

        # Remove bottom 10%
        to_remove = len(self._entities) - int(self._MAX_ENTITIES * 0.9)
        for eid, _ in entities_with_score[:to_remove]:
            self.forget(eid)

    def _prune_edges(self):
        """Remove weakest edges when at capacity."""
        if len(self._edges) <= self._MAX_EDGES:
            return

        # Sort by weight * recency
        edges_with_score = []
        for idx, edge in enumerate(self._edges):
            recency = self._recency_score(edge.last_activated)
            score = edge.weight * recency
            edges_with_score.append((idx, score))

        edges_with_score.sort(key=lambda x: x[1])

        # Remove bottom 10%
        to_remove = len(self._edges) - int(self._MAX_EDGES * 0.9)
        indices_to_remove = {idx for idx, _ in edges_with_score[:to_remove]}
        self._edges = [e for idx, e in enumerate(self._edges) if idx not in indices_to_remove]

        # Rebuild adjacency
        self._adjacency.clear()
        for idx, edge in enumerate(self._edges):
            self._adjacency[edge.source_id].append(idx)

    # ─── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        """Load knowledge graph from disk."""
        if not _KNOWLEDGE_GRAPH_FILE.exists():
            self._seed_default_nodes()
            return

        try:
            data = json.loads(_KNOWLEDGE_GRAPH_FILE.read_text(encoding="utf-8"))

            for e_data in data.get("entities", []):
                entity = Entity.from_dict(e_data)
                self._entities[entity.id] = entity

            for edge_data in data.get("edges", []):
                edge = Edge.from_dict(edge_data)
                edge_idx = len(self._edges)
                self._edges.append(edge)
                self._adjacency[edge.source_id].append(edge_idx)

        except Exception as e:
            logger.error("[KnowledgeGraph] Failed to load: {}", e)

    def _seed_default_nodes(self):
        """Seed knowledge graph with default application and file location nodes."""
        import os
        import platform
        import socket

        # System information
        system_info = [
            {"id": "sys:hostname", "name": "Hostname", "value": socket.gethostname(), "category": "system"},
            {"id": "sys:username", "name": "Username", "value": os.getenv("USERNAME", "Unknown"), "category": "system"},
            {"id": "sys:os", "name": "Operating System", "value": f"Windows {platform.version()}", "category": "system"},
            {"id": "sys:python", "name": "Python Version", "value": platform.python_version(), "category": "system"},
            {"id": "sys:processor", "name": "Processor", "value": platform.processor(), "category": "system"},
            {"id": "sys:machine", "name": "Machine Type", "value": platform.machine(), "category": "system"},
        ]

        # Common keyboard shortcuts
        shortcuts = [
            {"id": "shortcut:copy", "name": "Copy", "value": "Ctrl+C", "category": "shortcut"},
            {"id": "shortcut:paste", "name": "Paste", "value": "Ctrl+V", "category": "shortcut"},
            {"id": "shortcut:cut", "name": "Cut", "value": "Ctrl+X", "category": "shortcut"},
            {"id": "shortcut:undo", "name": "Undo", "value": "Ctrl+Z", "category": "shortcut"},
            {"id": "shortcut:redo", "name": "Redo", "value": "Ctrl+Y", "category": "shortcut"},
            {"id": "shortcut:save", "name": "Save", "value": "Ctrl+S", "category": "shortcut"},
            {"id": "shortcut:find", "name": "Find", "value": "Ctrl+F", "category": "shortcut"},
            {"id": "shortcut:selectall", "name": "Select All", "value": "Ctrl+A", "category": "shortcut"},
            {"id": "shortcut:taskmanager", "name": "Open Task Manager", "value": "Ctrl+Shift+Esc", "category": "shortcut"},
            {"id": "shortcut:lock", "name": "Lock Computer", "value": "Win+L", "category": "shortcut"},
            {"id": "shortcut:screenshot", "name": "Screenshot", "value": "Win+Shift+S", "category": "shortcut"},
            {"id": "shortcut:run", "name": "Run Dialog", "value": "Win+R", "category": "shortcut"},
            {"id": "shortcut:search", "name": "Windows Search", "value": "Win+S", "category": "shortcut"},
            {"id": "shortcut:desktop", "name": "Show Desktop", "value": "Win+D", "category": "shortcut"},
            {"id": "shortcut:alttab", "name": "Switch Apps", "value": "Alt+Tab", "category": "shortcut"},
        ]

        # Common tasks and commands
        tasks = [
            {"id": "task:shutdown", "name": "Shutdown Computer", "value": "shutdown /s /t 0", "category": "command"},
            {"id": "task:restart", "name": "Restart Computer", "value": "shutdown /r /t 0", "category": "command"},
            {"id": "task:logoff", "name": "Log Off", "value": "shutdown /l", "category": "command"},
            {"id": "task:sleep", "name": "Put Computer to Sleep", "value": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0", "category": "command"},
            {"id": "task:emptyrecycle", "name": "Empty Recycle Bin", "value": "rd /s /q C:\\$Recycle.Bin", "category": "command"},
            {"id": "task:clearcache", "name": "Clear Temp Files", "value": "del /q /f /s %TEMP%\\*", "category": "command"},
            {"id": "task:ipconfig", "name": "Show IP Configuration", "value": "ipconfig /all", "category": "command"},
            {"id": "task:wifi", "name": "Show WiFi Password", "value": "netsh wlan show profile name=WiFiName key=clear", "category": "command"},
        ]

        # Common applications with their paths
        apps = [
            {"id": "app:chrome", "name": "Google Chrome", "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "category": "browser"},
            {"id": "app:edge", "name": "Microsoft Edge", "path": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", "category": "browser"},
            {"id": "app:vscode", "name": "Visual Studio Code", "path": os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"), "category": "editor"},
            {"id": "app:notepad", "name": "Notepad", "path": "C:\\Windows\\System32\\notepad.exe", "category": "editor"},
            {"id": "app:filemanager", "name": "File Explorer", "path": "C:\\Windows\\explorer.exe", "category": "utility"},
            {"id": "app:terminal", "name": "Terminal", "path": "C:\\Windows\\System32\\cmd.exe", "category": "utility"},
            {"id": "app:powershell", "name": "PowerShell", "path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe", "category": "utility"},
            {"id": "app:settings", "name": "Windows Settings", "path": "ms-settings:", "category": "system"},
            {"id": "app:taskmanager", "name": "Task Manager", "path": "C:\\Windows\\System32\\Taskmgr.exe", "category": "system"},
            {"id": "app:calculator", "name": "Calculator", "path": "ms-calculator:", "category": "utility"},
            {"id": "app:paint", "name": "Paint", "path": "C:\\Windows\\System32\\mspaint.exe", "category": "creative"},
            {"id": "app:photos", "name": "Photos", "path": "ms-photos:", "category": "creative"},
            {"id": "app:spotify", "name": "Spotify", "path": os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"), "category": "media"},
            {"id": "app:discord", "name": "Discord", "path": os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"), "category": "communication"},
            {"id": "app:zoom", "name": "Zoom", "path": os.path.expandvars(r"%APPDATA%\Zoom\bin\Zoom.exe"), "category": "communication"},
            {"id": "app:word", "name": "Microsoft Word", "path": "C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE", "category": "productivity"},
            {"id": "app:excel", "name": "Microsoft Excel", "path": "C:\\Program Files\\Microsoft Office\\root\\Office16\\EXCEL.EXE", "category": "productivity"},
            {"id": "app:powerpoint", "name": "Microsoft PowerPoint", "path": "C:\\Program Files\\Microsoft Office\\root\\Office16\\POWERPNT.EXE", "category": "productivity"},
            {"id": "app:outlook", "name": "Microsoft Outlook", "path": "C:\\Program Files\\Microsoft Office\\root\\Office16\\OUTLOOK.EXE", "category": "communication"},
        ]

        # Common file locations
        locations = [
            {"id": "loc:desktop", "name": "Desktop", "path": os.path.expandvars(r"%USERPROFILE%\Desktop"), "category": "folder"},
            {"id": "loc:documents", "name": "Documents", "path": os.path.expandvars(r"%USERPROFILE%\Documents"), "category": "folder"},
            {"id": "loc:downloads", "name": "Downloads", "path": os.path.expandvars(r"%USERPROFILE%\Downloads"), "category": "folder"},
            {"id": "loc:pictures", "name": "Pictures", "path": os.path.expandvars(r"%USERPROFILE%\Pictures"), "category": "folder"},
            {"id": "loc:music", "name": "Music", "path": os.path.expandvars(r"%USERPROFILE%\Music"), "category": "folder"},
            {"id": "loc:videos", "name": "Videos", "path": os.path.expandvars(r"%USERPROFILE%\Videos"), "category": "folder"},
            {"id": "loc:appdata", "name": "AppData", "path": os.path.expandvars(r"%LOCALAPPDATA%"), "category": "system"},
            {"id": "loc:programfiles", "name": "Program Files", "path": "C:\\Program Files", "category": "system"},
            {"id": "loc:programfilesx86", "name": "Program Files (x86)", "path": "C:\\Program Files (x86)", "category": "system"},
            {"id": "loc:windows", "name": "Windows", "path": "C:\\Windows", "category": "system"},
            {"id": "loc:home", "name": "User Home", "path": os.path.expandvars(r"%USERPROFILE%"), "category": "folder"},
        ]

        # Add app entities
        for app in apps:
            if not Path(app["path"]).exists() and not app["path"].startswith("ms-"):
                continue  # Skip apps that aren't installed
            entity = Entity(
                id=app["id"],
                entity_type="application",
                name=app["name"],
                attributes={"path": app["path"], "category": app["category"]},
                importance=2.0,
            )
            self._entities[entity.id] = entity

        # Add location entities
        for loc in locations:
            entity = Entity(
                id=loc["id"],
                entity_type="location",
                name=loc["name"],
                attributes={"path": loc["path"], "category": loc["category"]},
                importance=1.5,
            )
            self._entities[entity.id] = entity

        # Add system info entities
        for info in system_info:
            entity = Entity(
                id=info["id"],
                entity_type="system_info",
                name=info["name"],
                attributes={"value": info["value"], "category": info["category"]},
                importance=1.0,
            )
            self._entities[entity.id] = entity

        # Add shortcut entities
        for shortcut in shortcuts:
            entity = Entity(
                id=shortcut["id"],
                entity_type="shortcut",
                name=shortcut["name"],
                attributes={"keys": shortcut["value"], "category": shortcut["category"]},
                importance=1.5,
            )
            self._entities[entity.id] = entity

        # Add task/command entities
        for task in tasks:
            entity = Entity(
                id=task["id"],
                entity_type="task",
                name=task["name"],
                attributes={"command": task["value"], "category": task["category"]},
                importance=1.5,
            )
            self._entities[entity.id] = entity

        # Add edges connecting related items
        # Browser apps connect to each other
        self._add_edge("app:chrome", "app:edge", "alternatives", 0.5)
        # Editor apps connect
        self._add_edge("app:vscode", "app:notepad", "alternatives", 0.5)
        # Communication apps connect
        self._add_edge("app:discord", "app:zoom", "alternatives", 0.5)
        self._add_edge("app:outlook", "app:zoom", "alternatives", 0.5)
        # Productivity apps connect
        self._add_edge("app:word", "app:excel", "office_suite", 0.7)
        self._add_edge("app:word", "app:powerpoint", "office_suite", 0.7)
        self._add_edge("app:excel", "app:powerpoint", "office_suite", 0.7)
        # System utilities connect
        self._add_edge("app:terminal", "app:powershell", "alternatives", 0.6)
        self._add_edge("app:filemanager", "app:terminal", "file_operations", 0.4)
        # Locations connect to each other
        self._add_edge("loc:desktop", "loc:home", "inside", 0.8)
        self._add_edge("loc:documents", "loc:home", "inside", 0.8)
        self._add_edge("loc:downloads", "loc:home", "inside", 0.8)
        self._add_edge("loc:pictures", "loc:home", "inside", 0.8)
        self._add_edge("loc:music", "loc:home", "inside", 0.8)
        self._add_edge("loc:videos", "loc:home", "inside", 0.8)
        # Shortcuts connect to apps they work with
        self._add_edge("shortcut:copy", "app:vscode", "works_with", 0.3)
        self._add_edge("shortcut:paste", "app:vscode", "works_with", 0.3)
        self._add_edge("shortcut:save", "app:word", "works_with", 0.3)
        # Tasks connect to commands
        self._add_edge("task:shutdown", "task:restart", "related", 0.5)
        self._add_edge("task:shutdown", "task:logoff", "related", 0.5)
        self._add_edge("task:shutdown", "task:sleep", "related", 0.5)

        self._save()
        logger.info("[KnowledgeGraph] Seeded {} apps, {} locations", len(apps), len(locations))

    def _add_edge(self, source_id: str, target_id: str, relationship: str, weight: float = 1.0):
        """Add an edge between two entities."""
        if source_id in self._entities and target_id in self._entities:
            edge = Edge(
                source_id=source_id,
                target_id=target_id,
                relationship=relationship,
                weight=weight,
            )
            edge_idx = len(self._edges)
            self._edges.append(edge)
            self._adjacency[source_id].append(edge_idx)

    def _save(self):
        """Save knowledge graph to disk."""
        try:
            _KNOWLEDGE_GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "entities": [e.to_dict() for e in self._entities.values()],
                "edges": [e.to_dict() for e in self._edges],
                "metadata": {
                    "last_saved": datetime.now().isoformat(),
                    "entity_count": len(self._entities),
                    "edge_count": len(self._edges),
                },
            }

            _KNOWLEDGE_GRAPH_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("[KnowledgeGraph] Failed to save: {}", e)

    def get_stats(self) -> dict:
        """Get knowledge graph statistics."""
        with self._lock:
            entity_types = defaultdict(int)
            for entity in self._entities.values():
                entity_types[entity.entity_type] += 1

            relationship_types = defaultdict(int)
            for edge in self._edges:
                relationship_types[edge.relationship] += 1

            return {
                "total_entities": len(self._entities),
                "total_edges": len(self._edges),
                "entity_types": dict(entity_types),
                "relationship_types": dict(relationship_types),
                "avg_connections_per_entity": len(self._edges) / max(len(self._entities), 1),
            }


# ─── Global Instance ──────────────────────────────────────────────────────────

knowledge_graph = KnowledgeGraph()


# ─── Entity Extraction Helpers ────────────────────────────────────────────────

def extract_entities_from_text(text: str) -> list[dict]:
    """
    Extract potential entities from text using pattern matching.
    Returns list of (entity_type, name, attributes) tuples.
    """
    import re

    entities = []

    # Extract names (capitalized words that might be people)
    name_patterns = [
        r"\b(?:with|to|from|for|about|mention)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        r"\b([A-Z][a-z]+)\s+(?:said|told|asked|mentioned|wants|needs|prefers)",
    ]
    for pat in name_patterns:
        for m in re.finditer(pat, text):
            name = m.group(1).strip()
            if len(name) >= 2 and name.lower() not in {"the", "and", "for", "with", "this", "that"}:
                entities.append({
                    "type": "person",
                    "name": name,
                    "attributes": {},
                })

    # Extract emails
    email_pattern = r"\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b"
    for m in re.finditer(email_pattern, text):
        entities.append({
            "type": "contact",
            "name": m.group(1),
            "attributes": {"email": m.group(1)},
        })

    # Extract phone numbers
    phone_pattern = r"\b(\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9})\b"
    for m in re.finditer(phone_pattern, text):
        entities.append({
            "type": "contact",
            "name": m.group(1),
            "attributes": {"phone": m.group(1)},
        })

    # Extract dates
    date_patterns = [
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4})\b",
    ]
    for pat in date_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            entities.append({
                "type": "date",
                "name": m.group(1),
                "attributes": {},
            })

    # Extract project names (Project X, Initiative Y, etc.)
    project_patterns = [
        r"\b(?:project|initiative|program|plan)\s+([A-Z][a-zA-Z0-9]+)\b",
        r"\b([A-Z][a-zA-Z0-9]+)\s+(?:project|initiative|program|plan)\b",
    ]
    for pat in project_patterns:
        for m in re.finditer(pat, text):
            entities.append({
                "type": "project",
                "name": m.group(1),
                "attributes": {},
            })

    # Extract preferences
    pref_patterns = [
        r"\b(?:prefer|like|love|enjoy|favorite)\s+(.+?)(?:\.|,|$)",
        r"\b(?:don't like|hate|dislike|avoid)\s+(.+?)(?:\.|,|$)",
    ]
    for pat in pref_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            entities.append({
                "type": "preference",
                "name": m.group(1).strip(),
                "attributes": {},
            })

    return entities


def auto_connect_entities(text: str, graph: KnowledgeGraph) -> list[str]:
    """
    Automatically extract entities from text and create connections.
    Returns list of created entity IDs.
    """
    import re

    extracted = extract_entities_from_text(text)
    created_ids = []

    # Add all extracted entities
    entity_map = {}
    for ext in extracted:
        entity_type = ext["type"]
        name = ext["name"]
        entity_id = f"{entity_type}:{name.lower().replace(' ', '_')}"
        graph.add_entity(entity_id, entity_type, name, ext.get("attributes", {}))
        entity_map[entity_id] = name
        created_ids.append(entity_id)

    # Connect co-occurring entities
    entity_ids = list(entity_map.keys())
    for i in range(len(entity_ids)):
        for j in range(i + 1, len(entity_ids)):
            # Create bidirectional connection
            graph.add_edge(
                entity_ids[i],
                entity_ids[j],
                "co_occurs_with",
                weight=1.0,
                metadata={"context": text[:200]},
            )

    return created_ids



















