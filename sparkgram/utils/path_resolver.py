"""
Fuzzy WorkDir Path Resolver for SparkGram.
Handles Desktop shorthand, tilde expansion, forward/backslash normalization,
case-insensitive Windows paths, and space-containing folder names.
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, List

log = logging.getLogger(__name__)


def _try_candidate(p: Path) -> Optional[Path]:
    """Returns resolved Path if it exists and is a directory, else None."""
    try:
        if p.exists() and p.is_dir():
            return p.resolve()
    except Exception:
        pass
    return None


def _expand_tilde(p_str: str) -> Path:
    """Expands ~ and ~user safely."""
    try:
        return Path(p_str).expanduser()
    except Exception:
        return Path(p_str)


def _case_insensitive_exists(base: Path, rel_parts: List[str]) -> Optional[Path]:
    """
    Walks case-insensitively under base for rel_parts.
    E.g., base=C:/Users/Reynboo/Desktop, rel_parts=["RISET","Digitalisasi Karbon","HyperSpectral"]
    This avoids failure due to casing mismatch on Windows edge cases.
    """
    cur = base
    try:
        for part in rel_parts:
            if not part or part == ".":
                continue
            if not cur.exists() or not cur.is_dir():
                return None
            # Find child case-insensitively
            found = None
            part_low = part.lower()
            for child in cur.iterdir():
                if child.name.lower() == part_low:
                    found = child
                    break
            if found is None:
                return None
            cur = found
        if cur.exists() and cur.is_dir():
            return cur.resolve()
    except Exception as e:
        log.debug(f"case_insensitive walk failed: {e}")
    return None


def _rglob_find_last_token(desktop: Path, last_token: str, full_hint: str) -> Optional[Path]:
    """
    Fallback: rglob search under Desktop for folder matching last_token,
    then verify its full path contains hint tokens.
    """
    try:
        if not desktop.exists() or not desktop.is_dir():
            return None
        hint_tokens = [t.lower() for t in re.split(r"[\\/ ]+", full_hint) if t.strip()]
        # Keep only meaningful tokens (>2 chars)
        hint_tokens = [t for t in hint_tokens if len(t) > 2]
        candidates = []
        for p in desktop.rglob("*"):
            if not p.is_dir():
                continue
            if p.name.lower() == last_token.lower():
                full_low = str(p).lower()
                # Score by how many hint tokens appear
                score = sum(1 for tok in hint_tokens if tok in full_low)
                # Require at least last_token + one other hint if available
                if score >= 1:
                    candidates.append((score, len(str(p)), p))
        if candidates:
            candidates.sort(key=lambda x: (-x[0], x[1]))
            return candidates[0][2].resolve()
    except Exception as e:
        log.debug(f"rglob fallback failed: {e}")
    return None


def resolve_workdir_path(raw: str, current_workdir: Optional[str] = None) -> Tuple[Optional[Path], Optional[str]]:
    """
    Attempts to resolve a fuzzy workdir path string to an existing directory.

    Returns (resolved_path, debug_info). If resolved_path is None, debug_info explains attempts.
    Handles:
      - Absolute Windows paths with spaces (no quoting needed)
      - Forward slash normalization
      - ~ and ~/Desktop expansion
      - 'desktop/...' shorthand (case-insensitive)
      - 'Desktop/RISET/...' relative to home
      - Plain folder name like 'hyperspectral' -> search under Desktop
    """
    if not raw or not raw.strip():
        return None, "empty input"

    original = raw.strip()
    # Strip surrounding quotes if user typed them
    if (original.startswith('"') and original.endswith('"')) or (original.startswith("'") and original.endswith("'")):
        original = original[1:-1].strip()

    # Normalize: strip trailing slashes, but keep root
    candidates_to_try: List[Path] = []
    debug_attempts: List[str] = []

    # 1. Direct path as-is (with expanduser, normalized slashes)
    for variant in [original, original.replace("/", "\\"), original.replace("\\", "/")]:
        p = _expand_tilde(variant)
        # Normalize with Path
        try:
            # Don't resolve yet, just check exists via _try_candidate which resolves
            res = _try_candidate(p)
            if res:
                return res, f"direct:{variant}"
            debug_attempts.append(f"direct miss: {p}")
        except Exception:
            debug_attempts.append(f"direct err: {variant}")

    # 2. Handle desktop shorthand
    low = original.lower()
    desktop_root = Path.home() / "Desktop"
    # Detect prefixes: desktop, ~/desktop, ./desktop, desktop\
    desktop_prefix_re = re.compile(r"^(?:~[/\\]+)?(?:\./)?desktop[/\\ ]*", re.IGNORECASE)
    m = desktop_prefix_re.match(original)
    if m:
        remainder = original[m.end():].strip()
        # Also handle case where remainder is empty -> just Desktop itself
        if not remainder:
            res = _try_candidate(desktop_root)
            if res:
                return res, "desktop root"
            debug_attempts.append("desktop root miss")
        else:
            # Try remainder as subpath under Desktop
            # Normalize remainder: keep spaces inside folder names, but handle both slash styles
            # Try as-is
            for rem_variant in [remainder, remainder.replace("/", os.sep), remainder.replace("\\", os.sep)]:
                cand = desktop_root / rem_variant
                res = _try_candidate(cand)
                if res:
                    return res, f"desktop+{rem_variant}"
                debug_attempts.append(f"desktop+{rem_variant} miss")
                # Try case-insensitive walk
                parts = re.split(r"[\\/]+", rem_variant)
                # If rem_variant contains spaces but no slash, split by spaces intelligently?
                # For "riset digitalisasi karbon hyperspectral" without slashes,
                # we need to guess folder boundaries. The filesystem has:
                # RISET / Digitalisasi Karbon / HyperSpectral
                # Splitting purely by spaces would give 4 tokens, not 3 parts.
                # So we try also walking with rglob fallback later.
                ci_res = _case_insensitive_exists(desktop_root, parts)
                if ci_res:
                    return ci_res, f"desktop CI walk: {parts}"
                debug_attempts.append(f"desktop CI miss: {parts}")

            # If remainder has no slashes but has spaces, attempt to interpret spaces as possible separators
            # e.g., "riset digitalisasi karbon hyperspectral" -> try to find path via scanning
            if "/" not in remainder and "\\" not in remainder:
                # Try rglob for last token
                tokens = remainder.split()
                if tokens:
                    last = tokens[-1]
                    rglob_res = _rglob_find_last_token(desktop_root, last, remainder)
                    if rglob_res:
                        return rglob_res, f"desktop rglob last={last}"
                    debug_attempts.append(f"desktop rglob miss last={last}")

    # 3. Try raw as subpath under Desktop (without explicit desktop prefix)
    # e.g., "riset/digitalisasi karbon/hyperspectral" or "hyperspectral"
    if not original.lower().startswith("c:") and not os.path.isabs(original):
        # Under Desktop
        for variant in [original, original.replace("/", os.sep)]:
            cand = desktop_root / variant
            res = _try_candidate(cand)
            if res:
                return res, f"Desktop/{variant}"
            debug_attempts.append(f"Desktop/{variant} miss")
            # Case-insensitive walk
            parts = re.split(r"[\\/]+", variant)
            ci_res = _case_insensitive_exists(desktop_root, parts)
            if ci_res:
                return ci_res, f"Desktop CI {parts}"
        # Rglob last token (use last word token to handle space-separated without slash)
        tokens = re.split(r"[\\/ ]+", original.strip())
        tokens = [t for t in tokens if t]
        last_token = tokens[-1] if tokens else Path(original).name
        rglob_res = _rglob_find_last_token(desktop_root, last_token, original)
        if rglob_res:
            return rglob_res, f"Desktop rglob {last_token}"
        debug_attempts.append(f"Desktop rglob miss {last_token}")

        # 4. Try relative to current workdir (if provided)
        if current_workdir:
            try:
                base = Path(current_workdir)
                cand = base / original
                res = _try_candidate(cand)
                if res:
                    return res, f"cwd+{original}"
                debug_attempts.append(f"cwd+{original} miss")
            except Exception:
                debug_attempts.append(f"cwd err {original}")

        # 5. Try under home
        home_cand = Path.home() / original
        res = _try_candidate(home_cand)
        if res:
            return res, f"home+{original}"
        debug_attempts.append(f"home+{original} miss")

    # 6. Try to handle Windows drive without slash? Already covered
    # 7. Try to normalize drive letter case: c:\ -> C:\
    # Already handled by Path exists which is case-insensitive

    return None, "; ".join(debug_attempts[:8])


def extract_workdir_target(prompt: str) -> Optional[str]:
    """
    Detects natural language workdir intent and extracts the path substring.
    Returns None if no intent detected.
    Handles:
      - "pindah ke ..."
      - "ganti direktori ke ..."
      - "cd ..."
      - "workdir ..."
      - "buka folder ..."
      - "/workdir ..." (without slash command handling)
    """
    if not prompt or not prompt.strip():
        return None

    text = prompt.strip()
    low = text.lower()

    # Ignore if it's already a slash command handled elsewhere (/workdir, /files, etc.)
    if low.startswith("/workdir") or low.startswith("/files") or low.startswith("/cat"):
        return None

    # Patterns ordered by specificity (longer first)
    patterns = [
        # pindah/ganti/ubah direktori/folder/workdir ... ke ...
        r"(?:pindah|ganti|ubah|masuk|buka)\s+(?:direktori|folder|workdir|directory|path)?\s*(?:ke|menjadi|ke\s+folder|ke\s+direktori)?\s*[\"']?(.+?)[\"']?\s*$",
        # cd / workdir explicit
        r"^(?:cd|workdir|pwd)\s+[\"']?(.+?)[\"']?\s*$",
        # ganti ke ... / pindah ke ...
        r"(?:ganti|pindah)\s+ke\s+[\"']?(.+?)[\"']?\s*$",
    ]

    # Quick heuristic: if prompt is short and contains no workdir keywords, but looks like a path, detect
    # e.g., "desktop/riset/..." alone could be considered? But we avoid false positives.
    # Only trigger if low contains one of the keywords or starts with cd
    keywords = ["pindah", "ganti", "ubah", "direktori", "folder", "workdir", "directory", " cd ", "cd "]
    has_keyword = any(k in low for k in keywords)
    if not has_keyword:
        return None

    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) < 3:
                continue
            # Remove trailing filler words like "dong", "ya", "please", "tolong"
            candidate = re.sub(r"\s+(dong|ya|please|tolong|yaa|yuk)\s*$", "", candidate, flags=re.IGNORECASE).strip()
            # Strip leading "folder"/"direktori" that may have been captured after "ke"
            candidate = re.sub(r"^(?:folder|direktori|directory|path)\s+", "", candidate, flags=re.IGNORECASE).strip()
            # Collapse multiple spaces but preserve single spaces inside names
            candidate = re.sub(r"\s{2,}", " ", candidate).strip()
            # Reject if candidate is too generic like just "ke" or "folder"
            if len(candidate) < 3 or candidate.lower() in ("folder", "direktori", "directory", "ke"):
                continue
            if candidate:
                return candidate
    return None
