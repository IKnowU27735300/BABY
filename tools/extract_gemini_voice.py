"""
tools/extract_gemini_voice.py — Utility script to generate a reference WAV file of the Gemini Kore/Puck voices.
Used for offline voice cloning in Coqui XTTS-v2.
"""

import os
import sys
import json
import base64
import wave
import urllib.request
import urllib.error
import time
from pathlib import Path

# Script of ~12 seconds with diverse phonetic sounds for optimal cloning
DEFAULT_SCRIPT = (
    "Hello! I am your companion assistant. I can help you manage your tasks, "
    "control your desktop, and chat about anything you like. Let's make today productive and fun!"
)

def generate_voice(api_key: str, voice_name: str, text: str, output_path: Path):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent?key={api_key}"
    
    payload = {
        "contents": [{"parts": [{"text": f"[read] {text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name
                    }
                }
            }
        }
    }
    
    print(f"Requesting '{voice_name}' voice from Gemini API...")
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    max_retries = 3
    retry_delay = 5
    res_data = None
    
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                print(f"Rate limited (429). Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"Error calling API: {e}", file=sys.stderr)
                try:
                    error_details = e.read().decode("utf-8")
                    print(f"Details: {error_details}", file=sys.stderr)
                except Exception:
                    pass
                sys.exit(1)
        except Exception as e:
            print(f"Error calling API: {e}", file=sys.stderr)
            sys.exit(1)
        
    if res_data is None:
        print("Error: No response received from Gemini API.", file=sys.stderr)
        sys.exit(1)
        
    try:
        base64_audio = res_data['candidates'][0]['content']['parts'][0]['inlineData']['data']
    except (KeyError, IndexError):
        print("Error: API response did not contain audio data.", file=sys.stderr)
        print("Response:", json.dumps(res_data, indent=2), file=sys.stderr)
        sys.exit(1)
        
    pcm_bytes = base64.b64decode(base64_audio)
    
    # Save raw 16-bit 24kHz mono PCM data as WAV
    print(f"Writing audio to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), 'wb') as wav_file:
        wav_file.setnchannels(1)       # Mono
        wav_file.setsampwidth(2)       # 16-bit (2 bytes)
        wav_file.setframerate(24000)   # 24kHz
        wav_file.writeframes(pcm_bytes)
        
    print(f"Successfully saved {voice_name} reference WAV to {output_path}!")

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY environment variable not found.")
        api_key = input("Please enter your Gemini API Key: ").strip()
        if not api_key:
            print("API Key is required to generate the voice.", file=sys.stderr)
            sys.exit(1)
            
    print("\n--- Gemini Voice Extractor ---")
    print("1) Mahiru (Female - Soft, warm, Mahiru's default)")
    print("2) Puck (Male - Friendly, casual, Dost/Bhai mode)")
    choice = input("Choose voice (1 or 2, default: 1): ").strip()
    
    voice_name = "Puck" if choice == "2" else "Kore"
    display_name = "mahiru" if voice_name == "Kore" else "puck"
    
    output_filename = f"{display_name}_reference.wav"
    output_path = Path("data") / output_filename
    
    generate_voice(api_key, voice_name, DEFAULT_SCRIPT, output_path)
    
    print("\nTo use this voice in Baby for offline XTTS cloning:")
    print(f"1. Set 'voice: data/{display_name}_reference.wav' or 'voice: Mahiru' in your config.yaml")
    print("2. Set 'engine: xtts' in your config.yaml")

if __name__ == "__main__":
    main()



















