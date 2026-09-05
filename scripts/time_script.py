"""Measure whether the demo script actually fits in three minutes.

A script that runs over is discovered while recording, which is the most
expensive moment to discover it. The arithmetic is simple enough to be worth
doing before you press record, and easy enough to get wrong by hand.

Two things happen in each beat and they overlap: narration, and the product
executing. Adding them double-counts, because talking over a wait is free.
Subtracting them entirely is optimistic, because you cannot talk for forty
seconds over a five second click. So each beat costs

    max(narration_time, execution_time) + transition

and the beats are summed. Execution times are declared in the script itself as
`<!-- exec: 27 -->` comments so this stays honest when the narration is edited.

    python scripts/time_script.py
    python scripts/time_script.py --fix-headings   # renumber the beats to match
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The script uses en dashes and arrows; a Windows console defaults to a codepage
# that cannot encode them and the tool dies on its own output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT = Path(__file__).resolve().parents[1] / "docs" / "DEMO-SCRIPT.md"
WORDS_PER_MINUTE = 165
TRANSITION_SECONDS = 1.5
HARD_LIMIT = 180
TARGET = 172


def beats(text: str) -> list[tuple[str, int, float]]:
    """Return (title, narrated words, declared execution seconds) per beat."""

    found: list[tuple[str, int, float]] = []
    sections = re.split(r"\n## ", text)
    for section in sections:
        heading = section.split("\n", 1)[0].strip()
        if not re.match(r"\d\d?:\d\d", heading):
            continue
        # Stage directions live in blockquotes and narration does not.
        # Without this, naming an on-screen heading in a DO line as
        # **"Diagnose"** counts as something the presenter says, and the
        # beat is costed for words nobody speaks.
        narration = chr(10).join(
            line for line in section.splitlines() if not line.lstrip().startswith(">")
        )
        spoken = re.findall(r'\*\*"(.+?)"\*\*', narration, re.S)
        words = sum(len(re.findall(r"[\w'’-]+", block)) for block in spoken)
        exec_match = re.search(r"<!--\s*exec:\s*([\d.]+)\s*-->", section)
        found.append((heading, words, float(exec_match.group(1)) if exec_match else 0.0))
    return found


def rewrite_headings(text: str, rows: list[tuple[str, int, float]]) -> str:
    """Renumber the beat timestamps from the measured costs.

    Hand-written timestamps drift the moment narration is edited, and a reader
    then finds a two second gap between one beat ending and the next starting.
    The costs are already computed, so the headings can just be derived.
    """

    clock = 0.0
    for heading, words, execution in rows:
        cost = max(words / WORDS_PER_MINUTE * 60, execution) + TRANSITION_SECONDS
        start, end = clock, clock + cost
        title = heading.split("·", 1)[1].strip() if "·" in heading else heading
        stamped = (
            f"{int(start // 60)}:{int(start % 60):02d}–{int(end // 60)}:{int(end % 60):02d}"
            f" · {title}"
        )
        text = text.replace(f"## {heading}", f"## {stamped}", 1)
        clock = end
    return text


def main() -> int:
    fix = "--fix-headings" in sys.argv
    text = SCRIPT.read_text(encoding="utf-8")
    rows = beats(text)
    if not rows:
        print("no timed beats found; headings must start with a timestamp")
        return 2

    total = 0.0
    print(f"{'beat':<44} {'words':>6} {'say':>7} {'run':>7} {'costs':>7}")
    print("-" * 76)
    for heading, words, execution in rows:
        say = words / WORDS_PER_MINUTE * 60
        cost = max(say, execution) + TRANSITION_SECONDS
        total += cost
        print(f"{heading[:44]:<44} {words:>6} {say:>6.0f}s {execution:>6.0f}s {cost:>6.0f}s")

    if fix:
        SCRIPT.write_text(rewrite_headings(text, rows), encoding="utf-8")
        print(chr(10) + "headings renumbered from the measured costs")

    print("-" * 76)
    minutes, seconds = divmod(int(round(total)), 60)
    print(f"{'estimated runtime':<44} {'':>6} {'':>7} {'':>7} {minutes}:{seconds:02d}")
    print()
    if total > HARD_LIMIT:
        print(f"OVER the {HARD_LIMIT}s hard limit by {total - HARD_LIMIT:.0f}s. Cut narration.")
        return 1
    if total > TARGET:
        print(f"Fits, but only {HARD_LIMIT - total:.0f}s of margin. Trim a sentence.")
        return 0
    print(f"Fits with {HARD_LIMIT - total:.0f}s of margin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
