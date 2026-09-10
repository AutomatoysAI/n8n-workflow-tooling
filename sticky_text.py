"""Undo the hard line wrapping in sticky-note text before it goes into the JSON.

The problem this fixes
----------------------

Sticky-note content is written inside the build scripts as ordinary Python
triple-quoted strings, hand-wrapped at about 78 columns so the source stays
readable. Every one of those wraps is a real newline in the string.

n8n keeps a single newline in a sticky note as a line break. So a paragraph
written as three tidy source lines arrives on the canvas broken across three
lines at whatever width the source happened to wrap at - stopping mid-sentence,
nothing to do with the width of the note. Reading it aloud on a call means
stitching the sentences back together by eye.

So paragraphs get joined back together here, at build time, and the build
scripts keep their readable wrapping.

How to use it
-------------

At the top of a build script:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sticky_text import unwrap

and inside sticky(), pass the content through it:

    {"content": unwrap(content), ...}

The demos built before September 2026 do not use this and are deliberately left
as they are.

What it leaves alone
--------------------

- Blank lines, which are what separates one paragraph from the next.
- Fenced code blocks and the ASCII canvas diagrams inside them.
- Headings, table rows, and the first line of a list item or a blockquote.
- Two trailing spaces, which is markdown's own way of asking for a line break.

A wrapped continuation line joins the line above it. A line that starts a new
block never does.
"""
import re

# A line opening a block of its own: heading, list item, table row, quote.
OPENS_BLOCK = re.compile(r"^(#{1,6}\s|[-*+]\s|\d+[.)]\s|\||>)")


def unwrap(text):
    """Join hard-wrapped lines back into paragraphs. Idempotent."""
    out = []
    in_code = False

    for raw in text.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(raw)
            continue
        if not stripped:
            out.append("")
            continue

        prev = out[-1] if out else ""
        prev_stripped = prev.strip()

        # Nothing to join onto, or the line above ended a block deliberately.
        if (not prev_stripped
                or prev_stripped.startswith("|")
                or prev_stripped.startswith("```")
                or prev.endswith("  ")):
            out.append(line)
            continue

        in_quote = stripped.startswith(">")
        prev_in_quote = prev_stripped.startswith(">")

        if in_quote != prev_in_quote:
            out.append(line)              # entering or leaving a quote
            continue

        # Inside a quote, compare what comes after the "> " marker.
        body = stripped.lstrip(">").strip() if in_quote else stripped
        if not body or OPENS_BLOCK.match(body):
            out.append(line)              # a new heading, bullet, row or item
            continue

        out[-1] = prev + " " + body

    return "\n".join(out)
