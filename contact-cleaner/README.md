# contact-cleaner

A command line tool that turns a messy contact spreadsheet into a file a CRM will accept. It is formatted for a HubSpot contact import by default. Other CRMs can be targeted by changing the output headers in a mapping file.

Typical situation: a business has a contact list built up over years by different people. Names are in capitals, phone numbers are in ten formats, the same person appears three times, and some rows have no way to reach anyone. The CRM import rejects it or fills the CRM with junk.

The tool cleans what it safely can, flags what a person should decide, and counts every change in a report.

## Built with

- Python 3.11
- openpyxl (reads and writes .xlsx)
- phonenumbers (phone number parsing)
- PyYAML (mapping file)
- pytest (tests)
- Playwright was used once to take the screenshots; the tool does not need it.

## Install

```
python -m venv .venv
.venv\Scripts\activate          (Windows)
source .venv/bin/activate       (macOS or Linux)
pip install -r requirements.txt
pip install -e .
```

## Run

```
contact-cleaner clean contacts.xlsx --out cleaned
contact-cleaner clean contacts.csv --out cleaned --mapping mapping.yaml
contact-cleaner clean contacts.xlsx --out cleaned --sheet "Customers"
```

`python -m contact_cleaner clean ...` works the same way.

The input can be `.xlsx` or `.csv`. CSV files are read as UTF-8 (with or without a byte order mark) and fall back to Windows-1252. For a workbook the first sheet is read unless `--sheet` names another.

The separator in a CSV file (comma, semicolon, tab or pipe) is detected from the header line.

The tool prints its guess of which source column holds which field before it starts. If a guess is wrong, fix it in the mapping file.

If no name, email or phone column is recognised, the tool stops with exit code 2 and a message. This usually means the file has no header row, or a mapping file is needed to name the columns.

A CSV row with more cells than the header keeps the extra cells in `passthrough.csv` (as "Extra cell 1" and so on) and is flagged. A workbook formula with no saved result (a file never opened in Excel) keeps the formula text and is flagged.

## Outputs

All in the `--out` folder. Every row in every file carries `Source row`, the row number in the original file (the header is row 1), so anything can be traced back.

| File | What it holds |
| --- | --- |
| `clean_contacts.csv` | The import file. UTF-8, one row per contact, CRM headers. |
| `review.csv` | One line per flag on a kept row: the flag, a plain explanation, and the cleaned values. |
| `rejects.csv` | Rows left out, with the reason and the original values unchanged. |
| `passthrough.csv` | Every input row's unmapped columns (and the original full name), so nothing is lost. |
| `merges.csv` | Each exact duplicate merged: which row was kept, which was merged in, what was filled in, and any differing values not kept. |
| `report.html` | One self-contained page: counts before and after, the column mapping, what each rule changed, flags, rejects, examples of each fix and the merges. |

The counts always reconcile: rows in = clean + rejected + merged away. The report checks this.

## The rules

Each rule can be switched off in the mapping file.

**whitespace.** Removes spaces at either end, collapses runs of spaces, tabs and non-breaking spaces into one space. Applies to every mapped column.

**split_name.** When a row has a full name but no first or last name, splits it. Handles titles at the front (Mr, Mrs, Ms, Miss, Mx, Dr, Prof, Sir, Dame, Rev, Lord, Lady) which go to Salutation, suffixes at the end (Jr, Sr, II, III, PhD, OBE, MBE, CBE, KC and others) which go to Name suffix, the "Surname, Forename" form, and surname particles (van, von, de, der, da, di, le, la and others), so "Pieter van der Berg" gives "Pieter" and "van der Berg". A single word goes to first name and is flagged. Several given names are kept together as the first name and flagged for a check.

**name_case.** Only touches names typed entirely in capitals or entirely in lower case. Mixed case is taken as deliberate and left alone. It produces McDonald, O'Neill, D'Arcy, N'Diaye, Smith-Jones, keeps initials in capitals ("J.R. SMITH" becomes "J.R. Smith"), and keeps particles lower case after the first word ("VAN DER BERG" becomes "Van der Berg"; "van der Berg" is left as it is). Names starting "Mac" are left alone and flagged, because Macdonald and MacDonald are both real. Names with letters whose case cannot be changed safely, such as the German sharp s or the Turkish dotted I, are left alone and flagged.

