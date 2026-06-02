"""Common CSS base injected into free-form academy_render_image HTML.

The general-purpose render tool lets the model hand over raw HTML, but raw HTML
with no styling renders with a blocky system font, no number alignment, and
collapsed table borders — 명단/표의 줄이 어긋나 보이는 주된 원인이다. This module
provides the same quality recipe the dedicated academy report (report_design.py)
and the KBO/health image cards rely on, packaged as a *base* layer:

- the bundled Pretendard webfont (report_fonts.report_font_css) so Korean always
  renders in a clean typeface offline, never a host fallback;
- ``font-variant-numeric: tabular-nums`` so digits are fixed-width and columns of
  numbers line up;
- ``table-layout: fixed`` + ``border-collapse`` + cell padding + tabular digits so
  table rows and headers line up structurally;
- light paper background, soft borders, alternating rows, ``word-break: keep-all``.

The base deliberately does NOT set ``text-align`` on table cells: column
alignment (text=left, number/record=right, header matching its column) is
semantic and belongs to the model, which writes it inline or in its own
<style>. The base only supplies font/reset/structure so the model's alignment
is never fought by a base center/left default.

The base is injected as the FIRST stylesheet inside <head>, so the model's own
<style> still wins when it wants a custom look — the base only fills in the
common case where the model supplied data but no styling.
"""

from __future__ import annotations

import re

from .report_fonts import PRETENDARD_FAMILY, report_font_css

# Korean-first font stack — bundled Pretendard primary, robust system fallbacks
# (mirrors report_design._FONT_STACK and the KBO/health card font stacks).
_FONT_STACK = (
    f"'{PRETENDARD_FAMILY}','Goyang','GoyangDeogyang','Pretendard',"
    "'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif"
)

# Clean base stylesheet for free-form HTML. Same design intent as
# report_design._CSS but generic (no academy report chrome): readable Korean
# typography, aligned tables, tidy lists/cards. Selectors are plain element
# selectors so a model that only emits a <table>/<ul> gets the good defaults,
# and any class/inline styles the model adds still override these.
_BASE_CSS = f"""
*{{box-sizing:border-box;}}
html,body{{margin:0;background:#eef0f4;}}
body{{font-family:{_FONT_STACK};color:#16181d;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  font-variant-numeric:tabular-nums;
  font-size:16px;line-height:1.5;letter-spacing:-.01em;
  word-break:keep-all;padding:40px 44px;}}
.sheet,main,section{{max-width:1180px;}}
h1{{font-size:30px;font-weight:700;line-height:1.15;margin:0 0 6px;letter-spacing:-.02em;}}
h2{{font-size:21px;font-weight:700;line-height:1.2;margin:24px 0 10px;letter-spacing:-.015em;}}
h3{{font-size:17px;font-weight:700;margin:18px 0 8px;}}
p{{margin:0 0 10px;}}
ul,ol{{margin:0 0 12px;padding-left:24px;line-height:1.55;}}
li{{margin:3px 0;}}
table{{width:100%;border-collapse:collapse;table-layout:fixed;
  background:#ffffff;border:1px solid #e6e9ef;border-radius:14px;
  overflow:hidden;margin:0 0 16px;
  box-shadow:0 1px 2px rgba(20,24,29,.05),0 18px 44px -28px rgba(20,24,29,.24);}}
/* No text-align here: column alignment is the model's job (text=left,
   number/record=right), set via inline style or its own <style>. The base only
   lays out padding, number tabular-figures, and cell clipping — it must not
   force center/left and fight the model's per-column alignment. */
th,td{{padding:13px 16px;font-size:15px;
  font-variant-numeric:tabular-nums;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
thead th{{font-size:12.5px;font-weight:700;color:#717784;letter-spacing:.01em;
  background:#f8fafc;border-bottom:1.5px solid #e6e9ef;}}
tbody td{{border-bottom:1px solid #f0f2f6;color:#16181d;}}
tbody tr:nth-child(even) td{{background:#f8fafc;}}
tbody tr:last-child td{{border-bottom:none;}}
caption{{caption-side:top;text-align:left;font-size:18px;font-weight:700;
  margin:0 0 10px;color:#16181d;}}
"""


def _base_style_block() -> str:
    return f"<style>{report_font_css()}{_BASE_CSS}</style>"


_HEAD_OPEN_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_HTML_OPEN_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)


def inject_base_style(html: str) -> str:
    """Return ``html`` with the common base stylesheet injected first in <head>.

    The base is placed at the very start of <head> so any <style> or inline
    styles the model wrote afterwards take precedence (CSS source order), while
    unstyled raw HTML still gets the clean, aligned defaults. Handles three
    shapes the model may hand over:

    - a full document with <head> → inject right after <head>;
    - a document with <html> but no <head> → add a <head> with the base;
    - a bare fragment (no <html>) → wrap it in a full document.
    """
    head_match = _HEAD_OPEN_RE.search(html)
    if head_match:
        insert_at = head_match.end()
        return html[:insert_at] + _base_style_block() + html[insert_at:]

    html_match = _HTML_OPEN_RE.search(html)
    if html_match:
        insert_at = html_match.end()
        head = f"<head><meta charset='utf-8'>{_base_style_block()}</head>"
        return html[:insert_at] + head + html[insert_at:]

    return (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        f"{_base_style_block()}</head><body>{html}</body></html>"
    )
