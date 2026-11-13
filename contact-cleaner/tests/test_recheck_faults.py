"""Cases from the re-check (N-C1 to N-C4, C5, C10, C11)."""

import csv
from pathlib import Path

import pytest

from contact_cleaner import rules
from contact_cleaner.config import Settings
from contact_cleaner.pipeline import run


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# N-C1 / C10 / C5: uncertain emails and phones leave the clean file
def test_nc1_uncertain_values_removed_and_rows_rejected(tmp_path):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email", "Phone"], [
        ["Only Badphone", "", "0123456789"],
        ["Only Dotcom", "a@b.c", ""],
        ["Spacey Kept", "john smith@example.com", "07700 900123"],
    ])
    result = run(src, tmp_path / "out", Settings(), echo=False)
    rejects = read(tmp_path / "out" / "rejects.csv")
    assert [r["Source row"] for r in rejects] == ["2", "3"]
    assert "0123456789" in rejects[0]["Reason"] and "a@b.c" in rejects[1]["Reason"]
    clean = read(tmp_path / "out" / "clean_contacts.csv")
    assert len(clean) == 1 and clean[0]["Email"] == "" and clean[0]["Phone number"] == "+447700900123"
    review = read(tmp_path / "out" / "review.csv")
    assert any(r["Flag"] == "email_unusual" and "john smith@example.com" in r["Explanation"]
               and "removed from the clean file" in r["Explanation"] for r in review)
    assert any(c.rule == "email" and c.before == "john smith@example.com" and c.after == "" for c in result.changes)
    assert result.input_rows == len(result.clean) + len(result.rejects) + len(result.merges)


def test_nc1_switch_off_keeps_flagged_values(tmp_path):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email", "Phone"], [["Only Badphone", "", "0123456789"]])
    settings = Settings()
    settings.rules["strict_contact_columns"] = False
    result = run(src, tmp_path / "out", settings, echo=False)
    assert result.clean[0].values["phone"] == "0123456789"


@pytest.mark.parametrize("raw, expected", [
    ("john@example.com (work)", "john@example.com"),
    ("email: x@example.com", "x@example.com"),
    ("x@example.com ext", "x@example.com"),
    ("x@example.com?subject=hi", "x@example.com"),
    ("Jane Smith <jane@example.com>", "jane@example.com"),
    ("  'jane@example.com';", "jane@example.com"),
])
def test_nc1_address_pulled_out_of_junk(raw, expected):
    value, flags = rules.clean_email(raw)
    assert value == expected and not flags


@pytest.mark.parametrize("raw", ["john smith@example.com", "a@1.2.3.4", "a@b.c", "<a@example.com><c@example.org>"])
def test_nc1_uncertain_emails_flagged(raw):
    assert rules.clean_email(raw)[1][0][0] == "email_unusual"


# N-C2: formula guard only on real formulas
@pytest.mark.parametrize("raw, guarded", [
    ("=cmd|' /C calc'!A0", True),
    ("+SUM(1,2)", True),
    ("-2+3", True),
    ("@SUM(A1:A2)", True),
    ("=1", True),
    ("-", False),
    ("--", False),
    ("+1 Main St", False),
    ("-5 Degrees Ltd", False),
    ("+ve Thinking", False),
    ("@home", False),
    ("+447700900123", False),
    ("-1", False),
])
def test_nc2_formula_guard(raw, guarded):
    assert rules.guard_formula(raw) == ("'" + raw if guarded else raw)


# N-C3: Unicode case
def test_nc3_unicode_email_lowercased_and_merged(tmp_path):
    assert rules.clean_email("MÜLLER@EXAMPLE.DE")[0] == "müller@example.de"
    assert rules.clean_email("İSTANBUL@EXAMPLE.COM")[0] == "İSTANBUL@example.com"
    src = write_csv(tmp_path / "in.csv", ["Name", "Email"], [
        ["Hans Müller", "müller@example.de"], ["Hans Müller", "MÜLLER@EXAMPLE.DE"],
        ["Ayşe Kaya", "İSTANBUL@example.com"], ["Ayşe Kaya", "İstanbul@EXAMPLE.com"],
    ])
    result = run(src, tmp_path / "out", Settings(), echo=False)
    assert len(result.merges) == 2 and len(result.clean) == 2


# N-C4: labels on phones
@pytest.mark.parametrize("raw", ["07700 900 123 (mobile)", "Mobile: 07700 900123", "07700 900123 work"])
def test_nc4_phone_labels(raw):
    assert rules.clean_phone(raw) == ("+447700900123", [])


# C11: a column called just "Name"
def test_c11_name_column_note(tmp_path, capsys):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email"], [["Acme Example Ltd", "info@example.com"]])
    run(src, tmp_path / "out", Settings(), echo=True)
    assert "read as a person's full name" in capsys.readouterr().out
    assert "read as a person&#x27;s full name" in (tmp_path / "out" / "report.html").read_text(encoding="utf-8")


# Reconcile and idempotence on all the new cases
def test_recheck_cases_reconcile_and_idempotent(tmp_path):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email", "Phone", "Company", "Address"], [
        ["Only Badphone", "", "0123456789", "-", "+1 Main St"],
        ["Only Dotcom", "a@b.c", "", "", ""],
        ["Ann Lee", "ann@example.com (work)", "07700 900123 (mobile)", "-2+3", "@home"],
        ["Hans Müller", "MÜLLER@EXAMPLE.DE", "", "+SUM(1)", ""],
        ["Hans Müller", "müller@example.de", "", "", ""],
        ["Two Addresses", "<a@example.com><c@example.org>", "020 7946 0123", "", ""],
    ])
    first = run(src, tmp_path / "o1", Settings(), echo=False)
    assert first.input_rows == len(first.clean) + len(first.rejects) + len(first.merges)
    second = run(tmp_path / "o1" / "clean_contacts.csv", tmp_path / "o2", Settings(), echo=False)
    assert second.changes == [] and not second.rejects and not second.merges
    assert (tmp_path / "o1" / "clean_contacts.csv").read_bytes() == (tmp_path / "o2" / "clean_contacts.csv").read_bytes()
