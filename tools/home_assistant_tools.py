"""
Home Assistant integration tools for Baby/BABY.
Provides control over lights, switches, climate, covers, media players, and scenes.
"""

from __future__ import annotations

import asyncio
import json
import os
import ssl
import websockets.client
import websockets.legacy.client
import websockets.legacy.protocol
import websockets.legacy.handshake
import websockets.legacy.auth
import websockets.extensions
import websockets.headers
import websockets.http
import websockets.uri
import websockets.datastructures
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import websockets
from loguru import logger


@dataclass
class HAConfig:
    """Home Assistant connection configuration."""
    url: str = ""           # e.g., "http://homeassistant.local:8123"
    token: str = ""         # Long-lived access token
    verify_ssl: bool = True
    timeout: float = 10.0


class HomeAssistantClient:
    """Async client for Home Assistant REST API and WebSocket."""

    def __init__(self, config: HAConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id = 0
        self._entity_cache: dict[str, dict] = {}

    async def connect(self) -> bool:
        """Initialize HTTP client and test connection."""
        if not self.config.url or not self.config.token:
            logger.warning("[HA] No URL or token configured")
            return False

        headers = {
            "Authorization": f"Bearer {self.config.token}",
            "Content-Type": "application/json",
        }
        ssl_ctx = None if self.config.verify_ssl else ssl.create_default_context()
        if ssl_ctx:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        self._client = httpx.AsyncClient(
            base_url=self.config.url.rstrip("/"),
            headers=headers,
            timeout=self.config.timeout,
            verify=self.config.verify_ssl,
        )

        try:
            resp = await self._client.get("/api/")
            if resp.status_code == 200:
                logger.success("[HA] Connected to Home Assistant")
                await self._refresh_entity_cache()
                return True
            logger.error("[HA] Connection failed: {}", resp.status_code)
            return False
        except Exception as e:
            logger.error("[HA] Connection error: {}", e)
            return False

    async def close(self):
        if self._client:
            await self._client.aclose()
        if self._ws:
            await self._ws.close()

    async def _refresh_entity_cache(self):
        """Fetch all entity states for local queries."""
        if not self._client:
            return
        try:
            resp = await self._client.get("/api/states")
            if resp.status_code == 200:
                states = resp.json()
                self._entity_cache = {s["entity_id"]: s for s in states}
                logger.debug("[HA] Cached {} entities", len(self._entity_cache))
        except Exception as e:
            logger.warning("[HA] Failed to refresh entity cache: {}", e)

    def get_entity(self, entity_id: str) -> Optional[dict]:
        """Get cached entity state."""
        return self._entity_cache.get(entity_id)

    def get_entities_by_domain(self, domain: str) -> list[dict]:
        """Get all entities of a specific domain (light, switch, climate, etc.)."""
        return [e for eid, e in self._entity_cache.items() if eid.startswith(f"{domain}.")]

    # ─── Core API Methods ────────────────────────────────────────────────────

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: Optional[str] = None,
        data: Optional[dict] = None,
        target: Optional[dict] = None,
    ) -> dict:
        """Call a Home Assistant service."""
        payload = dict(data or {})
        if entity_id:
            payload["entity_id"] = entity_id
        if target:
            payload["target"] = target

        if not self._client:
            return {"success": False, "error": "Home Assistant client not connected."}

        try:
            resp = await self._client.post(
                f"/api/services/{domain}/{service}",
                json=payload,
            )
            if resp.status_code in (200, 201):
                await self._refresh_entity_cache()
                return {"success": True, "result": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_state(self, entity_id: str) -> Optional[dict]:
        """Get current state of an entity."""
        if not self._client:
            return None
        try:
            resp = await self._client.get(f"/api/states/{entity_id}")
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.warning("[HA] get_state error: {}", e)
            return None

    async def get_config(self) -> dict:
        """Get Home Assistant config (for area/device info)."""
        if not self._client:
            return {}
        try:
            resp = await self._client.get("/api/config")
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception:
            return {}

    # ─── Convenience Methods ────────────────────────────────────────────────

    # Lights
    async def light_turn_on(self, entity_id: str, **kwargs) -> dict:
        return await self.call_service("light", "turn_on", entity_id=entity_id, data=kwargs)

    async def light_turn_off(self, entity_id: str, **kwargs) -> dict:
        return await self.call_service("light", "turn_off", entity_id=entity_id, data=kwargs)

    async def light_toggle(self, entity_id: str, **kwargs) -> dict:
        return await self.call_service("light", "toggle", entity_id=entity_id, data=kwargs)

    # Switches
    async def switch_turn_on(self, entity_id: str) -> dict:
        return await self.call_service("switch", "turn_on", entity_id=entity_id)

    async def switch_turn_off(self, entity_id: str) -> dict:
        return await self.call_service("switch", "turn_off", entity_id=entity_id)

    async def switch_toggle(self, entity_id: str) -> dict:
        return await self.call_service("switch", "toggle", entity_id=entity_id)

    # Climate
    async def climate_set_temperature(self, entity_id: str, temperature: float, hvac_mode: Optional[str] = None) -> dict:
        data: dict[str, Any] = {"temperature": temperature}
        if hvac_mode:
            data["hvac_mode"] = hvac_mode
        return await self.call_service("climate", "set_temperature", entity_id=entity_id, data=data)

    async def climate_set_hvac_mode(self, entity_id: str, hvac_mode: str) -> dict:
        return await self.call_service("climate", "set_hvac_mode", entity_id=entity_id, data={"hvac_mode": hvac_mode})

    async def climate_turn_off(self, entity_id: str) -> dict:
        return await self.call_service("climate", "turn_off", entity_id=entity_id)

    # Covers (blinds, garage, etc.)
    async def cover_open(self, entity_id: str) -> dict:
        return await self.call_service("cover", "open_cover", entity_id=entity_id)

    async def cover_close(self, entity_id: str) -> dict:
        return await self.call_service("cover", "close_cover", entity_id=entity_id)

    async def cover_stop(self, entity_id: str) -> dict:
        return await self.call_service("cover", "stop_cover", entity_id=entity_id)

    async def cover_set_position(self, entity_id: str, position: int) -> dict:
        return await self.call_service("cover", "set_cover_position", entity_id=entity_id, data={"position": position})

    # Media Players
    async def media_play(self, entity_id: str) -> dict:
        return await self.call_service("media_player", "media_play", entity_id=entity_id)

    async def media_pause(self, entity_id: str) -> dict:
        return await self.call_service("media_player", "media_pause", entity_id=entity_id)

    async def media_volume_set(self, entity_id: str, volume: float) -> dict:
        return await self.call_service("media_player", "volume_set", entity_id=entity_id, data={"volume_level": volume})

    async def media_select_source(self, entity_id: str, source: str) -> dict:
        return await self.call_service("media_player", "select_source", entity_id=entity_id, data={"source": source})

    # Scenes
    async def scene_activate(self, scene_id: str) -> dict:
        return await self.call_service("scene", "turn_on", entity_id=scene_id)

    # Scripts/Automations
    async def script_turn_on(self, script_id: str) -> dict:
        return await self.call_service("script", "turn_on", entity_id=script_id)

    async def automation_trigger(self, automation_id: str) -> dict:
        return await self.call_service("automation", "trigger", entity_id=automation_id)


# ─── Tool Schemas for AntiGravity ──────────────────────────────────────────

HOME_ASSISTANT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "ha_light_control",
            "description": "Control Home Assistant lights: turn on/off/toggle, set brightness, color, color temperature.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["on", "off", "toggle"], "description": "Action to perform"},
                    "entity_id": {"type": "string", "description": "Entity ID (e.g., 'light.living_room')"},
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 255, "description": "Brightness 0-255"},
                    "color_name": {"type": "string", "description": "Color name (red, blue, warm_white, etc.)"},
                    "color_temp": {"type": "integer", "description": "Color temperature in mireds (153-500)"},
                    "kelvin": {"type": "integer", "description": "Color temperature in Kelvin (2000-6500)"},
                    "transition": {"type": "number", "description": "Transition time in seconds"},
                },
                "required": ["action", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_switch_control",
            "description": "Control Home Assistant switches/outlets: turn on/off/toggle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["on", "off", "toggle"], "description": "Action to perform"},
                    "entity_id": {"type": "string", "description": "Entity ID (e.g., 'switch.outlet_1')"},
                },
                "required": ["action", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_climate_control",
            "description": "Control Home Assistant climate devices: set temperature, mode, turn off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["set_temperature", "set_mode", "off"], "description": "Action to perform"},
                    "entity_id": {"type": "string", "description": "Entity ID (e.g., 'climate.living_room')"},
                    "temperature": {"type": "number", "description": "Target temperature"},
                    "hvac_mode": {"type": "string", "enum": ["heat", "cool", "heat_cool", "auto", "dry", "fan_only", "off"], "description": "HVAC mode"},
                },
                "required": ["action", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_cover_control",
            "description": "Control Home Assistant covers (blinds, garage, shutters): open/close/stop/set_position.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open", "close", "stop", "set_position"], "description": "Action to perform"},
                    "entity_id": {"type": "string", "description": "Entity ID (e.g., 'cover.blinds_living')"},
                    "position": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Position 0-100 (for set_position)"},
                },
                "required": ["action", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_media_control",
            "description": "Control Home Assistant media players: play/pause/volume/source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["play", "pause", "volume", "source"], "description": "Action to perform"},
                    "entity_id": {"type": "string", "description": "Entity ID (e.g., 'media_player.living_room_tv')"},
                    "volume": {"type": "number", "minimum": 0, "maximum": 1, "description": "Volume level 0.0-1.0"},
                    "source": {"type": "string", "description": "Source/input name"},
                },
                "required": ["action", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_scene_activate",
            "description": "Activate a Home Assistant scene.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scene_id": {"type": "string", "description": "Scene entity ID (e.g., 'scene.movie_night')"},
                },
                "required": ["scene_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_script_run",
            "description": "Run a Home Assistant script.",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_id": {"type": "string", "description": "Script entity ID (e.g., 'script.good_morning')"},
                },
                "required": ["script_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_get_state",
            "description": "Get current state of any Home Assistant entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string", "description": "Entity ID to query"},
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ha_list_entities",
            "description": "List all entities, optionally filtered by domain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "Optional domain filter (light, switch, climate, cover, media_player, scene, script, sensor, binary_sensor)"},
                    "area": {"type": "string", "description": "Optional area name filter"},
                },
                "required": [],
            },
        },
    },
]

