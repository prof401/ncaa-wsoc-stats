# NCAA Women's Soccer Stats Scraper

A Python scraper for NCAA Women's Soccer data from [stats.ncaa.org](https://stats.ncaa.org), capturing teams and contest histories from 2019 onward.

## Features

- **Initial discovery:** Fetches team IDs from the National Rankings page for any season and division
- **Robust requests:** Uses minimal headers (User-Agent, Referer) to avoid HTTP 406/403 errors
- **Season-agnostic:** No hardcoded ranking periods—extracts the correct URL from the NCAA site
- **Rate limiting:** Built-in delay between requests to reduce blocking risk

## Requirements

- Python 3.10+
- `requests`, `beautifulsoup4`, `pandas`

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

```bash
# Fetch D1 team IDs for 2024 season (default)
python ncaa_scraper.py

# Specify season and division
python ncaa_scraper.py --season 2023 --division 2

# Dry run (print URL only, no fetch)
python ncaa_scraper.py --season 2024 --dry-run
```

### Options

| Option | Default | Description |
|--------|---------|--------------|
| `--season` | 2024 | Season year (e.g., 2024 for 2024-25) |
| `--division` | 1 | NCAA division (1, 2, or 3) |
| `--dry-run` | — | Print URL only, do not fetch |

## Project Structure

```
├── ncaa_scraper.py    # Main scraper script
├── requirements.txt   # Python dependencies
├── requirements.md   # Functional requirements
├── architecture.md    # System design and data schemas
└── README.md
```

## Data Flow (Planned)

1. **Seed:** Fetch team IDs from National Rankings (`change_sport_year_div` → `national_ranking`)
2. **Team pages:** Visit each team to extract metadata (name, coach, conference) and schedule
3. **Discovery:** Add opponent teams found in schedules to the crawl queue
4. **Output:** Write `teams.csv` and `contests.csv`

See [architecture.md](architecture.md) for full schemas and workflow.

## Technical Notes

- Uses `change_sport_year_div` as the entry point (no `ranking_period` parameter)
- Session-based requests with an initial visit to establish cookies
- Winning Percentage (stat_seq=60) used as the seed ranking stat

## License

MIT
