# site-watch

site-watch checks web pages for changes. When a page changes it keeps evidence: the text before and after, a diff, and full-page screenshots of both. It then sends an alert by email, by webhook, or both.

It is for anyone who needs to know when a page changes and needs proof of what it said. Examples are a supplier price list, a planning notices page or a stock status page.

Built with Python, Playwright (headless Chromium), SQLite and pytest.

## What it does

- Loads each page in a real headless browser. After the page loads it waits for network activity to stop (for up to 10 seconds), so content that scripts fetch after loading is read. For content that appears without a network request, such as after a timer, set `wait_for` and, if needed, `settle_seconds`.
- Compares only the part of the page you pick with a CSS selector, or the whole page.
- Removes noise such as timestamps with regex ignore patterns before comparing.
- On the first check of a watch it stores a baseline and reports nothing.
- On a change it saves `before.txt`, `after.txt`, `diff.txt`, `before.png` and `after.png` in a dated evidence folder, records the change in SQLite, and sends an alert.
- Writes one HTML evidence report with each change, the diff highlighted, and the screenshots side by side.
- Treats timeouts, HTTP errors, a server that is down, a missing or invalid selector, a `wait_for` element that never appears and a page that cannot be screenshotted as failed checks. Each watch runs on its own: a failure in one is logged and recorded, and the other watches are still checked. A failure never counts as a change.
- Keeps any alert that could not be sent, shows it in the report, and tries it again at the start of the next check.

## Install

You need Python 3.10 or later.

```
python -m venv .venv
.venv\Scripts\activate          (Windows)
source .venv/bin/activate       (macOS or Linux)
pip install -e ".[test]"
python -m playwright install chromium
```

`requirements.txt` lists the same pinned versions if you prefer `pip install -r requirements.txt`.

## Run

Copy `watches.example.json` to `watches.json` and edit it. Then:

```
site-watch -c watches.json check            run every watch once and send alerts
site-watch -c watches.json check --dry-run  run once, write alerts to files instead
site-watch -c watches.json run              keep running, each watch on its own interval
site-watch -c watches.json report -o report/report.html
```

Exit codes for `check`: 0 when every check worked and no alert is waiting to be sent, 1 when any check failed or any alert (from this run or an earlier one) is still unsent, 2 for a config error, and 130 when stopped with Ctrl+C. Ctrl+C stops at once, even in the middle of loading a page; the check in progress is abandoned and nothing is recorded for it.

## The demo

```
python demo/run_demo.py
```

This starts a small web server on 127.0.0.1 port 8765 with four fictional pages: a supplier price list, a council planning notices page, a stock status page and a delivery lead times page. The delivery page is empty when it loads; a script fills in the table from a second request about a second later. The pages change on a fixed, seeded schedule. The demo stores a baseline, moves the pages forward five times with a check after each step, and finds six changes. It writes:

- `demo/output/report.html` with its `images/` folder
- `demo/output/alerts/` with the six dry-run alerts
- two preview images of the report

The stock page has a timestamp that changes every step. Its watch ignores that timestamp, so you only see a change when the stock status itself changes. The demo never contacts any other website.

## Config reference

The config is a JSON file. Relative paths in it are read from the folder the config file is in.

| Field | Required | Meaning |
| --- | --- | --- |
| `data_dir` | no | Where the database, snapshots and evidence go. Default `data`. |
| `alerts_dir` | no | Where dry-run alerts are written. Default `<data_dir>/alerts`. |
| `timeout_seconds` | no | Page load timeout. Default 20. |
| `watches` | yes | List of watches, see below. |

Each watch:

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | A unique name. Used in alerts and folder names. |
| `url` | yes | The page to check. |
| `selector` | no | CSS selector. Only the text of matching elements is compared. If it matches nothing, the check fails. |
| `ignore` | no | List of regex patterns removed from the text before comparing. |
| `interval_minutes` | no | How often `run` checks this watch. Default 60. |
| `wait_for` | no | CSS selector to wait for before reading the page. If it does not appear within `timeout_seconds`, the check fails. |
| `settle_seconds` | no | Extra seconds to wait before reading. Default 0. |

Blank lines and repeated spaces are ignored when comparing. A config with a wrong type, for example `ignore` given as text instead of a list, is rejected with a config error.