HOME_ASSISTANT_TOOL_RISK = {
    "ha_light_control": "low",
    "ha_switch_control": "low",
    "ha_climate_control": "medium",
    "ha_cover_control": "medium",
    "ha_media_control": "low",
    "ha_scene_activate": "low",
    "ha_script_run": "medium",
    "ha_get_state": "low",
    "ha_list_entities": "low",
}

# ─── Tool Execution Functions ──────────────────────────────────────────────

_ha_client: Optional[HomeAssistantClient] = None


def _get_ha_client() -> Optional[HomeAssistantClient]:
    global _ha_client
    return _ha_client


def set_ha_client(client: Optional[HomeAssistantClient]):
    global _ha_client
    _ha_client = client


def execute_ha_tool(name: str, args: dict) -> dict:
    """Execute a Home Assistant tool by name."""
    client = _get_ha_client()
    if not client:
        return {"success": False, "error": "Home Assistant not configured. Set URL and token in config.yaml."}

    try:
        if name == "ha_light_control":
            return asyncio.run(_exec_light(client, args))
        elif name == "ha_switch_control":
            return asyncio.run(_exec_switch(client, args))
        elif name == "ha_climate_control":
            return asyncio.run(_exec_climate(client, args))
        elif name == "ha_cover_control":
            return asyncio.run(_exec_cover(client, args))
        elif name == "ha_media_control":
            return asyncio.run(_exec_media(client, args))
        elif name == "ha_scene_activate":
            return asyncio.run(_exec_scene(client, args))
        elif name == "ha_script_run":
            return asyncio.run(_exec_script(client, args))
        elif name == "ha_get_state":
            return asyncio.run(_exec_get_state(client, args))
        elif name == "ha_list_entities":
            return asyncio.run(_exec_list_entities(client, args))
        else:
            return {"success": False, "error": f"Unknown HA tool: {name}"}
    except Exception as e:
        logger.error("[HA] Tool execution error: {}", e)
        return {"success": False, "error": str(e)}


