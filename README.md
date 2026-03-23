# NCAA Women's Soccer Stats Scraper

A Python scraper for NCAA Women's Soccer data from [stats.ncaa.org](https://stats.ncaa.org), capturing teams and contest histories from 2019 onward.

## Features

- **Initial discovery:** Fetches team IDs from the National Rankings page for any season and division
- **Team metadata:** Extracts name, coach, overall record from each team page
- **Contest extraction:** Scrapes Schedule/Results table (date, opponent, result, attendance)
- **Discovery queue:** Automatically adds opponent teams found in schedules
- **Robust requests:** Uses minimal headers (User-Agent, Referer) to avoid HTTP 406/403 errors
- **Season-agnostic:** No hardcoded ranking periods—extracts the correct URL from the NCAA site
- **Rate limiting:** Built-in delay between requests to reduce blocking risk
- **Box score Scoring Summary:** Separate `contest` command writes per-goal rows (period, clock, teams, play text, score after goal) to `scoring_summary.csv`

## Requirements

- Python 3.10+
- `requests`, `beautifulsoup4`, `pandas`, `curl_cffi`

## Setup

```bash
# Clone the repository (or use existing project)
# Replace 'owner' with the GitHub username or org that hosts the repo
git clone https://github.com/owner/ncaa-wsoc-stats.git
cd ncaa-wsoc-stats

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Team crawl (seed, schedules, contests list)

The same flags work as before **without** a subcommand, or use the explicit `teams` subcommand:

```bash
# Full scrape: seed + team pages + contests (2024 D3 default)
python main.py

# Explicit subcommand (equivalent)
python main.py teams --season 2024 --division 3

# Specify season and division
python main.py --season 2023 --division 2

# Dry run (print URL only, no fetch)
python main.py --season 2024 --dry-run

# Test with limited teams
python main.py --limit 3
```

### Contest box score (Scoring Summary)

Fetches each contest’s box score page and writes one row per goal to `scoring_summary.csv` (game metadata repeated on each row).

- **`--contest-id` only:** scrapes just those IDs (does **not** load `contests_raw.csv`).
- **Neither flag:** loads `<output-dir>/contests_raw.csv` (bulk).
- **`--from-csv`:** loads that file; add `--contest-id` to merge extra IDs into the same run.

```bash
# One contest only
python main.py contest --contest-id 1739490

# Bulk: all contest IDs from ./contests_raw.csv (no --contest-id)
python main.py contest --output-dir .

# Merge file + explicit IDs
python main.py contest --from-csv contests_raw.csv --contest-id 1739490

# Re-scrape contests already present in scoring_summary.csv
python main.py contest --from-csv contests_raw.csv --no-skip-existing

# Limit for testing (applies after ID list is built)
python main.py contest --from-csv contests_raw.csv --limit 5
```

### Team crawl options

| Option | Default | Description |
|--------|---------|--------------|
| `--season` | 2024 | Season year (e.g., 2024 for 2024-25) |
| `--division` | 3 | NCAA division (1, 2, or 3) |
| `--dry-run` | — | Print URL only, do not fetch |
| `--output-dir` | . | Directory for teams.csv and contests.csv |
| `--delay` | 1.0 | Seconds between requests |
| `--limit` | — | Max teams to process (for testing) |

### Contest box score options

| Option | Default | Description |
|--------|---------|--------------|
| `--contest-id` | — | Contest ID (repeat for multiple). If used alone, **only** these IDs—no auto CSV. |
| `--from-csv` | — | CSV with `contest_id`. Omit both this and `--contest-id` to use `<output-dir>/contests_raw.csv` |
| `--output-dir` | . | Directory for `scoring_summary.csv` |
| `--scoring-csv` | scoring_summary.csv | Output filename |
| `--delay` | 1.0 | Seconds between requests |
| `--limit` | — | Max contests to process (for testing) |
| `--skip-existing` | on | Skip `--no-skip-existing` to re-fetch all IDs in the list |

## Project Structure

```
├── main.py            # Entry point
├── ncaa_wsoc/         # Package
│   ├── http.py        # Session, fetch_stats_page (Akamai interstitial)
│   ├── rankings.py   # SeedProcessor
│   ├── team.py       # TeamProcessor
│   ├── contest.py    # Box score / Scoring Summary parsing
│   ├── discovery.py  # DiscoveryManager
│   ├── storage.py    # CSV persistence
│   └── cli.py        # CLI orchestration
├── tests/             # Unit tests (e.g. contest parsing fixtures)
├── ncaa_scraper.py   # Legacy (rankings-only)
├── requirements.txt   # Python dependencies
├── requirements.md   # Functional requirements
├── architecture.md    # System design and data schemas
└── README.md
```

## Data Flow

1. **Seed:** Fetch team IDs from National Rankings (`change_sport_year_div` → `national_ranking`)
2. **Team pages:** Visit each team to extract metadata (name, coach, overall record) and schedule
3. **Discovery:** Add opponent teams found in schedules to the crawl queue
4. **Output:** Write `teams.csv` and `contests.csv`

See [architecture.md](architecture.md) for full schemas and workflow.

Run tests from the project root:

```bash
python -m unittest discover -s tests -v
```

## Technical Notes

- Uses `change_sport_year_div` as the entry point (no `ranking_period` parameter)
- Session-based requests with an initial visit to establish cookies
- Winning Percentage (stat_seq=60) used as the seed ranking stat

## Pushing to GitHub

Create a new repository on GitHub, then:

```bash
git init
git add .
git commit -m "Initial commit: NCAA WSOC scraper"
git branch -M main
git remote add origin https://github.com/owner/ncaa-wsoc-stats.git  # use your repo URL
git push -u origin main
```

## License

MIT
