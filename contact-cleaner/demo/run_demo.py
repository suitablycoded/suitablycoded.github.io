"""Generate the messy demo workbook, clean it, and write the outputs to demo/output."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from make_messy_workbook import write_workbook  # noqa: E402

from contact_cleaner.config import load_settings  # noqa: E402
from contact_cleaner.pipeline import run  # noqa: E402


def main() -> None:
    workbook = write_workbook(HERE / "input" / "messy_contacts.xlsx")
    result = run(workbook, HERE / "output", load_settings(None))
    print(f"Rows in: {result.input_rows}")
    print(f"Clean contacts: {len(result.clean)}")
    print(f"Rejected: {len(result.rejects)}")
    print(f"Merged away as exact duplicates: {len(result.merges)}")
    print(f"Kept rows needing review: {sum(1 for r in result.clean if r.flags)}")
    print(f"Individual changes: {len(result.changes)}")
    print("Outputs in demo/output (open report.html)")


if __name__ == "__main__":
    main()