**email.** Lower-cases the address, including letters from other alphabets (MÜLLER@EXAMPLE.DE becomes müller@example.de). A part where lower-casing would change the number of letters, such as the Turkish dotted I, is written as typed. Duplicates are matched on a Unicode case-folded copy of the address, so such spellings still merge. When there is one address with obvious junk around it, the address is pulled out and the change is counted: "Name <address>", `mailto:`, "email: x@example.com", "x@example.com (work)", "x@example.com?subject=hi", surrounding quotes, brackets and trailing punctuation. Punycode domains and quoted local parts are accepted. An address that certainly cannot work (no @, more than one @, nothing before or after the @, no dot in the domain, dots in the wrong place) is removed and flagged `email_invalid`. An address the tool cannot stand behind (a space inside, two addresses in one cell, a one-letter or numeric ending such as a@b.c or a@1.2.3.4) is flagged `email_unusual`; see `strict_contact_columns` for what happens to it. Common domain typos (gmial.com, hotmial.co.uk, outlok.com and others) are flagged as suggestions and not changed, unless `apply_email_suggestions` is on.

**phone.** Formats numbers to E.164 (+447700900123). Numbers without a country code are read using `default_country` (GB unless set). Numbers that already carry another country code keep it. Handles "(0)", a "00" prefix, brackets, dashes, and UK numbers that lost their leading zero because Excel stored them as numbers. A plain label is removed ("Mobile: 07700 900123", "07700 900123 (mobile)"). An extension is dropped and flagged. A value that cannot be read as a number at all, or is far too short, is removed and flagged `phone_unreadable`. A number that reads but is not valid for its country (for example a US number written without +1 in a UK list, or a UK number with a digit missing) is flagged `phone_not_valid` and is never forced into the default country; see `strict_contact_columns` for what happens to it. Validity uses the number plans in the phonenumbers library. Ofcom's ranges reserved for drama are treated as valid so test data works. None of this proves a number is in service.

**dates.** Converts the Date added column to YYYY-MM-DD. Reads day first by default (`day_first: false` to change). A date like 03/04/2021, which could be read either way, is converted and flagged as ambiguous. A date that only works the other way round (12/25/2020) is converted and flagged. Also read: 2021/03/04, text dates such as "14th December 2015" and "4 Sept 2020", real Excel date and date-time cells (each conversion is counted, and a dropped time of day is flagged), and a five-digit Excel day number such as 44197 (converted and flagged for a check). Anything else is left as it is and flagged.

**postcode.** For rows where the country is blank or a UK name, upper-cases the postcode and puts the single space in the right place (sw1a1aa becomes SW1A 1AA). A value that does not match the UK postcode pattern is left as it is and flagged. This is a format check, not a lookup against the Royal Mail address file.

**dedupe_exact.** Rows with the same cleaned email are merged. The most complete row (most filled fields, then the earliest) is kept. Its blank fields are filled from the others. Values that differ are not kept but are listed in `merges.csv` and flagged on the kept row, so a person can check.

**flag_likely_duplicates.** Rows with the same name and company (ignoring case, punctuation and endings such as Ltd, Limited, plc) but different emails are flagged as possible duplicates. They are not merged.

**strict_contact_columns** (on by default). The clean file goes straight into a CRM, so an email or phone the tool cannot stand behind is not put in it. A value flagged `email_unusual` or `phone_not_valid` is taken out of the clean file, kept in full in the explanation in `review.csv` (or in `rejects.csv` if the row is rejected), and counted in the report. Switched off, such values stay in the clean file with their flag. Dates and postcodes are not affected: an unreadable one stays as it was and is flagged.

**formula_guard.** Puts an apostrophe in front of a value a spreadsheet would run as a formula: anything starting with =, a function call starting with +, - or @ (for example +SUM(1,2) or @SUM(A1:A2)), or a sum of numbers starting with + or - (for example -2+3). Ordinary text that merely starts with a sign is left alone: a lone dash, "+1 Main St", "-5 Degrees Ltd", "@home", a negative number, and phone numbers in +44 form. Each guarded value is counted.

**reject_no_contact.** A row with no usable email and no usable phone or mobile goes to `rejects.csv` with the reason, including the values that were removed. Fully empty rows are rejected as "empty row".

## Mapping file reference

See `mapping.example.yaml`. All keys are optional.

