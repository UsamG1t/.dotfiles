#!/usr/bin/env python3
"""
keybinds_gen.py
Generates keyhints.txt from keybinds.lua by reading structured comments.

Comment conventions in keybinds.lua:
    -- Group name          ← section header (line before a group of binds)
    hl.bind(...) -- desc   ← per-bind description (inline, after closing paren)

For-loop binds are represented with <variable> placeholders.
Groups separated by blank lines.

Usage:
    python3 keybinds_gen.py [keybinds.lua] [keyhints.txt]
    (defaults to sibling files in the same directory as this script)

Rebuild logic:
    Regenerates only when keyhints.txt is missing or older than keybinds.lua.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# ── Key normalisation ──────────────────────────────────────────────────────────

MODIFIER_MAP: dict[str, str] = {
    "SUPER":   "Super",
    "ALT":     "Alt",
    "SHIFT":   "Shift",
    "CTRL":    "Ctrl",
    "CONTROL": "Ctrl",
}

KEY_NAME_MAP: dict[str, str] = {
    "question":     "?",
    "slash":        "/",
    "backslash":    "\\",
    "period":       ".",
    "comma":        ",",
    "semicolon":    ";",
    "colon":        ":",
    "minus":        "-",
    "equal":        "=",
    "bracketleft":  "[",
    "bracketright": "]",
    "apostrophe":   "'",
    "grave":        "`",
    "space":        "Space",
    "return":       "Enter",
    "escape":       "Esc",
    "backspace":    "Backspace",
    "tab":          "Tab",
    "mouse_down":   "Scroll↓",
    "mouse_up":     "Scroll↑",
    "mouse:272":    "LMB",
    "mouse:273":    "RMB",
}


def normalize_key(raw: str) -> str:
    """
    Normalize a joined key expression.
    'SUPER + SHIFT + H'  →  'Super + Shift + H'
    'ALT + <i>'          →  'Alt + <i>'
    """
    parts = [p.strip() for p in raw.split("+") if p.strip()]
    result = []
    for part in parts:
        if part.startswith("<") and part.endswith(">"):
            result.append(part)  # loop variable placeholder — leave as-is
        else:
            upper = part.upper()
            token = (
                MODIFIER_MAP.get(upper)
                or KEY_NAME_MAP.get(part.lower())
                or part
            )
            result.append(token)
    return " + ".join(result)


# ── Lua expression evaluator ───────────────────────────────────────────────────

def eval_key_expr(expr: str, variables: dict[str, str], loop_var: str | None) -> str:
    """
    Evaluate a Lua string-concatenation key expression into a display string.

    Examples:
        mainMod .. " + Q"                →  'Super + Q'
        "CTRL + " .. mainMod .. " + Q"   →  'Ctrl + Super + Q'
        "ALT + " .. i                    →  'Alt + <i>'
    """
    segments: list[str] = []

    for part in re.split(r"\s*\.\.\s*", expr.strip()):
        part = part.strip()
        # String literal
        if (part.startswith('"') and part.endswith('"')) or \
           (part.startswith("'") and part.endswith("'")):
            segments.append(part[1:-1])
        # For-loop variable
        elif loop_var and part == loop_var:
            segments.append(f"<{loop_var}>")
        # Known Lua local variable (e.g. mainMod)
        elif part in variables:
            segments.append(variables[part])
        # Anything else — wrap in angle brackets so it's visible
        else:
            segments.append(f"<{part}>")

    return normalize_key("".join(segments))


# ── Key expression extractor ───────────────────────────────────────────────────

def extract_key_and_comment(line: str) -> tuple[str | None, str | None]:
    """
    Parse a single hl.bind(...) line and return (key_expr, inline_comment).
    Returns (None, None) when the line has no inline comment (excluded from hints).
    """
    start = line.find("hl.bind(")
    if start == -1:
        return None, None

    start += len("hl.bind(")
    depth = 0
    in_string = False
    string_char = ""
    key_end = -1

    for i, ch in enumerate(line[start:], start):
        if in_string:
            if ch == string_char:
                in_string = False
        else:
            if ch in ('"', "'"):
                in_string = True
                string_char = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            elif ch == "," and depth == 0:
                key_end = i
                break

    if key_end == -1:
        return None, None

    key_expr = line[start:key_end].strip()

    # Inline comment must appear after the outermost closing paren
    comment_match = re.search(r"\)\s*--\s*(.+)$", line)
    if not comment_match:
        return None, None  # no comment → skip this bind

    return key_expr, comment_match.group(1).strip()


# ── Parser ─────────────────────────────────────────────────────────────────────

def is_group_comment(text: str) -> bool:
    """
    Heuristic: a comment is a group section header if it looks like prose,
    not commented-out Lua code.  Lua calls always contain parentheses.
    """
    return "(" not in text and ")" not in text


def parse(lua: str) -> list[dict]:
    """
    Parse keybinds.lua and return a list of groups:
        [{"header": str, "binds": [{"key": str, "comment": str}]}, ...]
    """
    lines = lua.splitlines()

    # First pass: collect `local name = "value"` definitions
    variables: dict[str, str] = {}
    var_re = re.compile(r'^\s*local\s+(\w+)\s*=\s*["\']([^"\']+)["\']')
    for line in lines:
        m = var_re.match(line)
        if m:
            variables[m.group(1)] = m.group(2)

    groups: list[dict] = []
    current_group: dict | None = None
    pending_header: str | None = None
    loop_var: str | None = None

    for_re = re.compile(r"^\s*for\s+(\w+)\s*=\s*[\w]+\s*,\s*[\w]+\s+do")
    comment_re = re.compile(r"^\s*--\s+(.+)$")

    for line in lines:
        stripped = line.strip()

        # Blank line — skip
        if not stripped:
            continue

        # End of for-loop
        if stripped == "end":
            loop_var = None
            continue

        # For-loop header  →  remember the loop variable
        m = for_re.match(line)
        if m:
            loop_var = m.group(1)
            continue

        # hl.bind() line
        if "hl.bind(" in stripped:
            key_expr, comment = extract_key_and_comment(stripped)
            if key_expr is None:
                continue  # no inline comment → excluded from hints

            key = eval_key_expr(key_expr, variables, loop_var)

            # Start a new group when a fresh section header was seen
            if pending_header is not None:
                if current_group is None or current_group["header"] != pending_header:
                    current_group = {"header": pending_header, "binds": []}
                    groups.append(current_group)
                pending_header = None

            if current_group is None:
                current_group = {"header": "Misc", "binds": []}
                groups.append(current_group)

            current_group["binds"].append({"key": key, "comment": comment})
            continue

        # Comment line — potential group header
        m = comment_re.match(line)
        if m:
            text = m.group(1).strip()
            if is_group_comment(text):
                pending_header = text  # overwrites previous if nothing matched yet
            continue

        # Everything else (local vars, calls, …) — ignore

    return [g for g in groups if g["binds"]]


# ── Formatter ──────────────────────────────────────────────────────────────────

def format_hints(groups: list[dict]) -> str:
    """Render groups into aligned plain-text columns."""
    out: list[str] = []

    for i, group in enumerate(groups):
        if i > 0:
            out.append("")
        out.append(group["header"])

        # Align the '--' separator within each group
        max_key_len = max(len(b["key"]) for b in group["binds"])
        for bind in group["binds"]:
            padding = " " * (max_key_len - len(bind["key"]))
            out.append(f"    {bind['key']}{padding}  --  {bind['comment']}")

    return "\n".join(out) + "\n"


# ── Rebuild check ──────────────────────────────────────────────────────────────

def needs_rebuild(lua_path: Path, hint_path: Path) -> bool:
    if not hint_path.exists():
        return True
    return lua_path.stat().st_mtime > hint_path.stat().st_mtime


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    script_dir = Path(__file__).parent
    lua_path  = Path(sys.argv[1]) if len(sys.argv) > 1 else script_dir / "keybinds.lua"
    hint_path = Path(sys.argv[2]) if len(sys.argv) > 2 else script_dir / "keyhints.txt"

    if not needs_rebuild(lua_path, hint_path):
        sys.exit(0)  # up-to-date — silent exit so callers don't wait

    try:
        lua_src = lua_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Error: {lua_path} not found", file=sys.stderr)
        sys.exit(1)

    groups = parse(lua_src)
    hint_path.write_text(format_hints(groups), encoding="utf-8")


if __name__ == "__main__":
    main()
