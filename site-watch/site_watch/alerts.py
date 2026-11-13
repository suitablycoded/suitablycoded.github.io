"""Change alerts: email over SMTP, a JSON webhook, or a local file in dry-run mode.

Settings come from environment variables (see .env.example). A channel with no
settings is skipped. An alert that fails to send is kept in the failed-alerts
folder and tried again at the start of the next check.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Alert:
    watch: str
    url: str
    at: str
    evidence: str
    added: int
    removed: int
    diff: str

    @property
    def subject(self) -> str:
        return f"[site-watch] Change detected: {self.watch}"

    @property
    def file_stem(self) -> str:
        return f"{self.at[:10]}-{Path(self.evidence).name}"

    @property
    def body(self) -> str:
        return (
            f"A change was detected on '{self.watch}'.\n\n"
            f"URL: {self.url}\n"
            f"Time: {self.at}\n"
            f"Lines added: {self.added}, lines removed: {self.removed}\n"
            f"Evidence folder, inside the site-watch data folder: {self.evidence}\n"
            f"The email version of this alert has the diff and both screenshots attached.\n\n"
            f"Diff:\n{self.diff}\n"
        )


def write_dry_run(alert: Alert, alerts_dir: Path) -> Path:
    """Write what would have been sent, instead of sending it."""
    alerts_dir.mkdir(parents=True, exist_ok=True)
    out = alerts_dir / f"{alert.file_stem}.json"
    payload = {
        "email": {"subject": alert.subject, "body": alert.body},
        "webhook": asdict(alert),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out


def email_configured() -> bool:
    return bool(os.environ.get("SITE_WATCH_SMTP_HOST") and os.environ.get("SITE_WATCH_EMAIL_TO"))


def webhook_configured() -> bool:
    return bool(os.environ.get("SITE_WATCH_WEBHOOK_URL"))


def send_email(alert: Alert, evidence_root: Path) -> None:
    msg = EmailMessage()
    msg["Subject"] = alert.subject
    msg["From"] = os.environ.get("SITE_WATCH_EMAIL_FROM", "site-watch@localhost")
    msg["To"] = os.environ["SITE_WATCH_EMAIL_TO"]
    msg.set_content(alert.body)
    folder = evidence_root / alert.evidence
    for name, maintype, subtype in (("diff.txt", "text", "plain"), ("before.png", "image", "png"), ("after.png", "image", "png")):
        if (folder / name).exists():
            msg.add_attachment((folder / name).read_bytes(), maintype=maintype, subtype=subtype, filename=name)
    port = int(os.environ.get("SITE_WATCH_SMTP_PORT", "587"))
    with smtplib.SMTP(os.environ["SITE_WATCH_SMTP_HOST"], port, timeout=30) as smtp:
        if os.environ.get("SITE_WATCH_SMTP_STARTTLS", "true").lower() != "false":
            smtp.starttls()
        user = os.environ.get("SITE_WATCH_SMTP_USER")
        if user:
            smtp.login(user, os.environ.get("SITE_WATCH_SMTP_PASSWORD", ""))
        smtp.send_message(msg)


def send_webhook(alert: Alert) -> None:
    data = json.dumps(asdict(alert)).encode("utf-8")
    req = urllib.request.Request(
        os.environ["SITE_WATCH_WEBHOOK_URL"], data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def send(alert: Alert, evidence_root: Path, only: list[str] | None = None) -> dict[str, str]:
    """Send on each configured channel, or only on the channels named in `only`.

    Returns {channel: error} for every channel that failed.
    """
    errors: dict[str, str] = {}
    channels = []
    if email_configured():
        channels.append(("email", lambda: send_email(alert, evidence_root)))
    if webhook_configured():
        channels.append(("webhook", lambda: send_webhook(alert)))
    if not channels:
        log.warning("no alert channel is configured, so the alert for %s was not sent; see .env.example", alert.watch)
    for name, sender in channels:
        if only is not None and name not in only:
            continue
        try:
            sender()
            log.info("alert sent by %s for %s", name, alert.watch)
        except Exception as exc:  # network and SMTP errors must not stop the run
            log.error("%s alert failed for %s: %s", name, alert.watch, exc)
            errors[name] = str(exc)
    return errors


def keep_failed(alert: Alert, failed_dir: Path, pending: list[str]) -> Path:
    """Save an alert so the channels in `pending` can be retried later."""
    failed_dir.mkdir(parents=True, exist_ok=True)
    out = failed_dir / f"{alert.file_stem}.json"
    out.write_text(json.dumps({"pending": pending, "alert": asdict(alert)}, indent=2), encoding="utf-8")
    return out


def pending_count(failed_dir: Path) -> int:
    return len(list(failed_dir.glob("*.json"))) if failed_dir.exists() else 0


def retry_failed(failed_dir: Path, evidence_root: Path) -> int:
    """Retry each kept alert on the channels that failed before. Returns how many are still unsent.

    A kept file that cannot be read is renamed to `.damaged` and skipped, so it
    cannot block later checks.
    """
    for path in sorted(failed_dir.glob("*.json")) if failed_dir.exists() else []:
        try:
            kept = json.loads(path.read_text(encoding="utf-8"))
            alert = Alert(**kept["alert"])
            pending = [str(c) for c in kept["pending"]]
        except (ValueError, KeyError, TypeError) as exc:
            log.error("kept alert %s is damaged and was set aside (%s)", path.name, exc)
            path.replace(path.with_suffix(".damaged"))
            continue
        errors = send(alert, evidence_root, only=pending)
        if errors:
            keep_failed(alert, failed_dir, sorted(errors))  # only the channels still failing
        else:
            log.info("kept alert for %s sent on retry", alert.watch)
            path.unlink()
    return pending_count(failed_dir)
