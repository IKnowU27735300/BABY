"""
core/seed_memory.py — Pre-seed Baby's memory with user information and common knowledge.

Run this script to populate Baby's memory with known facts about the user,
common commands, and frequently used applications. This ensures Baby can
personalize responses from the very first conversation.

Usage:
    python -m core.seed_memory              # Interactive mode - prompts for info
    python -m core.seed_memory --defaults   # Use default profile
    python -m core.seed_memory --clear      # Clear all memory
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from loguru import logger

_MEMORY_FILE = Path("data/personal_memory.json")


def _load_existing() -> dict:
    """Load existing memory file if it exists."""
    if _MEMORY_FILE.exists():
        try:
            return json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load existing memory: {}", e)
    return {}


def _save_memory(data: dict) -> None:
    """Save memory data to file."""
    _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _MEMORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.success("Memory saved to {}", _MEMORY_FILE)


def seed_interactive() -> None:
    """Interactively seed memory with user information."""
    print("\n=== Baby Memory Seed ===")
    print("Help Baby remember everything about you!\n")

    existing = _load_existing()
    profile = existing.get("profile", {})

    # Get user name
    current_name = profile.get("name", "")
    name = input(f"Your name [{current_name or 'skip'}]: ").strip()
    if name:
        profile["name"] = name

    # Get occupation
    facts = profile.get("facts", {})
    current_occ = facts.get("occupation", "")
    occupation = input(f"What do you do? (job/study) [{current_occ or 'skip'}]: ").strip()
    if occupation:
        facts["occupation"] = occupation

    # Get location
    current_loc = facts.get("location", "")
    location = input(f"Where do you live? [{current_loc or 'skip'}]: ").strip()
    if location:
        facts["location"] = location

    # Get favorite things
    current_fav_color = facts.get("color", "")
    fav_color = input(f"Favorite color [{current_fav_color or 'skip'}]: ").strip()
    if fav_color:
        facts["color"] = fav_color

    current_fav_food = facts.get("food", "")
    fav_food = input(f"Favorite food [{current_fav_food or 'skip'}]: ").strip()
    if fav_food:
        facts["food"] = fav_food

    current_fav_music = facts.get("music", "")
    fav_music = input(f"Favorite music/artist [{current_fav_music or 'skip'}]: ").strip()
    if fav_music:
        facts["music"] = fav_music

    current_fav_movie = facts.get("movie", "")
    fav_movie = input(f"Favorite movie/show [{current_fav_movie or 'skip'}]: ").strip()
    if fav_movie:
        facts["movie"] = fav_movie

    # Get preferred language
    lang_counts = profile.get("lang_counts", {"en": 0, "hi": 0, "kn": 0})
    print("\nPreferred language:")
    print("  1. English")
    print("  2. Hindi")
    print("  3. Kannada")
    lang_choice = input("Choose [1/2/3]: ").strip()
    lang_map = {"1": "en", "2": "hi", "3": "kn"}
    if lang_choice in lang_map:
        profile["preferred_lang"] = lang_map[lang_choice]

    # Get frequently used apps
    apps = profile.get("frequent_apps", [])
    print(f"\nFrequently used apps (current: {', '.join(apps[:5]) if apps else 'none'})")
    print("Enter apps separated by commas (e.g., vscode, chrome, spotify)")
    apps_input = input("Add apps: ").strip()
    if apps_input:
        new_apps = [a.strip().lower() for a in apps_input.split(",") if a.strip()]
        for app in new_apps:
            if app not in apps:
                apps.append(app)
        profile["frequent_apps"] = apps[:20]

    # Get schedules
    schedules = profile.get("schedules", [])
    print(f"\nKnown schedules (current: {', '.join(schedules[:3]) if schedules else 'none'})")
    print("Enter schedules (e.g., 'every morning at 8', 'remind me at 7pm daily')")
    sched_input = input("Add schedule: ").strip()
    if sched_input and sched_input not in schedules:
        schedules.append(sched_input)
        profile["schedules"] = schedules[:10]

    # Get additional memories
    print("\nAdditional things to remember (enter to skip):")
    memories = [
        ("Pet's name", "pet_name"),
        ("Partner's name", "partner_name"),
        ("Birthday", "birthday"),
        ("Workplace", "workplace"),
        ("Hobbies", "hobbies"),
    ]
    for label, key in memories:
        current = facts.get(key, "")
        value = input(f"  {label} [{current or 'skip'}]: ").strip()
        if value:
            facts[key] = value

    # Update profile
    profile["facts"] = facts

    # Build complete memory structure
    data = existing.copy()
    data["profile"] = profile
    data.setdefault("vocab", {"en": {}, "hi": {}, "kn": {}})
    data.setdefault("cmd_cache", {})
    data.setdefault("corrections", [])

    _save_memory(data)
    print("\n✓ Baby's memory has been updated!")
    print("She will remember all this information in future conversations.\n")


def seed_defaults() -> None:
    """Seed with a default profile (for testing)."""
    existing = _load_existing()
    profile = existing.get("profile", {})
    facts = profile.get("facts", {})

    # Only set defaults if not already set
    if not profile.get("name"):
        profile["name"] = "User"
    if not profile.get("preferred_lang"):
        profile["preferred_lang"] = "en"
    if not profile.get("frequent_apps"):
        profile["frequent_apps"] = ["chrome", "vscode", "notepad", "spotify", "whatsapp"]
    if not facts:
        facts = {
            "occupation": "Developer",
            "location": "India",
            "hobbies": "Programming, music",
        }
        profile["facts"] = facts

    data = existing.copy()
    data["profile"] = profile
    data.setdefault("vocab", {"en": {}, "hi": {}, "kn": {}})
    data.setdefault("cmd_cache", {})
    data.setdefault("corrections", [])

    _save_memory(data)
    print("✓ Default memory profile seeded.\n")


def clear_memory() -> None:
    """Clear all memory."""
    if _MEMORY_FILE.exists():
        _MEMORY_FILE.unlink()
        print("✓ Memory cleared.")
    else:
        print("No memory file to clear.")


def show_memory() -> None:
    """Display current memory contents."""
    data = _load_existing()
    if not data:
        print("No memory data found.")
        return

    profile = data.get("profile", {})
    print("\n=== Baby's Memory ===")
    print(f"Name: {profile.get('name', 'Unknown')}")
    print(f"Preferred language: {profile.get('preferred_lang', 'Unknown')}")
    print(f"Frequent apps: {', '.join(profile.get('frequent_apps', []))}")
    print(f"Schedules: {', '.join(profile.get('schedules', []))}")

    facts = profile.get("facts", {})
    if facts:
        print("Personal facts:")
        for k, v in facts.items():
            print(f"  {k}: {v}")

    vocab = data.get("vocab", {})
    total_vocab = sum(len(v) for v in vocab.values())
    print(f"Vocabulary entries: {total_vocab}")
    print(f"Cached commands: {len(data.get('cmd_cache', {}))}")
    print(f"Corrections: {len(data.get('corrections', []))}")
    print()


if __name__ == "__main__":
    if "--clear" in sys.argv:
        clear_memory()
    elif "--defaults" in sys.argv:
        seed_defaults()
    elif "--show" in sys.argv:
        show_memory()
    else:
        seed_interactive()



















