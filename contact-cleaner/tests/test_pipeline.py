import csv
import sys
from pathlib import Path

import pytest

from contact_cleaner.cli import main
from contact_cleaner.config import Settings, guess_mapping, load_settings
from contact_cleaner.pipeline import NoUsableColumns, run

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "demo"))
from make_messy_workbook import write_workbook  # noqa: E402

HEADER = ["Full Name", "E-mail", "Tel", "Organisation", "Post Code", "Date Added", "Favourite Colour"]


def write_csv(path: Path, rows: list[list[str]], encoding: str = "utf-8", header: list[str] = HEADER) -> Path:
    with path.open("w", encoding=encoding, newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_header_guess():
    mapping = guess_mapping(["E-mail", "Email Address ", "Tel", "Mobile", "Full Name", "Organisation", "Misc"], Settings())
    assert mapping["email"] == "E-mail"
    assert mapping["phone"] == "Tel"
    assert mapping["mobile"] == "Mobile"
    assert mapping["full_name"] == "Full Name"
    assert mapping["company"] == "Organisation"
    assert "Misc" not in mapping.values()


def test_mapping_file_overrides(tmp_path):
    mapping_file = tmp_path / "m.yaml"
    mapping_file.write_text("columns:\n  company: Favourite Colour\n  email: null\ntargets:\n  email: E-mail Address\n", encoding="utf-8")
    settings = load_settings(mapping_file)
    mapping = guess_mapping(HEADER, settings)
    assert mapping["company"] == "Favourite Colour"
    assert "email" not in mapping
    assert settings.targets["email"] == "E-mail Address"


def test_mapping_file_rejects_unknown_rule(tmp_path):
    mapping_file = tmp_path / "m.yaml"
    mapping_file.write_text("rules:\n  spellcheck: true\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(mapping_file)


def test_exact_duplicates_merged_keeping_most_complete(tmp_path):
    src = write_csv(tmp_path / "in.csv", [
        ["Jane Smith", "jane@example.com", "", "", "", "", ""],
        ["Jane Smith", " JANE@example.com", "07700 900001", "Acme Example Ltd", "m1 1ae", "", "red"],
        ["Jane Smith", "jane@example.com", "", "Other Example Ltd", "", "01/02/2020", ""],
    ])
    result = run(src, tmp_path / "out", Settings(), echo=False)
    assert len(result.clean) == 1
    kept = result.clean[0]
    assert kept.row == "3"  # the most complete record
    assert kept.values["date_added"] == "2020-02-01"  # filled in from row 4
    assert kept.values["company"] == "Acme Example Ltd"
    assert {m.merged_row for m in result.merges} == {"2", "4"}
    conflict = [m for m in result.merges if m.merged_row == "4"][0]
    assert any("Other Example" in d for d in conflict.discarded)
    assert any(code == "merge_conflict" for code, _ in kept.flags)
    merges = read(tmp_path / "out" / "merges.csv")
    assert len(merges) == 2


def test_likely_duplicates_flagged_not_merged(tmp_path):
    src = write_csv(tmp_path / "in.csv", [
        ["Jane Smith", "jane@example.com", "", "Acme Example Ltd", "", "", ""],
        ["JANE SMITH", "j.smith@example.net", "", "Acme Example Limited", "", "", ""],
        ["Jane Smith", "jane2@example.org", "", "Different Example plc", "", "", ""],
    ])
    result = run(src, tmp_path / "out", Settings(), echo=False)
    assert len(result.clean) == 3
    flagged = {r.row for r in result.clean if any(c == "possible_duplicate" for c, _ in r.flags)}
    assert flagged == {"2", "3"}


def test_rejects_rows_without_contact_route(tmp_path):
    src = write_csv(tmp_path / "in.csv", [
        ["Jane Smith", "not an email", "n/a", "", "", "", ""],
        ["", "", "", "", "", "", ""],
        ["Bob Jones", "", "07700 900002", "", "", "", ""],
    ])
    result = run(src, tmp_path / "out", Settings(), echo=False)
    rejects = read(tmp_path / "out" / "rejects.csv")
    assert [r["Source row"] for r in rejects] == ["2", "3"]
    assert "no valid email" in rejects[0]["Reason"] and "not an email" in rejects[0]["Reason"]
    assert rejects[0]["E-mail"] == "not an email"  # original values kept
    assert rejects[1]["Reason"] == "empty row"
    assert len(result.clean) == 1


def test_switching_rules_off(tmp_path):
    src = write_csv(tmp_path / "in.csv", [["JANE SMITH", "Jane@Example.com", "07700 900003", "", "", "", ""]])
    settings = Settings()
    settings.rules.update(email=False, name_case=False, phone=False)
    result = run(src, tmp_path / "out", settings, echo=False)
    v = result.clean[0].values
    assert (v["first_name"], v["email"], v["phone"]) == ("JANE", "Jane@Example.com", "07700 900003")


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1252"])
def test_encodings(tmp_path, encoding):
    src = write_csv(tmp_path / "in.csv", [["Zoë Brontë", "zoe@example.com", "", "Café Example Ltd", "", "", "£5"]], encoding)
    result = run(src, tmp_path / "out", Settings(), echo=False)
    clean = read(tmp_path / "out" / "clean_contacts.csv")
    assert clean[0]["First name"] == "Zoë" and clean[0]["Last name"] == "Brontë"
    assert clean[0]["Company name"] == "Café Example Ltd"
    assert read(tmp_path / "out" / "passthrough.csv")[0]["Favourite Colour"] == "£5"
    assert result.table.encoding == encoding


def test_passthrough_keeps_every_row_and_unmapped_column(tmp_path):
    src = write_csv(tmp_path / "in.csv", [
        ["Jane Smith", "jane@example.com", "", "", "", "", "blue"],
        ["Jane Smith", "jane@example.com", "", "", "", "", "green"],
        ["Nobody", "", "", "", "", "", "red"],
    ])
    run(src, tmp_path / "out", Settings(), echo=False)
    rows = read(tmp_path / "out" / "passthrough.csv")
    assert [(r["Source row"], r["Favourite Colour"], r["Full Name"]) for r in rows] == [
        ("2", "blue", "Jane Smith"), ("3", "green", "Jane Smith"), ("4", "red", "Nobody")]


def test_sheet_option(tmp_path):
    wb = write_workbook(tmp_path / "w.xlsx", seed=1)
    with pytest.raises(NoUsableColumns):  # the second sheet holds notes, not contacts
        run(wb, tmp_path / "out", Settings(), sheet="Archive notes", echo=False)
    assert run(wb, tmp_path / "out", Settings(), sheet="Contacts", echo=False).input_rows == 600


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    base = tmp_path_factory.mktemp("demo")
    wb = write_workbook(base / "messy.xlsx", seed=7)
    first = run(wb, base / "out1", Settings(), echo=False)
    second = run(base / "out1" / "clean_contacts.csv", base / "out2", Settings(), echo=False)
    return base, first, second


def test_row_counts_reconcile(demo_run):
    _, first, _ = demo_run
    assert first.input_rows == 600
    assert first.input_rows == len(first.clean) + len(first.rejects) + len(first.merges)
    assert len(first.merges) > 0 and len(first.rejects) > 0


def test_every_output_row_traceable(demo_run):
    base, first, _ = demo_run
    numbers = {str(n) for n, _ in first.table.rows}
    for name in ("clean_contacts.csv", "rejects.csv", "review.csv", "passthrough.csv"):
        rows = read(base / "out1" / name)
        assert rows and all(r["Source row"] in numbers for r in rows), name
    clean = {r["Source row"] for r in read(base / "out1" / "clean_contacts.csv")}
    rejected = {r["Source row"] for r in read(base / "out1" / "rejects.csv")}
    merged = {r["Merged row"] for r in read(base / "out1" / "merges.csv")}
    assert clean | rejected | merged == numbers
    assert not (clean & rejected) and not (clean & merged) and not (rejected & merged)


def test_idempotent(demo_run):
    base, first, second = demo_run
    assert second.changes == []
    assert second.merges == [] and second.rejects == []
    assert (base / "out1" / "clean_contacts.csv").read_bytes() == (base / "out2" / "clean_contacts.csv").read_bytes()


def test_report_counts_every_change(demo_run):
    base, first, _ = demo_run
    html = (base / "out1" / "report.html").read_text(encoding="utf-8")
    assert f"<b>{len(first.changes)}</b>" in html
    assert "This adds up" in html
    assert "http" not in html.replace("http-equiv", "")  # self-contained, nothing loaded


def test_cli(tmp_path, capsys):
    src = write_csv(tmp_path / "in.csv", [["Jane Smith", "jane@example.com", "", "", "", "", ""]])
    assert main(["clean", str(src), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "email" in out and "<- E-mail" in out and "Clean: 1" in out
    assert (tmp_path / "out" / "report.html").exists()
