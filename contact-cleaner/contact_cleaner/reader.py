"""Read .xlsx and .csv files into header list plus rows of text, keeping row numbers."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook


@dataclass
class Table:
    headers: list[str]
    rows: list[tuple[int, dict[str, str]]]  # (row number in the source file, header -> text)
    encoding: str = ""
    sheet: str = ""
    delimiter: str = ""
    row_flags: dict[int, list[tuple[str, str]]] = field(default_factory=dict)  # row number -> flags


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")  # the date rule converts this, so the change is counted
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _unique_headers(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, header in enumerate(raw):
        name = header.strip() or f"Column {i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        out.append(name)
    return out


def read_xlsx(path: Path, sheet: str | None = None) -> Table:
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[0]
    title = ws.title
    values = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    # A workbook never opened in Excel has formulas but no stored results.
    # Keep the formula text rather than a silent blank, and flag the row.
    formulas = load_workbook(path, read_only=True, data_only=False)
    row_flags: dict[int, list[tuple[str, str]]] = {}
    for number, (cached, raw) in enumerate(zip(values, formulas[title].iter_rows(values_only=True)), start=1):
        for i, (c, f) in enumerate(zip(cached, raw)):
            if c is None and isinstance(f, str) and f.startswith("="):
                cached[i] = f
                row_flags.setdefault(number, []).append(
                    ("formula_not_calculated", f"cell {f} has no calculated value saved; formula text kept"))
    formulas.close()
    if not values:
        return Table([], [], sheet=title)
    width = max(len(r) for r in values)
    headers = _unique_headers([_cell_text(v) for v in values[0]] + [""] * (width - len(values[0])))
    rows = []
    for offset, raw in enumerate(values[1:], start=2):
        cells = [_cell_text(v) for v in raw] + [""] * len(headers)
        rows.append((offset, dict(zip(headers, cells))))
    while rows and not any(rows[-1][1].values()):
        rows.pop()  # openpyxl can report formatted but empty trailing rows
    return Table(headers, rows, sheet=title, row_flags=row_flags)


def decode(data: bytes) -> tuple[str, str]:
    """UTF-8 (with or without BOM) first, then Windows-1252."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), "cp1252"


def sniff_delimiter(text: str) -> str:
    """Comma, semicolon, tab or pipe: whichever appears most in the header line."""
    header = text.split("\n", 1)[0]
    counts = {d: header.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] else ","


def read_csv(path: Path) -> Table:
    text, encoding = decode(Path(path).read_bytes())
    delimiter = sniff_delimiter(text)
    records = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not records:
        return Table([], [], encoding=encoding, delimiter=delimiter)
    width = len(records[0])
    extra = max(len(r) for r in records) - width
    headers = _unique_headers(records[0] + [f"Extra cell {i + 1}" for i in range(max(extra, 0))])
    rows = []
    row_flags: dict[int, list[tuple[str, str]]] = {}
    for offset, raw in enumerate(records[1:], start=2):
        if len(raw) > width and any(c.strip() for c in raw[width:]):
            row_flags[offset] = [("extra_cells", f"row has {len(raw) - width} more cells than the header; kept in passthrough.csv")]
        cells = raw + [""] * len(headers)
        rows.append((offset, dict(zip(headers, cells))))
    return Table(headers, rows, encoding=encoding, delimiter=delimiter, row_flags=row_flags)


def read_table(path: Path, sheet: str | None = None) -> Table:
    suffix = Path(path).suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        return read_xlsx(Path(path), sheet)
    if suffix == ".csv":
        return read_csv(Path(path))
    raise ValueError(f"Unsupported file type '{suffix}'; use .xlsx or .csv")
