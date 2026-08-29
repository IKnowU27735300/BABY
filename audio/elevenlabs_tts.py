"""
ElevenLabs TTS Integration for Baby/BABY
Provides natural, expressive voices with multi-language support (English + Hindi)
"""

from __future__ import annotations

import asyncio
import base64
import os
from dataclasses import dataclass
from typing import Optional, AsyncIterator

import httpx
from loguru import logger


@dataclass
class ElevenLabsConfig:
    api_key: str
    base_url: str = "https://api.elevenlabs.io/v1"
    timeout: float = 30.0


@dataclass
class VoiceSettings:
    stability: float = 0.5          # 0-1: lower = more expressive
    similarity_boost: float = 0.75  # 0-1: higher = more similar to original
    style: float = 0.5              # 0-1: style exaggeration
    use_speaker_boost: bool = True  # boost similarity


class ElevenLabsTTS:
    """
    ElevenLabs TTS client with streaming support.
    Supports multi-language (English + Hindi) with natural, expressive voices.
    """

    # Pre-configured voice IDs for Indian English + Hindi
    VOICES = {
        "naughty_indian": {
            "id": "JBFqnCBsd6RMkjVDRZzb",  # User's preferred voice
            "name": "Naughty Indian",
            "description": "Playful, expressive Indian voice for English + Hindi",
            "languages": ["en", "hi"],
        },
        "indian_female": {
            "id": "EXAVITQu4vr4xnSDxMaL",  # Bella - good for Indian accent
            "name": "Indian Female",
            "description": "Warm Indian female voice",
            "languages": ["en", "hi"],
        },
        "indian_male": {
            "id": "TxGEqnHWrfWFTfGW9XjX",  # Josh - Indian male
            "name": "Indian Male",
            "description": "Confident Indian male voice",
            "languages": ["en", "hi"],
        },
    }

    def __init__(self, config: ElevenLabsConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            headers={
                "xi-api-key": self.config.api_key,
                "Content-Type": "application/json",
            },
            timeout=self.config.timeout,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    async def text_to_speech(
        self,
        text: str,
        voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
        model_id: str = "eleven_multilingual_v2",
        voice_settings: Optional[VoiceSettings] = None,
        output_format: str = "mp3_44100_128",
    ) -> bytes:
        """
        Convert text to speech and return audio bytes.
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        settings = voice_settings or VoiceSettings()

        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": settings.stability,
                "similarity_boost": settings.similarity_boost,
                "style": settings.style,
                "use_speaker_boost": settings.use_speaker_boost,
            },
        }

        url = f"/text-to-speech/{voice_id}"
        params = {"output_format": output_format}

        try:
            response = await self._client.post(url, json=payload, params=params)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as e:
            logger.error("[ElevenLabs] HTTP error: {} - {}", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("[ElevenLabs] Error: {}", e)
            raise

    async def text_to_speech_stream(
        self,
        text: str,
        voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
        model_id: str = "eleven_multilingual_v2",
        voice_settings: Optional[VoiceSettings] = None,
        output_format: str = "mp3_44100_128",
        chunk_size: int = 1024,
    ) -> AsyncIterator[bytes]:
        """
        Stream text to speech as audio chunks.
        """
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        settings = voice_settings or VoiceSettings()

        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": settings.stability,
                "similarity_boost": settings.similarity_boost,
                "style": settings.style,
                "use_speaker_boost": settings.use_speaker_boost,
            },
        }

        url = f"/text-to-speech/{voice_id}/stream"
        params = {"output_format": output_format}

        try:
            async with self._client.stream("POST", url, json=payload, params=params) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size):
                    if chunk:
                        yield chunk
        except httpx.HTTPStatusError as e:
            logger.error("[ElevenLabs] HTTP error: {} - {}", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("[ElevenLabs] Stream error: {}", e)
            raise

    async def get_voices(self) -> list[dict]:
        """Get all available voices."""
        if not self._client:
            raise RuntimeError("Client not initialized.")
        response = await self._client.get("/voices")
        response.raise_for_status()
        return response.json().get("voices", [])

    async def get_voice(self, voice_id: str) -> dict:
        """Get details for a specific voice."""
        if not self._client:
            raise RuntimeError("Client not initialized.")
        response = await self._client.get(f"/voices/{voice_id}")
        response.raise_for_status()
        return response.json()

    def save_audio(self, audio_bytes: bytes, filepath: str):
        """Save audio bytes to file."""
        with open(filepath, "wb") as f:
            f.write(audio_bytes)
        logger.info("[ElevenLabs] Saved audio to {}", filepath)


# ─── Convenience Functions ────────────────────────────────────────────────

async def speak_with_elevenlabs(
    text: str,
    api_key: str,
    voice_id: str = "JBFqnCBsd6RMkjVDRZzb",
    language: str = "en",
    save_path: Optional[str] = None,
) -> bytes:
    """
    One-shot function to generate speech with ElevenLabs.
    """
    config = ElevenLabsConfig(api_key=api_key)
    async with ElevenLabsTTS(config) as tts:
        # Adjust voice settings based on language
        if language == "hi":
            # Slightly different settings for Hindi
            settings = VoiceSettings(stability=0.4, similarity_boost=0.8, style=0.6)
        else:
            settings = VoiceSettings(stability=0.5, similarity_boost=0.75, style=0.5)

        audio = await tts.text_to_speech(text, voice_id=voice_id, voice_settings=settings)

        if save_path:
            tts.save_audio(audio, save_path)

        return audio


# ─── Example Usage ────────────────────────────────────────────────────────

async def main():
    """Demo: Generate speech with the naughty Indian voice."""
    API_KEY = "9535da8b8ec7b6b211a03cc650be70d3faed6b1376036ffd13ddaa754b913edb"

    # English
    english_text = "Hello there, handsome! Ready for some fun? I've been waiting for you all day."
    
    # Hindi
    hindi_text = "नमस्ते जी! कैसे हो आप? आज बहुत मज़ा आएगा, तुम देखना!"

    async with ElevenLabsTTS(ElevenLabsConfig(api_key=API_KEY)) as tts:
        # English with naughty Indian voice
        print("Generating English...")
        english_audio = await tts.text_to_speech(
            english_text,
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            voice_settings=VoiceSettings(stability=0.4, similarity_boost=0.8, style=0.7),
        )
        with open("english_naughty.mp3", "wb") as f:
            f.write(english_audio)

        # Hindi with same voice
        print("Generating Hindi...")
        hindi_audio = await tts.text_to_speech(
            hindi_text,
            voice_id="JBFqnCBsd6RMkjVDRZzb",
            voice_settings=VoiceSettings(stability=0.3, similarity_boost=0.85, style=0.8),
        )
        with open("hindi_naughty.mp3", "wb") as f:
            f.write(hindi_audio)

        print("Done! Files saved: english_naughty.mp3, hindi_naughty.mp3")


if __name__ == "__main__":
    asyncio.run(main())


















