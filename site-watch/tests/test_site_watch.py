"""Tests against the bundled local demo server only."""

from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))

from server import DemoServer, DemoSite  # noqa: E402

from site_watch.checker import run_checks  # noqa: E402
from site_watch.config import Config, ConfigError, load_config  # noqa: E402
from site_watch.report import build_report  # noqa: E402
from site_watch.store import Store  # noqa: E402


@pytest.fixture()
def site() -> DemoSite:
    return DemoSite(seed=7)


@pytest.fixture()
def server(site: DemoSite):
    with DemoServer(site) as srv:
        yield srv


def make_config(tmp_path: Path, watches: list[dict], timeout: float = 10) -> Config:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "watches.json"
    path.write_text(json.dumps({"timeout_seconds": timeout, "watches": watches}), encoding="utf-8")
    return load_config(path)


def events(config: Config, kind: str) -> list:
    store = Store(config.db_path)
    try:
        return store.events(kind)
    finally:
        store.close()


def test_first_run_stores_baseline_and_sends_nothing(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#prices"}])
    [result] = run_checks(config, dry_run=True)
    assert result.status == "baseline"
    assert not config.alerts_dir.exists()
    assert events(config, "changed") == []


def test_no_change_when_page_is_the_same(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#prices"}])
    run_checks(config, dry_run=True)
    [result] = run_checks(config, dry_run=True)
    assert result.status == "unchanged"


def test_change_detected_with_evidence(tmp_path, server, site):
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#prices"}])
    run_checks(config, dry_run=True)
    site.advance()
    site.advance()  # step 2 raises a price
    [result] = run_checks(config, dry_run=True)
    assert result.status == "changed"
    folder = config.data_dir / result.evidence
    for name in ("before.txt", "after.txt", "diff.txt", "before.png", "after.png"):
        assert (folder / name).stat().st_size > 0
    diff = (folder / "diff.txt").read_text(encoding="utf-8")
    assert "-Hex bolt M8" in diff and "+Hex bolt M8" in diff
    assert len(events(config, "changed")) == 1


def test_ignore_patterns_remove_timestamp_noise(tmp_path, server, site):
    url = f"{server.base_url}/stock"
    noisy = make_config(tmp_path / "noisy", [{"name": "Stock", "url": url}])
    quiet = make_config(
        tmp_path / "quiet", [{"name": "Stock", "url": url, "ignore": [r"Last checked: .*", r"Page generated .*"]}]
    )
    run_checks(noisy, dry_run=True)
    run_checks(quiet, dry_run=True)
    site.advance()  # step 1 only changes the timestamps
    assert run_checks(noisy, dry_run=True)[0].status == "changed"
    assert run_checks(quiet, dry_run=True)[0].status == "unchanged"


def test_missing_selector_is_a_failed_check(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#nothing-here"}])
    [result] = run_checks(config, dry_run=True)
    assert result.status == "failed"
    assert "selector not found" in result.detail
    assert len(events(config, "failed")) == 1
    store = Store(config.db_path)
    assert store.snapshot("Prices") is None
    store.close()


def test_http_error_is_a_failed_check(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Gone", "url": f"{server.base_url}/no-such-page"}])
    [result] = run_checks(config, dry_run=True)
    assert result.status == "failed"
    assert "HTTP 404" in result.detail


def test_timeout_is_a_failed_check(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Slow", "url": f"{server.base_url}/slow"}], timeout=1)
    [result] = run_checks(config, dry_run=True)
    assert result.status == "failed"
    assert "timed out" in result.detail


def test_server_down_is_a_failed_check_not_a_change(tmp_path, site):
    with DemoServer(site) as srv:
        url = f"{srv.base_url}/prices"
        config = make_config(tmp_path, [{"name": "Prices", "url": url, "selector": "#prices"}])
        run_checks(config, dry_run=True)
    # The server is now stopped, so the port refuses connections.
    with socket.socket() as s:
        assert s.connect_ex(("127.0.0.1", int(url.split(":")[2].split("/")[0]))) != 0
    [result] = run_checks(config, dry_run=True)
    assert result.status == "failed"
    assert "could not load page" in result.detail
    assert events(config, "changed") == []
    assert not config.alerts_dir.exists()


def test_dry_run_alert_content(tmp_path, server, site):
    config = make_config(tmp_path, [{"name": "Planning notices", "url": f"{server.base_url}/planning", "selector": "#notices"}])
    run_checks(config, dry_run=True)
    site.advance()
    site.advance()  # step 2 adds a notice
    run_checks(config, dry_run=True)
    [alert_file] = list(config.alerts_dir.glob("*.json"))
    alert = json.loads(alert_file.read_text(encoding="utf-8"))
    assert alert["email"]["subject"] == "[site-watch] Change detected: Planning notices"
    assert "Lines added: 1, lines removed: 0" in alert["email"]["body"]
    hook = alert["webhook"]
    assert hook["watch"] == "Planning notices"
    assert hook["url"].endswith("/planning")
    assert hook["added"] == 1 and hook["removed"] == 0
    assert "+PA/0421" in hook["diff"]
    assert not Path(hook["evidence"]).is_absolute()


def test_report_links_images_by_relative_path(tmp_path, server, site):
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#prices"}])
    run_checks(config, dry_run=True)
    site.advance()
    site.advance()
    run_checks(config, dry_run=True)
    out = tmp_path / "report" / "report.html"
    assert build_report(config, out) == 1
    page = out.read_text(encoding="utf-8")
    assert 'src="images/0002-before.png"' in page and 'class="add"' in page
    assert (out.parent / "images" / "0002-after.png").exists()
    assert str(tmp_path) not in page


# --- Fault fixes from the independent check -------------------------------


def test_bad_selector_does_not_stop_other_watches(tmp_path, server):
    config = make_config(
        tmp_path,
        [
            {"name": "Broken", "url": f"{server.base_url}/prices", "selector": "p[["},
            {"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#prices"},
        ],
    )
    broken, good = run_checks(config, dry_run=True)
    assert broken.status == "failed"
    assert good.status == "baseline"
    assert len(events(config, "failed")) == 1


def test_unexpected_error_in_one_watch_is_isolated(tmp_path, server, monkeypatch):
    import site_watch.checker as checker

    real = checker.capture

    def flaky(browser, watch, timeout):
        if watch.name == "First":
            raise RuntimeError("disk full")
        return real(browser, watch, timeout)

    monkeypatch.setattr(checker, "capture", flaky)
    config = make_config(
        tmp_path,
        [
            {"name": "First", "url": f"{server.base_url}/prices"},
            {"name": "Second", "url": f"{server.base_url}/planning"},
        ],
    )
    first, second = run_checks(config, dry_run=True)
    assert first.status == "failed" and "disk full" in first.detail
    assert second.status == "baseline"


def test_very_tall_page_gets_a_capped_screenshot(tmp_path, server):
    from site_watch.fetch import MAX_SCREENSHOT_HEIGHT

    config = make_config(
        tmp_path,
        [{"name": "Tall", "url": f"{server.base_url}/tall"}, {"name": "Prices", "url": f"{server.base_url}/prices"}],
        timeout=30,
    )
    tall, good = run_checks(config, dry_run=True)
    assert tall.status == "baseline"
    assert good.status == "baseline"
    png = (config.data_dir / "snapshots" / "tall.png").read_bytes()
    assert int.from_bytes(png[20:24], "big") == MAX_SCREENSHOT_HEIGHT


def test_content_fetched_after_load_is_read(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Delivery", "url": f"{server.base_url}/delivery"}])
    run_checks(config, dry_run=True)
    store = Store(config.db_path)
    text = store.snapshot("Delivery").text
    store.close()
    assert "North (fictional) 3 working days" in text
    assert "Loading..." not in text


def test_wait_for_catches_content_added_by_a_timer(tmp_path, server):
    url = f"{server.base_url}/timer"
    plain = make_config(tmp_path / "plain", [{"name": "Batch", "url": url, "selector": "#late"}])
    waiting = make_config(tmp_path / "wait", [{"name": "Batch", "url": url, "selector": "#late", "wait_for": "#ready"}])
    run_checks(plain, dry_run=True)
    run_checks(waiting, dry_run=True)
    for config, expected in ((plain, "Loading..."), (waiting, "Batch status: ready")):
        store = Store(config.db_path)
        assert store.snapshot("Batch").text == expected
        store.close()


def test_wait_for_that_never_appears_is_a_failed_check(tmp_path, server):
    config = make_config(
        tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "wait_for": "#never"}], timeout=2
    )
    [result] = run_checks(config, dry_run=True)
    assert result.status == "failed" and "wait_for" in result.detail


class _Hook(BaseHTTPRequestHandler):
    received: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        data = self.rfile.read(int(self.headers["Content-Length"]))
        _Hook.received.append(json.loads(data))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_failed_alert_is_kept_reported_retried_and_sets_exit_code(tmp_path, server, site, monkeypatch):
    from site_watch.cli import main

    port = _free_port()  # nothing listens here yet
    monkeypatch.delenv("SITE_WATCH_SMTP_HOST", raising=False)
    monkeypatch.setenv("SITE_WATCH_WEBHOOK_URL", f"http://127.0.0.1:{port}/hook")
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#prices"}])
    cfg = str(tmp_path / "watches.json")

    assert main(["-c", cfg, "check"]) == 0  # baseline, no alert
    site.advance()
    site.advance()
    assert main(["-c", cfg, "check"]) == 1  # change found, alert could not be sent
    kept = list(config.failed_alerts_dir.glob("*.json"))
    assert len(kept) == 1
    [failure] = events(config, "alert_failed")
    assert failure.detail.startswith("webhook:")
    out = tmp_path / "report" / "report.html"
    build_report(config, out)
    assert "Kept, will be retried on the next check" in out.read_text(encoding="utf-8")

    _Hook.received = []
    hook = HTTPServer(("127.0.0.1", port), _Hook)
    thread = threading.Thread(target=hook.serve_forever, daemon=True)
    thread.start()
    try:
        assert main(["-c", cfg, "check"]) == 0  # no new change; kept alert sent on retry
    finally:
        hook.shutdown()
        hook.server_close()
    assert [a["watch"] for a in _Hook.received] == ["Prices"]
    assert list(config.failed_alerts_dir.glob("*.json")) == []
    build_report(config, out)
    assert "Sent on a later retry" in out.read_text(encoding="utf-8")


def test_ctrl_c_during_a_check_exits_promptly(tmp_path, server):
    config_path = tmp_path / "watches.json"
    config_path.write_text(
        json.dumps({"timeout_seconds": 60, "watches": [{"name": "Slow", "url": f"{server.base_url}/slow"}]}),
        encoding="utf-8",
    )
    windows = sys.platform == "win32"
    proc = subprocess.Popen(
        [sys.executable, "-m", "site_watch", "-c", str(config_path), "check"],
        cwd=Path(__file__).resolve().parents[1],
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        line = proc.stderr.readline()
        if "Slow: checking" in line or not line:
            break
    time.sleep(1.5)  # the page request is now in flight
    proc.send_signal(signal.CTRL_BREAK_EVENT if windows else signal.SIGINT)
    started = time.monotonic()
    try:
        code = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("site-watch did not exit within 10 seconds of Ctrl+C")
    assert code == 130
    assert time.monotonic() - started < 10


@pytest.mark.parametrize(
    "raw",
    [
        {"watches": [{"name": "A", "url": "http://127.0.0.1/", "ignore": "abc"}]},
        {"watches": [{"name": "A", "url": "http://127.0.0.1/", "interval_minutes": "often"}]},
        {"timeout_seconds": "slow", "watches": [{"name": "A", "url": "http://127.0.0.1/"}]},
        {"watches": ["x"]},
        [{"name": "A", "url": "http://127.0.0.1/"}],
    ],
)
def test_bad_config_values_are_config_errors(tmp_path, raw):
    from site_watch.cli import main

    path = tmp_path / "watches.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
    assert main(["-c", str(path), "check"]) == 2


def test_non_latin_names_get_distinct_slugs(tmp_path):
    config = make_config(
        tmp_path, [{"name": "価格", "url": "http://127.0.0.1/a"}, {"name": "料金", "url": "http://127.0.0.1/b"}]
    )
    assert [w.slug for w in config.watches] == ["価格", "料金"]


def test_diff_body_lines_starting_with_double_signs_are_not_headers():
    from site_watch.report import _diff_html

    page = _diff_html("--- before\n+++ after\n@@ -1 +1 @@\n--old\n++new")
    assert '<span class="del">--old</span>' in page
    assert '<span class="add">++new</span>' in page


def _kept_alert_setup(tmp_path, server, site, monkeypatch, email_log):
    """Email works (recorded, not really sent); the webhook points at a closed port."""
    import site_watch.alerts as alerts

    monkeypatch.setenv("SITE_WATCH_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SITE_WATCH_EMAIL_TO", "someone@example.com")
    monkeypatch.setenv("SITE_WATCH_WEBHOOK_URL", f"http://127.0.0.1:{_free_port()}/hook")
    monkeypatch.setattr(alerts, "send_email", lambda alert, root: email_log.append(alert.watch))
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices", "selector": "#prices"}])
    return config, str(tmp_path / "watches.json")


def test_retry_only_resends_on_the_channel_that_failed(tmp_path, server, site, monkeypatch):
    from site_watch.cli import main

    emails: list[str] = []
    config, cfg = _kept_alert_setup(tmp_path, server, site, monkeypatch, emails)
    main(["-c", cfg, "check"])
    site.advance()
    site.advance()
    main(["-c", cfg, "check"])  # email sent, webhook failed
    for _ in range(3):
        main(["-c", cfg, "check"])  # webhook still down
    assert emails == ["Prices"]
    [kept] = config.failed_alerts_dir.glob("*.json")
    assert json.loads(kept.read_text(encoding="utf-8"))["pending"] == ["webhook"]


def test_exit_code_stays_1_while_a_kept_alert_is_unsent(tmp_path, server, site, monkeypatch):
    from site_watch.cli import main

    config, cfg = _kept_alert_setup(tmp_path, server, site, monkeypatch, [])
    assert main(["-c", cfg, "check"]) == 0
    site.advance()
    site.advance()
    assert main(["-c", cfg, "check"]) == 1
    assert main(["-c", cfg, "check"]) == 1  # nothing new, but the alert is still waiting


def test_damaged_kept_alert_does_not_block_checks(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Prices", "url": f"{server.base_url}/prices"}])
    config.failed_alerts_dir.mkdir(parents=True)
    (config.failed_alerts_dir / "broken.json").write_text("{not json", encoding="utf-8")
    [result] = run_checks(config, dry_run=False)
    assert result.status == "baseline"
    assert (config.failed_alerts_dir / "broken.damaged").exists()


def test_very_long_watch_name_works(tmp_path, server):
    config = make_config(tmp_path, [{"name": "Price list " * 30, "url": f"{server.base_url}/prices"}])
    assert len(config.watches[0].slug) <= 60
    [result] = run_checks(config, dry_run=True)
    assert result.status == "baseline"