async def _exec_light(client: HomeAssistantClient, args: dict) -> dict:
    action = args["action"]
    entity_id = args["entity_id"]
    data = {k: v for k, v in args.items() if k not in ("action", "entity_id")}
    if action == "on":
        return await client.light_turn_on(entity_id, **data)
    elif action == "off":
        return await client.light_turn_off(entity_id, **data)
    else:
        return await client.light_toggle(entity_id, **data)


async def _exec_switch(client: HomeAssistantClient, args: dict) -> dict:
    action = args["action"]
    entity_id = args["entity_id"]
    if action == "on":
        return await client.switch_turn_on(entity_id)
    elif action == "off":
        return await client.switch_turn_off(entity_id)
    else:
        return await client.switch_toggle(entity_id)


async def _exec_climate(client: HomeAssistantClient, args: dict) -> dict:
    action = args["action"]
    entity_id = args["entity_id"]
    if action == "set_temperature":
        raw_temp = args.get("temperature")
        if raw_temp is None:
            return {"success": False, "error": "Missing 'temperature' argument"}
        try:
            temp = float(raw_temp)
        except (ValueError, TypeError):
            return {"success": False, "error": f"Invalid temperature value: {raw_temp}"}
        mode = args.get("hvac_mode")
        mode_str = str(mode) if mode is not None else None
        return await client.climate_set_temperature(entity_id, temp, mode_str)
    elif action == "set_mode":
        mode = args.get("hvac_mode")
        if not mode:
            return {"success": False, "error": "Missing 'hvac_mode' argument"}
        return await client.climate_set_hvac_mode(entity_id, str(mode))
    else:
        return await client.climate_turn_off(entity_id)


