"""
core/memory_engine.py — Baby's Adaptive Learning & Personal Memory System.

Every conversation turn is observed and distilled into five persistent stores:

  1. personal_vocab   — words/phrases the user says frequently.
                        Fed back to Whisper as initial_prompt so it recognises
                        the user's personal lexicon with higher accuracy.

  2. user_profile     — facts Baby has learned about the user: name, preferred
                        language, frequently-used apps, schedules, preferences.
                        Injected into the LLM system prompt every turn.

  3. command_cache    — maps frequently-repeated commands to their last known
                        responses or action patterns so Baby can answer
                        instantly (sub-second) without an LLM round-trip.

  4. correction_log   — every time the user says "no, I meant …" or similar,
                        the original/corrected pair is saved so future
                        transcriptions avoid the same mistake.

  5. knowledge_graph  — neural network-like associative memory where all
                        information is interconnected. Mentioning "John" 
                        surfaces his email, projects, preferences, and 
                        related deadlines automatically.

All data is stored in data/personal_memory.json and data/knowledge_graph.json 
(local, never leaves device).
Saving is non-blocking (runs in a background thread).
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque

from loguru import logger

from core.knowledge_graph import knowledge_graph, auto_connect_entities, extract_entities_from_text

# ─── Storage paths ─────────────────────────────────────────────────────────────
_MEMORY_FILE = Path("data/personal_memory.json")

# ─── Correction trigger phrases ────────────────────────────────────────────────
_CORRECTION_PATTERNS = [
    r"\bno[,.]?\s+i (?:meant|said|wanted)\b",
    r"\bthat's? (?:wrong|incorrect)\b",
    r"\bactually[,.]?\s+(?:i meant|do)\b",
    r"\bnot that[,.]?\s+i meant\b",
    r"\bcorrect (?:that|it)\b",
    r"\bनहीं[,।]?\s+मुझे (?:कहना था|चाहिए था)\b",
    r"\bಇಲ್ಲ[,.]?\s+ನಾನು (?:ಹೇಳಬೇಕಿತ್ತು|ಅರ್ಥ ಮಾಡಿದ್ದು)\b",
]
_CORRECTION_RE = re.compile("|".join(_CORRECTION_PATTERNS), re.IGNORECASE)


class MemoryEngine:
    """
    Baby's adaptive, persistent personal memory.

    Usage in orchestrator (after every conversation turn):
        memory.record_turn(user_text, user_lang, assistant_response, action_taken)

    Usage for STT priming (in stt.py):
        memory.get_stt_vocab_hint(lang)  # → str to append to initial_prompt

    Usage for LLM priming (in context_manager.py):
        memory.get_profile_system_block()  # → str to inject as system message
    """

    # Max vocabulary entries per language (oldest replaced when full)
    _MAX_VOCAB = 300
    # Max command cache entries (LRU)
    _MAX_CACHE = 200
    # Min times a command must appear before it's cached for fast-path
    _CACHE_MIN_HITS = 1
    # Rolling window for frequency analysis
    _FREQ_WINDOW = 50

    def __init__(self):
        self._lock = threading.Lock()
        self._save_lock = threading.Lock()
        self._dirty = False

        # ── Vocabulary: {lang: Counter(phrase → count)} ───────────────────────
        self._vocab: dict[str, Counter] = {"en": Counter(), "hi": Counter(), "kn": Counter()}

        # ── User profile: free-form key→value dict ────────────────────────────
        self._profile: dict[str, Any] = {
            "name": None,
            "preferred_lang": None,
            "frequent_apps": [],
            "preferences": {},
            "schedules": [],
            "last_seen": None,
        }

        # ── Command cache: text_key → {response, action, hits, last_used} ─────
        self._cmd_cache: dict[str, dict] = {}

        # ── Correction log: [(wrong, corrected, lang, ts)] ───────────────────
        self._corrections: list[dict] = []

        # ── Rolling turn buffer for analysis ─────────────────────────────────
        self._recent_turns: Deque[dict] = deque(maxlen=self._FREQ_WINDOW)

        # ── Session stats ─────────────────────────────────────────────────────
        self._session_turns = 0
        self._session_start = datetime.now().isoformat()

        # Load persisted memory from disk
        self._load()

    # ─── Public: called once per conversation turn ────────────────────────────

    def record_turn(
        self,
        user_text: str,
        user_lang: str,
        assistant_response: str,
        action_taken: str | None = None,
    ) -> None:
        """
        Observe one complete conversation turn and update all learning stores.
        Thread-safe; save is asynchronous.
        """
        if not user_text.strip():
            return

        with self._lock:
            self._session_turns += 1
            ts = datetime.now().isoformat()

            turn = {
                "user": user_text,
                "lang": user_lang,
                "assistant": assistant_response,
                "action": action_taken,
                "ts": ts,
            }
            self._recent_turns.append(turn)

            # 1. Vocabulary learning
            self._learn_vocab(user_text, user_lang)

            # 2. Profile inference
            self._infer_profile(user_text, user_lang, assistant_response)

            # 3. Command caching
            self._learn_command_cache(user_text, user_lang, assistant_response, action_taken)

            # 4. Correction detection
            self._detect_correction(user_text, user_lang)

            # 5. Knowledge graph: auto-extract entities and create connections
            self._update_knowledge_graph(user_text, assistant_response)

            # 6. Update profile's last_seen
            self._profile["last_seen"] = ts

            self._dirty = True

        # Non-blocking persist (every turn, on a background thread)
        threading.Thread(target=self._save_if_dirty, daemon=True).start()

    # ─── Public: query interface for STT ──────────────────────────────────────

    def get_stt_vocab_hint(self, lang: str) -> str:
        """
        Return a compact string of the user's top personal vocabulary for the
        given language.  Append this to Whisper's initial_prompt — Whisper
        will bias toward these words, dramatically improving recognition of
        names, app names, and personal commands.
        """
        with self._lock:
            vocab = self._vocab.get(lang, Counter())
            if not vocab:
                return ""
            # Top 40 most frequent personal terms
            top = [phrase for phrase, _ in vocab.most_common(40)]
            return ", ".join(top)

    # ─── Public: query interface for LLM ──────────────────────────────────────

    def get_profile_system_block(self) -> str:
        """
        Return a short system-message fragment injecting what Baby has learned
        about the user — their name, preferences, frequently-used apps, etc.
        Inject this early in every LLM call so the model can personalize replies.
        """
        with self._lock:
            lines: list[str] = []
            p = self._profile

            if p.get("name"):
                lines.append(f"User's name: {p['name']}")
            if p.get("preferred_lang"):
                lang_names = {"en": "English", "hi": "Hindi", "kn": "Kannada"}
                lines.append(f"User's preferred language: {lang_names.get(p['preferred_lang'], p['preferred_lang'])}")
            if p.get("frequent_apps"):
                apps = ", ".join(p["frequent_apps"][:6])
                lines.append(f"Frequently used apps: {apps}")
            if p.get("preferences"):
                prefs = "; ".join(f"{k}: {v}" for k, v in list(p["preferences"].items())[:5])
                lines.append(f"Known preferences: {prefs}")
            if p.get("schedules"):
                scheds = "; ".join(p["schedules"][:3])
                lines.append(f"Known schedule patterns: {scheds}")
            if p.get("facts"):
                facts = "; ".join(f"{k}: {v}" for k, v in list(p["facts"].items())[:8])
                lines.append(f"Personal facts: {facts}")

            # Recent corrections to avoid repeating mistakes
            if self._corrections:
                last = self._corrections[-3:]
                pairs = "; ".join(f"\"{c['wrong']}\" → \"{c['corrected']}\"" for c in last)
                lines.append(f"Recent transcription corrections: {pairs}")

            if not lines:
                return ""

            block = (
                "ADAPTIVE USER PROFILE (learned from past interactions):\n"
                + "\n".join(f"  • {l}" for l in lines)
                + "\n"
                + f"  • Total interactions so far: {self._session_turns}\n"
            )
            return block

    def memory_recall(self, query: str) -> str:
        """
        Search stored memory for information matching the query.
        Returns a formatted string of matching facts, or empty string if nothing found.
        Used by the LLM to retrieve what it knows about the user.
        Now includes knowledge graph queries for associative recall.
        """
        query_lower = query.lower()
        results: list[str] = []

        with self._lock:
            p = self._profile

            # Check name
            if p.get("name") and any(w in query_lower for w in ("name", "who am i", "what's my name", "मेरा नाम", "ನನ್ನ ಹೆಸರು")):
                results.append(f"User's name: {p['name']}")

            # Check preferred language
            if p.get("preferred_lang") and any(w in query_lower for w in ("language", "preferred", "भाषा", "ಭಾಷೆ")):
                lang_names = {"en": "English", "hi": "Hindi", "kn": "Kannada"}
                results.append(f"Preferred language: {lang_names.get(p['preferred_lang'], p['preferred_lang'])}")

            # Check apps
            if p.get("frequent_apps") and any(w in query_lower for w in ("app", "application", "use", "open", "ऐप", "ಆ್ಯಪ್")):
                results.append(f"Frequently used apps: {', '.join(p['frequent_apps'][:8])}")

            # Check preferences
            if p.get("preferences"):
                for k, v in p["preferences"].items():
                    if any(word in query_lower for word in v.lower().split()[:3]):
                        results.append(f"Preference: {v}")

            # Check facts - more robust matching
            if p.get("facts"):
                for k, v in p["facts"].items():
                    # Match if query words appear in fact key or value
                    query_words = query_lower.split()
                    fact_key_words = k.lower().replace("_", " ").split()
                    fact_val_words = v.lower().split()

                    # Check if any query word matches fact key or value
                    for qw in query_words:
                        if len(qw) >= 3:  # Only match words with 3+ chars
                            if any(qw in fkw for fkw in fact_key_words):
                                results.append(f"{k}: {v}")
                                break
                            if any(qw in fvw for fvw in fact_val_words):
                                results.append(f"{k}: {v}")
                                break
                            # Also check for partial matches (e.g., "work" matches "occupation")
                            if qw in ("work", "job", "occupation", "career", "ನನ್ನ ಕೆಲಸ"):
                                if k in ("occupation", "workplace"):
                                    results.append(f"{k}: {v}")
                                    break
                            if qw in ("favorite", "fav", "like", "love", "ಪ್ರೀತಿಯ"):
                                if k.startswith("favorite") or k in ("color", "food", "music", "movie"):
                                    results.append(f"{k}: {v}")
                                    break

            # Check schedules
            if p.get("schedules") and any(w in query_lower for w in ("schedule", "routine", "time", "routine", "समय", "ಸಮಯ")):
                results.append(f"Schedules: {', '.join(p['schedules'][:3])}")

            # Check corrections
            if self._corrections and any(w in query_lower for w in ("correct", "mistake", "wrong", "error")):
                last = self._corrections[-3:]
                pairs = "; ".join(f"\"{c['wrong']}\" → \"{c['corrected']}\"" for c in last)
                results.append(f"Recent corrections: {pairs}")

        # Knowledge Graph: Associative recall
        try:
            # Search for matching entities in the knowledge graph
            kg_results = knowledge_graph.search(query, max_results=5)
            if kg_results:
                for item in kg_results:
                    entity = item["entity"]
                    entity_name = entity["name"]
                    entity_type = entity["entity_type"]
                    attrs = entity.get("attributes", {})
                    
                    # Format entity info
                    info_parts = [f"{entity_type}: {entity_name}"]
                    for k, v in attrs.items():
                        if v:
                            info_parts.append(f"{k}: {v}")
                    results.append(" | ".join(info_parts))
                    
                    # Get related entities (associative recall)
                    related = knowledge_graph.query(entity["id"], max_depth=1, max_results=3)
                    for rel in related:
                        rel_entity = rel["entity"]
                        rel_name = rel_entity["name"]
                        rel_type = rel_entity["entity_type"]
                        rel_attrs = rel_entity.get("attributes", {})
                        
                        # Find the relationship
                        connections = rel.get("connections", [])
                        relationship = connections[0]["relationship"] if connections else "related_to"
                        
                        rel_info = [f"  → {relationship}: {rel_type} {rel_name}"]
                        for k, v in rel_attrs.items():
                            if v:
                                rel_info.append(f"    {k}: {v}")
                        results.append(" | ".join(rel_info))
        except Exception as e:
            logger.error("[Memory] Knowledge graph recall failed: {}", e)

        if results:
            return "Memory recall:\n" + "\n".join(f"  • {r}" for r in results)
        return ""

    # ─── Public: fast command cache lookup ────────────────────────────────────

    def get_cached_response(self, user_text: str, user_lang: str) -> str | None:
        """
        Check if this exact (or very similar) command has a cached response.
        Returns the cached response string if found, None otherwise.
        Only returns cache hits for commands seen at least _CACHE_MIN_HITS times.
        """
        key = self._cache_key(user_text, user_lang)
        with self._lock:
            entry = self._cmd_cache.get(key)
            if entry and entry.get("hits", 0) >= self._CACHE_MIN_HITS:
                entry["last_used"] = datetime.now().isoformat()
                logger.debug("[Memory] Fast-path cache hit for: '{}'", user_text[:50])
                return entry.get("response")
        return None

    # ─── Internal: vocabulary learning ───────────────────────────────────────

    def _learn_vocab(self, text: str, lang: str) -> None:
        """Extract meaningful n-grams from the user's speech and count them."""
        if lang not in self._vocab:
            self._vocab[lang] = Counter()

        words = self._tokenize(text)
        # Unigrams (single meaningful words)
        stop_words = {
            "i", "a", "the", "is", "it", "in", "on", "and", "or", "to", "of",
            "me", "my", "can", "do", "you", "please", "baby", "बेबी", "ಬೇಬಿ",
            "that", "this", "for", "with", "what", "how", "are",
        }
        for w in words:
            if len(w) >= 3 and w not in stop_words:
                self._vocab[lang][w] += 1

        # Bigrams (two-word phrases)
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if len(bigram) >= 6:
                self._vocab[lang][bigram] += 1

        # Prune to max size
        if len(self._vocab[lang]) > self._MAX_VOCAB:
            # Keep the most frequent _MAX_VOCAB entries
            top = self._vocab[lang].most_common(self._MAX_VOCAB)
            self._vocab[lang] = Counter(dict(top))

    def _tokenize(self, text: str) -> list[str]:
        """Simple word tokenizer that handles Latin, Devanagari and Kannada scripts."""
        # Split on whitespace and punctuation
        words = re.findall(r"[\w\u0900-\u097F\u0C80-\u0CFF]+", text.lower())
        return [w for w in words if len(w) >= 2]

    # ─── Internal: profile inference ─────────────────────────────────────────

    _APP_NAMES = [
        "chrome", "firefox", "edge", "notepad", "word", "excel", "powerpoint",
        "vlc", "spotify", "youtube", "whatsapp", "telegram", "vs code", "vscode",
        "paint", "calculator", "terminal", "cmd", "file explorer", "control panel",
        "zoom", "teams", "slack", "discord", "photoshop", "blender", "obs",
        "brave", "opera", "safari", "tor", "arc", "sublime", "atom", "vim",
        "pycharm", "intellij", "android studio", "xcode", "postman", "docker",
        "github", "git", "npm", "node", "python", "java", "gcc", "make",
        "wordpad", "onenote", "outlook", "teams", "skype", "zoom",
        "photos", "camera", "maps", "weather", "clock", "calendar",
        "store", "settings", "control panel", "task manager", "registry editor",
        "snipping tool", "magnifier", "narrator", "on-screen keyboard",
        "media player", "groove music", "xbox", "steam", "epic games",
        "blender", "maya", "cinema 4d", "houdini", "unreal engine", "unity",
        "figma", "sketch", "canva", "illustrator", "indesign", "premiere", "after effects",
    ]
    _NAME_PATTERNS = [
        r"\bmy name is ([A-Z][a-z]+)\b",
        r"\bi(?:'m| am) ([A-Z][a-z]+)\b",
        r"\bcall me ([A-Z][a-z]+)\b",
        r"\bमेरा नाम ([^\s]+) है\b",
        r"\bನನ್ನ ಹೆಸರು ([^\s]+)\b",
    ]
    _PREF_PATTERNS = [
        (r"\bi (?:prefer|like|love|want|always use) (.+?)(?:\.|$)", "preference"),
        (r"\bमुझे (.+?) पसंद है\b", "preference"),
        (r"\bನನಗೆ (.+?) ಇಷ್ಟ\b", "preference"),
    ]
    _FACT_PATTERNS = [
        # "I work at ..." / "I study at ..." - store the company/school
        (r"\bi (?:work|am working) (?:at|for|in) (.+?)(?:\.|$)", "workplace"),
        (r"\bi (?:study|am studying) (?:at|in|at) (.+?)(?:\.|$)", "school"),
        (r"\bमैं (.+?) में काम करता हूँ\b", "workplace"),
        (r"\bನಾನು (.+?) ನಲ್ಲಿ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ\b", "workplace"),
        # "I live in ..." / "I am from ..."
        (r"\bi (?:live in|am from|reside in|stay in) (.+?)(?:\.|$)", "location"),
        (r"\bमैं (.+?) से हूँ\b", "location"),
        (r"\bನಾನು (.+?) ನಿಂದ ಬಂದಿದ್ದೇನೆ\b", "location"),
        # "My favorite color/food/music/movie is ..."
        (r"\bmy favorite (.+?) is (.+?)(?:\.|$)", "favorite"),
        (r"\bमेरा पसंदीदा (.+?) (.+?) है\b", "favorite"),
        # "I am a student / developer / engineer / etc." - store the job title
        (r"\bi am (?:a|an) (.+?)(?:\.|$)", "occupation"),
        (r"\bमैं एक (.+?) हूँ\b", "occupation"),
        # "I am a software engineer / data scientist / etc."
        (r"\bi am (?:a|an) (.+?) (?:at|for|in) (.+?)(?:\.|$)", "occupation"),
        # "Remember that ..."
        (r"\bremember (?:that )?(.+?)(?:\.|$)", "memorize"),
        # "Don't forget ..."
        (r"\b(?:don't|do not) forget (.+?)(?:\.|$)", "memorize"),
        # Additional patterns for more user info
        (r"\bmy (?:age|birthday|birth date|DOB) is (.+?)(?:\.|$)", "age"),
        (r"\bi (?:am|'m) (\d{1,3}) (?:years? old|yr|yrs?)\b", "age"),
        (r"\bmy (?:email|e-mail) is (.+?)(?:\.|$)", "email"),
        (r"\bmy (?:phone|mobile|number) (?:is|no\.?|number) (.+?)(?:\.|$)", "phone"),
        (r"\bmy (?:hobby|hobbies) (?:is|are) (.+?)(?:\.|$)", "hobbies"),
        (r"\bi (?:like|love|enjoy) (.+?)(?:\.|$)", "likes"),
        (r"\bi (?:hate|dislike|don't like) (.+?)(?:\.|$)", "dislikes"),
        (r"\bmy (?:goal|dream|aspiration) (?:is|are) (.+?)(?:\.|$)", "goals"),
        (r"\bmy (?:pet|dog|cat) (?:is|'s name) (?:named )?(.+?)(?:\.|$)", "pet"),
        (r"\bmy (?:partner|wife|husband|boyfriend|girlfriend) (?:is|'s name) (?:named )?(.+?)(?:\.|$)", "partner"),
        (r"\bmy (?:home|house|flat|apartment) (?:is in|is at|'s address) (.+?)(?:\.|$)", "home_address"),
        (r"\bmy (?:car|vehicle) (?:is a?|'s a?) (.+?)(?:\.|$)", "vehicle"),
        (r"\bmy (?:favorite color|colour) (?:is) (.+?)(?:\.|$)", "favorite_color"),
        (r"\bmy (?:favorite food|fav food|favourite food) (?:is) (.+?)(?:\.|$)", "favorite_food"),
        (r"\bmy (?:favorite movie|fav movie|favourite movie) (?:is) (.+?)(?:\.|$)", "favorite_movie"),
        (r"\bmy (?:favorite song|fav song|favourite song) (?:is) (.+?)(?:\.|$)", "favorite_song"),
        (r"\bmy (?:favorite book|fav book|favourite book) (?:is) (.+?)(?:\.|$)", "favorite_book"),
        (r"\bmy (?:favorite place|fav place|favourite place) (?:is) (.+?)(?:\.|$)", "favorite_place"),
        (r"\bmy (?:favorite game|fav game|favourite game) (?:is) (.+?)(?:\.|$)", "favorite_game"),
        (r"\bmy (?:favorite show|fav show|favourite show|favorite series) (?:is) (.+?)(?:\.|$)", "favorite_show"),
    ]

    def _infer_profile(self, user_text: str, lang: str, response: str) -> None:
        """Extract profile facts from the user's speech."""
        text_lower = user_text.lower()

        # Learn user's name
        if not self._profile.get("name"):
            for pat in self._NAME_PATTERNS:
                m = re.search(pat, user_text, re.IGNORECASE)
                if m:
                    self._profile["name"] = m.group(1).strip().title()
                    logger.info("[Memory] Learned user name: {}", self._profile["name"])
                    break

        # Learn preferred language (track frequency)
        lang_counts = self._profile.setdefault("lang_counts", {"en": 0, "hi": 0, "kn": 0})
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        # Preferred lang = most-used lang over all sessions
        preferred = max(lang_counts, key=lang_counts.get)
        self._profile["preferred_lang"] = preferred

        # Learn frequently used app names
        apps = self._profile.setdefault("frequent_apps", [])
        for app in self._APP_NAMES:
            if app in text_lower and app not in apps:
                apps.append(app)
                if len(apps) > 20:
                    apps.pop(0)

        # Learn explicit preferences
        prefs = self._profile.setdefault("preferences", {})
        for pat, key in self._PREF_PATTERNS:
            m = re.search(pat, user_text, re.IGNORECASE)
            if m:
                pref_value = m.group(1).strip()
                if len(pref_value) < 60:  # sanity guard
                    pref_key = f"pref_{len(prefs)}"
                    prefs[pref_key] = pref_value
                    logger.info("[Memory] Learned preference: {}", pref_value)

        # Learn personal facts (occupation, location, favorites, roles, memorized items)
        facts = self._profile.setdefault("facts", {})
        for pat, key in self._FACT_PATTERNS:
            m = re.search(pat, user_text, re.IGNORECASE)
            if m:
                groups = m.groups()
                if key == "favorite" and len(groups) == 2:
                    fact_key = f"{groups[0].strip()}"
                    fact_val = groups[1].strip()
                elif key == "memorize":
                    fact_key = f"memorized_{len([k for k in facts if k.startswith('memorized_')])}"
                    fact_val = groups[0].strip() if groups else ""
                else:
                    fact_key = key
                    fact_val = groups[0].strip() if groups else ""
                if fact_val and len(fact_val) < 100:
                    facts[fact_key] = fact_val
                    logger.info("[Memory] Learned fact: {} = {}", fact_key, fact_val)

        # Learn schedule mentions ("every morning at 8", "remind me at 7pm daily")
        schedules = self._profile.setdefault("schedules", [])
        sched_patterns = [
            r"\bevery (morning|evening|night|day|week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"\bat (\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+(?:daily|every day|remind)\b",
            r"\bहर (सुबह|शाम|रात|दिन|सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार)\b",
        ]
        for pat in sched_patterns:
            m = re.search(pat, user_text, re.IGNORECASE)
            if m:
                sched_text = m.group(0).strip()
                if sched_text not in schedules:
                    schedules.append(sched_text)
                    if len(schedules) > 10:
                        schedules.pop(0)

    # ─── Internal: command caching ────────────────────────────────────────────

    def _cache_key(self, text: str, lang: str) -> str:
        """Normalised cache key: lowercase, alphanumeric only, + lang tag."""
        norm = re.sub(r"[^\w\u0900-\u097F\u0C80-\u0CFF\s]", "", text.lower()).strip()
        return f"{lang}::{norm}"

    def _learn_command_cache(
        self,
        user_text: str,
        lang: str,
        response: str,
        action: str | None,
    ) -> None:
        """Increment hit count for a command and cache its response once threshold is met."""
        key = self._cache_key(user_text, lang)
        entry = self._cmd_cache.setdefault(key, {
            "text": user_text,
            "lang": lang,
            "response": response,
            "action": action,
            "hits": 0,
            "last_used": datetime.now().isoformat(),
        })
        entry["hits"] += 1
        # Always update response to the latest (most accurate) version
        entry["response"] = response
        entry["action"] = action
        entry["last_used"] = datetime.now().isoformat()

        # LRU pruning: if over limit, remove least-recently-used entries
        if len(self._cmd_cache) > self._MAX_CACHE:
            sorted_entries = sorted(
                self._cmd_cache.items(),
                key=lambda kv: kv[1].get("last_used", ""),
            )
            # Remove oldest 20%
            to_remove = int(self._MAX_CACHE * 0.2)
            for k, _ in sorted_entries[:to_remove]:
                del self._cmd_cache[k]

    # ─── Internal: correction detection ──────────────────────────────────────

    def _detect_correction(self, user_text: str, lang: str) -> None:
        """Detect when the user is correcting a previous response and log it."""
        if not _CORRECTION_RE.search(user_text):
            return
        if len(self._recent_turns) < 2:
            return

        # The previous turn's user text is what was "wrong"
        prev = self._recent_turns[-2]
        wrong_text = prev.get("user", "")
        corrected_text = user_text

        if wrong_text and wrong_text != corrected_text:
            correction = {
                "wrong": wrong_text[:100],
                "corrected": corrected_text[:100],
                "lang": lang,
                "ts": datetime.now().isoformat(),
            }
            self._corrections.append(correction)
            if len(self._corrections) > 100:
                self._corrections = self._corrections[-100:]
            logger.info("[Memory] Logged correction: '{}' → '{}'", wrong_text[:40], corrected_text[:40])

    def _update_knowledge_graph(self, user_text: str, assistant_response: str) -> None:
        """
        Extract entities from conversation and update the knowledge graph.
        Creates connections between co-occurring entities for associative recall.
        """
        try:
            # Extract entities from user text
            user_entities = auto_connect_entities(user_text, knowledge_graph)
            
            # Extract entities from assistant response (less aggressive)
            from core.knowledge_graph import extract_entities_from_text
            assistant_entities = extract_entities_from_text(assistant_response)
            for ext in assistant_entities:
                entity_type = ext["type"]
                name = ext["name"]
                entity_id = f"{entity_type}:{name.lower().replace(' ', '_')}"
                knowledge_graph.add_entity(entity_id, entity_type, name, ext.get("attributes", {}))
            
            # Connect user entities to assistant entities (conversation context)
            for uid in user_entities:
                for ext in assistant_entities:
                    entity_type = ext["type"]
                    name = ext["name"]
                    aid = f"{entity_type}:{name.lower().replace(' ', '_')}"
                    knowledge_graph.add_edge(uid, aid, "discussed_in_context", weight=0.5)
            
            # Create temporal connection to conversation context
            if user_entities:
                # Connect all entities from same turn
                for i in range(len(user_entities)):
                    for j in range(i + 1, len(user_entities)):
                        knowledge_graph.add_edge(
                            user_entities[i],
                            user_entities[j],
                            "same_conversation",
                            weight=0.8,
                        )
            
            logger.debug("[Memory] Knowledge graph updated with {} entities", len(user_entities))
        except Exception as e:
            logger.error("[Memory] Knowledge graph update failed: {}", e)

    # ─── Persistence ──────────────────────────────────────────────────────────

    def _save_if_dirty(self) -> None:
        with self._save_lock:
            with self._lock:
                if not self._dirty:
                    return
                payload = {
                    "vocab": {lang: dict(ctr) for lang, ctr in self._vocab.items()},
                    "profile": self._profile,
                    "cmd_cache": self._cmd_cache,
                    "corrections": self._corrections,
                    "session_start": self._session_start,
                    "session_turns": self._session_turns,
                    "saved_at": datetime.now().isoformat(),
                }
                self._dirty = False

            try:
                import uuid
                _MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                tmp = _MEMORY_FILE.with_name(f"personal_memory_{uuid.uuid4().hex[:8]}.tmp")
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                try:
                    tmp.replace(_MEMORY_FILE)
                except OSError:
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
                logger.debug("[Memory] Persisted personal memory ({} vocab entries, {} cached commands).",
                             sum(len(v) for v in payload["vocab"].values()),
                             len(payload["cmd_cache"]))
            except Exception as e:
                logger.error("[Memory] Save failed: {}", e)

    def _load(self) -> None:
        if not _MEMORY_FILE.exists():
            logger.info("[Memory] No existing memory file — starting fresh.")
            return
        try:
            data = json.loads(_MEMORY_FILE.read_text(encoding="utf-8"))
            with self._lock:
                vocab_raw = data.get("vocab", {})
                for lang, counts in vocab_raw.items():
                    self._vocab[lang] = Counter(counts)
                self._profile.update(data.get("profile", {}))
                self._cmd_cache = data.get("cmd_cache", {})
                self._corrections = data.get("corrections", [])
                total_vocab = sum(len(v) for v in self._vocab.values())
                total_cache = len(self._cmd_cache)
            logger.success(
                "[Memory] Loaded personal memory: {} vocab entries, {} cached commands, {} corrections.",
                total_vocab, total_cache, len(self._corrections),
            )
        except Exception as e:
            logger.warning("[Memory] Failed to load memory (starting fresh): {}", e)

    # ─── Stats / Debug ────────────────────────────────────────────────────────

    def stats(self) -> dict:
        with self._lock:
            return {
                "vocab": {lang: len(ctr) for lang, ctr in self._vocab.items()},
                "cmd_cache": len(self._cmd_cache),
                "corrections": len(self._corrections),
                "session_turns": self._session_turns,
                "profile_name": self._profile.get("name"),
                "preferred_lang": self._profile.get("preferred_lang"),
            }


# ─── Singleton accessor ───────────────────────────────────────────────────────
_instance: MemoryEngine | None = None
_instance_lock = threading.Lock()


def get_memory() -> MemoryEngine:
    """Return the global MemoryEngine singleton (lazy-init)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = MemoryEngine()
    return _instance



















