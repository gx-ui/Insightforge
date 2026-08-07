"""Identify dead CSS rules in src/styles.css against live class names in src/**/*.tsx.

Dry-run by default: prints dead top-level blocks with line ranges and bytes.
Usage: python scripts/find-dead-css.py [--apply]
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / 'src' / 'styles.css'
SRC = ROOT / 'src'

# ---- collect live class names from TSX ----
live = set()
for tsx in SRC.rglob('*.tsx'):
    text = tsx.read_text(encoding='utf-8')
    # double-quoted and single-quoted className strings
    for m in re.finditer(r'className=(["\'])(.*?)\1', text):
        for token in re.split(r'\s+', m.group(2)):
            if token:
                live.add(token)
    # template-literal class names like `message-row role-${x}`
    for m in re.finditer(r'className=\{`([^`]*)`\}', text):
        for token in re.split(r'\s+', m.group(1)):
            if token:
                live.add(token)
    # plain string classes inside templates e.g. `storyboard-panel ${...}`
    for m in re.finditer(r'className=\{`([^`]*\$\{[^`]*\}[^`]*)`\}', text):
        for token in re.split(r'\s+', m.group(1)):
            if token and not token.startswith('${'):
                live.add(token)

# also gather classes referenced from index.html / main html not needed here

def class_tokens(selector):
    """Return the bare class names referenced by a selector (pseudo/combinators stripped)."""
    out = set()
    # strip pseudo-classes/elements: :hover, :focus-visible, :nth-child(2), :is-open, etc.
    sel = re.sub(r'::?[\w-]+(\([^)]*\))?', '', selector)
    for m in re.finditer(r'\.([A-Za-z_][\w-]*)', sel):
        out.add(m.group(1))
    return out

css = CSS.read_text(encoding='utf-8')
lines = css.split('\n')

# ---- parse top-level blocks with line ranges ----
blocks = []  # (start_line, end_line, text)
i = 0
n = len(lines)
depth = 0
start = 0
in_comment = False
in_brace = False
# simple brace counter respecting strings/comments (CSS has no strings beyond font urls)
for idx, line in enumerate(lines):
    # strip comments for brace counting
    stripped = re.sub(r'/\*.*?\*/', '', line, flags=re.S)
    stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
    stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
    opens = stripped.count('{')
    closes = stripped.count('}')
    if not in_brace and opens:
        start = idx
        in_brace = True
    depth += opens - closes
    if in_brace and depth <= 0:
        blocks.append((start, idx, '\n'.join(lines[start:idx + 1])))
        in_brace = False
        depth = 0

# ---- classify and filter ----
KEEP_PREFIXES = ('@import', '@font-face', '@theme')
dead = []
kept_live = 0
kept_keyframes = 0
kept_media_live = 0
for s, e, text in blocks:
    first = text.split('{', 1)[0].strip()
    # keep directives & keyframes & font-face & theme
    if first.startswith(KEEP_PREFIXES) or first.startswith('@keyframes') or first.startswith('@media') or first.startswith('@layer') or first.startswith('@supports'):
        kept_live += 1
        continue
    tokens = class_tokens(first)
    if not tokens:
        # e.g. bare element selectors like `html`, `body`, `button:focus-visible` — keep conservatively
        kept_live += 1
        continue
    # a rule is live if ANY of its selectors references a live class
    if tokens & live:
        kept_live += 1
        continue
    dead.append((s, e, text))

total = 0
for s, e, text in dead:
    total += len(text.encode('utf-8'))
    head = text.split('{', 1)[0].strip().replace('\n', ' ')
    print(f'{s + 1:>5}-{e + 1:<5} {len(text):>6}B  {head[:110]}')

print(f'\n-- {len(dead)} dead top-level blocks, {total} bytes (~{total / 1024:.1f} KB)')
print(f'-- kept: {kept_live} blocks (directives/keyframes/media/live rules)')

if not getattr(sys, '_dead_apply', False) and '--apply' not in sys.argv:
    sys.exit(0)

# -- apply removal (exact substring; remove leading blank line; collapse double blanks) --
result = css
for s, e, text in sorted(dead, key=lambda b: b[0], reverse=True):
    result = result.replace('\n' + text, '', 1)
result = re.sub(r'\n{3,}', '\n\n', result)
CSS.write_text(result, encoding='utf-8')
print(f'\n-- applied: removed {len(dead)} blocks ({total} bytes), rewrote {CSS.name}')
