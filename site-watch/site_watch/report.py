"""Build a single HTML evidence report.

Screenshots are copied into an `images` folder next to the report and linked by
relative path, so the report folder can be copied anywhere.
"""

from __future__ import annotations

import html
import shutil
from pathlib import Path

from .config import Config
from .store import Event, Store

CSS = """
body { font-family: system-ui, sans-serif; margin: 0; background: #f4f5f7; color: #1d2330; }
header { background: #1d2330; color: #fff; padding: 20px 32px; }
header h1 { margin: 0 0 4px; font-size: 22px; }
header p { margin: 0; color: #c5cad6; }
main { padding: 24px 32px; max-width: 1400px; }
.change { background: #fff; border: 1px solid #d8dce4; border-radius: 6px; margin-bottom: 28px; padding: 16px 20px; }
.change h2 { margin: 0 0 4px; font-size: 18px; }
.meta { color: #5b6475; font-size: 14px; margin-bottom: 12px; }
.meta a { color: #2457c5; }
pre.diff { background: #fafbfc; border: 1px solid #e3e6ec; padding: 10px; overflow-x: auto; font-size: 13px; line-height: 1.45; }
pre.diff span { display: block; padding: 0 4px; }
.add { background: #e3f6e5; color: #145c1e; }
.del { background: #fde6e6; color: #8a1616; }
.hunk { color: #6a5acd; }
.shots { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.shots figure { margin: 0; }
.shots figcaption { font-weight: 600; margin-bottom: 6px; }
.shots img { width: 100%; border: 1px solid #d8dce4; }
table { border-collapse: collapse; background: #fff; font-size: 14px; }
td, th { border: 1px solid #d8dce4; padding: 6px 10px; text-align: left; }
"""


def _diff_html(diff: str) -> str:
    out = []
    for i, line in enumerate(diff.splitlines()):
        cls = ""
        if i < 2 and line.startswith(("+++", "---")):  # file headers only
            cls = "hunk"
        elif line.startswith("+"):
            cls = "add"
        elif line.startswith("-"):
            cls = "del"
        elif line.startswith("@@"):
            cls = "hunk"
        out.append(f'<span class="{cls}">{html.escape(line) or "&nbsp;"}</span>')
    return "".join(out)


def _change_html(event: Event, config: Config, images: Path) -> str:
    folder = config.data_dir / (event.evidence or "")
    tag = f"{event.id:04d}"
    for side in ("before", "after"):
        src = folder / f"{side}.png"
        if src.exists():
            shutil.copyfile(src, images / f"{tag}-{side}.png")
    diff_file = folder / "diff.txt"
    diff = diff_file.read_text(encoding="utf-8") if diff_file.exists() else "(diff file missing)"
    return f"""
<section class="change">
  <h2>{html.escape(event.watch)}</h2>
  <div class="meta">{html.escape(event.at.replace("T", " "))} &middot; lines {html.escape(event.detail)} &middot;
    <a href="{html.escape(event.url)}">{html.escape(event.url)}</a></div>
  <pre class="diff">{_diff_html(diff)}</pre>
  <div class="shots">
    <figure><figcaption>Before</figcaption><img src="images/{tag}-before.png" alt="Before"></figure>
    <figure><figcaption>After</figcaption><img src="images/{tag}-after.png" alt="After"></figure>
  </div>
</section>"""


def _retry_state(config: Config, event: Event) -> str:
    kept = config.failed_alerts_dir / (event.evidence or "")
    return "Kept, will be retried on the next check" if kept.is_file() else "Sent on a later retry"


def build_report(config: Config, out_file: Path) -> int:
    """Write the report and return the number of changes in it."""
    images = out_file.parent / "images"
    images.mkdir(parents=True, exist_ok=True)
    store = Store(config.db_path)
    try:
        changes = store.events("changed")
        failures = store.events("failed")
        alert_failures = store.events("alert_failed")
    finally:
        store.close()

    sections = "".join(_change_html(e, config, images) for e in reversed(changes))
    if not changes:
        sections = "<p>No changes recorded yet.</p>"
    fail_rows = "".join(
        f"<tr><td>{html.escape(f.at.replace('T', ' '))}</td><td>{html.escape(f.watch)}</td>"
        f"<td>{html.escape(f.detail)}</td></tr>"
        for f in reversed(failures)
    )
    fail_block = (
        f"<h2>Failed checks</h2><table><tr><th>Time</th><th>Watch</th><th>Reason</th></tr>{fail_rows}</table>"
        if failures
        else ""
    )
    alert_rows = "".join(
        f"<tr><td>{html.escape(a.at.replace('T', ' '))}</td><td>{html.escape(a.watch)}</td>"
        f"<td>{html.escape(a.detail)}</td><td>{_retry_state(config, a)}</td></tr>"
        for a in reversed(alert_failures)
    )
    alert_block = (
        "<h2>Alerts that could not be sent</h2><table><tr><th>Time</th><th>Watch</th><th>Error</th>"
        f"<th>Now</th></tr>{alert_rows}</table>"
        if alert_failures
        else ""
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>site-watch evidence report</title><style>{CSS}</style></head>
<body><header><h1>site-watch evidence report</h1>
<p>{len(changes)} change(s), {len(failures)} failed check(s), {len(alert_failures)} alert(s) not sent. Newest first.</p></header>
<main>{alert_block}{sections}{fail_block}</main></body></html>
"""
    out_file.write_text(page, encoding="utf-8")
    return len(changes)
