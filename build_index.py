#!/usr/bin/env python3
"""Regenerate index.html for the ENRG 330 self-guided lectures repo.

Scans the repo root (and one level of subdirectories) for lecture HTML files,
reads a small amount of metadata out of each, and writes index.html.

Standard library only. No dependencies, no build toolchain.

How a lecture declares itself (in order of precedence):

  1. Meta tags in the <head>:
         <meta name="lecture-number" content="7">      (or "7a")
         <meta name="lecture-title"  content="Phase Diagrams I">
         <meta name="lecture-topic"  content="One-line description">   (optional)
  2. Filename matching  L##_slug.html  (e.g. L07_phase-diagrams.html,
     L07a_phase-diagrams.html) -- digits after L are the number, optional
     trailing letter is the suffix, slug becomes the title.
  3. <title> is used as a second fallback for the title.

A file with neither a meta number nor a parseable filename is NOT skipped: it
lands in an "Unfiled" section at the bottom of the index and a warning is
printed to stdout.

Determinism: the output contains no timestamps and no random ordering, so
running this twice with no file changes produces a byte-identical index.html.
The GitHub Action relies on that -- a timestamp would mean a commit on every
push, forever.

Run by hand:   py build_index.py       (Windows)
               python3 build_index.py  (macOS/Linux/CI)
"""

from __future__ import annotations

import html
import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import quote

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

OUTPUT_NAME = "index.html"

PAGE_HEADING = "ENRG 330: Self-Guided Lectures"

# Directories never scanned for lectures (matched case-insensitively).
EXCLUDED_DIRS = {
    ".git",
    ".github",
    "assets",
    "img",
    "images",
    "css",
    "js",
    "template",
    "templates",
    "node_modules",
}

# Files never treated as a lecture (matched case-insensitively).
EXCLUDED_FILES = {OUTPUT_NAME.lower()}

# Filename fallback. All of these parse:
#   L07_phase-diagrams.html          -> 7,  "Phase Diagrams"
#   L07a-phase-diagrams.html         -> 7a
#   lecture3s_density-solver.html    -> 3s, "Density Solver"
#   lecture 2s bond-energy-solver    -> 2s
#   Lecture-12.html                  -> 12
# The prefix word is optional in form but required in kind: something has to
# say "lecture" before the digits, or every file with a number in its name
# would be swept in.
FILENAME_PATTERN = re.compile(
    r"^(?:lecture|lect|lec|L)[_\-\s]*(\d{1,3})\s*([A-Za-z]{0,2})\s*(?:[_\-\s]+(?P<slug>.*))?$",
    re.IGNORECASE,
)

# Contents of a lecture-number meta tag: "7", "07", "7a", "7 a".
META_NUMBER_PATTERN = re.compile(r"^\s*(\d{1,3})\s*([A-Za-z]{0,2})\s*$")


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


