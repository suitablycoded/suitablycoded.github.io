# Route scheduler

A small web app that assigns a day of service jobs to field technicians and puts each technician's visits in a sensible order.

It is built for a firm that services fire and security systems. Today the office books jobs by dragging each one onto a calendar by hand. This app does the first draft of the day automatically, then lets the planner adjust it.

All companies, people and jobs in it are fictional. The places are real villages around Harrogate, and the map is from OpenStreetMap (© OpenStreetMap contributors); distances are straight-line estimates, not road distances.

## What it does

- Loads a sample day: 40 jobs and 6 technicians, the same every time.
- Draws a real map of the Harrogate area with each job as a pin and each technician's route as a coloured line.
- Shows a timeline with one row per technician: travel, jobs, lunch and hours off shift.
- Shows a manual plan first, so you can compare before and after.
- Auto-schedule builds a full plan in well under a second and shows the time taken.
- Shows totals that update at once: travel time, distance, jobs done, jobs late, jobs unassigned and rule breaks, each next to the manual plan figure.
- Lists jobs that cannot be placed, with a reason that says only what was checked.
- Lets you drag a job to another technician or to a new place in a row. You can also select a job and use buttons to move it, and the keyboard focus stays on that job. Any rule the move breaks is flagged, not fixed for you.
- Add, edit and remove jobs with a form. Reset to the sample day at any time.
- Imports jobs from CSV. Exports the schedule, and exports the job list in a form that can be imported again.
- Saves your work in the browser. If the browser blocks storage, the app still works for that visit. If saved data is damaged, it is cleared and the sample day is loaded, with a notice.
- Works on a phone-width screen and follows the device's light or dark setting.

## Results on the sample day

| Measure | Manual plan | Auto-schedule |
| --- | --- | --- |
| Total travel | 592.5 min | 364.9 min |
| Total distance | 296.3 km | 182.4 km |
| Jobs done | 31 | 38 |
| Jobs late | 12 | 0 |
| Jobs unassigned | 1 | 2 |
| Rule breaks | 21 | 0 |

The main gain is that no job is late and no rule is broken, with more jobs fitted in. The travel gain is real but smaller against a careful dispatcher.

The manual plan shows only 1 unassigned job because it puts every job somewhere, even where that breaks a rule. Auto-schedule leaves a job out rather than break a rule. The two it leaves out cannot be done by anyone: J039 needs a skill nobody has, and J040 cannot be reached by 08:00 for a one-hour visit.

## How the scheduling works

First the app sorts the jobs so that urgent jobs, and jobs with a narrow time window, are placed first. It tries each job in every possible place in every route of a technician with the right skill, and keeps the place that adds the least travel without breaking a rule.

Then it improves the plan. It reverses a stretch of a route, moves a run of one to three jobs to another place or another technician, and swaps two jobs between technicians. A change is kept only if it breaks no rule and cuts travel. For each job still left over, it tries taking out one placed job, putting the left-over job in, and finding the removed job a new place.

Last, it runs 3,000 rounds of "remove and rebuild". Each round takes out a few jobs, either near each other or picked at random, and puts them back with any left-over jobs in a shuffled order. A round that places more jobs, or travels less, is kept. Early on it may also keep a slightly worse plan, so it can climb out of a dead end, but it always remembers the best plan seen. When not every job fits, High jobs come before any Normal job and Normal before any Low, so a High job is never left out to make room for lower-priority ones. Between plans that place the same jobs, it prefers fewest rule breaks, then least travel.

The shuffling uses a fixed seed, so the same jobs always give the same plan on any device. Lists of more than 100 jobs also have a time limit of 0.7 seconds; for those the result may vary a little with the speed of the machine.

A job left over gets a reason that reflects what was checked: nobody has the skill; the window is shorter than the visit; even an empty day cannot reach it in time; or it fits nowhere, even after trying to move any one other job out of the way or to take out a lower-priority job.

## Rules and assumptions