| Key | Meaning |
| --- | --- |
| `default_country` | Two-letter country code for phone numbers with no country code. Default GB. Also used for postcode checks on rows with no country when it is not GB. |
| `columns` | Field name to source column, to override the guess. `null` stops a column being mapped. |
| `targets` | Field name to output header. Change these to target another CRM. |
| `rules` | Switch each rule on or off: `whitespace`, `name_case`, `split_name`, `email`, `apply_email_suggestions`, `phone`, `dates`, `day_first`, `postcode`, `dedupe_exact`, `flag_likely_duplicates`, `reject_no_contact`, `formula_guard`, `strict_contact_columns`. |

Field names: `salutation`, `full_name` (input only), `first_name`, `last_name`, `name_suffix`, `email`, `phone`, `mobile`, `company`, `job_title`, `address`, `city`, `postcode`, `country`, `date_added`.

The header guess recognises common variants, for example "E-mail", "Email Address", "Tel", "Telephone", "Mobile", "Cell", "Full Name", "Forename", "Surname", "Organisation", "Company", "Position", "Town", "Post Code", "Zip". A column headed "Title" is read as the salutation; if your "Title" column holds job titles, map it with `columns: {job_title: Title}`.

## Output headers and HubSpot

The default output headers are the labels of HubSpot's default contact properties: Salutation, First name, Last name, Email, Phone number, Mobile phone number, Company name, Job title, Street address, City, Postal code, Country/Region. These labels were checked against HubSpot's public knowledge base article listing its default contact properties (November 2026). HubSpot can change its labels, so check the import mapping screen when you import.

Two output columns are not HubSpot default properties: **Name suffix** and **Date added**. Create them as custom contact properties before importing, or tell the importer not to import them. **Source row** is for tracing only; skip it at import.

This project is formatted for a HubSpot contact import. It is not made, endorsed or supported by HubSpot.

## Demo

```
python demo/run_demo.py
```

This writes `demo/input/messy_contacts.xlsx`, a seeded 600-row workbook of entirely fictional people and companies, then cleans it into `demo/output/`. Email domains are reserved example domains. Phone numbers come from Ofcom's ranges reserved for drama (07700 900xxx and 020 7946 0xxx) and the fictional US 555-01xx range. The workbook has every kind of fault the rules handle, plus a second sheet that is ignored, two empty rows and two unmapped columns.

Figures from the committed run: 600 rows in, 515 clean contacts, 33 rejected (31 with no valid contact route, 2 empty), 52 merged away as exact duplicates, 235 kept rows flagged for review, 2,932 individual changes.

Running the tool again on its own `clean_contacts.csv` makes no changes and writes an identical file.

## Tests

```
pytest
```

The tests cover each rule with awkward cases, exact and likely duplicates, the three encodings, semicolon files, files with no header row, ragged rows, the sheet option, rules switched off, mapping overrides, that every row is traceable, that counts reconcile, that a second run changes nothing, and that 20,000 rows run in under 30 seconds.

## Speed

Measured on one ordinary Windows desktop with generated CSV files of six columns, about one row in ten an exact duplicate: 10,000 rows in 0.9 seconds, 20,000 in 2.3 seconds, 50,000 in 6.9 seconds, 100,000 in 16.8 seconds. Time grows roughly in line with the number of rows.

## Limits

- UK-first. Name rules suit British and Irish names; other naming customs (family name first, single names, patronymics) are not split well and should be checked.
- Postcodes are checked for format only, and only for UK rows.
- Phone numbers are checked against number plans, not that they are in service. An extension is dropped, not moved to another field.
- Unreadable dates and invalid postcodes stay in the clean file as they were (and are flagged), so read review.csv before importing.
- A column headed just "Name" is read as a person's full name; the tool prints a note and the report repeats it. If it holds company names, map it with `columns: {company: Name}`. If two columns look like email, the first is used and the other goes to passthrough.csv.
- Likely duplicates need the same name and company. Nicknames (Bob and Robert) and typos in names are not matched.
- Exact duplicates are matched on email only. Two rows with the same phone number and different emails are not merged.
- Only one date column (Date added) is cleaned. Other date columns go to passthrough unchanged.
- It does not upload anything to a CRM, check emails can receive mail, or look up missing data.
- Files are read into memory. A hundred thousand rows is fine; millions are not what it is for.
