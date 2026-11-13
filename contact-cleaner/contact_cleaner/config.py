"""Settings: default target headers, header variants and rule switches.

Everything here can be overridden by a YAML mapping file (see mapping.example.yaml).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Internal field name -> output header. Labels follow HubSpot's default contact
# property labels, except the two marked custom, which a HubSpot portal would
# need to create before importing.
DEFAULT_TARGETS: dict[str, str] = {
    "salutation": "Salutation",
    "first_name": "First name",
    "last_name": "Last name",
    "name_suffix": "Name suffix",  # custom property
    "email": "Email",
    "phone": "Phone number",
    "mobile": "Mobile phone number",
    "company": "Company name",
    "job_title": "Job title",
    "address": "Street address",
    "city": "City",
    "postcode": "Postal code",
    "country": "Country/Region",
    "date_added": "Date added",  # custom property
}

SOURCE_ROW_HEADER = "Source row"

# Normalised header (lower case, letters and digits only) -> internal field.
HEADER_VARIANTS: dict[str, list[str]] = {
    "salutation": ["salutation", "title", "honorific", "prefix"],
    "full_name": ["fullname", "name", "contactname", "contact", "customername"],
    "first_name": ["firstname", "first", "forename", "givenname", "fname"],
    "last_name": ["lastname", "last", "surname", "familyname", "lname"],
    "name_suffix": ["namesuffix", "suffix"],
    "email": ["email", "emailaddress", "mail", "emailaddr", "workemail", "contactemail"],
    "phone": ["phone", "phonenumber", "tel", "telephone", "telno", "landline", "workphone", "officephone"],
    "mobile": ["mobile", "mobilephone", "mobilephonenumber", "mob", "cell", "cellphone", "mobileno"],
    "company": ["company", "companyname", "organisation", "organization", "org", "business", "employer", "account"],
    "job_title": ["jobtitle", "position", "role", "job"],
    "address": ["address", "streetaddress", "address1", "addressline1", "street"],
    "city": ["city", "town", "towncity"],
    "postcode": ["postcode", "postalcode", "zip", "zipcode", "postcodezip"],
    "country": ["country", "countryregion"],
    "date_added": ["dateadded", "created", "createddate", "datecreated", "added", "since", "customersince"],
    "source_row": ["sourcerow"],
}

DEFAULT_RULES: dict[str, Any] = {
    "whitespace": True,
    "name_case": True,
    "split_name": True,
    "email": True,
    "apply_email_suggestions": False,
    "phone": True,
    "dates": True,
    "day_first": True,
    "postcode": True,
    "dedupe_exact": True,
    "flag_likely_duplicates": True,
    "reject_no_contact": True,
    "formula_guard": True,
    "strict_contact_columns": True,
}


def normalise_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


@dataclass
class Settings:
    targets: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TARGETS))
    columns: dict[str, str] = field(default_factory=dict)  # field -> source header override
    rules: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_RULES))
    default_country: str = "GB"

    def on(self, rule: str) -> bool:
        return bool(self.rules.get(rule, False))


def load_settings(path: Path | None) -> Settings:
    settings = Settings()
    if path is None:
        return settings
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    unknown = set(data) - {"targets", "columns", "rules", "default_country"}
    if unknown:
        raise ValueError(f"Unknown keys in mapping file: {sorted(unknown)}")
    targets = copy.deepcopy(DEFAULT_TARGETS)
    targets.update(data.get("targets") or {})
    settings.targets = targets
    settings.columns = dict(data.get("columns") or {})
    bad_rules = set(data.get("rules") or {}) - set(DEFAULT_RULES)
    if bad_rules:
        raise ValueError(f"Unknown rules in mapping file: {sorted(bad_rules)}")
    settings.rules.update(data.get("rules") or {})
    settings.default_country = str(data.get("default_country") or "GB").upper()
    return settings


def guess_mapping(headers: list[str], settings: Settings) -> dict[str, str]:
    """Return internal field -> source header. Overrides in settings win."""
    lookup = {variant: fieldname for fieldname, variants in HEADER_VARIANTS.items() for variant in variants}
    mapping: dict[str, str] = {}
    for header in headers:
        fieldname = lookup.get(normalise_header(header))
        if fieldname and fieldname not in mapping:
            mapping[fieldname] = header
    # Target headers from a previous run map back to their fields (idempotence).
    for fieldname, target in settings.targets.items():
        for header in headers:
            if normalise_header(header) == normalise_header(target):
                mapping[fieldname] = header
    for fieldname, header in settings.columns.items():
        if header is None:
            mapping.pop(fieldname, None)
        elif header not in headers:
            raise ValueError(f"Mapping file names column '{header}' for '{fieldname}', but the input has no such column")
        else:
            mapping[fieldname] = header
    return mapping


def name_column_note(mapping: dict[str, str]) -> str:
    header = mapping.get("full_name", "")
    if header.strip().lower() == "name":
        return (f"the column '{header}' was read as a person's full name. If it holds company names, "
                "map it with columns: {company: " + header + "} in a mapping file.")
    return ""
