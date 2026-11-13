"""Build the showcase pages from site.json and each project's showcase.json.

Standard library only. Run from anywhere:  python build_site.py
Writes index.html and projects/<slug>.html. Output is deterministic.
"""
import json
import re
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FIGURE_LABELS = {
    "rows_in": "rows in the messy file",
    "clean_contacts": "clean contacts out",
    "rejected": "rows set aside with a reason",
    "merged_duplicates": "exact duplicates merged",
    "kept_rows_flagged_for_review": "kept rows flagged for a person to check",
    "individual_changes": "individual changes, each one counted",
}

HOW_A_JOB_RUNS = [
    ("A working demo first, where the job allows",
     "For most small jobs you see a short working demo of your own task with the proposal, before you commit. If it needs your private data or systems, you get a clear plan and a sample instead."),
    ("Fixed price", "The price is fixed and agreed up front where the job allows it."),
    ("Tests, README and source",
     "Every delivery comes with tests, a plain-English README and the source code."),
    ("You own the code", "The code is yours."),
]


def e(text):
    return escape(str(text), quote=True)


def load():
    site = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
    projects = []
    for entry in site["projects"]:
        folder = entry["folder"]
        show = json.loads((ROOT / folder / "showcase.json").read_text(encoding="utf-8"))
        limits = read_limits(ROOT / folder / "README.md")
        results = read_results(ROOT / folder / "README.md")
        run = show["run"] if isinstance(show["run"], list) else [show["run"]]
        projects.append({**entry, "show": show, "limits": limits, "results": results, "run": run})
    return site, projects


def read_limits(readme):
    lines = readme.read_text(encoding="utf-8").splitlines()
    out, inside = [], False
    for line in lines:
        if line.strip().lower() == "## limits":
            inside = True
            continue
        if inside and line.startswith("## "):
            break
        if inside and line.startswith("- "):
            out.append(line[2:].strip())
    return out


def read_results(readme):
    """The before-and-after table in a README: header row starts with '| Measure |'."""
    rows, inside = [], False
    for line in readme.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Measure |"):
            inside = True
        if inside:
            if not line.startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):
                rows.append(cells)
    return rows


def card_tools(tools):
    """Tools for a card: drop bracket notes, and tools only used for an aside."""
    out = []
    for t in tools:
        if "(" in t and "only" in t.split("(", 1)[1]:
            continue
        name = t.split("(", 1)[0].strip()
        if name not in out:
            out.append(name)
    return out


def inline_code(text):
    """Escape text and turn `code` spans into <code> elements."""
    parts = str(text).split("`")
    return "".join(f"<code>{e(p)}</code>" if i % 2 else e(p) for i, p in enumerate(parts))


def page(title, description, body, prefix, site):
    contact = ""
    if site.get("contact_url"):
        contact = (f'<a class="btn btn-primary" href="{e(site["contact_url"])}">'
                   f'{e(site.get("contact_label") or "Contact")}</a>')
    repo = ""
    if site.get("repo_url"):
        repo = f'<a href="{e(site["repo_url"])}">Source code</a>'
    nav_links = "".join(x for x in (repo, contact) if x)
    return f"""<!doctype html>
<html lang="en-GB" data-skin="glass" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<meta name="color-scheme" content="dark">
<link rel="stylesheet" href="{prefix}assets/theme-glass.css">
<link rel="stylesheet" href="{prefix}assets/site.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top">
<div class="wrap top-inner">
<a class="brand" href="{prefix}index.html">{e(site["owner_name"])}</a>
<nav aria-label="Main"><a href="{prefix}index.html#work">Work</a><a href="{prefix}index.html#how">How a job runs</a>{nav_links}</nav>
</div>
</header>
<main id="main">
{body}
</main>
<footer class="foot">
<div class="wrap">
<p>All names, companies, addresses and figures in these samples are fictional.</p>
<p>{e(site["owner_name"])}</p>
</div>
</footer>
<script src="{prefix}assets/touches.js" defer></script>
</body>
</html>
"""


def card_img(p):
    return (f'<img src="assets/img/{p["folder"]}-card.jpg" width="640" height="400" '
            f'alt="{e(p["card_alt"])}" loading="lazy">')


def figure(p, i, up, sizes="(min-width: 1000px) 920px, 100vw"):
    slug = p["folder"]
    full = f"{up}{slug}/{p['show']['screenshots'][i]}"
    alt = p["alt"][i] if i < len(p.get("alt", [])) else ""
    sm, lg = f"{up}assets/img/{slug}-{i + 1}-sm.jpg", f"{up}assets/img/{slug}-{i + 1}.jpg"
    return f"""<figure class="shot">
<a href="{e(full)}"><img src="{lg}" srcset="{sm} 640w, {lg} 1200w" sizes="{sizes}" alt="{e(alt)}" loading="lazy"></a>
<figcaption>{e(alt)} <a href="{e(full)}">Full size</a></figcaption>
</figure>"""


