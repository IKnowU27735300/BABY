"""
tools/file_tools.py — Safe OS-agnostic file system tools.
All tools are exposed via JSON schema for LLM function-calling.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger


# ─── Schemas for LLM function-calling ────────────────────────────────────────

FILE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and folders in a directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list."}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "copy_file",
            "description": "Copy a file or folder from source to destination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source":      {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Move or rename a file or folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source":      {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["source", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Permanently delete a file or folder. DANGEROUS — needs user consent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":      {"type": "string"},
                    "recursive": {"type": "boolean", "default": False,
                                  "description": "Set true to delete non-empty directories."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the text contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 4000},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text content to a file (creates or overwrites).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Launch an application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string",
                                 "description": "App name, e.g. 'notepad', 'chrome', 'calculator'"},
                },
                "required": ["app_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Create a new folder (directory) at the given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the folder to create, e.g. 'reports' or 'C:/work/reports'"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for files and folders matching a name or pattern. Searches from user's home directory and system drives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Filename or pattern to search for (e.g., '*.pdf', 'document', 'photo.jpg')"},
                    "search_path": {"type": "string", "description": "Optional: Starting directory to search from (default: user home directory)"},
                    "file_type": {"type": "string", "description": "Optional: Filter by file type - 'file', 'folder', or 'any' (default: 'any')"},
                    "max_results": {"type": "integer", "description": "Maximum number of results to return (default: 50)", "default": 50},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_n8n_webhook",
            "description": "Trigger a custom n8n automation workflow with a JSON payload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "webhook_url": {"type": "string", "description": "The exact URL of the n8n webhook node."},
                    "payload": {"type": "object", "description": "JSON payload containing input parameters for the workflow."}
                },
                "required": ["webhook_url", "payload"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append text to the end of an existing file (or create it if it doesn't exist). Use when the user says 'add to', 'append to', 'add a line to', or 'write at the end of' a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Path to the file to append to."},
                    "content": {"type": "string", "description": "Text to append. A newline is added automatically if the file already has content."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Make a surgical edit to a file without rewriting the whole thing. "
                "Use when the user says 'edit', 'modify', 'change', 'replace', 'find and replace', "
                "'insert after', 'insert before', 'delete lines matching', or 'update' a specific "
                "part of a file. Supported operations: "
                "'find_replace' (replace all occurrences of old_text with new_text), "
                "'insert_after' (insert new_text after the first occurrence of anchor_text), "
                "'insert_before' (insert new_text before the first occurrence of anchor_text), "
                "'delete_lines' (delete all lines containing pattern), "
                "'replace_lines' (replace all lines containing pattern with new_text)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path":        {"type": "string", "description": "Path to the file to edit."},
                    "operation":   {
                        "type": "string",
                        "enum": ["find_replace", "insert_after", "insert_before", "delete_lines", "replace_lines"],
                        "description": "Which edit operation to perform.",
                    },
                    "old_text":    {"type": "string", "description": "Text to find (for find_replace)."},
                    "new_text":    {"type": "string", "description": "Replacement or inserted text (for find_replace, insert_after, insert_before, replace_lines)."},
                    "anchor_text": {"type": "string", "description": "Existing text to insert before/after (for insert_after / insert_before)."},
                    "pattern":     {"type": "string", "description": "Substring to match in lines (for delete_lines / replace_lines)."},
                    "count":       {"type": "integer", "description": "Max replacements for find_replace (0 = all). Default 0.", "default": 0},
                },
                "required": ["path", "operation"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_pdf",
            "description": "Read and extract text from a PDF document by path. Use when the user asks to summarize, read, scan, or analyze a PDF file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":      {"type": "string", "description": "Path to the PDF file, e.g. 'C:/docs/paper.pdf' or 'report.pdf'"},
                    "max_pages": {"type": "integer", "default": 20, "description": "Maximum number of pages to read (default: 20)."},
                },
                "required": ["path"],
            },
        },
    },
]

# ─── Risk classification ──────────────────────────────────────────────────────

TOOL_RISK: dict[str, str] = {
    "list_directory":      "low",
    "read_file":           "low",
    "read_pdf":            "low",
    "search_files":        "low",
    "copy_file":           "medium",
    "move_file":           "medium",
    "write_file":          "medium",
    "append_file":         "medium",
    "edit_file":           "medium",
    "create_directory":    "low",
    "open_application":    "low",
    "trigger_n8n_webhook": "medium",
    "delete_file":         "high",
}

# ─── Implementations ──────────────────────────────────────────────────────────

def list_directory(path: str = ".") -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"Path does not exist: {p}"}
    try:
        items = []
        for item in sorted(p.iterdir()):
            entry: dict[str, Any] = {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
            }
            if item.is_file():
                entry["size_bytes"] = item.stat().st_size
            items.append(entry)
        return {"path": str(p), "total": len(items), "contents": items}
    except PermissionError as e:
        return {"error": f"Permission denied: {e}"}


def read_file(path: str, max_chars: int = 4000) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"Not a file: {p}"}
    try:
        with p.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read(max_chars + 1)
        truncated = len(text) > max_chars
        content = text[:max_chars]
        total_chars = p.stat().st_size
        return {
            "path": str(p),
            "content": content,
            "truncated": truncated,
            "total_chars": total_chars,
        }
    except Exception as e:
        return {"error": str(e)}


def read_pdf(path: str, max_pages: int = 20, extract_metadata: bool = True) -> dict:
    """Read and extract text from a PDF file using PyMuPDF (fitz) or pypdf fallback.

    Enhanced for JARVIS-level PDF intelligence:
    - Extracts document metadata (title, author, subject)
    - Provides structured content with page numbers
    - Detects sections, headings, and key content
    - Returns summary-ready formatted output
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"PDF file not found: {p}"}

    pages_text: list[str] = []
    total_pages = 0
    pages_read = 0
    metadata = {}

    # Try PyMuPDF (fitz) first (fastest, cleanest text & formula extraction)
    try:
        import fitz  # type: ignore
        doc = fitz.open(str(p))
        total_pages = len(doc)

        # Extract metadata
        if extract_metadata:
            meta = doc.metadata
            if meta:
                metadata = {
                    "title": meta.get("title", ""),
                    "author": meta.get("author", ""),
                    "subject": meta.get("subject", ""),
                    "creator": meta.get("creator", ""),
                    "producer": meta.get("producer", ""),
                    "page_count": total_pages,
                    "file_size_kb": round(p.stat().st_size / 1024, 1),
                }

        limit = min(total_pages, max_pages) if max_pages > 0 else total_pages
        for i in range(limit):
            page = doc.load_page(i)
            text = page.get_text("text").strip()

            # Also extract tables if available
            tables = page.find_tables()
            table_text = ""
            if tables and tables.tables:
                for table in tables.tables:
                    table_data = table.extract()
                    if table_data:
                        # Convert table to readable format
                        headers = table_data[0] if table_data else []
                        rows = table_data[1:] if len(table_data) > 1 else []
                        if headers:
                            table_text += "\n[Table]\n"
                            table_text += " | ".join(str(h) for h in headers if h) + "\n"
                            table_text += "-" * 40 + "\n"
                            for row in rows:
                                table_text += " | ".join(str(c) for c in row if c) + "\n"

            if text or table_text:
                page_content = f"--- Page {i + 1} ---\n"
                if text:
                    page_content += text
                if table_text:
                    page_content += table_text
                pages_text.append(page_content)
            pages_read += 1
        doc.close()
    except Exception as err_fitz:
        logger.warning("[FileTools] fitz PDF read failed, trying pypdf fallback: {}", err_fitz)
        try:
            import pypdf  # type: ignore
            reader = pypdf.PdfReader(str(p))
            total_pages = len(reader.pages)

            # Extract metadata
            if extract_metadata and reader.metadata:
                meta = reader.metadata
                metadata = {
                    "title": getattr(meta, "title", "") or "",
                    "author": getattr(meta, "author", "") or "",
                    "subject": getattr(meta, "subject", "") or "",
                    "page_count": total_pages,
                    "file_size_kb": round(p.stat().st_size / 1024, 1),
                }

            limit = min(total_pages, max_pages) if max_pages > 0 else total_pages
            for i in range(limit):
                text = (reader.pages[i].extract_text() or "").strip()
                if text:
                    pages_text.append(f"--- Page {i + 1} ---\n{text}")
                pages_read += 1
        except Exception as err_pypdf:
            return {"error": f"Failed to read PDF '{p.name}': PyMuPDF error ({err_fitz}), pypdf error ({err_pypdf})"}

    full_text = "\n\n".join(pages_text)
    if not full_text.strip():
        return {
            "success": True,
            "path": str(p),
            "total_pages": total_pages,
            "pages_read": pages_read,
            "content": "(PDF appears to be scanned images or empty text. Use vision OCR if opened on screen.)",
            "is_image_pdf": True,
            "metadata": metadata,
        }

    # Build structured output
    result = {
        "success": True,
        "path": str(p),
        "filename": p.name,
        "total_pages": total_pages,
        "pages_read": pages_read,
        "content": full_text,
        "truncated": pages_read < total_pages,
    }

    if metadata:
        result["metadata"] = metadata

    # Add content statistics for summarization
    words = full_text.split()
    result["word_count"] = len(words)
    result["char_count"] = len(full_text)
    result["estimated_reading_time_min"] = max(1, len(words) // 200)

    return result



def write_file(path: str, content: str) -> dict:
    p = Path(path).expanduser().resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(p), "bytes_written": len(content.encode())}
    except Exception as e:
        return {"error": str(e)}


