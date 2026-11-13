"""Cases from the independent check (faults C1 to C12). Each one damaged or lost data before."""

import csv
import time
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from contact_cleaner import rules
from contact_cleaner.cli import main
from contact_cleaner.config import Settings
from contact_cleaner.pipeline import NoUsableColumns, run


def write_csv(path: Path, header: list[str], rows: list[list[str]], delimiter: str = ",") -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# C1: internationalised addresses are valid
@pytest.mark.parametrize("raw, expected", [
    ("müller@example.de", "müller@example.de"),
    ("info@bücher.de", "info@bücher.de"),
    ("Info@Bücher.DE", "info@bücher.de"),
    ("ivan@example.xn--p1ai", "ivan@example.xn--p1ai"),
    ("\"john smith\"@example.com", "\"john smith\"@example.com"),
    ("o'neill@example.com", "o'neill@example.com"),
])
def test_c1_international_emails_kept(raw, expected):
    value, flags = rules.clean_email(raw)
    assert value == expected
    assert not any(code == "email_invalid" for code, _ in flags)


def test_c1_row_with_international_email_not_rejected(tmp_path):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email"], [["Hans Müller", "info@bücher.de"]])
    result = run(src, tmp_path / "out", Settings(), echo=False)
    assert len(result.clean) == 1 and not result.rejects
    assert result.clean[0].values["email"] == "info@bücher.de"


# C2: near-linear time
def test_c2_large_file_is_fast(tmp_path):
    rows = [[f"Person {i}", f"p{i % 15000}@example.com", f"07700 900{i % 1000:03d}", f"Company {i % 50}"]
            for i in range(20000)]
    src = write_csv(tmp_path / "big.csv", ["Name", "Email", "Phone", "Company"], rows)
    start = time.perf_counter()
    result = run(src, tmp_path / "out", Settings(), echo=False)
    elapsed = time.perf_counter() - start
    assert result.input_rows == len(result.clean) + len(result.rejects) + len(result.merges)
    assert len(result.merges) == 5000
    assert elapsed < 30, f"20,000 rows took {elapsed:.1f} s"


# C3: names
@pytest.mark.parametrize("raw, expected, flagged", [
    ("J.R. SMITH", "J.R. Smith", False),
    ("A.B. CHEN", "A.B. Chen", False),
    ("N'DIAYE", "N'Diaye", False),
    ("STRAUß", "STRAUß", False),  # mixed case already: left alone
    ("straße", "straße", True),
    ("ÖZDEMİR", "ÖZDEMİR", True),
])
def test_c3_names_not_damaged(raw, expected, flagged):
    value, flags = rules.fix_name_case(raw)
    assert value == expected
    assert bool(flags) == flagged


# C4: phone numbers not valid for the country are left as they were and flagged
@pytest.mark.parametrize("raw", ["(212) 555-0131", "0770090012", "1234567", "0123456789"])
def test_c4_invalid_phones_left_and_flagged(raw):
    value, flags = rules.clean_phone(raw, "GB")
    assert value == raw
    assert flags[0][0] == "phone_not_valid"


def test_c4_us_number_with_us_default():
    assert rules.clean_phone("(212) 555-0131", "US")[0] == "+12125550131"


# C5: no invented addresses
def test_c5_space_inside_email_flagged_not_joined():
    value, flags = rules.clean_email("john smith@example.com")
    assert value == "john smith@example.com"
    assert flags[0][0] == "email_unusual"


# C6: dates with a time, slashes, Sept, Excel day numbers
@pytest.mark.parametrize("raw, expected, flag", [
    ("2021-03-04 13:45:00", "2021-03-04", "date_time_dropped"),
    ("2021-03-04 00:00:00", "2021-03-04", None),
    ("2021/03/04", "2021-03-04", None),
    ("4 Sept 2020", "2020-09-04", None),
    ("44197", "2021-01-01", "date_from_serial"),
])
def test_c6_dates(raw, expected, flag):
    value, flags = rules.clean_date(raw)
    assert value == expected
    assert [f[0] for f in flags] == ([flag] if flag else [])


