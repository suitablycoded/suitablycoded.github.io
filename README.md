# Sample projects

Three finished sample projects, each with tests, a README and a demo you can run. The site in this repository (`index.html` and `projects/`) presents them, and is served as-is by GitHub Pages.

All names, companies, addresses and figures in the sample data are fictional.

## The projects

### [Route scheduler](route-scheduler/)

A browser app for a servicing firm that books a day of jobs by hand. It assigns jobs to technicians with the right skills, respects time windows, working hours and lunch, and orders each route within every rule. It compares the result with a manual plan, shows routes on a map and a timeline, lets the planner drag jobs between technicians, and imports and exports CSV. Built with HTML, CSS, JavaScript and SVG, with no server.

### [Site watch](site-watch/)

A command-line tool that checks web pages on a schedule and alerts on real changes. It loads pages in a headless browser, compares only the part of the page you choose, ignores noise such as timestamps, and keeps before and after text, a diff and screenshots for every change in an HTML evidence report. Built with Python, Playwright and SQLite.

### [Contact cleaner](contact-cleaner/)

A command-line tool that turns a messy contact spreadsheet into a file a CRM will accept. It fixes names, emails, UK phone numbers, dates and postcodes, merges exact duplicates, flags likely ones for a person to decide, sets aside rows with no way to contact anyone, and writes a report counting every change. Built with Python and openpyxl.

## Building the site

The pages and this README are generated from `site.json` and each project's `showcase.json` and README. The generated files are committed, so the host needs no build step.

```
python build_site.py
```

This needs Python 3.11 or later and nothing else. Running it twice gives identical output.

`site.json` holds the owner name, tagline, contact link and repository link. A link left empty is left off the pages.

To preview locally, serve the repository root:

```
python -m http.server 8000
```

Then open `http://localhost:8000/`.

Maintained by Suitably Coded.
