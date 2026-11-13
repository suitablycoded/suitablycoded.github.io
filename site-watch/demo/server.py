"""A tiny local web server with four fictional pages that change on a seeded schedule.

It also serves three pages used only by the tests: /timer (filled by a timer
after load), /tall (too tall to screenshot) and /slow (never answers in time).

Each call to `advance()` moves the pages one step forward. The content of every
step is fixed by the seed, so a demo run is repeatable. It only listens on
127.0.0.1 and never contacts any other site.
"""

from __future__ import annotations

import json
import random
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRODUCTS = ["Widget bracket, steel", "Hex bolt M8 (box of 100)", "Rubber grommet 20 mm", "Cable tie 300 mm (pack)"]
NOTICES = [
    ("PA/0412", "Single-storey rear extension, 14 Example Lane, Testville"),
    ("PA/0417", "Change of use from shop to cafe, 3 Sample Street, Testville"),
    ("PA/0421", "Two new dwellings on land behind 8 Demo Road, Testville"),
    ("PA/0430", "Replacement windows, Old Mill House, Mockford"),
]
STOCK = ["In stock", "Low stock", "Out of stock", "Back order"]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:Georgia,serif;margin:40px;max-width:760px;color:#222}}
header{{border-bottom:3px solid {colour};margin-bottom:16px}} h1{{color:{colour};margin:0 0 6px}}
table{{border-collapse:collapse;width:100%}} td,th{{border:1px solid #ccc;padding:6px 10px;text-align:left}}
.note{{color:#666;font-size:13px}} footer{{margin-top:24px;color:#888;font-size:12px}}</style></head>
<body><header><h1>{title}</h1><p class="note">Fictional demo page. Not a real business.</p></header>
<main id="content">{body}</main>
<footer>Page generated {generated}</footer></body></html>"""


class DemoSite:
    def __init__(self, seed: int = 7) -> None:
        self.seed = seed
        self.step = 0

    def advance(self) -> None:
        self.step += 1

    def _clock(self) -> str:
        # Changes on every step: this is the noise the ignore patterns remove.
        return (datetime(2026, 1, 5, 9, 0) + timedelta(minutes=37 * self.step)).strftime("%d %b %Y %H:%M")

    def prices(self) -> str:
        rng = random.Random(self.seed)
        base = [round(rng.uniform(2, 40), 2) for _ in PRODUCTS]
        # From step 2 one price rises; from step 4 another one falls.
        if self.step >= 2:
            base[1] = round(base[1] * 1.12, 2)
        if self.step >= 4:
            base[3] = round(base[3] * 0.9, 2)
        rows = "".join(f"<tr><td>{p}</td><td>&pound;{v:.2f}</td></tr>" for p, v in zip(PRODUCTS, base))
        return PAGE.format(
            title="Acme Example Supplies: trade price list",
            colour="#1f5f8b",
            generated=self._clock(),
            body=f'<p>Prices exclude VAT.</p><table id="prices"><tr><th>Item</th><th>Price</th></tr>{rows}</table>',
        )

    def planning(self) -> str:
        shown = NOTICES[: 2 + min(self.step // 2, 2)]  # a new notice at steps 2 and 4
        items = "".join(f"<li><strong>{ref}</strong>: {text}</li>" for ref, text in shown)
        return PAGE.format(
            title="Testville District Council (fictional): planning notices",
            colour="#3c7a3c",
            generated=self._clock(),
            body=f'<p>Applications received this month.</p><ul id="notices">{items}</ul>',
        )

    def stock(self) -> str:
        rng = random.Random(self.seed * 100 + self.step // 3)  # status moves every third step
        status = rng.choice(STOCK)
        return PAGE.format(
            title="Example Parts Depot: stock status",
            colour="#8b4b1f",
            generated=self._clock(),
            body=(
                f'<div id="status"><p>Model DX-200 demo unit: <strong>{status}</strong></p>'
                f"<p>Last checked: {self._clock()}</p></div>"
            ),
        )


    def delivery_page(self) -> str:
        # The table is empty when the page loads. A script fetches the data
        # afterwards, as many real sites do.
        script = (
            "<script>window.addEventListener('load', () => {"
            "fetch('/delivery-data').then(r => r.json()).then(rows => {"
            "document.getElementById('times').innerHTML = rows.map("
            "r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');"
            "document.getElementById('state').textContent = 'Loaded';});});</script>"
        )
        return PAGE.format(
            title="Example Freight Co: delivery lead times",
            colour="#5b3c8b",
            generated=self._clock(),
            body=(
                '<p id="state">Loading...</p><table><tr><th>Region</th><th>Lead time</th></tr>'
                f'<tbody id="times"></tbody></table>{script}'
            ),
        )

    def delivery_data(self) -> list[list[str]]:
        north = "3 working days" if self.step < 3 else "5 working days"
        return [["North (fictional)", north], ["South (fictional)", "2 working days"], ["Islands (fictional)", "7 working days"]]

    def timer_page(self) -> str:
        # Filled in by a timer 1.5 s after load, with no network request.
        # Only a watch with `wait_for` sees this content.
        script = (
            "<script>window.addEventListener('load', () => setTimeout(() => {"
            "document.getElementById('late').innerHTML = '<p id=\"ready\">Batch status: ready</p>';"
            "}, 1500));</script>"
        )
        return PAGE.format(
            title="Example batch status", colour="#555", generated=self._clock(),
            body=f'<div id="late"><p>Loading...</p></div>{script}',
        )

    def tall_page(self) -> str:
        # Too tall for Chromium to screenshot in one image.
        return PAGE.format(
            title="Very long page", colour="#555", generated=self._clock(),
            body='<div style="height:1300000px">tall</div>',
        )


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False  # do not wait for a deliberately slow request on shutdown


class DemoServer:
    """Runs a DemoSite on 127.0.0.1 in a background thread."""

    def __init__(self, site: DemoSite, port: int = 0) -> None:
        site_ref = site

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (name set by http.server)
                pages = {
                    "/prices": site_ref.prices,
                    "/planning": site_ref.planning,
                    "/stock": site_ref.stock,
                    "/delivery": site_ref.delivery_page,
                    "/timer": site_ref.timer_page,
                    "/tall": site_ref.tall_page,
                }
                content_type = "text/html; charset=utf-8"
                if self.path == "/slow":
                    threading.Event().wait(30)
                    text = "<p>slow</p>"
                elif self.path == "/delivery-data":
                    threading.Event().wait(1.0)  # a slow data request after load
                    text = json.dumps(site_ref.delivery_data())
                    content_type = "application/json"
                elif self.path in pages:
                    text = pages[self.path]()
                else:
                    self.send_error(404, "Not found")
                    return
                body = text.encode("utf-8")
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # the browser gave up and closed the connection

            def log_message(self, *args: object) -> None:
                pass

        self.httpd = _Server(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self) -> DemoServer:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