class HeadParser(HTMLParser):
    """Pull <meta name=...> and <title> out of the document head.

    Stops collecting once </head> (or <body>) is reached, so a lecture with a
    few hundred KB of inline script costs almost nothing to inspect.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metas: dict[str, str] = {}
        self.title: str | None = None
        self._in_title = False
        self._title_parts: list[str] = []
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        tag = tag.lower()
        if tag == "body":
            self._finish()
        elif tag == "meta":
            a = {k.lower(): (v or "") for k, v in attrs}
            name = a.get("name", "").strip().lower()
            if name:
                # First occurrence wins.
                self.metas.setdefault(name, a.get("content", "").strip())
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if self.done:
            return
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            if self.title is None:
                self.title = "".join(self._title_parts).strip() or None
        elif tag == "head":
            self._finish()

    def handle_data(self, data):
        if self._in_title and not self.done:
            self._title_parts.append(data)

    def _finish(self) -> None:
        if self._title_parts and self.title is None:
            self.title = "".join(self._title_parts).strip() or None
        self.done = True


def read_text(path: str) -> str:
    """Read a file as text, tolerating the usual Windows encoding drift."""
    with open(path, "rb") as fh:
        raw = fh.read()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_head(path: str) -> tuple[dict[str, str], str | None]:
    """Return ({meta name: content}, title-or-None) for one HTML file."""
    text = read_text(path)
    parser = HeadParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:  # malformed markup -- keep whatever was parsed
        pass
    return parser.metas, parser.title


# --------------------------------------------------------------------------
# Metadata resolution
# --------------------------------------------------------------------------


def titlecase_slug(slug: str) -> str:
    """'phase-diagrams_I' -> 'Phase Diagrams I'."""
    words = re.split(r"[\s_\-]+", slug.strip())
    out = []
    for word in words:
        if not word:
            continue
        # Leave anything already containing an uppercase letter alone (FCC, I, II).
        out.append(word if any(c.isupper() for c in word) else word.capitalize())
    return " ".join(out)


def parse_number(raw: str) -> tuple[int, str] | None:
    """'07a' -> (7, 'a'). Returns None if not parseable."""
    m = META_NUMBER_PATTERN.match(raw or "")
    if not m:
        return None
    return int(m.group(1)), m.group(2).lower()


def describe(number: int, suffix: str) -> str:
    return f"{number}{suffix}"


class Lecture:
    __slots__ = ("relpath", "number", "suffix", "title", "topic", "source")

    def __init__(self, relpath, number, suffix, title, topic, source):
        self.relpath = relpath          # posix-style path relative to repo root
        self.number = number            # int, or None for Unfiled
        self.suffix = suffix            # '' or 'a'
        self.title = title
        self.topic = topic
        self.source = source            # 'meta' | 'filename' | 'unfiled'

    @property
    def label(self) -> str:
        return describe(self.number, self.suffix) if self.number is not None else ""

    @property
    def sort_key(self):
        return (self.number, self.suffix, self.relpath.lower())


def build_lecture(repo_root: str, relpath: str, warnings: list[str]) -> Lecture:
    abspath = os.path.join(repo_root, relpath.replace("/", os.sep))
    metas, doc_title = parse_head(abspath)

    stem = os.path.splitext(os.path.basename(relpath))[0]
    fm = FILENAME_PATTERN.match(stem)

    # ---- number -----------------------------------------------------------
    number = suffix = None
    source = "unfiled"

    meta_num = parse_number(metas.get("lecture-number", ""))
    if meta_num is not None:
        number, suffix = meta_num
        source = "meta"
    elif fm:
        number, suffix = int(fm.group(1)), (fm.group(2) or "").lower()
        source = "filename"
    else:
        raw = metas.get("lecture-number")
        if raw:
            warnings.append(
                f'{relpath}: lecture-number meta tag is "{raw}", which is not a '
                f"number (expected e.g. 7 or 7a) -- filed as Unfiled"
            )
        else:
            warnings.append(
                f"{relpath}: no lecture-number meta tag, and the filename does not "
                f"carry a number (expected something like lecture7_slug.html or "
                f"L07_slug.html) -- filed as Unfiled"
            )

    # ---- title ------------------------------------------------------------
    title = (metas.get("lecture-title") or "").strip()
    if not title and doc_title:
        title = doc_title.strip()
    if not title and fm and fm.group("slug"):
        title = titlecase_slug(fm.group("slug"))
    if not title:
        title = titlecase_slug(stem)

    # Collapse whitespace so a wrapped <title> does not produce a ragged entry.
    title = re.sub(r"\s+", " ", title)

    # ---- topic ------------------------------------------------------------
    topic = re.sub(r"\s+", " ", (metas.get("lecture-topic") or "").strip()) or None

    return Lecture(relpath, number, suffix, title, topic, source)


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------


def find_lecture_files(repo_root: str) -> list[str]:
    """Root-level *.html plus *.html one directory down. Sorted, posix paths."""
    found: list[str] = []

    def html_files_in(directory: str, prefix: str) -> list[str]:
        names = []
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if not os.path.isfile(full):
                continue
            if not name.lower().endswith(".html"):
                continue
            if name.lower() in EXCLUDED_FILES:
                continue
            names.append(prefix + name)
        return names

    found.extend(html_files_in(repo_root, ""))

    for name in sorted(os.listdir(repo_root)):
        sub = os.path.join(repo_root, name)
        if not os.path.isdir(sub):
            continue
        if name.lower() in EXCLUDED_DIRS or name.startswith("."):
            continue
        found.extend(html_files_in(sub, name + "/"))

    return sorted(found, key=str.lower)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

STYLE = """\
    :root {
      color-scheme: light dark;
      --bg: #ffffff;
      --fg: #1a1c20;
      --muted: #55606e;
      --accent: #1f3864;
      --line: #d7dde5;
      --card: #f6f8fa;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --bg: #14161a;
        --fg: #e8eaed;
        --muted: #a4adba;
        --accent: #9db8e8;
        --line: #2c313a;
        --card: #1c1f25;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      -webkit-text-size-adjust: 100%;
    }
    .wrap { max-width: 40rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
    h1 { font-size: 1.5rem; line-height: 1.3; margin: 0 0 0.25rem; color: var(--accent); }
    .sub { margin: 0 0 2rem; color: var(--muted); font-size: 0.95rem; }
    h2 {
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin: 2.5rem 0 0.75rem;
      border-top: 1px solid var(--line);
      padding-top: 1rem;
    }
    ul { list-style: none; margin: 0; padding: 0; }
    li { margin: 0 0 0.5rem; }
    a.entry {
      display: flex;
      gap: 0.7rem;
      align-items: baseline;
      padding: 0.75rem 0.9rem;
      border: 1px solid var(--line);
      border-radius: 0.5rem;
      background: var(--card);
      text-decoration: none;
      color: inherit;
    }
    a.entry:hover, a.entry:focus { border-color: var(--accent); }
    a.entry:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .num {
      flex: 0 0 auto;
      min-width: 1.8rem;
      font-variant-numeric: tabular-nums;
      font-weight: 700;
      color: var(--accent);
    }
    .body { flex: 1 1 auto; min-width: 0; }
    .title { display: block; font-weight: 600; }
    .topic { display: block; margin: 0.2rem 0 0; color: var(--muted); font-size: 0.9rem; }
    .file { display: block; margin: 0.2rem 0 0; color: var(--muted); font-size: 0.85rem; word-break: break-word; }
    .empty { color: var(--muted); }
"""


def render_entry(lecture: Lecture, show_filename: bool) -> list[str]:
    href = quote(lecture.relpath, safe="/")
    lines = ["    <li>", f'      <a class="entry" href="{html.escape(href, quote=True)}">']
    if lecture.label:
        lines.append(f'        <span class="num">{html.escape(lecture.label)}</span>')
    lines.append("        <span class=\"body\">")
    lines.append(f'          <span class="title">{html.escape(lecture.title)}</span>')
    if lecture.topic:
        lines.append(f'          <span class="topic">{html.escape(lecture.topic)}</span>')
    if show_filename:
        lines.append(f'          <span class="file">{html.escape(lecture.relpath)}</span>')
    lines.append("        </span>")
    lines.append("      </a>")
    lines.append("    </li>")
    return lines


def render_index(numbered: list[Lecture], unfiled: list[Lecture]) -> str:
    out: list[str] = []
    add = out.append

    add("<!DOCTYPE html>")
    add('<html lang="en">')
    add("<head>")
    add('<meta charset="UTF-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add(f"<title>{html.escape(PAGE_HEADING)}</title>")
    add("<style>")
    add(STYLE.rstrip("\n"))
    add("</style>")
    add("</head>")
    add("<body>")
    add('<main class="wrap">')
    add(f"  <h1>{html.escape(PAGE_HEADING)}</h1>")
    add('  <p class="sub">Supplemental self-guided lectures and problems.</p>')

    if numbered:
        add("  <ul>")
        for lecture in numbered:
            out.extend(render_entry(lecture, show_filename=False))
        add("  </ul>")
    else:
        add('  <p class="empty">No numbered lectures yet.</p>')

    if unfiled:
        add("  <h2>Unfiled</h2>")
        add('  <p class="sub">These files carry no lecture number yet.</p>')
        add("  <ul>")
        for lecture in unfiled:
            out.extend(render_entry(lecture, show_filename=True))
        add("  </ul>")

    add("</main>")
    add("</body>")
    add("</html>")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    repo_root = REPO_ROOT

    try:
        relpaths = find_lecture_files(repo_root)
    except OSError as exc:
        print(f"ERROR: could not scan the repo: {exc}", file=sys.stderr)
        return 1

    warnings: list[str] = []
    lectures: list[Lecture] = []
    for relpath in relpaths:
        try:
            lectures.append(build_lecture(repo_root, relpath, warnings))
        except OSError as exc:
            print(f"ERROR: could not read {relpath}: {exc}", file=sys.stderr)
            return 1

    numbered = sorted(
        (lec for lec in lectures if lec.number is not None), key=lambda l: l.sort_key
    )
    unfiled = sorted(
        (lec for lec in lectures if lec.number is None), key=lambda l: l.relpath.lower()
    )

    document = render_index(numbered, unfiled)
    output_path = os.path.join(repo_root, OUTPUT_NAME)
    try:
        # newline="\n" on purpose: identical bytes on Windows and on the CI
        # runner, so the Action does not commit a line-ending flip every push.
        with open(output_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(document)
    except OSError as exc:
        print(f"ERROR: could not write {OUTPUT_NAME}: {exc}", file=sys.stderr)
        return 1

    # ---- summary ----------------------------------------------------------
    print(f"Wrote {OUTPUT_NAME}")
    print(f"  {len(numbered)} numbered lecture(s), {len(unfiled)} unfiled")
    if numbered:
        print("  numbers: " + ", ".join(lec.label for lec in numbered))
        duplicates = {}
        for lec in numbered:
            duplicates.setdefault(lec.label, []).append(lec.relpath)
        for label, paths in sorted(duplicates.items()):
            if len(paths) > 1:
                print(
                    f"  note: {len(paths)} files share number {label}: "
                    + ", ".join(paths)
                )
    for warning in warnings:
        print(f"  WARNING: {warning}")
    if unfiled:
        print(
            "  Unfiled files are listed at the bottom of the index. Add a "
            '<meta name="lecture-number" content="N"> tag to file them.'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