def append_file(path: str, content: str) -> dict:
    """Append text to the end of a file, creating it if it doesn't exist.

    Automatically prepends a newline separator if the file already has content
    and doesn't end with one.
    """
    p = Path(path).expanduser().resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = ""
        if p.exists():
            existing = p.read_text(encoding="utf-8", errors="replace")

        # Add a newline separator if the file already has content and doesn't end with one
        separator = "\n" if existing and not existing.endswith("\n") else ""
        new_content = existing + separator + content

        p.write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "path": str(p),
            "message": f"Appended {len(content)} characters to '{p.name}'.",
            "bytes_written": len(content.encode()),
        }
    except Exception as e:
        return {"error": str(e)}


def edit_file(
    path: str,
    operation: str,
    old_text: str = "",
    new_text: str = "",
    anchor_text: str = "",
    pattern: str = "",
    count: int = 0,
) -> dict:
    """Perform a surgical edit on a file.

    Operations:
        find_replace   – replace old_text with new_text (all occurrences, or up to count)
        insert_after   – insert new_text on a new line after the first occurrence of anchor_text
        insert_before  – insert new_text on a new line before the first occurrence of anchor_text
        delete_lines   – remove all lines that contain pattern
        replace_lines  – replace all lines containing pattern with new_text
    """
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        return {"error": f"File not found: {p}"}

    try:
        original = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"error": f"Could not read file: {e}"}

    op = (operation or "").lower().strip()
    changes = 0

    try:
        if op == "find_replace":
            if not old_text:
                return {"error": "old_text is required for find_replace."}
            max_rep = count if count and count > 0 else 0
            if max_rep:
                result_text = original.replace(old_text, new_text, max_rep)
                changes = original.count(old_text)  # approximate
            else:
                result_text = original.replace(old_text, new_text)
                changes = original.count(old_text)
            if changes == 0:
                return {"success": False, "message": f"Text not found in '{p.name}': {old_text!r}"}

        elif op == "insert_after":
            anchor = anchor_text or old_text
            if not anchor:
                return {"error": "anchor_text is required for insert_after."}
            idx = original.find(anchor)
            if idx == -1:
                return {"success": False, "message": f"Anchor text not found in '{p.name}': {anchor!r}"}
            insert_pos = idx + len(anchor)
            # Move to end of line
            nl = original.find("\n", insert_pos)
            if nl == -1:
                nl = len(original)
            result_text = original[:nl] + "\n" + new_text + original[nl:]
            changes = 1

        elif op == "insert_before":
            anchor = anchor_text or old_text
            if not anchor:
                return {"error": "anchor_text is required for insert_before."}
            idx = original.find(anchor)
            if idx == -1:
                return {"success": False, "message": f"Anchor text not found in '{p.name}': {anchor!r}"}
            # Find start of the line containing anchor
            line_start = original.rfind("\n", 0, idx)
            line_start = line_start + 1 if line_start != -1 else 0
            result_text = original[:line_start] + new_text + "\n" + original[line_start:]
            changes = 1

        elif op == "delete_lines":
            if not pattern:
                return {"error": "pattern is required for delete_lines."}
            lines = original.splitlines(keepends=True)
            new_lines = [ln for ln in lines if pattern not in ln]
            changes = len(lines) - len(new_lines)
            if changes == 0:
                return {"success": False, "message": f"No lines containing {pattern!r} found in '{p.name}'."}
            result_text = "".join(new_lines)

        elif op == "replace_lines":
            if not pattern:
                return {"error": "pattern is required for replace_lines."}
            lines = original.splitlines(keepends=True)
            new_lines = []
            for ln in lines:
                if pattern in ln:
                    new_lines.append(new_text + ("\n" if not new_text.endswith("\n") else ""))
                    changes += 1
                else:
                    new_lines.append(ln)
            if changes == 0:
                return {"success": False, "message": f"No lines containing {pattern!r} found in '{p.name}'."}
            result_text = "".join(new_lines)

        else:
            return {"error": f"Unknown operation: '{operation}'. Use: find_replace, insert_after, insert_before, delete_lines, replace_lines."}

    except Exception as e:
        return {"error": f"Edit operation failed: {e}"}

    # Write the result back
    try:
        p.write_text(result_text, encoding="utf-8")
    except Exception as e:
        return {"error": f"Could not write file: {e}"}

    return {
        "success": True,
        "path": str(p),
        "operation": op,
        "changes_made": changes,
        "message": f"'{p.name}' updated ({changes} change(s) made).",
    }