async def _exec_cover(client: HomeAssistantClient, args: dict) -> dict:
    action = args["action"]
    entity_id = args["entity_id"]
    if action == "open":
        return await client.cover_open(entity_id)
    elif action == "close":
        return await client.cover_close(entity_id)
    elif action == "stop":
        return await client.cover_stop(entity_id)
    else:
        pos = args.get("position", 50)
        return await client.cover_set_position(entity_id, pos)


async def _exec_media(client: HomeAssistantClient, args: dict) -> dict:
    action = args["action"]
    entity_id = args["entity_id"]
    if action == "play":
        return await client.media_play(entity_id)
    elif action == "pause":
        return await client.media_pause(entity_id)
    elif action == "volume":
        vol = args.get("volume", 0.5)
        return await client.media_volume_set(entity_id, vol)
    else:
        src = args.get("source", "")
        return await client.media_select_source(entity_id, src)


async def _exec_scene(client: HomeAssistantClient, args: dict) -> dict:
    return await client.scene_activate(args["scene_id"])


async def _exec_script(client: HomeAssistantClient, args: dict) -> dict:
    return await client.script_turn_on(args["script_id"])


async def _exec_get_state(client: HomeAssistantClient, args: dict) -> dict:
    state = await client.get_state(args["entity_id"])
    if state:
        return {"success": True, "state": state}
    return {"success": False, "error": "Entity not found"}


async def _exec_list_entities(client: HomeAssistantClient, args: dict) -> dict:
    domain = args.get("domain")
    if domain:
        entities = client.get_entities_by_domain(domain)
    else:
        entities = list(client._entity_cache.values())
    return {"success": True, "entities": entities}


















