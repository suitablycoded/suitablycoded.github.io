"""Cleaning rules. Each function takes a value and returns (new value, flags).

A flag is a short code plus a plain explanation. Functions never raise on bad data.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta

import phonenumbers

Flag = tuple[str, str]

# ---------------------------------------------------------------- whitespace

_SPACE = re.compile(r"\s+")


def clean_whitespace(value: str) -> str:
    return _SPACE.sub(" ", value.replace(" ", " ")).strip()


# ---------------------------------------------------------------- names

PARTICLES = {"van", "von", "der", "den", "de", "da", "di", "du", "del", "della", "la", "le", "ter", "ten", "bin", "al"}


def _cap_part(part: str) -> str:
    low = part.lower()
    if low.startswith("mc") and len(low) > 2:
        return "Mc" + low[2].upper() + low[3:]
    if len(low) > 2 and low[1] in "'’":  # O'Neill, D'Arcy, N'Diaye
        return low[0].upper() + low[1] + low[2].upper() + low[3:]
    return low[:1].upper() + low[1:]


def _cap_word(word: str) -> str:
    # Capitalise after hyphens and after the dots of initials (J.R.).
    return "-".join(".".join(_cap_part(p) for p in piece.split(".")) for piece in word.split("-"))


def _case_safe(value: str) -> bool:
    """False for letters whose case does not round-trip, such as German sharp s or Turkish dotted I."""
    return value.lower().upper() == value.upper() and len(value.lower()) == len(value) and len(value.upper()) == len(value)


def fix_name_case(value: str) -> tuple[str, list[Flag]]:
    """Fix names typed all in capitals or all in lower case.

    Mixed case is taken as deliberate and left alone. "Mac" names, and names with
    letters whose case cannot be changed safely, are left alone and flagged.
    """
    letters = [c for c in value if c.isalpha()]
    if not letters or not (value.isupper() or value.islower()):
        return value, []
    if re.search(r"\bmac[a-z]{2,}", value.lower()):
        return value, [("name_case_uncertain", f"'{value}' looks like a Mac name; casing left for a person to check")]
    if not _case_safe(value):
        return value, [("name_case_uncertain", f"'{value}' has letters whose case cannot be changed safely; left for a person to check")]
    words = value.split(" ")
    out: list[str] = []
    for i, word in enumerate(words):
        if i > 0 and word.lower() in PARTICLES:
            out.append(word.lower())
        else:
            out.append(_cap_word(word))
    if len(words) == 1 and words[0].lower() in PARTICLES:
        out = [words[0].capitalize()]
    return " ".join(out), []


TITLES = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "professor", "sir", "dame", "rev", "revd", "lady", "lord"}
SUFFIXES = {"jr", "jnr", "sr", "snr", "ii", "iii", "iv", "phd", "md", "mbe", "obe", "cbe", "qc", "kc", "esq"}


def _bare(token: str) -> str:
    return token.lower().strip(".,")


def split_full_name(value: str) -> tuple[dict[str, str], list[Flag]]:
    """Split a full name into salutation, first, last and suffix.

    Handles "Surname, Forename", leading titles, trailing suffixes and surname
    particles (van der Berg). A single word is kept as the first name and flagged.
    """
    parts: dict[str, str] = {"salutation": "", "first_name": "", "last_name": "", "name_suffix": ""}
    flags: list[Flag] = []
    text = value.strip()
    if not text:
        return parts, flags
    if text.count(",") == 1:
        left, right = (s.strip() for s in text.split(","))
        if right and _bare(right) not in SUFFIXES and right.split(" ")[0] and len(left.split(" ")) <= 3:
            text = f"{right} {left}"
    tokens = text.replace(",", " ").split()
    titles: list[str] = []
    while tokens and _bare(tokens[0]) in TITLES and len(tokens) > 1:
        titles.append(tokens.pop(0))
    suffixes: list[str] = []
    while len(tokens) > 1 and _bare(tokens[-1]) in SUFFIXES:
        suffixes.insert(0, tokens.pop())
    parts["salutation"] = " ".join(titles)
    parts["name_suffix"] = " ".join(suffixes)
    if len(tokens) == 1:
        parts["first_name"] = tokens[0]
        flags.append(("single_name", f"'{value}' has one name only; put in first name"))
        return parts, flags
    last_start = len(tokens) - 1
    for i in range(1, len(tokens) - 1):
        if tokens[i].lower() in PARTICLES:
            last_start = i
            break
    parts["first_name"] = " ".join(tokens[:last_start])
    parts["last_name"] = " ".join(tokens[last_start:])
    if last_start > 1:
        flags.append(("name_split_check", f"'{value}' has several given names; first name is '{parts['first_name']}'"))
    return parts, flags


# ---------------------------------------------------------------- email

# Unicode-aware: \w matches letters in any script, so müller@bücher.de is accepted.
LOCAL_RE = re.compile(r"^([\w!#$%&'*+/=?^`{|}~-]+(\.[\w!#$%&'*+/=?^`{|}~-]+)*|\"[^\"\\]+\")$")
LABEL_RE = re.compile(r"^[^\W_]([\w-]*[^\W_])?$")
TLD_RE = re.compile(r"^([^\W\d_]{2,}|xn--[a-z0-9-]+)$")
# One address-shaped run of characters, used to pull an address out of junk around it.
_ADDRESS_TOKEN = re.compile(r"[^\s<>()\[\],;:\"?]+@[^\s<>()\[\],;:\"?@]+\.[^\s<>()\[\],;:\"?@]*[^\s<>()\[\],;:\"?@.]")


def _lower_safe(text: str) -> str:
    """Lower case, unless that would change the length (Turkish dotted I and the like)."""
    low = text.lower()
    return low if len(low) == len(text) else text


def lower_email(text: str) -> str:
    """Lower-case the domain, and the local part where it is safe to do so."""
    if "@" not in text:
        return _lower_safe(text)
    local, _, domain = text.rpartition("@")
    return (local if local.startswith('"') else _lower_safe(local)) + "@" + _lower_safe(domain)


def email_key(email: str) -> str:
    """Comparison key for duplicate matching: Unicode-normalised and case-folded."""
    return unicodedata.normalize("NFKC", email).casefold()


def _email_broken(text: str) -> str:
    """Reason the address is certainly unusable, or '' if it might be valid."""
    if "@" not in text:
        return "has no @"
    local, _, domain = text.rpartition("@")
    if not local or not domain:
        return "is missing the part before or after the @"
    if "@" in local and not (local.startswith('"') and local.endswith('"')):
        return "has more than one @"
    if "." not in domain or "" in domain.split("."):
        return "has no proper domain"
    if not local.startswith('"') and (".." in local or local.startswith(".") or local.endswith(".")):
        return "has dots in the wrong place"
    return ""


def _email_strict(text: str) -> bool:
    local, _, domain = text.rpartition("@")
    labels = domain.split(".")
    return bool(LOCAL_RE.match(local)) and all(LABEL_RE.match(lb) for lb in labels) and bool(TLD_RE.match(labels[-1]))

DOMAIN_TYPOS: dict[str, str] = {
    "gmial.com": "gmail.com", "gamil.com": "gmail.com", "gmai.com": "gmail.com", "gmail.co": "gmail.com",
    "gmail.con": "gmail.com", "googlemail.co": "googlemail.com",
    "hotmial.com": "hotmail.com", "hotmial.co.uk": "hotmail.co.uk", "hotmal.co.uk": "hotmail.co.uk",
    "hotmail.co": "hotmail.co.uk", "hotmail.con": "hotmail.com",
    "yahooo.com": "yahoo.com", "yaho.co.uk": "yahoo.co.uk", "yahoo.co": "yahoo.co.uk",
    "outlok.com": "outlook.com", "outlook.co": "outlook.com", "btinternet.co": "btinternet.com",
    "exmaple.com": "example.com", "examle.com": "example.com", "example.cmo": "example.com",
    "exmaple.co.uk": "example.co.uk", "example.co.k": "example.co.uk", "example.couk": "example.co.uk",
}


def clean_email(value: str, apply_suggestion: bool = False) -> tuple[str, list[Flag]]:
    """Lower-case, strip junk, check.

    Returns '' only when the address is certainly unusable. One address with
    obvious junk around it ("email: x@y.com", "x@y.com (work)") is pulled out.
    Anything unusual but possibly valid is returned as it was with an
    'email_unusual' flag; the pipeline decides whether it stays in the clean file.
    """
    flags: list[Flag] = []
    text = unicodedata.normalize("NFC", value.strip())
    if not text.startswith('"'):
        tokens = _ADDRESS_TOKEN.findall(text)
        if len(tokens) > 1:
            return value, [("email_unusual", f"'{value}' holds more than one address; left for a person to choose")]
        if len(tokens) == 1:
            start = text.index(tokens[0])
            before, after = text[:start].rstrip(), text[start + len(tokens[0]):]
            if (not before or before[-1] in "<(:[\"'") and (not after or after[0] in " \t>)]?,;\"'"):
                text = tokens[0].strip("'")
    text = re.sub(r"^mailto:", "", text.strip(), flags=re.I)
    text = text.strip(" \t<>()[];,").rstrip(".:")
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'" and text.count(text[0]) == 2:
        text = text[1:-1].strip()
    text = lower_email(text)
    if not text:
        return "", flags
    broken = _email_broken(text)
    if broken:
        return "", [("email_invalid", f"'{value}' {broken}, so it is not a usable email address; removed")]
    if not text.startswith('"') and re.search(r"\s", text):
        return value, [("email_unusual", f"'{value}' has a space inside; left as it was for a person to check")]
    if not _email_strict(text):
        return value, [("email_unusual", f"'{value}' has an unusual form; left as it was for a person to check")]
    domain = text.rpartition("@")[2]
    if domain in DOMAIN_TYPOS:
        fixed = text.split("@", 1)[0] + "@" + DOMAIN_TYPOS[domain]
        if apply_suggestion:
            flags.append(("email_typo_fixed", f"domain '{domain}' changed to '{DOMAIN_TYPOS[domain]}'"))
            return fixed, flags
        flags.append(("email_typo_suggestion", f"domain '{domain}' may be a typo for '{DOMAIN_TYPOS[domain]}'; not changed"))
    return text, flags


# ---------------------------------------------------------------- phone

# Ofcom's numbers reserved for drama (07700 900xxx and others). The phone library
# marks them unallocated, but they are well-formed, so test and demo data can use them.
# A plain label next to a number: "Mobile: 07700 900123", "07700 900123 (mobile)".
PHONE_LABEL = re.compile(r"^\s*(tel|phone|mobile|mob|cell|work|home|office|landline)\.?\s*:?\s*|\s*\(\s*(mobile|mob|cell|work|home|office|landline|direct|main)\s*\)\s*$|\s+(mobile|mob|cell|work|home|office|landline)\s*$", re.I)
DRAMA_RANGES = re.compile(r"^\+44(7700900|1134960|1144960|1154960|1164960|1174960|1184960|1214960|1314960|1414960|1514960|1614960|2079460|2890180|2920180|3069990|8081570|9098790)\d{3}$")


def clean_phone(value: str, default_country: str = "GB") -> tuple[str, list[Flag]]:
    """Format as E.164.

    Returns '' when the value cannot be read as a number at all. A number that
    reads but is not valid for its country is left as it was and flagged.
    """
    text = PHONE_LABEL.sub("", value).strip()
    if not text:
        return "", [("phone_unreadable", f"'{value}' could not be read as a phone number; removed")] if value.strip() else []
    digits = re.sub(r"\D", "", text)
    # Spreadsheets often drop the leading zero of a UK number stored as a number.
    if default_country == "GB" and re.fullmatch(r"[1-37]\d{9}", text):
        text = "0" + text
    text = text.replace("(0)", "")
    if text.startswith("00"):
        text = "+" + text[2:]
    try:
        number = phonenumbers.parse(text, default_country)
    except phonenumbers.NumberParseException:
        return "", [("phone_unreadable", f"'{value}' could not be read as a phone number; removed")]
    if not phonenumbers.is_possible_number(number) or len(digits) < 7:
        return "", [("phone_unreadable", f"'{value}' has the wrong number of digits; removed")]
    formatted = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    if not (phonenumbers.is_valid_number(number) or DRAMA_RANGES.match(formatted)):
        return value, [("phone_not_valid", f"'{value}' is not a valid number for {phonenumbers.region_code_for_number(number) or default_country}; left as it was")]
    flags: list[Flag] = []
    if number.extension:
        flags.append(("phone_extension_dropped", f"extension {number.extension} dropped from '{value}'"))
    return formatted, flags


# ---------------------------------------------------------------- dates

_NUMERIC_DATE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})$")
_TEXT_FORMATS = ["%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y", "%d %B, %Y", "%B %d, %Y", "%b %d, %Y"]


def clean_date(value: str, day_first: bool = True) -> tuple[str, list[Flag]]:
    """Return an ISO date (YYYY-MM-DD). Unreadable dates are left as they are and flagged."""
    text = value.strip()
    if not text:
        return "", []
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?", text)
    if m:
        try:
            iso = date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return value, [("date_unreadable", f"'{value}' is not a real date; left as it is")]
        if m.group(4) and any(int(g) for g in m.group(4, 5, 6) if g):
            return iso, [("date_time_dropped", f"time of day dropped from '{value}'")]
        return iso, []
    if re.fullmatch(r"\d{5}", text) and 20000 <= int(text) <= 80000:
        serial = (date(1899, 12, 30) + timedelta(days=int(text))).isoformat()
        return serial, [("date_from_serial", f"'{value}' read as an Excel day number, {serial}; please check")]
    m = _NUMERIC_DATE.match(text)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        day, month = (a, b) if day_first else (b, a)
        flags: list[Flag] = []
        if a <= 12 and b <= 12 and a != b:
            flags.append(("date_ambiguous", f"'{value}' could be day-month or month-day; read as {'day' if day_first else 'month'} first"))
        try:
            return date(year, month, day).isoformat(), flags
        except ValueError:
            try:
                return date(year, day, month).isoformat(), [("date_order_swapped", f"'{value}' only makes sense the other way round")]
            except ValueError:
                return value, [("date_unreadable", f"'{value}' is not a real date; left as it is")]
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)
    cleaned = re.sub(r"\bSept\b", "Sep", cleaned, flags=re.I).replace(",", ", ").replace("  ", " ")
    for fmt in _TEXT_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat(), []
        except ValueError:
            continue
    return value, [("date_unreadable", f"'{value}' could not be read as a date; left as it is")]


# ---------------------------------------------------------------- postcode

POSTCODE_RE = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?) ?([0-9][A-Z]{2})$")
UK_NAMES = {"", "uk", "gb", "united kingdom", "great britain", "england", "scotland", "wales", "northern ireland"}


def clean_postcode(value: str, country: str = "") -> tuple[str, list[Flag]]:
    """Upper-case and space a UK postcode. Non-UK rows are left alone."""
    text = value.strip()
    if not text or country.strip().lower() not in UK_NAMES:
        return value, []
    compact = re.sub(r"\s", "", text.upper())
    m = POSTCODE_RE.match(compact)
    if not m:
        return value, [("postcode_invalid", f"'{value}' is not a valid UK postcode format; left as it is")]
    return f"{m.group(1)} {m.group(2)}", []


# ---------------------------------------------------------------- formula guard

# Only values a spreadsheet would actually treat as a formula are guarded:
# anything starting "=", a function call ("+SUM(", "@SUM(", "-HYPERLINK("), or a
# sum of numbers ("-2+3"). A lone dash, "+1 Main St" or "@home" is left alone.
_FUNCTION_CALL = re.compile(r"^[+\-@]\s*[A-Za-z_][A-Za-z0-9_.]*\s*\(")
_ARITHMETIC = re.compile(r"^[+\-][\d.\s()]*\d[\d.\s()]*[+\-*/^&][\d.\s()+\-*/^&]*$")


def looks_like_formula(value: str) -> bool:
    return value.startswith("=") or bool(_FUNCTION_CALL.match(value) or _ARITHMETIC.match(value))


def guard_formula(value: str) -> str:
    """Put an apostrophe before a value a spreadsheet would run as a formula."""
    return "'" + value if looks_like_formula(value) else value
