# Sleeper Dynasty Tenure Tracker

A command-line tool that calculates how many consecutive seasons each player has been kept (not drafted) while remaining on a roster in your [Sleeper](https://sleeper.com) fantasy football league.

## What It Does

For dynasty and keeper leagues, this tool analyzes your league's history and shows players with tenure > 0:

| Column | Description |
|--------|-------------|
| Player | Player's name |
| Pos | Position |
| Owner | Current roster owner |
| Tenure | Consecutive seasons kept |

## How Tenure Is Calculated

Tenure is a **league-wide** concept tracking how many consecutive seasons a player has avoided the draft while remaining rostered.

**Tenure = 0** when:
- Player is drafted by ANY team in the league

**Tenure increments (+1)** when:
- Player is on ANY team's week 1 roster
- Player was NOT drafted in that season's draft
- Player was in the league the previous season (on week 1 roster OR drafted)

**Tenure resets to 0** when:
- Player is drafted by any team, OR
- Player is not on any week 1 roster (dropped/not kept)

### Example

| Season | Event | Tenure |
|--------|-------|--------|
| 2022 | Drafted by Team A | 0 |
| 2023 | Kept by Team B (traded mid-season) | 1 |
| 2024 | Kept by Team B | 2 |
| 2025 | Drafted by Team C | 0 (reset) |

## Installation

Requires Python 3.6+ and the `requests` library.

```bash
git clone https://github.com/knix24/sleeper-tenure-tracker.git
cd sleeper-tenure-tracker
pip install requests
```

## Usage

```bash
python tenure_tracker.py <sleeper_username> [season]
```

- `sleeper_username`: Your Sleeper username (or any league member)
- `season`: (optional) Season year, defaults to 2025

## Example Output

```
Fetching data for angus0024... OK
League: NFFL 30th ANNIVERSARY SZN
Tracing league history... OK (4 seasons: 2022, 2023, 2024, 2025)
Calculating tenure... OK
Fetching current rosters... OK
Fetching player database... OK

Player               Pos  Owner           Tenure
================================================
Josh Jacobs          RB   angus0024            3
Amon-Ra St. Brown    WR   angus0024            3
Jahmyr Gibbs         RB   angus0024            2
Bucky Irving         RB   angus0024            1
...
Courtland Sutton     WR   write2dkv            2
Chase Brown          RB   write2dkv            1

Total players with tenure > 0: 53
```

Results are sorted by owner (ascending), then by tenure (descending).

## How It Works

1. Looks up the user and finds their leagues for the specified season
2. Traces the league's history back through all previous seasons (via `previous_league_id`)
3. For each season:
   - Fetches draft picks to identify drafted players
   - Fetches week 1 matchups to get rosters at season start
4. Calculates tenure chronologically from oldest to newest season:
   - Players drafted get tenure = 0
   - Players kept (on week 1 roster, not drafted, were in league previous season) get tenure + 1
   - Players not on any week 1 roster get tenure reset to 0
5. Displays results for currently rostered players with tenure > 0

## Notes

- If you have multiple leagues, the tool uses the first one found
- Only players currently rostered with tenure > 0 are shown

## API

This tool uses the [Sleeper API](https://docs.sleeper.com/) which is free and requires no authentication.
