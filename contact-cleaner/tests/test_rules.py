import pytest

from contact_cleaner import rules


@pytest.mark.parametrize("raw, expected", [
    ("  Jane   Smith ", "Jane Smith"),
    ("\tJane Smith", "Jane Smith"),
    ("line\nbreak", "line break"),
    ("", ""),
])
def test_whitespace(raw, expected):
    assert rules.clean_whitespace(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("JOHN", "John"),
    ("mcdonald", "McDonald"),
    ("O'NEILL", "O'Neill"),
    ("d'arcy", "D'Arcy"),
    ("smith-jones", "Smith-Jones"),
    ("VAN DER BERG", "Van der Berg"),
    ("mary jane", "Mary Jane"),
    ("McDonald", "McDonald"),       # mixed case is left alone
    ("van der Berg", "van der Berg"),
    ("DeVito", "DeVito"),
])
def test_name_case(raw, expected):
    assert rules.fix_name_case(raw)[0] == expected


def test_name_case_mac_is_left_and_flagged():
    value, flags = rules.fix_name_case("MACLEOD")
    assert value == "MACLEOD"
    assert flags[0][0] == "name_case_uncertain"


@pytest.mark.parametrize("raw, sal, first, last, suffix", [
    ("Dr Jane Smith", "Dr", "Jane", "Smith", ""),
    ("Mr. John Smith Jr", "Mr.", "John", "Smith", "Jr"),
    ("Smith, John", "", "John", "Smith", ""),
    ("Pieter van der Berg", "", "Pieter", "van der Berg", ""),
    ("Prof Sir Alan Jones OBE", "Prof Sir", "Alan", "Jones", "OBE"),
    ("Anne Smith-Jones", "", "Anne", "Smith-Jones", ""),
    ("Mary Jane Watson", "", "Mary Jane", "Watson", ""),
])
def test_split_full_name(raw, sal, first, last, suffix):
    parts, _ = rules.split_full_name(raw)
    assert parts == {"salutation": sal, "first_name": first, "last_name": last, "name_suffix": suffix}


def test_split_single_name_flagged():
    parts, flags = rules.split_full_name("Madonna")
    assert parts["first_name"] == "Madonna" and parts["last_name"] == ""
    assert flags[0][0] == "single_name"


def test_split_title_only_word_is_kept_as_name():
    parts, _ = rules.split_full_name("Dr")
    assert parts["first_name"] == "Dr"


@pytest.mark.parametrize("raw, expected", [
    ("Jane.Smith@Example.COM", "jane.smith@example.com"),
    ("Jane Smith <jane@example.com>", "jane@example.com"),
    ("mailto:jane@example.com", "jane@example.com"),
    ("  'jane@example.com';", "jane@example.com"),
    ("jane@example.com.", "jane@example.com"),
    ("jane at example.com", ""),
    ("jane@", ""),
    ("jane@@example.com", ""),
    ("jane@example", ""),
])
def test_email(raw, expected):
    assert rules.clean_email(raw)[0] == expected


def test_email_typo_suggested_not_changed():
    value, flags = rules.clean_email("sam@gmial.com")
    assert value == "sam@gmial.com"
    assert flags[0][0] == "email_typo_suggestion" and "gmail.com" in flags[0][1]


def test_email_typo_fixed_when_asked():
    value, flags = rules.clean_email("sam@hotmial.co.uk", apply_suggestion=True)
    assert value == "sam@hotmail.co.uk"
    assert flags[0][0] == "email_typo_fixed"


@pytest.mark.parametrize("raw, expected", [
    ("07700 900123", "+447700900123"),
    ("+44 (0)7700 900123", "+447700900123"),
    ("0044 7700 900 123", "+447700900123"),
    ("7700900123", "+447700900123"),      # leading zero lost in Excel
    ("(020) 7946-0123", "+442079460123"),
    ("+1 202-555-0143", "+12025550143"),
    ("+447700900123", "+447700900123"),
    ("n/a", ""),
    ("123", ""),
    ("0207", ""),
])
def test_phone(raw, expected):
    assert rules.clean_phone(raw)[0] == expected


def test_phone_default_country():
    assert rules.clean_phone("(202) 555-0143", "US")[0] == "+12025550143"


def test_phone_extension_flagged():
    value, flags = rules.clean_phone("020 7946 0123 ext 45")
    assert value == "+442079460123"
    assert flags[0][0] == "phone_extension_dropped"


@pytest.mark.parametrize("raw, day_first, expected, flag", [
    ("25/12/2020", True, "2020-12-25", None),
    ("03/04/2021", True, "2021-04-03", "date_ambiguous"),
    ("03/04/2021", False, "2021-03-04", "date_ambiguous"),
    ("05/05/2021", True, "2021-05-05", None),
    ("12/25/2020", True, "2020-12-25", "date_order_swapped"),
    ("2021-06-01", True, "2021-06-01", None),
    ("1st March 2022", True, "2022-03-01", None),
    ("March 1, 2022", True, "2022-03-01", None),
    ("14/08/15", True, "2015-08-14", None),
    ("31/02/2021", True, "31/02/2021", "date_unreadable"),
    ("last spring", True, "last spring", "date_unreadable"),
])
def test_dates(raw, day_first, expected, flag):
    value, flags = rules.clean_date(raw, day_first)
    assert value == expected
    assert [f[0] for f in flags] == ([flag] if flag else [])


@pytest.mark.parametrize("raw, country, expected, flagged", [
    ("sw1a1aa", "", "SW1A 1AA", False),
    ("m1 1ae", "UK", "M1 1AE", False),
    ("  EC1A  1BB ", "United Kingdom", "EC1A 1BB", False),
    ("ABC 123", "UK", "ABC 123", True),
    ("90210", "United States", "90210", False),   # not UK: left alone
])
def test_postcode(raw, country, expected, flagged):
    value, flags = rules.clean_postcode(raw, country)
    assert value == expected
    assert bool(flags) == flagged