def test_c6_excel_datetime_cell_converted_and_counted(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Email", "Date Added"])
    ws.append(["Ann Lee", "ann@example.com", datetime(2021, 3, 4, 13, 45)])
    ws.append(["Bob Ray", "bob@example.com", datetime(2021, 3, 5)])
    wb.save(tmp_path / "d.xlsx")
    result = run(tmp_path / "d.xlsx", tmp_path / "out", Settings(), echo=False)
    assert [r.values["date_added"] for r in result.clean] == ["2021-03-04", "2021-03-05"]
    assert len([c for c in result.changes if c.rule == "dates"]) == 2


# C7: semicolons, and no header row
def test_c7_semicolon_csv(tmp_path):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email", "Tel"], [["Ann Lee", "ann@example.com", "07700 900123"]], ";")
    result = run(src, tmp_path / "out", Settings(), echo=False)
    assert result.clean[0].values["email"] == "ann@example.com"
    assert result.table.delimiter == ";"


def test_c7_no_header_stops_with_message(tmp_path, capsys):
    src = tmp_path / "in.csv"
    src.write_text("Ann Lee,ann@example.com,07700 900123\nBob Ray,bob@example.com,07700 900124\n", encoding="utf-8")
    with pytest.raises(NoUsableColumns):
        run(src, tmp_path / "out", Settings(), echo=False)
    assert main(["clean", str(src), "--out", str(tmp_path / "out")]) == 2
    err = capsys.readouterr().err
    assert "No name, email or phone column was recognised" in err and "--mapping" in err


# C8: ragged rows
def test_c8_extra_cells_kept_and_flagged(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("Name,Email,Tel\nAnn Lee,ann@example.com,07700 900123,EXTRA,MORE\nBob Ray,bob@example.com,\n",
                   encoding="utf-8")
    result = run(src, tmp_path / "out", Settings(), echo=False)
    passthrough = read(tmp_path / "out" / "passthrough.csv")
    assert passthrough[0]["Extra cell 1"] == "EXTRA" and passthrough[0]["Extra cell 2"] == "MORE"
    assert any(code == "extra_cells" for code, _ in result.clean[0].flags)
    assert not result.clean[1].flags


def test_c8_uncalculated_formula_kept(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "Email", "Notes"])
    ws.append(["Ann Lee", "ann@example.com", "=1+1"])
    wb.save(tmp_path / "f.xlsx")  # openpyxl saves no calculated value
    result = run(tmp_path / "f.xlsx", tmp_path / "out", Settings(), echo=False)
    assert read(tmp_path / "out" / "passthrough.csv")[0]["Notes"] == "=1+1"
    assert any(code == "formula_not_calculated" for code, _ in result.clean[0].flags)


# C9: formula injection
def test_c9_formula_guard(tmp_path):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email", "Company", "Phone"],
                    [["Ann Lee", "ann@example.com", "=HYPERLINK(1)", "07700 900123"],
                     ["Bob Ray", "bob@example.com", "@SUM(1)", ""]])
    run(src, tmp_path / "out", Settings(), echo=False)
    clean = read(tmp_path / "out" / "clean_contacts.csv")
    assert [r["Company name"] for r in clean] == ["'=HYPERLINK(1)", "'@SUM(1)"]
    assert clean[0]["Phone number"] == "+447700900123"


# Low: a merged duplicate's flags are not repeated on the kept row
def test_merged_flags_not_repeated(tmp_path):
    src = write_csv(tmp_path / "in.csv", ["Name", "Email", "Tel"], [
        ["Ann Lee", "ann@example.com", "020 7946 0123 ext 1"],
        ["Ann Lee", "ann@example.com", "020 7946 0123 ext 1"],
        ["Ann Lee", "ann@example.com", "020 7946 0123 ext 1"],
    ])
    result = run(src, tmp_path / "out", Settings(), echo=False)
    codes = [code for code, _ in result.clean[0].flags]
    assert codes.count("phone_extension_dropped") == 1


# Reconcile and idempotence on a file full of the awkward cases above
def test_nasty_file_reconciles_and_is_idempotent(tmp_path):
    src = tmp_path / "nasty.csv"
    src.write_text(
        "Full Name;Email;Tel;Company;Date Added\n"
        "J.R. SMITH;JR@Example.com;(212) 555-0131;=SUM(1);2021-03-04 13:45\n"
        "Hans Müller;info@bücher.de;;Bücher Example GmbH;4 Sept 2020\n"
        "john smith;john smith@example.com;0770090012;;44197\n"
        "STRAUß;;1234567;;last spring\n"
        "Ann Lee;ann@example.com;07700 900123;Acme Example Ltd;03/04/2021;EXTRA\n"
        "ANN LEE;ANN@example.com;;Acme Example Ltd;\n"
        "Nobody;not an email;n/a;;\n"
        ";;;;\n", encoding="utf-8")
    first = run(src, tmp_path / "out1", Settings(), echo=False)
    assert first.input_rows == 8
    assert first.input_rows == len(first.clean) + len(first.rejects) + len(first.merges)
    second = run(tmp_path / "out1" / "clean_contacts.csv", tmp_path / "out2", Settings(), echo=False)
    assert second.changes == [] and second.merges == [] and second.rejects == []
    assert (tmp_path / "out1" / "clean_contacts.csv").read_bytes() == (tmp_path / "out2" / "clean_contacts.csv").read_bytes()