The last snapshot of each watch is kept by name. If you remove a watch, its history stays in the report. If you add it back later, or change the URL of an existing name, the first check compares against the old snapshot. Use a new name to start again from a fresh baseline.

## Alerts

Alerts are set with environment variables. See `.env.example`. A channel with no settings is skipped.

- Email: `SITE_WATCH_SMTP_HOST`, `SITE_WATCH_SMTP_PORT`, `SITE_WATCH_SMTP_STARTTLS`, `SITE_WATCH_SMTP_USER`, `SITE_WATCH_SMTP_PASSWORD`, `SITE_WATCH_EMAIL_FROM`, `SITE_WATCH_EMAIL_TO`.
- Webhook: `SITE_WATCH_WEBHOOK_URL`. It receives a JSON POST with `watch`, `url`, `at`, `evidence`, `added`, `removed` and `diff`.

site-watch does not read `.env` files itself. Set the variables in your shell or scheduler. With `--dry-run` nothing is sent. Each alert is written to a JSON file holding the email subject and body and the webhook payload.

Email alerts carry `diff.txt`, `before.png` and `after.png` as attachments. The evidence folder named in the alert is relative to the data folder.

If sending fails, the error is logged and the run carries on. The change is still recorded, the alert is kept in `<data_dir>/failed-alerts/`, the report lists it, and `check` exits with code 1. The kept file records which channels failed. At the start of each later check (not in dry-run mode) the alert is sent again on those channels only, so a channel that already worked never gets a second copy. The file is removed once every channel has gone through. While any kept alert is still waiting, `check` exits with code 1, even when nothing new happened. A kept file that cannot be read is renamed to `.damaged`, logged and skipped, so it cannot block later checks.

## Scheduling

You can use `run`, or schedule `check` with the system scheduler.

Windows Task Scheduler:

```
schtasks /Create /TN "site-watch" /SC MINUTE /MO 30 /TR "\"<project folder>\.venv\Scripts\site-watch.exe\" -c \"<project folder>\watches.json\" check"
```

Or create a basic task in the Task Scheduler window that runs `.venv\Scripts\site-watch.exe` with the arguments `-c watches.json check` and the project folder as "Start in".

cron (every 30 minutes):

```
*/30 * * * * cd /path/to/site-watch && .venv/bin/site-watch -c watches.json check >> site-watch.log 2>&1
```

With a scheduler, every watch is checked on each run. `interval_minutes` is only used by `run`.

## Tests

```
pytest
```

The tests use the local demo server only. They cover the baseline, a detected change, no change, ignore patterns, a missing or invalid selector, an unexpected error in one watch, a very tall page (screenshot capped), content fetched after load, `wait_for`, an HTTP error, a timeout, a server that is down, the dry-run alert content, a failed alert being kept and retried on the failed channel only, the exit code while an alert is waiting, a damaged kept alert, a very long watch name, Ctrl+C during a check, bad config values and the report. Sending real email is not covered by the tests.

## Limits

- It compares visible text, not layout, colours or images. A change that only affects how a page looks is not detected.
- It does not log in to sites or fill in forms.
- It does not get past CAPTCHAs or bot blocking.
- Failed checks are logged, recorded and shown in the report, but no alert is sent for them.
- Content that a script adds without any network request is only read if you set `wait_for` or `settle_seconds`.
- Screenshots stop at 20,000 pixels from the top of the page. Chromium cannot capture very tall pages in one image (in testing, 300,000 pixels worked and 700,000 did not), so site-watch caps the height. The text of the whole page is still compared, so a change further down is still detected; it is just not in the screenshot.
- A page that keeps making network requests never goes quiet, so each check of it waits the full 10 seconds before reading.
- A removed watch keeps its history in the report. Adding it back, or changing the URL of an existing name, compares against the old snapshot.
- Watch names are cut to 60 characters for folder names, so two names that only differ after that count as the same.
- The evidence path in an alert is relative to the data folder on the machine that runs site-watch. Email alerts carry the files as attachments; webhook alerts do not.
- Times are local time with no time zone. Email over implicit TLS (port 465) is not supported; use STARTTLS.
- One process runs the checks one page at a time. It is meant for tens of pages, not thousands.
- Evidence and screenshots are kept until you delete them.