def copy_file(source: str, destination: str) -> dict:
    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    try:
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        return {"success": True, "from": str(src), "to": str(dst)}
    except Exception as e:
        return {"error": str(e)}


def move_file(source: str, destination: str) -> dict:
    src = Path(source).expanduser().resolve()
    dst = Path(destination).expanduser().resolve()
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"success": True, "from": str(src), "to": str(dst)}
    except Exception as e:
        return {"error": str(e)}


def delete_file(path: str, recursive: bool = False) -> dict:
    p = Path(path).expanduser().resolve()
    try:
        if p.is_dir():
            if recursive:
                shutil.rmtree(p)
            else:
                p.rmdir()   # Only works if empty
        elif p.is_file():
            p.unlink()
        else:
            return {"error": f"Path not found: {p}"}
        return {"success": True, "deleted": str(p)}
    except Exception as e:
        return {"error": str(e)}


def create_directory(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(p)}
    except Exception as e:
        return {"error": str(e)}


def search_files(query: str, search_path: str | None = None, file_type: str = "any", max_results: int = 50) -> dict:
    """
    Search for files and folders matching a name or pattern.
    Searches from user's home directory or specified path.
    """
    import os
    import fnmatch
    
    try:
        # Use home directory if no path specified
        if not search_path:
            search_path = str(Path.home())
        
        search_root = Path(search_path).expanduser().resolve()
        search_root_str = str(search_root)

        if not search_root.exists():
            return {"error": f"Search path not found: {search_path}"}
        
        results = []
        query_lower = query.lower()
        
        # Walk through directory tree
        for root, dirs, files in os.walk(search_root, topdown=True):
            # Limit recursion depth to avoid system directories
            if root.count(os.sep) - search_root_str.count(os.sep) > 5:
                dirs.clear()  # Don't descend further
                continue
            
            # Skip system/protected directories (case-insensitive)
            skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'appdata', 'system32', '$recycle.bin'}
            dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]
            
            # Search files
            if file_type in ("file", "any"):
                for filename in files:
                    if fnmatch.fnmatch(filename.lower(), f"*{query_lower}*") or \
                       fnmatch.fnmatch(filename.lower(), query_lower) or \
                       query_lower in filename.lower():
                        full_path = os.path.join(root, filename)
                        try:
                            size = os.path.getsize(full_path)
                            results.append({
                                "path": full_path,
                                "name": filename,
                                "type": "file",
                                "size_bytes": size,
                            })
                        except:
                            pass
                        
                        if len(results) >= max_results:
                            break
            
            # Search folders
            if file_type in ("folder", "any"):
                for dirname in dirs:
                    if fnmatch.fnmatch(dirname.lower(), f"*{query_lower}*") or \
                       fnmatch.fnmatch(dirname.lower(), query_lower) or \
                       query_lower in dirname.lower():
                        full_path = os.path.join(root, dirname)
                        results.append({
                            "path": full_path,
                            "name": dirname,
                            "type": "folder",
                        })
                        
                        if len(results) >= max_results:
                            break
            
            if len(results) >= max_results:
                break
        
        if not results:
            return {
                "success": True,
                "query": query,
                "results": [],
                "message": f"No files or folders found matching '{query}'"
            }
        
        return {
            "success": True,
            "query": query,
            "search_path": str(search_root),
            "results": results,
            "total_found": len(results),
            "truncated": len(results) >= max_results,
        }
        
    except Exception as e:
        logger.error("[Tool] Search files error: {}", e)
        return {"error": f"Search failed: {str(e)}"}


