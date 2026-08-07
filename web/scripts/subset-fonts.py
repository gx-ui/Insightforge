"""Subset the fonts in web/fonts-src into web/public/fonts as woff2.

Run from the repository root with the project venv:
  .venv/Scripts/python.exe web/scripts/subset-fonts.py

Charset policy (see doc/前端UI重构/实施方案-前端UI重构.md A3, revised in M1):
- Body font (MiSans) is NOT handled here: MiSans CJK outlines compress poorly,
  so it ships as unicode-range shards via web/scripts/prepare-misans.py and the
  browser lazy-loads only the ranges it renders.
- Display font (Smiley Sans): ASCII + CJK punctuation + UI copy scan only.
- Latin fonts (JetBrains Mono, Space Grotesk): ASCII + common symbols only.
"""
import re
import sys
from pathlib import Path

from fontTools import subset

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPO_ROOT / 'web'
FONTS_SRC = WEB_ROOT / 'fonts-src'
FONTS_OUT = WEB_ROOT / 'public' / 'fonts'

ASCII_CHARS = ''.join(chr(code) for code in range(0x20, 0x7F))
CJK_PUNCT = '　。、《》〈〉，；：？！…—·～％“”‘’「」『』（）【】〔〕〖〗'
COMMON_SYMBOLS = ASCII_CHARS + '©®™°±×÷←→↑↓↔✓✔✕✖●○◆◇★☆'



def ui_copy_chars() -> str:
    found = set()
    for pattern in ('src/**/*.ts', 'src/**/*.tsx', 'src/**/*.css', 'index.html'):
        for file in WEB_ROOT.glob(pattern):
            found.update(re.findall(r'[^\x00-\x7F]', file.read_text(encoding='utf-8')))
    return ''.join(sorted(found))


def subset_font(source: Path, target: Path, chars: str) -> int:
    options = subset.Options()
    options.flavor = 'woff2'
    options.desubroutinize = True
    options.name_IDs = ['*']
    font = subset.load_font(str(source), options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=chars)
    subsetter.subset(font)
    FONTS_OUT.mkdir(parents=True, exist_ok=True)
    font.save(str(target))
    return target.stat().st_size // 1024


def main() -> None:
    display_chars = ASCII_CHARS + CJK_PUNCT + ui_copy_chars()
    jobs = [
        ('SmileySans-Oblique.ttf', 'smileysans-subset.woff2', display_chars),
        ('jetbrains-mono-latin-400-normal.woff2', 'jetbrains-mono-regular-subset.woff2', COMMON_SYMBOLS),
        ('jetbrains-mono-latin-700-normal.woff2', 'jetbrains-mono-bold-subset.woff2', COMMON_SYMBOLS),
        ('space-grotesk-latin-400-normal.woff2', 'space-grotesk-regular-subset.woff2', COMMON_SYMBOLS),
        ('space-grotesk-latin-700-normal.woff2', 'space-grotesk-bold-subset.woff2', COMMON_SYMBOLS),
    ]
    total = 0
    for source_name, target_name, chars in jobs:
        size_kb = subset_font(FONTS_SRC / source_name, FONTS_OUT / target_name, chars)
        total += size_kb
        print(f'{target_name}: {size_kb} KB')
    print(f'total: {total} KB')


if __name__ == '__main__':
    sys.exit(main())