"""Command line entry point: site-watch check | run | report."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

from .checker import run_checks
from .alerts import pending_count
from .config import ConfigError, load_config
from .report import build_report

log = logging.getLogger("site_watch")


def _run_loop(config_path: Path, dry_run: bool) -> None:
    config = load_config(config_path)
    next_due = {w.name: 0.0 for w in config.watches}
    log.info("running %d watch(es); press Ctrl+C to stop", len(config.watches))
    while True:
        now = time.monotonic()
        due = [w for w in config.watches if next_due[w.name] <= now]
        if due:
            run_checks(config, dry_run, due)
            for w in due:
                next_due[w.name] = time.monotonic() + w.interval_minutes * 60
        time.sleep(max(1.0, min(next_due.values()) - time.monotonic()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="site-watch", description="Watch web pages for changes and keep evidence.")
    parser.add_argument("-c", "--config", type=Path, default=Path("watches.json"), help="config file (default: watches.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("check", "run every watch once"), ("run", "keep checking on each watch's interval")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--dry-run", action="store_true", help="write alerts to files instead of sending them")
    rep = sub.add_parser("report", help="write the HTML evidence report")
    rep.add_argument("-o", "--output", type=Path, default=Path("report/report.html"))
    args = parser.parse_args(argv)

    if hasattr(signal, "SIGBREAK"):  # Windows Ctrl+Break and console close
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        if args.command == "check":
            config = load_config(args.config)
            results = run_checks(config, args.dry_run)
            failed = sum(r.status == "failed" for r in results)
            changed = sum(r.status == "changed" for r in results)
            unsent = pending_count(config.failed_alerts_dir)  # this run's and older kept alerts
            log.info("done: %d checked, %d changed, %d failed, %d alert(s) not sent", len(results), changed, failed, unsent)
            return 1 if failed or unsent else 0
        if args.command == "run":
            _run_loop(args.config, args.dry_run)
        if args.command == "report":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            count = build_report(load_config(args.config), args.output)
            log.info("report written with %d change(s): %s", count, args.output)
    except ConfigError as exc:
        log.error("config error: %s", exc)
        return 2
    except KeyboardInterrupt:
        # Exit at once. Closing the browser in an orderly way after an
        # interrupt can hang; ending the process also ends the browser.
        log.info("stopped")
        logging.shutdown()
        os._exit(130)
    return 0


if __name__ == "__main__":
    sys.exit(main())
