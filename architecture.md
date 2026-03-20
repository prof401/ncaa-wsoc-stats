# System Architecture

## Data Flow
1. **Input:** Year and Division (e.g., 2024, D1).
2. **Crawler:** - `SeedProcessor`: Fetches IDs from the National Rankings page.
   - `TeamProcessor`: Visits each Team ID to pull metadata and the schedule table.
   - `DiscoveryManager`: A queue that tracks Team IDs found in schedules that weren't in the seed list.
3. **Output:** - `teams.csv`
   - `contests.csv`

## CSV Schemas

### Table 1: `teams.csv`
| Column | Description |
| :--- | :--- |
| `team_id` | The NCAA unique identifier for that specific season. |
| `name` | The school name. |
| `season` | The academic year (e.g., 2023-24). |
| `division` | NCAA Division (1, 2, or 3). |
| `coach` | Head coach name. |
| `overall_record` | Team overall W-L(-D) record for that season. |

### Table 2: `contests.csv`

Canceled games (any schedule row whose cells indicate a cancellation) are omitted.

| Column | Description |
| :--- | :--- |
| `contest_id` | Unique ID for the specific game. |
| `team_id` | The ID of the team being scraped (Primary). |
| `opponent_id` | The ID of the opponent team. |
| `result` | W/L/D and score (e.g., W 2-1). |
| `attendance` | Total attendance recorded. |
| `date` | Date of the contest. |

## Discovery Logic Workflow
1. Scrape Schedule for Team A.
2. Encounter Team B in the "Opponent" column.
3. Check `teams.csv` for Team B's ID.
4. If missing, add Team B ID to `discovery_queue`.
5. Process `discovery_queue` before finishing the session.
