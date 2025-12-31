# Sleeper Dynasty Tenure Calculator

A command-line tool that calculates how many consecutive seasons each player has been kept on a roster in your [Sleeper](https://sleeper.com) fantasy football league.

## What It Does

For dynasty and keeper leagues, it's useful to know how long players have been continuously rostered. This tool analyzes your league's history and shows you:

- **Player** - The player's name
- **Owner** - Who currently has them rostered
- **Tenure** - How many consecutive seasons they've been kept
- **First Kept** - The season when the current "kept" streak began

## How Tenure Is Calculated

A player's tenure **increments** when they are kept from one season to the next without being:
- Drafted in the league's rookie/annual draft
- Picked up via free agency or waivers

A player's tenure **resets to zero** when they:
- Enter the league through a draft
- Are added via free agency or waivers
- Are dropped and later re-acquired

This means tenure tracks *continuous* rostering through keeper/dynasty holds only.

## Installation

Requires Python 3.10+

```bash
pip install requests rich
```

## Usage

```bash
python tenure_calculator.py <sleeper_username>
```

Replace `<sleeper_username>` with your Sleeper username or any league member's username.

## Example Output

```
Fetching data for user: fantasypro123

Found user: FantasyPro (ID: 123456789)
Loaded 15432 players

Calculating tenure for all teams in: Dynasty Champions League
  Found 6 seasons of history: [2020, 2021, 2022, 2023, 2024, 2025]
  Processing 2020...
  Processing 2021...
  Processing 2022...
  Processing 2023...
  Processing 2024...
  Processing 2025...

              Player Tenure - Dynasty Champions League
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━┓
┃ Player             ┃ Owner         ┃ Tenure ┃ First Kept ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━┩
│ Patrick Mahomes    │ TeamAlpha     │      5 │ 2020       │
│ Justin Jefferson   │ GridironKing  │      4 │ 2021       │
│ Josh Allen         │ FantasyPro    │      4 │ 2021       │
│ Ja'Marr Chase      │ TeamAlpha     │      3 │ 2022       │
│ ...                │ ...           │    ... │ ...        │
└────────────────────┴───────────────┴────────┴────────────┘

Total players with tenure: 47
```

## How It Works

1. Looks up the user and finds their leagues for the current season
2. Traces the league's history back through previous seasons (via Sleeper's `previous_league_id`)
3. For each season, fetches rosters, draft picks, and transactions
4. Calculates tenure by checking if each rostered player was kept vs. acquired fresh
5. Displays results sorted by tenure (highest first)

## Notes

- The player database is cached locally (`players_cache.json`) after the first run
- If you have multiple leagues, the tool currently uses the first one listed
- League history is traced back to 2017 or the league's first season
- Only players with tenure > 0 who are currently rostered are shown

## API

This tool uses the [Sleeper API](https://docs.sleeper.com/) which is free and requires no authentication.
