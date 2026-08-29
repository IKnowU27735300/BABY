"""
antigravity/agents/browser_agent.py — Browser & Web Sub-Agent.

Handles: open URLs in the default browser, Google search, open specific apps
         like Chrome/Firefox to a target URL.

Uses subprocess + webbrowser for lightweight, dependency-free browser control.
Playwright integration can be added later when the dep is installed.
"""

from __future__ import annotations
import subprocess
import sys
import webbrowser
import urllib.request
from urllib.parse import quote_plus
import json
import re

from loguru import logger

from antigravity.base_agent import BaseAgent
from antigravity.goal_tracker import Task, TaskStatus


# ─── Tool registry ────────────────────────────────────────────────────────────

BROWSER_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Open a URL in the user's default web browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL including https://"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_search",
            "description": "Perform a Google search query in the default browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_open_app",
            "description": "Open a specific browser application (chrome, firefox, edge) with an optional URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "browser": {
                        "type": "string",
                        "enum": ["chrome", "firefox", "edge", "default"],
                        "description": "Which browser to open."
                    },
                    "url": {
                        "type": "string",
                        "description": "URL to open (optional). Defaults to browser home page."
                    }
                },
                "required": ["browser"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_search_text",
            "description": "Perform a web search and return the top text results directly to Baby.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query text"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fetch_page_text",
            "description": "Fetch and extract the readable text content from a specific URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL including https://"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_quick_answer",
            "description": "Answer a factual question instantly: web-search the query, fetch the top result, and return its readable text so Baby can summarize it. No browser window is opened. Use for 'what is X', 'who is X', 'tell me about X', 'latest news on X'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question or topic, e.g. 'capital of France', 'latest iPhone release date'"}
                },
                "required": ["question"],
            },
        },
    },
]

BROWSER_TOOL_RISK = {t["function"]["name"]: "low" for t in BROWSER_TOOLS_SCHEMA if isinstance(t, dict) and isinstance(t.get("function"), dict)}

# ─── Browser executable map (Windows-first) ───────────────────────────────────

