"""The cleaning run: map columns, apply rules, reject, de-duplicate, write outputs."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import rules
from .config import SOURCE_ROW_HEADER, Settings, guess_mapping, name_column_note
from .reader import Table, read_table
from .report import write_report

NAME_FIELDS = ("first_name", "last_name")
UNCERTAIN = {"email_unusual", "phone_not_valid"}
REMOVAL_CODES = {"email_invalid", "phone_unreadable"} | UNCERTAIN
CONTACT_FIELDS = {"full_name", "first_name", "last_name", "email", "phone", "mobile"}


class NoUsableColumns(ValueError):
    """The input has no column the tool can recognise as a name, email or phone."""


def _no_columns_message(table: Table) -> str:
    seen = ", ".join(repr(h) for h in table.headers[:8])
    sep = f" The file was read with separator {table.delimiter!r}." if table.delimiter else ""
    return (f"No name, email or phone column was recognised. The first row was read as headings: {seen}.{sep} "
            "Check that the first row holds column headings, or name the columns in a mapping file, for example:\n"
            "  columns:\n    email: Your email column\n    phone: Your phone column\n"
            "and run again with --mapping mapping.yaml.")
COMPANY_ENDINGS = re.compile(r"\b(ltd|limited|plc|llp|inc|co|company|group|uk)\b\.?", re.I)


@dataclass
class Change:
    rule: str
    row: str
    field: str
    before: str
    after: str


@dataclass
class Record:
    row: str  # traceable source row number
    original: dict[str, str]
    values: dict[str, str]
    flags: list[rules.Flag] = field(default_factory=list)

    def completeness(self) -> int:
        return sum(1 for v in self.values.values() if v)


@dataclass
class Merge:
    kept_row: str
    merged_row: str
    email: str
    filled: list[str]
    discarded: list[str]


@dataclass
class Result:
    input_rows: int
    clean: list[Record]
    rejects: list[tuple[Record, str]]
    merges: list[Merge]
    changes: list[Change]
    mapping: dict[str, str]
    unmapped: list[str]
    table: Table
    input_name: str
    flag_counts: dict[str, int]


class Cleaner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.changes: list[Change] = []

    def _set(self, rec: Record, rule: str, fieldname: str, new: str) -> None:
        old = rec.values.get(fieldname, "")
        if new != old:
            self.changes.append(Change(rule, rec.row, fieldname, old, new))
            rec.values[fieldname] = new

    def _removes(self, flags: list[rules.Flag]) -> bool:
        return self.settings.on("strict_contact_columns") and any(code in UNCERTAIN for code, _ in flags)

    def _strict(self, flags: list[rules.Flag]) -> list[rules.Flag]:
        """With strict_contact_columns on, uncertain emails and phones are taken out of the clean file."""
        if not self._removes(flags):
            return flags
        return [(code, text.replace("; left as it was", "") + "; removed from the clean file")
                if code in UNCERTAIN else (code, text) for code, text in flags]

    def clean_record(self, rec: Record) -> None:
        s = self.settings
        v = rec.values
        if s.on("whitespace"):
            for name in list(v):
                self._set(rec, "whitespace", name, rules.clean_whitespace(v[name]))
        full = v.pop("full_name", "")
        if s.on("split_name") and full and not v.get("first_name") and not v.get("last_name"):
            parts, flags = rules.split_full_name(full)
            rec.flags += flags
            self.changes.append(Change("split_name", rec.row, "full_name", full,
                                       " | ".join(p for p in parts.values() if p)))
            for name, part in parts.items():
                if part and not v.get(name):
                    v[name] = part
        if s.on("name_case"):
            for name in NAME_FIELDS:
                if v.get(name):
                    new, flags = rules.fix_name_case(v[name])
                    rec.flags += flags
                    self._set(rec, "name_case", name, new)
        if s.on("email") and v.get("email"):
            new, flags = rules.clean_email(v["email"], s.on("apply_email_suggestions"))
            rec.flags += self._strict(flags)
            self._set(rec, "email", "email", "" if self._removes(flags) else new)
        if s.on("phone"):
            for name in ("phone", "mobile"):
                if v.get(name):
                    new, flags = rules.clean_phone(v[name], s.default_country)
                    rec.flags += self._strict(flags)
                    self._set(rec, "phone", name, "" if self._removes(flags) else new)
        if s.on("dates") and v.get("date_added"):
            new, flags = rules.clean_date(v["date_added"], s.on("day_first"))
            rec.flags += flags
            self._set(rec, "dates", "date_added", new)
        if s.on("postcode") and v.get("postcode"):
            country = v.get("country", "") if "country" in v else ""
            if s.default_country != "GB" and not country:
                country = s.default_country
            new, flags = rules.clean_postcode(v["postcode"], country)
            rec.flags += flags
            self._set(rec, "postcode", "postcode", new)
        if s.on("formula_guard"):
            for name in list(v):
                self._set(rec, "formula_guard", name, rules.guard_formula(v[name]))

    def dedupe(self, records: list[Record]) -> tuple[list[Record], list[Merge]]:
        if not self.settings.on("dedupe_exact"):
            return records, []
        groups: dict[str, list[Record]] = defaultdict(list)
        for rec in records:
            if rec.values.get("email"):
                groups[rules.email_key(rec.values["email"])].append(rec)
        position = {id(rec): i for i, rec in enumerate(records)}
        merged_away: set[int] = set()
        merges: list[Merge] = []
        for email, group in groups.items():
            if len(group) < 2:
                continue
            keeper = max(group, key=lambda r: (r.completeness(), -position[id(r)]))
            for other in group:
                if other is keeper:
                    continue
                filled, discarded = [], []
                for name, value in other.values.items():
                    if not value:
                        continue
                    if not keeper.values.get(name):
                        self._set(keeper, "merge_fill", name, value)
                        filled.append(name)
                    elif keeper.values[name].casefold() != value.casefold():
                        discarded.append(f"{name}='{value}'")
                        self.changes.append(Change("merge_discard", other.row, name, value, ""))
                if discarded:
                    keeper.flags.append(("merge_conflict", f"merged with row {other.row}; its differing values were not kept: {', '.join(discarded)}"))
                have = {code for code, _ in keeper.flags}
                keeper.flags += [(code, f"(from merged row {other.row}) {text}") for code, text in other.flags if code not in have]
                merges.append(Merge(keeper.row, other.row, keeper.values["email"], filled, discarded))
                merged_away.add(id(other))
        return [r for r in records if id(r) not in merged_away], merges

    def flag_likely_duplicates(self, records: list[Record]) -> None:
        if not self.settings.on("flag_likely_duplicates"):
            return
        groups: dict[tuple[str, str], list[Record]] = defaultdict(list)
        for rec in records:
            name = re.sub(r"[\W\d_]", "", (rec.values.get("first_name", "") + rec.values.get("last_name", "")).casefold())
            company = re.sub(r"[\W_]", "", COMPANY_ENDINGS.sub("", rec.values.get("company", "").casefold()))
            if name and company:
                groups[(name, company)].append(rec)
        for group in groups.values():
            if len(group) > 1:
                for rec in group:
                    others = ", ".join(r.row for r in group if r is not rec)
                    rec.flags.append(("possible_duplicate", f"same name and company as row(s) {others}; not merged, please decide"))


def run(input_path: Path, out_dir: Path, settings: Settings, sheet: str | None = None,
        echo: bool = True) -> Result:
    table = read_table(Path(input_path), sheet)
    mapping = guess_mapping(table.headers, settings)
    if table.rows and not CONTACT_FIELDS & set(mapping):
        raise NoUsableColumns(_no_columns_message(table))
    if echo:
        print("Column mapping (field <- source column):")
        for name, header in mapping.items():
            print(f"  {name:12} <- {header}")
        if name_column_note(mapping):
            print("Note: " + name_column_note(mapping))
    mapped_headers = set(mapping.values())
    unmapped = [h for h in table.headers if h not in mapped_headers]
    passthrough_headers = unmapped + ([mapping["full_name"]] if "full_name" in mapping else [])

    cleaner = Cleaner(settings)
    kept: list[Record] = []
    rejects: list[tuple[Record, str]] = []
    for number, original in table.rows:
        values = {name: original.get(header, "") for name, header in mapping.items() if name != "source_row"}
        row = original.get(mapping["source_row"], "") if "source_row" in mapping else ""
        rec = Record(row or str(number), original, values, list(table.row_flags.get(number, [])))
        if not any(v.strip() for v in original.values()):
            rejects.append((rec, "empty row"))
            continue
        cleaner.clean_record(rec)
        if settings.on("reject_no_contact") and not rec.values.get("email") and not rec.values.get("phone") and not rec.values.get("mobile"):
            reason = "no valid email and no valid phone number"
            why = [text for code, text in rec.flags if code in REMOVAL_CODES]
            if why:
                reason += " (" + "; ".join(why) + ")"
            rejects.append((rec, reason))
            continue
        kept.append(rec)

    clean, merges = cleaner.dedupe(kept)
    cleaner.flag_likely_duplicates(clean)

    flag_counts: dict[str, int] = defaultdict(int)
    for rec in clean:
        for code, _ in rec.flags:
            flag_counts[code] += 1

    result = Result(len(table.rows), clean, rejects, merges, cleaner.changes, mapping, unmapped, table,
                    Path(input_path).name, dict(flag_counts))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_outputs(result, out_dir, settings, passthrough_headers)
    write_report(result, out_dir / "report.html", settings)
    return result


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def write_outputs(result: Result, out: Path, settings: Settings, passthrough_headers: list[str]) -> None:
    fields = list(settings.targets)
    headers = [settings.targets[f] for f in fields] + [SOURCE_ROW_HEADER]

    def clean_cells(rec: Record) -> list[str]:
        return [rec.values.get(f, "") for f in fields] + [rec.row]

    _write_csv(out / "clean_contacts.csv", headers, [clean_cells(r) for r in result.clean])
    _write_csv(out / "review.csv", [SOURCE_ROW_HEADER, "Flag", "Explanation"] + headers[:-1],
               [[r.row, code, text] + clean_cells(r)[:-1] for r in result.clean for code, text in r.flags])
    src = result.table.headers
    _write_csv(out / "rejects.csv", [SOURCE_ROW_HEADER, "Reason"] + src,
               [[r.row, reason] + [r.original.get(h, "") for h in src] for r, reason in result.rejects])
    rows = [rec for _, rec in result.table.rows]
    numbers = [str(n) for n, _ in result.table.rows]
    if "source_row" in result.mapping:
        numbers = [rec.get(result.mapping["source_row"], "") or n for n, rec in zip(numbers, rows)]
    _write_csv(out / "passthrough.csv", [SOURCE_ROW_HEADER] + passthrough_headers,
               [[n] + [rec.get(h, "") for h in passthrough_headers] for n, rec in zip(numbers, rows)])
    _write_csv(out / "merges.csv", ["Kept row", "Merged row", "Email", "Fields filled in", "Values not kept"],
               [[m.kept_row, m.merged_row, m.email, "; ".join(m.filled), "; ".join(m.discarded)] for m in result.merges])