def build_home(site, projects):
    cards = []
    for p in projects:
        s = p["show"]
        tools = "".join(f"<li>{e(t)}</li>" for t in card_tools(s["tools"]))
        demo = f'{p["folder"]}/{s["demo_path"]}'
        cards.append(f"""<article class="card">
<div class="card-shot">{card_img(p)}</div>
<div class="card-body">
<p class="kind">{e(p['kind'])}</p>
<h3><a href="projects/{p['folder']}.html">{e(p['short_title'])}</a></h3>
<p>{e(s['one_line'])}</p>
<ul class="tools" aria-label="Tools used">{tools}</ul>
<p class="actions"><a class="btn btn-primary" href="{e(demo)}">{e(p['action'])}</a><a class="btn" href="projects/{p['folder']}.html">How it works</a></p>
</div>
</article>""")
    steps = "".join(f"<li><h3>{e(h)}</h3><p>{e(t)}</p></li>" for h, t in HOW_A_JOB_RUNS)
    contact = ""
    if site.get("contact_url"):
        contact = (f'<p class="actions"><a class="btn btn-primary" href="{e(site["contact_url"])}">'
                   f'{e(site.get("contact_label") or "Contact")}</a></p>')
    repo = ""
    if site.get("repo_url"):
        repo = f'<p>The full source for all three projects is in the <a href="{e(site["repo_url"])}">source repository</a>.</p>'
    body = f"""<section class="hero hero-3d">
<canvas id="hero-3d" aria-hidden="true"></canvas>
<div class="wrap">
<p class="eyebrow">Freelance software</p>
<h1>{e(site['tagline'])}</h1>
<p class="lede">Below are three finished sample projects. Each one runs. Open the demo, read the output, then see how it is built and run.</p>
{contact}
</div>
</section>
<section id="work" class="wrap section" aria-labelledby="work-h">
<h2 id="work-h">Three sample projects</h2>
<div class="cards">
{chr(10).join(cards)}
</div>
</section>
<section id="how" class="band" aria-labelledby="how-h">
<div class="wrap section">
<h2 id="how-h">How a job runs</h2>
<ol class="steps">{steps}</ol>
{repo}
{contact}
</div>
</section>
<script type="module" src="assets/hero3d.js"></script>"""
    return page(f"{site['owner_name']}: sample projects", site["tagline"], body, "", site)


MAP_CREDIT = ('<p class="map-credit">Map of Harrogate: © <a href="https://www.openstreetmap.org/copyright">'
              'OpenStreetMap contributors</a>. Routes planned with OSRM.</p>')


