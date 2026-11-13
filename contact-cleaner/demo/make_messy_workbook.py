"""Write a messy 600-row contact workbook of fictional people for the demo.

All companies are made up, all email domains are reserved example domains, and
all phone numbers come from Ofcom's ranges reserved for drama (07700 900xxx and
020 7946 0xxx) or the fictional US 555-01xx range.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

SEED = 20261112
ROWS = 600

FIRST = ["Amelia", "Oliver", "Isla", "George", "Ava", "Harry", "Mia", "Noah", "Freya", "Jack", "Grace", "Leo",
         "Sophie", "Arthur", "Evie", "Oscar", "Ruby", "Charlie", "Lily", "Thomas", "Priya", "Arjun", "Fatima",
         "Yusuf", "Chloe", "Ewan", "Niamh", "Rhys", "Siobhan", "Hamish", "Mary Jane", "Jean-Luc", "Zoe", "Callum"]
LAST = ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Evans", "Thomas", "Patel", "Khan",
        "McDonald", "McKenzie", "O'Neill", "O'Brien", "van der Berg", "de Souza", "Smith-Jones", "Ashworth-Lee",
        "MacLeod", "Hughes", "Robinson", "Wright", "Walker", "Edwards", "Clarke", "Hall", "Fletcher", "D'Arcy"]
TITLES = ["Mr", "Mrs", "Ms", "Miss", "Dr", "Dr.", "Prof"]
SUFFIXES = ["Jr", "OBE", "PhD", "III"]
COMPANIES = ["Acme Example Ltd", "Placeholder Plumbing Ltd", "Sample Logistics plc", "Demo Bakery Co",
             "Fictional Foods Ltd", "Imaginary Interiors", "Testbed Engineering Ltd", "Mock Marketing LLP",
             "Notreal Nurseries", "Pretend Print Ltd", "Dummy Data Services", "Specimen Solicitors LLP"]
JOBS = ["Office Manager", "Director", "Buyer", "Accounts Assistant", "Sales Lead", "Owner", "Operations Manager", ""]
STREETS = ["High Street", "Station Road", "Church Lane", "Mill Road", "Park Avenue", "Victoria Road"]
TOWNS = ["Exampleton", "Sampleford", "Testbury", "Mockham", "Placeholder-on-Sea", "Demoworth"]
AREAS = ["AB", "B", "CF", "E", "EH", "G", "LS", "M", "N", "NE", "SW", "W", "YO", "BS"]
MANAGERS = ["Team A", "Team B", "Team C", ""]


def slug(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def company_domain(company: str) -> str:
    base = slug(company.split(" ")[0])
    return f"{base}.example." + ("com" if len(base) % 3 else "org")


class Generator:
    def __init__(self, seed: int = SEED) -> None:
        self.r = random.Random(seed)

    def chance(self, p: float) -> bool:
        return self.r.random() < p

    def messy_space(self, text: str) -> str:
        if not text or not self.chance(0.15):
            return text
        return self.r.choice([f" {text}", f"{text}  ", text.replace(" ", "  ", 1), f"\t{text}", f"{text} "])

    def casing(self, text: str) -> str:
        roll = self.r.random()
        return text.upper() if roll < 0.12 else text.lower() if roll < 0.2 else text

    def email(self, first: str, last: str, company: str) -> str:
        local = f"{slug(first.split(' ')[0])}.{slug(last)}"
        domain = company_domain(company) if self.chance(0.8) else self.r.choice(["example.net", "example.co.uk"])
        roll = self.r.random()
        if roll < 0.04:
            domain = self.r.choice(["exmaple.com", "example.cmo", "exmaple.co.uk"])
        elif roll < 0.07:
            return self.r.choice([f"{local} at {domain}", f"{local}@", f"{local}{domain}", "unknown"])
        address = f"{local}@{domain}"
        roll = self.r.random()
        if roll < 0.10:
            address = address.upper()
        elif roll < 0.14:
            address = f"{first} {last} <{address}>"
        elif roll < 0.17:
            address = f"mailto:{address}"
        elif roll < 0.20:
            address = address + self.r.choice([";", ".", " ,"])
        return address

    def phone(self, mobile: bool) -> object:
        n = self.r.randint(0, 999)
        if self.chance(0.04):
            return self.r.choice(["n/a", "ask switchboard", "0207", "TBC", "123"])
        if self.chance(0.03):
            return f"+1 202-555-01{n % 100:02d}"
        if mobile:
            choices = [f"07700 900{n:03d}", f"07700900{n:03d}", f"+44 7700 900{n:03d}", f"+44 (0)7700 900{n:03d}",
                       f"0044 7700 900 {n:03d}", f"(07700) 900-{n:03d}", int(f"7700900{n:03d}")]
        else:
            choices = [f"020 7946 0{n:03d}", f"(020) 7946 0{n:03d}", f"02079460{n:03d}", f"+44 20 7946 0{n:03d}",
                       f"020-7946-0{n:03d} ext 12", int(f"2079460{n:03d}")]
        return self.r.choice(choices)

    def date_added(self) -> object:
        when = datetime(2015, 1, 1) + timedelta(days=self.r.randint(0, 3600))
        roll = self.r.random()
        if roll < 0.40:
            return when
        if roll < 0.70:
            return when.strftime("%d/%m/%Y")
        if roll < 0.78:
            return when.strftime("%Y-%m-%d")
        if roll < 0.86:
            day = when.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            return f"{day}{suffix} {when.strftime('%B %Y')}"
        if roll < 0.90:
            return when.strftime("%d/%m/%y")
        if roll < 0.97:
            return ""
        return self.r.choice(["last spring", "31/02/2021", "?"])

    def postcode(self) -> str:
        r = self.r
        code = f"{r.choice(AREAS)}{r.randint(1, 19)} {r.randint(1, 9)}{r.choice('ABDEFGHJLNPQRSTUWXYZ')}{r.choice('ABDEFGHJLNPQRSTUWXYZ')}"
        roll = r.random()
        if roll < 0.15:
            return code.lower()
        if roll < 0.30:
            return code.replace(" ", "")
        if roll < 0.33:
            return r.choice(["ABC 123", "N/A", "TBC"])
        return code

    def person(self) -> dict[str, object]:
        r = self.r
        first, last = r.choice(FIRST), r.choice(LAST)
        company = r.choice(COMPANIES)
        row: dict[str, object] = {"Full Name": "", "First": "", "Surname": ""}
        if self.chance(0.45):
            name = f"{first} {last}"
            if self.chance(0.06):
                name = f"{last}, {first}"
            else:
                if self.chance(0.18):
                    name = f"{r.choice(TITLES)} {name}"
                if self.chance(0.05):
                    name = f"{name} {r.choice(SUFFIXES)}"
            row["Full Name"] = self.casing(name)
        else:
            row["First"], row["Surname"] = self.casing(first), self.casing(last)
        no_contact = self.chance(0.04)
        row["E-mail"] = "" if no_contact or self.chance(0.08) else self.email(first, last, company)
        row["Tel"] = "" if no_contact or self.chance(0.20) else self.phone(False)
        row["Mobile"] = "" if no_contact or self.chance(0.40) else self.phone(True)
        row["Organisation"] = company if self.chance(0.92) else ""
        row["Position"] = r.choice(JOBS)
        row["Address"] = f"{r.randint(1, 200)} {r.choice(STREETS)}"
        row["Town"] = r.choice(TOWNS)
        row["Post Code"] = self.postcode()
        row["Country"] = r.choice(["UK", "UK", "UK", "United Kingdom", "", "England"])
        row["Date Added"] = self.date_added()
        row["Account Manager"] = r.choice(MANAGERS)
        row["Notes"] = r.choice(["", "", "", "Met at trade show", "Prefers email", "Do not call before 10am"])
        return {k: self.messy_space(v) if isinstance(v, str) else v for k, v in row.items()}

    def exact_duplicate(self, base: dict[str, object]) -> dict[str, object]:
        dup = dict(base)
        email = str(dup["E-mail"]).strip()
        dup["E-mail"] = self.r.choice([email.upper(), f" {email}", email])
        for key in ("Tel", "Position", "Post Code", "Date Added", "Notes"):
            if self.chance(0.5):
                dup[key] = ""
        if self.chance(0.3):
            dup["Position"] = self.r.choice(JOBS[:-1])
        return dup

    def likely_duplicate(self, base: dict[str, object]) -> dict[str, object]:
        dup = dict(base)
        email = str(base["E-mail"])
        local = email.split("@")[0].split("<")[-1].strip().lower() or "contact"
        dup["E-mail"] = f"{local}{self.r.randint(1, 99)}@example.net"
        dup["Organisation"] = str(base["Organisation"]).replace(" Ltd", " Limited")
        return dup

    def rows(self) -> list[dict[str, object]]:
        people: list[dict[str, object]] = []
        while len(people) < ROWS - 2:
            roll = self.r.random()
            usable = [p for p in people if str(p["E-mail"]).count("@") == 1 and " at " not in str(p["E-mail"])]
            if usable and roll < 0.08:
                people.append(self.exact_duplicate(self.r.choice(usable)))
            elif people and roll < 0.11:
                candidates = [p for p in usable if p["Organisation"]]
                people.append(self.likely_duplicate(self.r.choice(candidates)) if candidates else self.person())
            else:
                people.append(self.person())
        for position in (137, 412):
            people.insert(position, {})
        return people


def write_workbook(path: Path, seed: int = SEED) -> Path:
    rows = Generator(seed).rows()
    headers = ["Full Name", "First", "Surname", "E-mail", "Tel", "Mobile", "Organisation", "Position", "Address",
               "Town", "Post Code", "Country", "Date Added", "Account Manager", "Notes"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Contacts"
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row.get(h, None) for h in headers])
    for cell in ws["M"][1:]:
        if isinstance(cell.value, datetime):
            cell.number_format = "dd/mm/yyyy"
    archive = wb.create_sheet("Archive notes")
    archive.append(["Note"])
    archive.append(["Old list merged in 2019. Not contacts."])
    wb.properties.creator = ""
    wb.properties.lastModifiedBy = ""
    wb.properties.title = "Messy contact list (fictional demo data)"
    wb.properties.created = datetime(2026, 1, 1)
    wb.properties.modified = datetime(2026, 1, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


if __name__ == "__main__":
    target = Path(__file__).parent / "input" / "messy_contacts.xlsx"
    write_workbook(target)
    print(f"Wrote {target.name}")