def _normalize_app_token(name: str) -> str:
    """Strip noise words and collapse whitespace for fuzzy matching."""
    import re
    noise = {
        "microsoft", "adobe", "google", "apple", "amazon", "logitech",
        "installer", "setup", "uninstall", "update", "manager", "launcher",
        "desktop", "app", "application", "client", "portable",
    }
    tokens = re.sub(r"[^a-z0-9\s]", " ", name.lower()).split()
    filtered = [t for t in tokens if t not in noise]
    return " ".join(filtered) if filtered else name.lower()


def find_windows_shortcut(app_name: str) -> str | None:
    """Search Start Menu shortcuts with fuzzy/token matching."""
    import os
    from pathlib import Path

    user_start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs"
    system_start_menu = Path(os.environ.get("ALLUSERSPROFILE", "C:/ProgramData")) / "Microsoft/Windows/Start Menu/Programs"

    search_dirs = [user_start_menu, system_start_menu]
    app_lower = app_name.lower().strip()
    app_tokens = _normalize_app_token(app_lower)

    best_path: str | None = None
    best_score = 0

    _EXCLUDE_KEYWORDS = {"remote desktop", "rdp", "citrix", "teamviewer", "anydesk", "logmein"}

    for sdir in search_dirs:
        if not sdir.exists():
            continue
        for root, _dirs, files in os.walk(sdir):
            for f in files:
                if not f.lower().endswith(".lnk"):
                    continue
                stem = f[:-4].lower()
                stem_tokens = _normalize_app_token(stem)
                score = 0
                # Exact match
                if app_lower == stem:
                    score = 100
                # App name is substring of shortcut name — but skip remote-desktop-like apps
                elif app_lower in stem:
                    if any(kw in stem for kw in _EXCLUDE_KEYWORDS):
                        score = 0
                    else:
                        score = 80
                # Token match
                elif app_tokens and app_tokens in stem_tokens:
                    score = 70
                # Any word in app_name appears in shortcut stem
                elif any(word in stem for word in app_lower.split() if len(word) > 2):
                    score = 50
                if score > best_score:
                    best_score = score
                    best_path = os.path.join(root, f)

    return best_path if best_score >= 50 else None


