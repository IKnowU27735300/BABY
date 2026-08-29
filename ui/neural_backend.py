"""ui/neural_backend.py — Backend for Social Network Graph.

Provides node/edge data to the QML NeuralNetworkViewer via signals.
Zero-gravity layout: random free positions, no force-directed algorithm.
"""
from __future__ import annotations

import json
import math
import random
import hashlib
from loguru import logger

from PySide6.QtCore import QObject, Signal, Slot


class NeuralNetworkBackend(QObject):
    """Backend that feeds graph data to the QML social-graph viewer."""

    graphDataReady = Signal(list, list, dict)   # nodes, edges, stats
    nodeSelected = Signal(dict)                  # selected node details
    showWindow = Signal()                        # signal to show the neural window

    def __init__(self, parent=None):
        super().__init__(parent)
        self._knowledge_graph = None
        self._neural_root = None

    def set_neural_root(self, root):
        self._neural_root = root

    def set_knowledge_graph(self, kg):
        self._knowledge_graph = kg

    @Slot()
    def refreshGraph(self):
        try:
            if not self._knowledge_graph:
                logger.warning("[SocialGraph] No knowledge graph available")
                self.graphDataReady.emit([], [], {"total_nodes": 0})
                return

            entities = self._knowledge_graph.get_all_entities()
            edges_data = list(self._knowledge_graph._edges)
            stats = self._knowledge_graph.get_stats()

            nodes, edges = self._build_graph(entities, edges_data)

            logger.info("[SocialGraph] Graph data ready: {} nodes, {} edges", len(nodes), len(edges))
            self.graphDataReady.emit(nodes, edges, stats)

            if hasattr(self, '_neural_root') and self._neural_root:
                self._neural_root.show()
                self._neural_root.raise_()
                try:
                    self._neural_root.requestActivate()
                except Exception:
                    pass

        except Exception as e:
            logger.error("[SocialGraph] Failed to refresh graph: {}", e)

    def _build_graph(self, entities: list[dict], edges_data: list) -> tuple[list[dict], list[dict]]:
        """Build nodes with random free positions — zero gravity layout."""
        nodes = []
        edges = []

        type_icons = {
            "application": "💻",
            "location": "📁",
            "system_info": "ℹ",
            "shortcut": "⌨",
            "task": "⚡",
            "person": "👤",
            "concept": "💡",
        }

        # Spread area for random placement
        margin = 80
        area_w = 900
        area_h = 600

        for i, entity in enumerate(entities):
            eid = entity.get("id", str(i))
            name = entity.get("name", eid)
            entity_type = entity.get("entity_type", "concept")
            importance = entity.get("importance", 1.0)

            # Random free position within viewport
            rng = random.Random(hash(eid) + 42)
            x = margin + rng.random() * area_w
            y = margin + rng.random() * area_h

            # Color by importance: red=high, green=mid, yellow=low
            if importance >= 0.8:
                node_color = "#ef4444"
            elif importance >= 0.5:
                node_color = "#22c55e"
            else:
                node_color = "#eab308"

            nodes.append({
                "id": eid,
                "name": name,
                "entity_type": entity_type,
                "color": node_color,
                "icon": type_icons.get(entity_type, "●"),
                "size": 5,
                "x": x,
                "y": y,
                "attributes": entity.get("attributes", {}),
                "importance": importance,
            })

        # Build edge list from knowledge graph
        for edge in edges_data:
            source_id = edge.source_id
            target_id = edge.target_id
            source_node = next((n for n in nodes if n["id"] == source_id), None)
            target_node = next((n for n in nodes if n["id"] == target_id), None)
            if source_node and target_node:
                edges.append({
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship": edge.relationship,
                    "weight": edge.weight,
                })

        # Add same-type connections
        type_groups: dict[str, list[dict]] = {}
        for node in nodes:
            t = node["entity_type"]
            if t not in type_groups:
                type_groups[t] = []
            type_groups[t].append(node)

        for group_nodes in type_groups.values():
            for i in range(len(group_nodes)):
                j = (i + 1) % len(group_nodes)
                edges.append({
                    "source_id": group_nodes[i]["id"],
                    "target_id": group_nodes[j]["id"],
                    "relationship": "same_type",
                    "weight": 0.3,
                })

        # Add cross-type links
        for node in nodes:
            h = int(hashlib.md5(node["id"].encode()).hexdigest()[:4], 16)
            num_links = 1 + (h % 2)
            candidates = [n for n in nodes if n["id"] != node["id"] and n["entity_type"] != node["entity_type"]]
            if not candidates:
                continue
            rng2 = random.Random(h)
            targets = rng2.sample(candidates, min(num_links, len(candidates)))
            for target in targets:
                already = any(
                    e["source_id"] == node["id"] and e["target_id"] == target["id"]
                    for e in edges
                )
                if not already:
                    edges.append({
                        "source_id": node["id"],
                        "target_id": target["id"],
                        "relationship": "related",
                        "weight": 0.15,
                    })

        return nodes, edges

    @Slot()
    def show_window(self):
        """Show and raise the neural network viewer window."""
        if self._neural_root:
            self._neural_root.show()
            self._neural_root.raise_()
            try:
                self._neural_root.requestActivate()
            except Exception:
                pass
            self.showWindow.emit()
        else:
            logger.warning("[SocialGraph] No neural root window available")

    @Slot(str)
    def selectNode(self, node_id: str):
        try:
            if not self._knowledge_graph:
                return
            entity = self._knowledge_graph.get_entity(node_id)
            if entity:
                self.nodeSelected.emit({
                    "id": entity.get("id", ""),
                    "name": entity.get("name", "Unknown"),
                    "entity_type": entity.get("entity_type", "concept"),
                    "attributes": entity.get("attributes", {}),
                    "importance": entity.get("importance", 1.0),
                })
        except Exception as e:
            logger.error("[SocialGraph] Node selection failed: {}", e)

    @Slot(result=str)
    def getGraphStats(self) -> str:
        if not self._knowledge_graph:
            return json.dumps({"total_nodes": 0})
        stats = self._knowledge_graph.get_stats()
        return json.dumps(stats)



