- Travel time is the straight-line distance times a road factor of 1.3, at an average speed of 30 km/h. Both values are set in `js/model.js` and shown on screen.
- A job can start once its window opens and must finish before the window closes. Arriving early means waiting.
- Each technician starts at their depot at the start of their hours and must be back by the end.
- Lunch is a fixed 30-minute break for each technician. No travel or work runs across it.
- A job needs a technician with the matching skill.
- The manual plan gives each job to the technician whose depot is nearest and who has the skill. Technicians who share a depot take turns. Each technician visits their jobs in time-window order. Nothing checks for clashes or hours.
- "Jobs done" counts visits by a technician with the right skill that finish within working hours. Late visits count as done and also as late.
- Routes of different technicians can cross on the map because jobs need particular skills.

## Run it

It is plain HTML, CSS and JavaScript with no build step. Browsers do not load JavaScript modules from a file opened directly, so serve the folder with any static file server, for example:

```
python -m http.server 8000
```

Then open `http://localhost:8000/index.html`.

## Run the tests

The scheduling and CSV code has no screen code in it and is tested with the test runner built into Node.js (version 20 or later). Nothing needs installing.

```
node --test
```

The 31 tests cover: the sample day is repeatable, travel time sums, skills, time windows, working hours and lunch, no job assigned twice, rule breaks flagged after a move, the improver never adds travel, the sample day reaches at least 38 placed with nothing late and travel at or below 370 minutes, other seeded days never do worse than insertion alone, a High job is never dropped for Low ones, duplicate ids are refused, the manual plan rule, reasons for unassigned jobs are true, CSV import errors by line number, unclosed quotes, semicolon and tab files, header-only files, formula-safe export, CSV round trips and damaged saved data.

## CSV format

### Jobs (import)

One header row, then one job per row. `sample-jobs.csv` is a working example.

| Column | Meaning |
| --- | --- |
| id | Job reference, letters, digits, - or _ |
| customer | Customer or site name |
| area | Optional. Filled from the nearest map area if blank |
| x_km, y_km | Position on the map in km from its top-left corner, 0 to 20 and 0 to 14 |
| duration_min | Time on site in minutes, 5 to 480, no longer than the window |
| window_start, window_end | Times such as 08:00 and 12:30 |
| skill | Fire alarm, Intruder alarm, CCTV, Extinguishers, Emergency lighting or Access control |
| priority | 1, 2 or 3, or High, Normal or Low |

Fields with commas or quotes can be wrapped in double quotes. Ids are matched ignoring capitals. Importing replaces the current jobs and shows the manual plan. Every row that cannot be used is reported with its line number and the problem. Good rows are still imported. A quote that is never closed is reported at the line where it starts. A file separated by semicolons is reported as such.

"Export jobs" writes this same format, so it can be imported again.

### Schedule (export)

One row per visit: `technician, order, job, customer, arrive, start, finish, travel_min, notes`. Notes list any broken rule. Unassigned jobs follow at the end with a blank technician and the note "unassigned". The schedule file is for reading, not for importing.

In both exports, text that a spreadsheet would treat as a formula (starting with =, +, - or @) gets a leading apostrophe. The import removes it again.

## Files

- `index.html`, `styles.css`: the page.
- `js/model.js`: sample data, settings and job checks.
- `js/scheduler.js`: route timing, totals, the manual plan and auto-schedule.
- `js/csv.js`: CSV reading and writing.
- `js/storage.js`: saving in the browser.
- `js/app.js`: the screen.
- `tests/`: the tests.

## Limits

- No road routing or traffic. Distances are straight lines times a fixed factor; the map is a background, and its roads and rivers do not affect travel.
- One day at a time. No multi-day jobs, follow-up visits or parts stock.
- Technicians and their hours are fixed sample data. They can only be changed in the code.
- Lunch is a fixed slot, not a flexible break.
- The method finds a good plan quickly. It does not prove the plan is the best possible.
- It is sized for tens of jobs. With hundreds of jobs and 6 technicians most cannot fit into one day; how many fit depends on the list, and the status line gives the real count and the reasons. Hundreds of jobs would need more technicians and a faster method.
- There is no login, server or shared data. Each browser keeps its own copy.

## Built with

HTML, CSS, JavaScript (ES modules), SVG, the Node.js test runner, Python (local static server) and Playwright (browser checks).