def _find_app_via_registry(app_name: str) -> str | None:
    """Look up app executable path in Windows Registry App Paths."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        app_lower = app_name.lower().strip()
        reg_roots = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ]
        hives = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
        for hive in hives:
            for reg_path in reg_roots:
                try:
                    with winreg.OpenKey(hive, reg_path) as base:
                        count = winreg.QueryInfoKey(base)[0]
                        for i in range(count):
                            try:
                                key_name = winreg.EnumKey(base, i)
                                stem = key_name.lower().replace(".exe", "")
                                stem_tokens = _normalize_app_token(stem)
                                app_tokens = _normalize_app_token(app_lower)
                                if (app_lower in stem or stem in app_lower
                                        or (app_tokens and app_tokens in stem_tokens)
                                        or (app_tokens and stem_tokens and app_tokens == stem_tokens)):
                                    with winreg.OpenKey(base, key_name) as sub:
                                        exe_path, _ = winreg.QueryValueEx(sub, "")
                                        if exe_path and Path(exe_path).exists():
                                            return exe_path
                            except (OSError, FileNotFoundError):
                                continue
                except (OSError, FileNotFoundError):
                    continue
    except Exception as e:
        logger.debug("[Tool] Registry lookup failed: {}", e)
    return None


def _find_app_via_powershell_startapps(app_name: str) -> str | None:
    """Use PowerShell Get-StartApps to locate a UWP or classic app."""
    if sys.platform != "win32":
        return None
    try:
        app_lower = app_name.lower().strip()
        app_tokens = _normalize_app_token(app_lower)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-StartApps | ConvertTo-Json -Depth 1"],
            capture_output=True, text=True, timeout=8,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        import json as _json
        apps = _json.loads(result.stdout)
        if isinstance(apps, dict):
            apps = [apps]
        best_app_id: str | None = None
        best_score = 0
        _EXCLUDE_KEYWORDS = {"remote desktop", "rdp", "citrix", "teamviewer", "anydesk", "logmein"}
        for entry in apps:
            name = (entry.get("Name") or "").strip()
            app_id = (entry.get("AppID") or "").strip()
            if not name or not app_id:
                continue
            name_lower = name.lower()
            name_tokens = _normalize_app_token(name_lower)
            score = 0
            if app_lower == name_lower:
                score = 100
            elif app_lower in name_lower:
                if any(kw in name_lower for kw in _EXCLUDE_KEYWORDS):
                    score = 0
                else:
                    score = 80
            elif name_lower in app_lower:
                score = 75
            elif app_tokens and app_tokens in name_tokens:
                score = 70
            elif any(word in name_lower for word in app_lower.split() if len(word) > 2):
                score = 55
            if score > best_score:
                best_score = score
                best_app_id = app_id
        if best_app_id and best_score >= 55:
            logger.info("[Tool] Get-StartApps matched '{}' → AppID={}", app_name, best_app_id)
            return f"__STARTAPP__:{best_app_id}"
    except Exception as e:
        logger.debug("[Tool] Get-StartApps lookup failed: {}", e)
    return None


def open_application(app_name: str) -> dict:
    import os
    import re
    import webbrowser

    app_lower = app_name.lower().strip()

    # Strip browser-suffix noise LLM sometimes adds ("open X in chrome browser")
    clean_targets = [
        " in chrome browser", " in the chrome browser", " in google chrome", " in chrome",
        " on chrome", " using chrome", " with chrome", " in browser", " on browser",
        " in edge browser", " in edge", " in firefox browser", " in firefox", " browser",
    ]
    cleaned_app = app_lower
    for phrase in clean_targets:
        cleaned_app = cleaned_app.replace(phrase, "")
    cleaned_app = cleaned_app.strip()
    if cleaned_app.startswith("open "):
        cleaned_app = cleaned_app[5:].strip()
    if not cleaned_app:
        return {"success": False, "error": "App name cannot be empty."}

    # ── Hardcoded app mappings (expanded) ────────────────────────────────────
    app_mappings: dict[str, str] = {
        # Windows built-ins (protocol / exe)
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "terminal": "wt.exe",            # Windows Terminal (if installed)
        "powershell": "powershell.exe",
        "pwsh": "pwsh.exe",
        "powershell 7": "pwsh.exe",
        "explorer": "explorer.exe",
        "file explorer": "explorer.exe",
        "windows explorer": "explorer.exe",
        "task manager": "taskmgr.exe",
        "taskmgr": "taskmgr.exe",
        "regedit": "regedit.exe",
        "registry editor": "regedit.exe",
        "mspaint": "mspaint.exe",
        "wordpad": "wordpad.exe",
        "snipping tool": "SnippingTool.exe",
        "snip": "SnippingTool.exe",
        # Windows UWP protocols
        "camera": "microsoft.windows.camera:",
        "settings": "ms-settings:",
        "windows settings": "ms-settings:",
        "photos": "ms-photos:",
        "store": "ms-windows-store:",
        "windows store": "ms-windows-store:",
        "microsoft store": "ms-windows-store:",
        "weather": "bingweather:",
        "maps": "bingmaps:",
        "bing maps": "bingmaps:",
        "clock": "ms-clock:",
        "calendar": "outlookcalendar:",
        "mail": "outlookmail:",
        "xbox": "xbox:",
        "xbox app": "xbox:",
        # Popular desktop apps (executables)
        "vscode": "code.exe",
        "vs code": "code.exe",
        "visual studio code": "code.exe",
        "code": "code.exe",
        "visual studio": "devenv.exe",
        "vlc": "vlc.exe",
        "vlc media player": "vlc.exe",
        "7zip": "7zFM.exe",
        "7-zip": "7zFM.exe",
        "winrar": "winrar.exe",
        "winzip": "winzip64.exe",
        "audacity": "audacity.exe",
        "gimp": "gimp-2.10.exe",
        "obs": "obs64.exe",
        "obs studio": "obs64.exe",
        "handbrake": "HandBrake.exe",
        "filezilla": "filezilla.exe",
        "putty": "putty.exe",
        "notepad++": "notepad++.exe",
        "notepad plus plus": "notepad++.exe",
        "sublime text": "sublime_text.exe",
        "atom": "atom.exe",
        "android studio": "studio64.exe",
        "pycharm": "pycharm64.exe",
        "intellij": "idea64.exe",
        "webstorm": "webstorm64.exe",
        "clion": "clion64.exe",
        # Messaging & social
        "telegram": "Telegram.exe",
        "discord": "Discord.exe",
        "slack": "slack.exe",
        "teams": "Teams.exe",
        "microsoft teams": "Teams.exe",
        "zoom": "Zoom.exe",
        "skype": "Skype.exe",
        "signal": "Signal.exe",
        "whatsapp": "WhatsApp.exe",
        # Browsers
        "chrome": "chrome.exe",
        "google chrome": "chrome.exe",
        "firefox": "firefox.exe",
        "mozilla firefox": "firefox.exe",
        "edge": "msedge.exe",
        "microsoft edge": "msedge.exe",
        "brave": "brave.exe",
        "brave browser": "brave.exe",
        "opera": "opera.exe",
        "opera gx": "opera.exe",
        "vivaldi": "vivaldi.exe",
        "tor": "firefox.exe",          # Tor Browser uses firefox base
        # Media
        "spotify": "Spotify.exe",
        "itunes": "iTunes.exe",
        "windows media player": "wmplayer.exe",
        "media player": "wmplayer.exe",
        "groove music": "ms-zune-music:",
        "netflix": "https://www.netflix.com",
        # Office / productivity
        "word": "WINWORD.EXE",
        "microsoft word": "WINWORD.EXE",
        "excel": "EXCEL.EXE",
        "microsoft excel": "EXCEL.EXE",
        "powerpoint": "POWERPNT.EXE",
        "microsoft powerpoint": "POWERPNT.EXE",
        "outlook": "OUTLOOK.EXE",
        "microsoft outlook": "OUTLOOK.EXE",
        "onenote": "ONENOTE.EXE",
        "microsoft onenote": "ONENOTE.EXE",
        "access": "MSACCESS.EXE",
        "libreoffice": "soffice.exe",
        "libre office": "soffice.exe",
        # Utilities
        "steam": "steam.exe",
        "epic games": "EpicGamesLauncher.exe",
        "epic": "EpicGamesLauncher.exe",
        "origin": "Origin.exe",
        "ea app": "EADesktop.exe",
        "battle.net": "Battle.net.exe",
        "battlenet": "Battle.net.exe",
        "uplay": "upc.exe",
        "ubisoft connect": "upc.exe",
        "gog galaxy": "GalaxyClient.exe",
        "gta 5": r"C:\Users\Public\Desktop\Grand Theft Auto V Legacy.lnk",
        "gta v": r"C:\Users\Public\Desktop\Grand Theft Auto V Legacy.lnk",
        "grand theft auto 5": r"C:\Users\Public\Desktop\Grand Theft Auto V Legacy.lnk",
        "grand theft auto v": r"C:\Users\Public\Desktop\Grand Theft Auto V Legacy.lnk",
        # VPN
        "planet vpn": "Planet VPN.exe",
        "vpn": "Planet VPN.exe",
        # AI & Development Tools
        "antigravity": "antigravity.exe",
        "opencode": "opencode.exe",
        "qwen": "qwen.exe",
        "aratti": "aratti.exe",
        "trae": "Trae.exe",
        "tldraw": "tldraw.exe",
        "kiro": "Kiro.exe",
        "lm studio": "LM Studio.exe",
        "lmstudio": "LM Studio.exe",
        # Video Editing
        "capcut": "CapCut.exe",
        "cap cut": "CapCut.exe",
        "postman": "Postman.exe",
        "insomnia": "Insomnia.exe",
        "docker": "Docker Desktop.exe",
        "docker desktop": "Docker Desktop.exe",
        "virtualbox": "VirtualBox.exe",
        "vmware": "vmware.exe",
        # Web (open in browser)
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chat.openai.com",
        "google": "https://www.google.com",
        "github": "https://www.github.com",
        "wikipedia": "https://www.wikipedia.org",
        "google maps": "https://maps.google.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com",
        "twitter": "https://www.twitter.com",
        "x": "https://www.x.com",
        "linkedin": "https://www.linkedin.com",
        "amazon": "https://www.amazon.com",
        "reddit": "https://www.reddit.com",
        "stackoverflow": "https://stackoverflow.com",
        "stack overflow": "https://stackoverflow.com",
        "flipkart": "https://www.flipkart.com",
        "notion": "https://www.notion.so",
        "figma": "https://www.figma.com",
        "canva": "https://www.canva.com",
    }

    target = app_mappings.get(cleaned_app, cleaned_app)

    def _launch_exe(exe_path: str) -> dict:
        """Try to launch an executable path or name and return a result dict."""
        try:
            os.startfile(exe_path)
            return {"success": True, "launched": exe_path,
                    "message": f"Opened {app_name} successfully."}
        except Exception:
            pass
        try:
            subprocess.Popen([exe_path], shell=True)
            return {"success": True, "launched": exe_path,
                    "message": f"Opened {app_name} successfully."}
        except Exception as e:
            return {"_failed": True, "error": str(e)}

    try:
        # ── 1. Check if user passed an explicit URL string ───────────────────
        raw_is_url = (cleaned_app.startswith(("http://", "https://", "ftp://"))
                      or (("." in cleaned_app) and any(cleaned_app.endswith(ext) for ext in (".com", ".org", ".net", ".io", ".dev", ".ai", ".co.in", ".edu", ".gov"))))
        if raw_is_url:
            url = cleaned_app if cleaned_app.startswith(("http://", "https://")) else f"https://{cleaned_app}"
            webbrowser.open(url)
            return {"success": True, "launched": f"webpage: {url}",
                    "message": f"Opened {app_name} in your browser."}

        # ── 2. Local Desktop App Search (Windows) ───────────────────────────
        if sys.platform == "win32":
            # UWP protocol (e.g. "ms-settings:")
            if target.endswith(":") or cleaned_app.endswith(":"):
                proto = target if target.endswith(":") else cleaned_app
                try:
                    os.startfile(proto)
                    return {"success": True, "launched": proto,
                            "message": f"Opened {app_name} successfully."}
                except Exception:
                    pass

            # A. Check Start Menu shortcut (fuzzy match — catches 99% of installed apps!)
            shortcut_path = find_windows_shortcut(cleaned_app) or (find_windows_shortcut(target) if not target.startswith("http") else None)
            if shortcut_path:
                logger.info("[Tool] Launching Start Menu shortcut: {}", shortcut_path)
                try:
                    os.startfile(shortcut_path)
                    return {"success": True, "launched": shortcut_path,
                            "message": f"Opened {app_name} successfully."}
                except Exception as e:
                    logger.debug("[Tool] os.startfile shortcut failed: {}", e)

            # B. Check PowerShell Get-StartApps (UWP + installed Store / Start menu apps)
            startapp_id = _find_app_via_powershell_startapps(cleaned_app) or (_find_app_via_powershell_startapps(target) if not target.startswith("http") else None)
            if startapp_id and startapp_id.startswith("__STARTAPP__:"):
                app_id = startapp_id[len("__STARTAPP__:"):]
                ps_cmd = f'Start-Process "shell:AppsFolder\\{app_id}"'
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    return {"success": True, "launched": app_name,
                            "message": f"Opened {app_name} successfully."}

            # C. Check Windows Registry App Paths
            reg_path = _find_app_via_registry(cleaned_app) or (_find_app_via_registry(target) if not target.startswith("http") else None)
            if reg_path:
                logger.info("[Tool] Found via Registry: {}", reg_path)
                res = _launch_exe(reg_path)
                if not res.get("_failed"):
                    return res

            # D. Check PATH via shutil.which()
            found_on_path = shutil.which(cleaned_app) or (shutil.which(target) if not target.startswith("http") else None)
            if found_on_path:
                logger.info("[Tool] Found on PATH: {}", found_on_path)
                res = _launch_exe(found_on_path)
                if not res.get("_failed"):
                    return res

            # E. Direct execution if target is an executable name
            if not target.startswith("http") and not target.endswith((".com", ".org", ".net")):
                res = _launch_exe(target)
                if not res.get("_failed"):
                    return res

        # ── 3. Non-Windows platforms (macOS / Linux) ─────────────────────────────
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", target])
            return {"success": True, "launched": target,
                    "message": f"Opened {app_name} successfully."}
        elif sys.platform != "win32":
            subprocess.Popen([target])
            return {"success": True, "launched": target,
                    "message": f"Opened {app_name} successfully."}

        # ── 4. Fallback to web URL if app is mapped to a URL or not found locally ──
        is_url = (target.startswith("http://") or target.startswith("https://")
                  or target.endswith(".com") or target.endswith(".org")
                  or target.endswith(".net"))
        if is_url:
            url = target if target.startswith(("http://", "https://")) else f"https://{target}"
            webbrowser.open(url)
            return {"success": True, "launched": f"webpage: {url}",
                    "message": f"Opened {app_name} in your browser."}

        # ── 5. Nothing worked — honest error ─────────────────────────────────────
        return {
            "success": False,
            "error": (
                f"I couldn't find '{app_name}' installed on your system. "
                f"Please make sure it's installed, or try a different name."
            ),
        }

    except Exception as e:
        logger.error("[Tool] Error launching application: {}", e)
        return {"error": str(e)}


def trigger_n8n_webhook(webhook_url: str, payload: dict) -> dict:
    import urllib.request
    import json
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            resp_data = response.read().decode("utf-8")
            try:
                parsed_resp = json.loads(resp_data)
            except Exception:
                parsed_resp = resp_data
            return {"success": True, "response": parsed_resp}
    except Exception as e:
        return {"error": str(e)}


# ─── Dispatcher ───────────────────────────────────────────────────────────────

_REGISTRY: dict[str, Any] = {
    "list_directory":      list_directory,
    "read_file":           read_file,
    "read_pdf":            read_pdf,
    "search_files":        search_files,
    "write_file":          write_file,
    "append_file":         append_file,
    "edit_file":           edit_file,
    "copy_file":           copy_file,
    "move_file":           move_file,
    "delete_file":         delete_file,
    "create_directory":    create_directory,
    "open_application":    open_application,
    "trigger_n8n_webhook": trigger_n8n_webhook,
}


def execute_tool(name: str, args: dict) -> dict:
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown tool: '{name}'"}
    
    # Normalize argument aliases for robustness against LLM variations
    normalized_args = dict(args) if isinstance(args, dict) else {}
    if name == "open_application":
        if "app_name" not in normalized_args:
            for k in ("app", "name", "application", "target", "app_name_str"):
                if k in normalized_args:
                    normalized_args["app_name"] = normalized_args.pop(k)
                    break
    elif name == "search_files":
        if "query" not in normalized_args:
            for k in ("pattern", "filename", "name", "search_term", "q", "file"):
                if k in normalized_args:
                    normalized_args["query"] = normalized_args.pop(k)
                    break
    elif name == "list_directory":
        if "path" not in normalized_args:
            normalized_args["path"] = "."
    elif name in ("read_file", "read_pdf", "write_file", "append_file", "edit_file", "delete_file"):
        if "path" not in normalized_args:
            for k in ("file", "filename", "filepath", "target", "pdf_path", "pdf"):
                if k in normalized_args:
                    normalized_args["path"] = normalized_args.pop(k)
                    break

    try:
        logger.debug("[Tool] {}({})", name, normalized_args)
        result = fn(**normalized_args)
        logger.debug("[Tool] {} → {}", name, result)
        return result
    except TypeError as e:
        return {"error": f"Invalid arguments for '{name}': {e}"}
    except Exception as e:
        return {"error": str(e)}



















