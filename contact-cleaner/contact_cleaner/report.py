"""Single self-contained HTML report of a cleaning run."""

from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Settings, name_column_note

if TYPE_CHECKING:
    from .pipeline import Result

RULE_TEXT = {
    "whitespace": "Trimmed and collapsed spaces",
    "split_name": "Split a full name into its parts",
    "name_case": "Fixed name capitals",
    "email": "Lower-cased or cleaned an email, or removed one that is unusable or uncertain",
    "phone": "Formatted a phone number to international (E.164) form, or removed one that is unreadable or not valid",
    "dates": "Converted a date to YYYY-MM-DD",
    "postcode": "Formatted a UK postcode",
    "formula_guard": "Put an apostrophe before text a spreadsheet would run as a formula",
    "merge_fill": "Filled a blank field from a duplicate being merged",
    "merge_discard": "Differing value on a merged duplicate, not kept (listed in merges.csv)",
}

CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:32px 0 10px}
.sub{color:#5b6475;margin:0 0 20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.tile{background:#fff;border:1px solid #dde1e8;border-radius:8px;padding:12px}
.tile b{display:block;font-size:1.6rem}.tile span{color:#5b6475;font-size:.85rem}
table{border-collapse:collapse;width:100%;background:#fff;font-size:.88rem}
th,td{border:1px solid #dde1e8;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#eef1f5}td.n{text-align:right;font-variant-numeric:tabular-nums}
.ok{color:#17703a}.wrap{overflow-x:auto}code{font-size:.85em}
del{color:#a3262b}ins{color:#17703a;text-decoration:none}
"""


def _tile(value: object, label: str) -> str:
    return f'<div class="tile"><b>{escape(str(value))}</b><span>{escape(label)}</span></div>'


def _table(headers: list[str], rows: list[list[str]], numeric: set[int] | None = None) -> str:
    numeric = numeric or set()
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f'<td{" class=n" if i in numeric else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>"
        for r in rows)
    return f'<div class="wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def write_report(result: Result, path: Path, settings: Settings) -> None:
    by_rule: dict[str, list] = defaultdict(list)
    for change in result.changes:
        by_rule[change.rule].append(change)
    rows_touched = {rule: len({c.row for c in changes}) for rule, changes in by_rule.items()}
    merged_away = len(result.merges)
    reconciles = result.input_rows == len(result.clean) + len(result.rejects) + merged_away
    reject_reasons = Counter(reason.split(" (")[0] for _, reason in result.rejects)

    parts = [f"<h1>Contact clean-up report</h1><p class=sub>Input: <code>{escape(result.input_name)}</code>"
             + (f", sheet <code>{escape(result.table.sheet)}</code>" if result.table.sheet else "")
             + (f", encoding {escape(result.table.encoding)}" if result.table.encoding else "") + "</p>"]
    parts.append('<div class="tiles">' + "".join([
        _tile(result.input_rows, "rows in"),
        _tile(len(result.clean), "clean contacts out"),
        _tile(len(result.rejects), "rejected"),
        _tile(merged_away, "merged as exact duplicates"),
        _tile(sum(1 for r in result.clean if r.flags), "kept rows needing review"),
        _tile(len(result.changes), "individual changes"),
    ]) + "</div>")
    check = "adds up" if reconciles else "DOES NOT ADD UP"
    parts.append(f'<p class="{"ok" if reconciles else ""}">Check: {result.input_rows} rows in = {len(result.clean)} clean + '
                 f'{len(result.rejects)} rejected + {merged_away} merged away. This {check}.</p>')

    parts.append("<h2>Column mapping</h2>")
    parts.append(_table(["Field", "Source column", "Output column"],
                        [[escape(f), escape(h), escape(settings.targets.get(f, "(passthrough.csv)"))]
                         for f, h in result.mapping.items()]))
    note = name_column_note(result.mapping)
    if note:
        parts.append(f"<p>Check: {escape(note)}</p>")
    if result.unmapped:
        parts.append("<p>Not mapped, kept in passthrough.csv: " + ", ".join(f"<code>{escape(h)}</code>" for h in result.unmapped) + "</p>")

    parts.append("<h2>What each rule changed</h2>")
    parts.append(_table(["Rule", "What it does", "Values changed", "Rows touched", "Switched on"],
                        [[f"<code>{r}</code>", escape(t), str(len(by_rule.get(r, []))), str(rows_touched.get(r, 0)),
                          "yes" if settings.on("dedupe_exact" if r.startswith("merge") else r) else "no"] for r, t in RULE_TEXT.items()],
                        numeric={2, 3}))

    parts.append("<h2>Flags on kept rows (see review.csv)</h2>")
    parts.append(_table(["Flag", "Rows"], [[f"<code>{escape(k)}</code>", str(v)] for k, v in sorted(result.flag_counts.items())], {1})
                 if result.flag_counts else "<p>None.</p>")

    parts.append("<h2>Rejected rows (see rejects.csv)</h2>")
    parts.append(_table(["Reason", "Rows"], [[escape(k), str(v)] for k, v in reject_reasons.items()], {1})
                 if reject_reasons else "<p>None.</p>")

    parts.append("<h2>Examples of each kind of fix</h2>")
    for rule, text in RULE_TEXT.items():
        changes = by_rule.get(rule, [])
        if not changes:
            continue
        seen: set[tuple[str, str]] = set()
        examples = []
        for c in changes:
            if (c.before, c.after) in seen:
                continue
            seen.add((c.before, c.after))
            examples.append([escape(c.row), escape(c.field), f"<del>{escape(repr(c.before)[1:-1])}</del>",
                             f"<ins>{escape(c.after) if c.after else '(blank)'}</ins>"])
            if len(examples) == 6:
                break
        parts.append(f"<h3>{escape(text)}</h3>" + _table(["Row", "Field", "Before", "After"], examples))

    parts.append("<h2>Exact duplicates merged (see merges.csv)</h2>")
    parts.append(_table(["Kept row", "Merged row", "Email", "Filled in", "Not kept"],
                        [[escape(m.kept_row), escape(m.merged_row), escape(m.email), escape("; ".join(m.filled)), escape("; ".join(m.discarded))]
                         for m in result.merges[:25]]) if result.merges else "<p>None.</p>")
    if len(result.merges) > 25:
        parts.append(f"<p>Showing 25 of {len(result.merges)}.</p>")

    html = ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Contact clean-up report</title><style>{CSS}</style></head><body><main>"
            + "".join(parts) + "</main></body></html>")
    path.write_text(html, encoding="utf-8")