_BROWSER_EXECUTABLES = {
    "chrome":  ["google-chrome", "chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
    "firefox": ["firefox", r"C:\Program Files\Mozilla Firefox\firefox.exe"],
    "edge":    ["msedge", "microsoft-edge",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
}

# ─── Site resolution ──────────────────────────────────────────────────────────
# "Open amazon in chrome" → LLMs frequently forget to pass the URL (or stuff
# the site name into the "browser" slot). These maps + helpers make the tool
# robust: a bare site name anywhere in the args/user text still resolves to a
# real URL before anything is launched.

_KNOWN_SITES = {
    "amazon": "https://www.amazon.com",
    "flipkart": "https://www.flipkart.com",
    "youtube": "https://www.youtube.com",
    "yt": "https://www.youtube.com",
    "google": "https://www.google.com",
    "google search": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "google maps": "https://maps.google.com",
    "maps": "https://maps.google.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "docs": "https://docs.google.com",
    "wikipedia": "https://www.wikipedia.org",
    "reddit": "https://www.reddit.com",
    "github": "https://github.com",
    "stack overflow": "https://stackoverflow.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://twitter.com",
    "x": "https://twitter.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "outlook": "https://outlook.live.com",
    "hotmail": "https://outlook.live.com",
    "yahoo": "https://www.yahoo.com",
    "yahoo mail": "https://mail.yahoo.com",
    "bing": "https://www.bing.com",
    "duckduckgo": "https://duckduckgo.com",
    "chatgpt": "https://chatgpt.com",
    "openai": "https://openai.com",
    "claude": "https://claude.ai",
    "gemini": "https://gemini.google.com",
    "bard": "https://gemini.google.com",
    "cloudflare": "https://www.cloudflare.com",
    "stackoverflow": "https://stackoverflow.com",
    "quora": "https://www.quora.com",
    "medium": "https://medium.com",
    "ebay": "https://www.ebay.com",
    "best buy": "https://www.bestbuy.com",
    "walmart": "https://www.walmart.com",
    "target": "https://www.target.com",
    "nytimes": "https://www.nytimes.com",
    "bbc": "https://www.bbc.com",
    "cnn": "https://www.cnn.com",
    "weather": "https://weather.com",
    "accuweather": "https://www.accuweather.com",
    "speedtest": "https://www.speedtest.net",
    "pinterest": "https://www.pinterest.com",
    "tumblr": "https://www.tumblr.com",
    "twitch": "https://www.twitch.tv",
    "discord": "https://discord.com",
    "telegram": "https://web.telegram.org",
    "zoom": "https://zoom.us",
    "meet": "https://meet.google.com",
    "google meet": "https://meet.google.com",
    "canva": "https://www.canva.com",
    "figma": "https://www.figma.com",
    "notion": "https://www.notion.so",
    "trello": "https://trello.com",
    "slack": "https://slack.com",
    "dropbox": "https://www.dropbox.com",
    "onedrive": "https://onedrive.live.com",
    "microsoft teams": "https://teams.microsoft.com",
    "teams": "https://teams.microsoft.com",
    "codeforces": "https://codeforces.com",
    "leetcode": "https://leetcode.com",
    "hackerrank": "https://www.hackerrank.com",
    "udemy": "https://www.udemy.com",
    "coursera": "https://www.coursera.org",
    "khan academy": "https://www.khanacademy.org",
    "prime video": "https://www.primevideo.com",
    "hulu": "https://www.hulu.com",
    "disney plus": "https://www.disneyplus.com",
    "hotstar": "https://www.hotstar.com",
    "zee5": "https://www.zee5.com",
    "jio cinema": "https://www.jiocinema.com",
    "paytm": "https://paytm.com",
    "phonepe": "https://www.phonepe.com",
    "upi": "https://www.npci.org.in",
    "irctc": "https://www.irctc.co.in",
    "make my trip": "https://www.makemytrip.com",
    "bookmyshow": "https://in.bookmyshow.com",
    "zomato": "https://www.zomato.com",
    "swiggy": "https://www.swiggy.com",
    "ola": "https://www.olacabs.com",
    "uber": "https://www.uber.com",
    "irctc": "https://www.irctc.co.in",
    "steam": "https://store.steampowered.com",
    "epic games": "https://store.epicgames.com",
    "pubg": "https://www.pubg.com",
    "minecraft": "https://www.minecraft.net",
    "roblox": "https://www.roblox.com",
    "valorant": "https://playvalorant.com",
    "codewars": "https://www.codewars.com",
}


def _normalize_url(url: str) -> str:
    """Turn a bare site name / domain into a full https URL."""
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("www."):
        return "https://" + url
    if "." in url:  # explicit domain like "amazon.com" or "maps.google.com"
        return "https://" + url
    resolved = _KNOWN_SITES.get(url.lower())
    if resolved:
        return resolved
    if " " in url:  # unknown multi-word site — open a search page instead
        return "https://duckduckgo.com/?q=" + quote_plus(url)
    return "https://www." + url.lower() + ".com"


def _resolve_site_name(site: str) -> str | None:
    """Resolve a possibly-messy site name to a full URL, or None."""
    site = (site or "").strip().lower()
    if not site:
        return None
    resolved = _KNOWN_SITES.get(site)
    if resolved:
        return resolved
    if "." in site or " " in site:
        return _normalize_url(site)
    return "https://www." + site + ".com"


_SITE_LABEL_MAP = {
    "whatsapp": "WhatsApp",
    "youtube": "YouTube",
    "github": "GitHub",
    "stackoverflow": "Stack Overflow",
    "chatgpt": "ChatGPT",
    "linkedin": "LinkedIn",
    "google": "Google",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "reddit": "Reddit",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "twitter": "Twitter",
    "amazon": "Amazon",
    "flipkart": "Flipkart",
    "wikipedia": "Wikipedia",
    "gmail": "Gmail",
}


def _friendly_site_label(url: str) -> str:
    """Extract a clean, readable site label from a URL (e.g. 'WhatsApp', 'Google')."""
    if not url:
        return "website"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        netloc = parsed.netloc or parsed.path
        netloc = netloc.split("@")[-1].split(":")[0]
        parts = [p for p in netloc.split(".") if p.lower() not in ("www", "web", "m", "mobile", "com", "org", "net", "gov", "edu", "co", "io", "in", "ai")]
        if parts:
            clean = parts[0].lower()
            if clean in _SITE_LABEL_MAP:
                return _SITE_LABEL_MAP[clean]
            return parts[0].capitalize()
    except Exception:
        pass
    return "website"


def _open_url(url: str) -> dict:
    try:
        webbrowser.open(url)
        label = _friendly_site_label(url)
        return {"success": True, "message": f"Opened {label} successfully."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _search_and_navigate(query: str) -> dict:
    """'Open anything': find the best URL for an unknown site via web search,
    then open the top organic result (falls back to the search page)."""
    query = (query or "").strip()
    if not query:
        return _open_url("https://duckduckgo.com/")
    try:
        res = _search_text(query)
        urls = res.get("urls", []) or []
        if urls:
            return _open_url(_normalize_url(urls[0]))
    except Exception as e:
        logger.debug("[BrowserAgent] Search-to-open fallback failed: {}", e)
    return _open_url("https://duckduckgo.com/?q=" + quote_plus(query))


def _open_with_browser(browser: str, url: str = "") -> dict:
    url = _normalize_url(url)
    executables = _BROWSER_EXECUTABLES.get(browser, [])
    label = _friendly_site_label(url) if url else ""
    for exe in executables:
        try:
            cmd = [exe] + ([url] if url else [])
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            msg = f"Opened {browser} for {label}." if label else f"Opened {browser}."
            return {"success": True, "message": msg}
        except (FileNotFoundError, PermissionError):
            continue
    # Fallback: use default browser
    if url:
        return _open_url(url)
    return {"success": False, "error": f"Browser '{browser}' not found and no URL to fallback to."}


def _strip_html(html: str) -> str:
    # Basic HTML tag stripping
    text = re.sub(r'<style.*?>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script.*?>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _fetch_page_text(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'BABYAssistant/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            text = _strip_html(html)
            # Truncate to reasonable length for LLM (e.g. 6000 chars)
            if len(text) > 6000:
                text = text[:6000] + "... [truncated]"
            return {"success": True, "text": text}
    except Exception as e:
        return {"error": f"Failed to fetch page: {str(e)}"}


def _search_text(query: str) -> dict:
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            
            results = []
            urls = []
            parts = html.split('class="result__title"')
            for part in parts[1:6]:
                try:
                    title_match = re.search(r'<a class="result__a"[^>]*>(.*?)</a>', part, re.DOTALL)
                    link_match  = re.search(r'href="([^"]+)"', part)
                    snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', part, re.DOTALL) or re.search(r'class="result__snippet"[^>]*>(.*?)</', part, re.DOTALL)
                    
                    if title_match and snippet_match:
                        title = _strip_html(title_match.group(1))
                        snippet = _strip_html(snippet_match.group(1))
                        results.append(f"Title: {title}\nSnippet: {snippet}")
                        if link_match:
                            urls.append(link_match.group(1))
                except Exception:
                    continue
            
            if not results:
                text = _strip_html(html)
                return {"success": True, "results": "Raw page snippet: " + text[:1500], "urls": []}
                
            return {"success": True, "results": "\n\n".join(results), "urls": urls}
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


def execute_browser_tool(name: str, args: dict) -> dict:
    if name in ("browser_navigate", "open_url", "navigate_url", "open_website", "goto_url"):
        url = _normalize_url(args.get("url", "https://www.google.com"))
        if url.startswith("https://duckduckgo.com/?q="):
            from urllib.parse import unquote
            return _search_and_navigate(unquote(url.split("q=", 1)[1]))
        return _open_url(url)

    elif name == "browser_search":
        query = args.get("query", "")
        url   = f"https://www.google.com/search?q={quote_plus(query)}"
        return _open_url(url)

    elif name in ("browser_open_app", "chrome_browser", "google_chrome_browser"):
        browser = args.get("browser", "chrome" if name in ("chrome_browser", "google_chrome_browser") else "default")
        url     = args.get("url", "")

        # Defensive correction: LLMs sometimes stuff the website name into the
        # "browser" slot ("browser": "amazon"). If the value isn't a real
        # browser, treat it as the site to open and fall back to the default browser.
        if url == "" and browser.lower() not in _BROWSER_EXECUTABLES:
            if browser.lower() not in ("default", ""):
                url = _resolve_site_name(browser) or ""
            browser = "default"
        else:
            url = _normalize_url(url)

        # "Open anything": an unresolved multi-word site becomes a quick
        # web search whose top result is opened in the chosen browser.
        if url.startswith("https://duckduckgo.com/?q=") and browser in _BROWSER_EXECUTABLES:
            from urllib.parse import unquote
            query = unquote(url.split("q=", 1)[1])
            try:
                res = _search_text(query)
                urls = res.get("urls", []) or []
                if urls:
                    url = _normalize_url(urls[0])
            except Exception:
                pass

        if browser == "default":
            return _open_url(url) if url else {"success": True, "message": "No URL provided for default browser."}
        return _open_with_browser(browser, url)

    elif name == "browser_search_text":
        return _search_text(args.get("query", ""))

    elif name == "browser_fetch_page_text":
        return _fetch_page_text(args.get("url", ""))

    elif name in ("web_quick_answer", "web_answer", "quick_answer", "search_and_answer"):
        return _web_quick_answer(args.get("question") or args.get("query") or args.get("q", ""))

    elif name == "open_application":
        # Fallback: LLM planner sometimes misroutes app-open tasks to BROWSER.
        # Delegate to the system tool executor so "open chrome" still works.
        try:
            from tools.file_tools import execute_tool
            return execute_tool("open_application", args)
        except Exception as e:
            return {"success": False, "error": f"Failed to open application: {e}"}

    return {"success": False, "error": f"Unknown browser tool: {name}"}


def _decode_ddg_redirect(url: str) -> str:
    """DuckDuckGo html results link to //duckduckgo.com/l/?uddg=<real-url>. Decode it."""
    if "duckduckgo.com/l/" in url and "uddg=" in url:
        try:
            from urllib.parse import unquote
            real = url.split("uddg=", 1)[1].split("&", 1)[0]
            return unquote(real)
        except Exception:
            pass
    return url


def _wiki_lookup(query: str) -> dict | None:
    """Wikipedia full-text search + top article summary (no API key)."""
    try:
        q = quote_plus(_strip_question_prefix(query))
        search_url = (
            "https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={q}&srlimit=3&format=json"
        )
        req = urllib.request.Request(search_url, headers={"User-Agent": "BABYAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        hits = data.get("query", {}).get("search", [])
        if not hits:
            return None
        title = quote_plus(hits[0]["title"].replace(" ", "_"))
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        req2 = urllib.request.Request(summary_url, headers={"User-Agent": "BABYAssistant/1.0"})
        with urllib.request.urlopen(req2, timeout=8) as resp2:
            summary = json.loads(resp2.read().decode("utf-8", errors="ignore"))
        extract = summary.get("extract", "")
        if not extract:
            return None
        logger.info("[BrowserAgent] wiki_lookup: '{}' → {}", query, summary.get("title", ""))
        return {
            "success": True,
            "answer": extract,
            "source": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "search_results": "",
            "title": summary.get("title", ""),
        }
    except Exception as e:
        logger.debug("[BrowserAgent] wiki_lookup failed: {}", e)
        return None


_QUESTION_PREFIXES = (
    "what is ", "what are ", "what was ", "what were ", "what's ", "whats ",
    "who is ", "who was ", "who are ", "who's ", "whos ",
    "tell me about ", "tell me about the ", "tell me about a ",
    "explain ", "define ", "meaning of ", "definition of ",
    "where is ", "when is ", "when was ", "how does ", "how do ", "how to ",
)


def _strip_question_prefix(query: str) -> str:
    q = query.strip().rstrip("?").strip()
    low = q.lower()
    for p in _QUESTION_PREFIXES:
        if low.startswith(p):
            return q[len(p):].strip()
    return q


def _web_quick_answer(question: str) -> dict:
    """Search the web, fetch the top result, return its readable text.

    No browser window opens — Baby summarizes the returned text directly.
    Uses Wikipedia for factual lookups, then falls back to DDG search + fetch.
    """
    question = (question or "").strip()
    if not question:
        return {"error": "No question provided for web_quick_answer."}
    try:
        wiki = _wiki_lookup(question)
        if wiki:
            return wiki

        res = _search_text(question)
        if res.get("error"):
            return {"error": res["error"]}
        urls = res.get("urls", []) or []
        if urls:
            real_url = _decode_ddg_redirect(urls[0])
            page = _fetch_page_text(_normalize_url(real_url))
            if page.get("success") and page.get("text"):
                text = page.get("text", "")
                logger.info("[BrowserAgent] web_quick_answer: got {} chars from {}", len(text), real_url)
                return {
                    "success": True,
                    "answer": text,
                    "source": real_url,
                    "search_results": res.get("results", ""),
                }
        return {
            "success": True,
            "answer": res.get("results", "No results found."),
            "source": "",
            "search_results": res.get("results", ""),
        }
    except Exception as e:
        logger.warning("[BrowserAgent] web_quick_answer failed: {}", e)
        return {"error": f"Quick answer failed: {e}"}


# ─── Agent class ──────────────────────────────────────────────────────────────

class BrowserAgent(BaseAgent):
    name        = "browser"
    description = "Opens websites, performs web searches, and launches browsers."

    async def run(self, task: Task) -> Task:
        task.status = TaskStatus.RUNNING
        results = []

        try:
            for tool_call in task.tools:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})

                logger.info("[BrowserAgent] Executing tool='{}' args={}", tool_name, tool_args)
                result = execute_browser_tool(tool_name, tool_args)
                logger.info("[BrowserAgent] Result: {}", result)
                results.append(result)

            has_error = any(isinstance(r, dict) and r.get("error") for r in results)

            if has_error:
                task.status = TaskStatus.FAILED
                task.error  = self._format_result(results)
            else:
                task.status = TaskStatus.DONE
                task.raw_results = results
                task.result = self._format_result(results)

        except Exception as e:
            logger.error("[BrowserAgent] Unexpected error: {}", e)
            task.status = TaskStatus.FAILED
            task.error  = str(e)

        return task



















