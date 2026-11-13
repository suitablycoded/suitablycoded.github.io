"""Run site-watch against the bundled fictional pages and build the sample report.

    python demo/run_demo.py

Starts the local demo server (four fictional pages), stores a baseline, moves the pages forward five
times with a check after each step (alerts in dry-run mode), then writes the
report to demo/output/. Nothing leaves this computer.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from playwright.sync_api import sync_playwright  # noqa: E402
from server import DemoServer, DemoSite  # noqa: E402

from site_watch.checker import run_checks  # noqa: E402
from site_watch.config import load_config  # noqa: E402
from site_watch.report import build_report  # noqa: E402

WORK = HERE / "work"
OUTPUT = HERE / "output"
STEPS = 5


def write_config(base_url: str) -> Path:
    config = {
        "data_dir": "data",
        "alerts_dir": "../output/alerts",
        "timeout_seconds": 10,
        "watches": [
            {"name": "Supplier price list", "url": f"{base_url}/prices", "selector": "#prices", "interval_minutes": 60},
            {"name": "Planning notices", "url": f"{base_url}/planning", "selector": "#notices", "interval_minutes": 1440},
            {
                "name": "Stock status",
                "url": f"{base_url}/stock",
                "ignore": [r"Last checked: .*", r"Page generated .*"],
                "interval_minutes": 15,
            },
            {"name": "Delivery lead times", "url": f"{base_url}/delivery", "selector": "table", "interval_minutes": 60},
        ],
    }
    path = WORK / "watches.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def capture_previews(report: Path) -> None:
    """Save two PNG previews of the report for the project page."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.goto(report.as_uri())
        page.screenshot(path=str(OUTPUT / "preview-report.png"))
        page.locator("section.change").first.screenshot(path=str(OUTPUT / "preview-change.png"))
        browser.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    for folder in (WORK, OUTPUT):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)

    site = DemoSite(seed=7)
    with DemoServer(site, port=8765) as server:
        config = load_config(write_config(server.base_url))
        logging.info(f"Step 0: storing baselines from {server.base_url}")
        run_checks(config, dry_run=True)
        for step in range(1, STEPS + 1):
            site.advance()
            logging.info(f"Step {step}: pages moved on, checking again")
            run_checks(config, dry_run=True)

    report = OUTPUT / "report.html"
    count = build_report(config, report)
    capture_previews(report)
    logging.info(f"Done. {count} change(s) in demo/output/report.html; alerts in demo/output/alerts/")


if __name__ == "__main__":
    main()
