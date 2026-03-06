# Project Requirements: NCAA Women's Soccer Data Scraper

## Overview
The goal is to build a robust scraper to retrieve and store NCAA Women's Soccer data from 2019-present, specifically capturing teams and their contest histories.

## Data Sources
- **Primary Seed:** `https://stats.ncaa.org/rankings/change_sport_year_div` (entry point, no ranking_period) followed by `https://stats.ncaa.org/rankings/national_ranking` (stat_seq=60 for Winning Percentage). The ranking_period is extracted from the change_sport_year_div page.
- **Secondary Source:** `https://stats.ncaa.org/teams/<team_id>` for metadata and schedules.

## Functional Requirements
1. **Initial Discovery:**
   - Scrape the National Rankings page for a specific `academic_year` and `division` to populate the initial "Known Teams" list.
2. **Team Metadata Extraction:**
   - For each Team ID, visit their specific team page.
   - Extract: Name, Coach, Season, and Conference.
3. **Contest Extraction & Discovery:**
   - Scrape the "Schedule/Results" table on the team page.
   - Extract: Contest ID, Date, Opponent Name, Opponent Team ID, Result (Score), and Attendance.
   - **Discovery Logic:** If an Opponent Team ID is found that does not exist in the "Known Teams" list (re-classifying programs), add it to a discovery queue to be scraped immediately.
4. **Data Persistence:**
   - Save data locally as CSV files.
   - Ensure the scraper can be restarted without duplicating rows (check if Team ID exists before writing).

## Technical Constraints
- **Language:** Python 3.10+.
- **Libraries:** `requests`, `BeautifulSoup4`, `pandas`.
- **Resilience:** Must include custom headers (User-Agent) to avoid HTTP 406/403 errors.
- **Rate Limiting:** Implement a `time.sleep()` between requests to prevent IP blocking.