def build_project(site, p):
    s = p["show"]
    slug = p["folder"]
    up = "../"
    demo = f'{up}{slug}/{s["demo_path"]}'
    is_app = s["demo_path"].endswith("index.html")
    bullets = "".join(f"<li>{e(b)}</li>" for b in s["what_it_does"])
    tools = "".join(f"<li>{e(t)}</li>" for t in s["tools"])
    limits = "".join(f"<li>{inline_code(l)}</li>" for l in p["limits"])
    compare = ""
    shown = set()
    if p.get("results"):
        head, *rows = p["results"]
        th = "".join(f'<th scope="col">{e(h)}</th>' for h in head)
        trs = "".join("<tr>" + f'<th scope="row">{e(r[0])}</th>' + "".join(f"<td>{e(c)}</td>" for c in r[1:]) + "</tr>"
                      for r in rows)
        compare = f"""<p>{e(p.get("compare_note", ""))}</p>
<div class="pair">
{figure(p, 0, up, "(min-width: 900px) 460px, 100vw")}
{figure(p, 1, up, "(min-width: 900px) 460px, 100vw")}
</div>
<div class="table-wrap"><table class="results"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>"""
        shown = {0, 1}
    shots = [figure(p, i, up) for i in range(len(s["screenshots"])) if i not in shown]
    run_blocks = []
    for cmd in p["run"]:
        if cmd.startswith("Open "):
            run_blocks.append(f"<p>{inline_code(cmd)}</p>")
        else:
            run_blocks.append(f"<pre><code>{e(cmd)}</code></pre>")
    figures = ""
    if s.get("figures"):
        rows = "".join(
            f'<div><dt>{e(FIGURE_LABELS.get(k, k.replace("_", " ")))}</dt><dd>{e(v)}</dd></div>'
            for k, v in s["figures"].items())
        figures = f'<dl class="figures">{rows}</dl>'
    extra = ""
    if p.get("extra_links"):
        items = "".join(f'<li><a href="{e(up + slug + "/" + x["path"])}">{e(x["label"])}</a></li>'
                        for x in p["extra_links"])
        extra = f'<p>Compare the two files yourself:</p><ul class="filelinks">{items}</ul>'
    note = f'<p class="demo-note">{e(p["demo_note"])}</p>' if p.get("demo_note") else ""
    if is_app:
        demo_block = f"""<p>This is the working app, not a recording. It runs entirely in your browser with sample data.</p>
<p class="actions"><a class="btn btn-primary" href="{e(demo)}">Open the app full screen</a></p>
{note}
<div class="embed"><iframe src="{e(demo)}" title="{e(p['short_title'])}, live demo" loading="lazy"></iframe></div>
<script src="{up}assets/embed.js" defer></script>"""
    else:
        demo_block = f"""<p>This is the real report the tool produced from the sample run.</p>
{note}
<p class="actions"><a class="btn btn-primary" href="{e(demo)}">Open the sample report</a></p>
{extra}"""
    branch = site.get("repo_branch") or "main"
    repo = site.get("repo_url", "").rstrip("/")
    source = ""
    if repo:
        source = f'<p><a class="btn" href="{e(f"{repo}/tree/{branch}/{slug}")}">View the source for this project</a></p>'
        readme = f'<p>Full instructions are in the project&#8217;s <a href="{e(f"{repo}/blob/{branch}/{slug}/README.md")}">README</a>.</p>'
    else:
        readme = f"<p>Full instructions are in the <code>README.md</code> file in the project's <code>{e(slug)}</code> folder.</p>"
    shot_note = f'<p class="demo-note">{e(p["shots_note"])}</p>' if p.get("shots_note") else ""
    sections = [
        ("The problem", f'<blockquote class="problem"><p>{e(s["problem"])}</p></blockquote>'),
        ("What it does", f'<ul class="ticks">{bullets}</ul>'),
    ]
    if compare:
        sections.append(("Before and after on the sample day", compare))
    sections.append(("Try it" if is_app else "See the sample output", demo_block))
    if figures:
        sections.append(("The sample run in figures", figures))
    sections += [
        ("More screenshots" if compare else "Screenshots", shot_note + "\n".join(shots)),
        ("How to run it", "\n".join(run_blocks) + "\n" + readme),
        ("Tools used", f'<ul class="tools">{tools}</ul>'),
        ("Honest limits", f'<ul class="limits">{limits}</ul>'),
    ]
    html = []
    for heading, content in sections:
        text = re.sub(r"<[^>]+>", "", content).strip()
        if not text or "<li></li>" in content or content.count("<li>") == 0 and content.startswith("<ul"):
            raise SystemExit(f"Build failed: section '{heading}' on {slug} is empty. Check its showcase.json and README.")
        html.append(f"<h2>{e(heading)}</h2>\n{content}")
    sections_html = "\n".join(html)
    body = f"""<section class="hero hero-3d project-hero" data-scene="{e(slug)}">
<canvas id="hero-3d" aria-hidden="true"></canvas>
<div class="wrap">
<p class="crumb"><a href="{up}index.html#work">All projects</a></p>
<p class="kind">{e(p['kind'])}</p>
<h1>{e(s['title'])}</h1>
<p class="lede">{e(s['one_line'])}</p>
{MAP_CREDIT if slug == "route-scheduler" else ""}
</div>
</section>
<script type="module" src="{up}assets/project3d.js"></script>
<article class="wrap project">
{sections_html}
{source}
<p class="note">All data in this sample is fictional.</p>
</article>"""
    return page(f"{p['short_title']}: {site['owner_name']}", s["one_line"], body, up, site)


def build_readme(site, projects):
    parts = ["# Sample projects", "",
             "Three finished sample projects, each with tests, a README and a demo you can run. "
             "The site in this repository (`index.html` and `projects/`) presents them, and is served as-is by GitHub Pages.",
             "", "All names, companies, addresses and figures in the sample data are fictional.", "", "## The projects", ""]
    for p in projects:
        parts += [f"### [{p['short_title']}]({p['folder']}/)", "", p["readme_summary"], ""]
    parts += ["## Building the site", "",
              "The pages and this README are generated from `site.json` and each project's `showcase.json` and README. "
              "The generated files are committed, so the host needs no build step.", "",
              "```", "python build_site.py", "```", "",
              "This needs Python 3.11 or later and nothing else. Running it twice gives identical output.", "",
              "`site.json` holds the owner name, tagline, contact link and repository link. A link left empty is left off the pages.", "",
              "To preview locally, serve the repository root:", "",
              "```", "python -m http.server 8000", "```", "",
              "Then open `http://localhost:8000/`.", "",
              f"Maintained by {site['owner_name']}.", ""]
    return "\n".join(parts)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def main():
    site, projects = load()
    write(ROOT / "index.html", build_home(site, projects))
    write(ROOT / "README.md", build_readme(site, projects))
    for p in projects:
        write(ROOT / "projects" / f"{p['folder']}.html", build_project(site, p))
    print(f"Built index.html and {len(projects)} project pages.")


if __name__ == "__main__":
    main()
