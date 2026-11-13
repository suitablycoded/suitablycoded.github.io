"""Command line entry point: contact-cleaner clean INPUT --out OUTDIR."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_settings
from .pipeline import NoUsableColumns, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contact-cleaner", description="Clean a contact spreadsheet for a CRM import.")
    sub = parser.add_subparsers(dest="command", required=True)
    clean = sub.add_parser("clean", help="clean an .xlsx or .csv file")
    clean.add_argument("input", type=Path)
    clean.add_argument("--out", type=Path, required=True, help="folder for the output files")
    clean.add_argument("--mapping", type=Path, help="YAML mapping file")
    clean.add_argument("--sheet", help="sheet name (default: the first sheet)")
    args = parser.parse_args(argv)

    try:
        result = run(args.input, args.out, load_settings(args.mapping), sheet=args.sheet)
    except (NoUsableColumns, ValueError, KeyError, FileNotFoundError) as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 2
    print(f"Rows in: {result.input_rows}. Clean: {len(result.clean)}. Rejected: {len(result.rejects)}. "
          f"Merged away: {len(result.merges)}. Changes: {len(result.changes)}.")
    print(f"Outputs written to {args.out}")
    return 0
