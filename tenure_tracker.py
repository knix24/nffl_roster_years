#!/usr/bin/env python3
"""
Player Tenure Tracker for Sleeper Fantasy Football Leagues

Calculates how many consecutive seasons a player has been kept (not drafted)
while remaining on a roster in the league.
"""

import argparse
import csv
import json
import os
import requests
import sys
import time
from datetime import datetime
from typing import Any

API_BASE = "https://api.sleeper.app/v1"
CACHE_DIR = os.path.expanduser("~/.cache/sleeper-tenure-tracker")
PLAYERS_CACHE_FILE = os.path.join(CACHE_DIR, "players.json")
CACHE_MAX_AGE = 86400  # 24 hours in seconds

# Global flag for quiet mode (CSV output)
_quiet = False


def log(message: str, end: str = "\n", flush: bool = False) -> None:
    """Print a status message unless in quiet mode."""
    if not _quiet:
        print(message, end=end, flush=flush)


def api_request(url: str, error_context: str) -> Any:
    """Make an API request with error handling."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        print(f"\nError: Request timed out while {error_context}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"\nError: Could not connect to Sleeper API while {error_context}")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"\nError: Not found while {error_context}")
        else:
            print(f"\nError: API returned status {e.response.status_code} while {error_context}")
        sys.exit(1)


def get_user(username: str) -> dict[str, Any]:
    """Get user info by username."""
    return api_request(f"{API_BASE}/user/{username}", f"fetching user '{username}'")


def get_user_leagues(user_id: str, sport: str, season: str) -> list[dict[str, Any]]:
    """Get all leagues for a user in a given season."""
    return api_request(f"{API_BASE}/user/{user_id}/leagues/{sport}/{season}", f"fetching leagues for season {season}")


def get_league(league_id: str) -> dict[str, Any]:
    """Get league details."""
    return api_request(f"{API_BASE}/league/{league_id}", "fetching league details")


def get_league_users(league_id: str) -> list[dict[str, Any]]:
    """Get all users in a league."""
    return api_request(f"{API_BASE}/league/{league_id}/users", "fetching league users")


def get_league_rosters(league_id: str) -> list[dict[str, Any]]:
    """Get all rosters in a league."""
    return api_request(f"{API_BASE}/league/{league_id}/rosters", "fetching rosters")


def get_league_drafts(league_id: str) -> list[dict[str, Any]]:
    """Get drafts for a league."""
    return api_request(f"{API_BASE}/league/{league_id}/drafts", "fetching drafts")


def get_draft_picks(draft_id: str) -> list[dict[str, Any]]:
    """Get all picks from a draft."""
    return api_request(f"{API_BASE}/draft/{draft_id}/picks", "fetching draft picks")


def get_matchups(league_id: str, week: int) -> list[dict[str, Any]]:
    """Get matchups for a given week."""
    return api_request(f"{API_BASE}/league/{league_id}/matchups/{week}", f"fetching week {week} matchups")


def get_all_players(refresh: bool = False) -> tuple[dict[str, Any], bool]:
    """Get all NFL players, with daily caching.

    Returns:
        Tuple of (players dict, was_cached bool)
    """
    # Check if cache exists and is fresh (unless refresh requested)
    if not refresh and os.path.exists(PLAYERS_CACHE_FILE):
        cache_age = time.time() - os.path.getmtime(PLAYERS_CACHE_FILE)
        if cache_age < CACHE_MAX_AGE:
            with open(PLAYERS_CACHE_FILE, "r") as f:
                return json.load(f), True

    # Fetch fresh data
    players = api_request(f"{API_BASE}/players/nfl", "fetching player database")

    # Save to cache
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(PLAYERS_CACHE_FILE, "w") as f:
        json.dump(players, f)

    return players, False


def get_league_history(league_id: str) -> list[dict[str, Any]]:
    """Trace back through all seasons of a league, returns list from oldest to newest."""
    leagues = []
    current_id = league_id

    while current_id:
        league = get_league(current_id)
        leagues.append(league)
        current_id = league.get("previous_league_id")

    return list(reversed(leagues))  # Oldest first


def get_season_data(league: dict[str, Any]) -> dict[str, Any]:
    """Get draft picks and week 1 rosters for a season."""
    league_id = league["league_id"]

    # Get draft picks
    drafts = get_league_drafts(league_id)
    drafted_players: set[str] = set()

    if drafts:
        draft_id = drafts[0]["draft_id"]
        picks = get_draft_picks(draft_id)
        drafted_players = {pick["player_id"] for pick in picks}

    # Get week 1 rosters
    matchups = get_matchups(league_id, 1)
    week1_players: set[str] = set()

    for matchup in matchups:
        if matchup.get("players"):
            week1_players.update(matchup["players"])

    return {
        "season": league["season"],
        "drafted": drafted_players,
        "week1_roster": week1_players,
    }


def calculate_tenure(league_history: list[dict[str, Any]]) -> dict[str, int]:
    """
    Calculate tenure for all players across seasons.

    A player is only a "keeper" if:
    1. They were on a roster at week 1 of the previous season OR drafted previous season
    2. They were NOT drafted in the current season
    3. They are on a roster at week 1 of the current season

    Tenure resets to 0 if:
    - Player is drafted, OR
    - Player is not on any week 1 roster (not kept)

    Returns:
        dict mapping player_id -> current tenure (int)
    """
    player_tenure: dict[str, int] = {}
    previous_week1_roster: set[str] = set()
    previous_drafted: set[str] = set()

    for league in league_history:
        season_data = get_season_data(league)
        drafted = season_data["drafted"]
        week1_roster = season_data["week1_roster"]

        # Players eligible to be kept: were on previous week 1 roster OR were drafted previous season
        eligible_for_keeper = previous_week1_roster | previous_drafted

        # True keepers: on week 1 roster, not drafted, AND were in league previous season
        keepers = (week1_roster - drafted) & eligible_for_keeper

        # Reset tenure for players who were in league but are not on any week 1 roster
        # (not drafted and not kept = dropped from league)
        if eligible_for_keeper:
            dropped_players = eligible_for_keeper - week1_roster - drafted
            for player_id in dropped_players:
                if player_id in player_tenure:
                    player_tenure[player_id] = 0

        # Process drafted players - reset tenure to 0
        for player_id in drafted:
            player_tenure[player_id] = 0

        # Process keepers - increment tenure (only if they were in league last season)
        for player_id in keepers:
            if player_id in player_tenure:
                player_tenure[player_id] += 1
            else:
                # Player appeared as keeper without being drafted in our history
                # This can happen if they were drafted before our league history starts
                player_tenure[player_id] = 1

        # Update previous season tracking for next iteration
        previous_week1_roster = week1_roster
        previous_drafted = drafted

    return player_tenure


def get_current_roster_info(league_id: str) -> dict[str, str]:
    """Get current roster info: player_id -> owner display name mapping."""
    rosters = get_league_rosters(league_id)
    users = get_league_users(league_id)

    # Map owner_id to display_name
    owner_names = {user["user_id"]: user.get("display_name") or user.get("username", "Unknown") for user in users}

    # Map player_id to owner display_name
    player_owners: dict[str, str] = {}
    for roster in rosters:
        owner_name = owner_names.get(roster["owner_id"], "Unknown")
        for player_id in roster.get("players", []):
            player_owners[player_id] = owner_name

    return player_owners


def select_league(leagues: list[dict[str, Any]], username: str, league_num: int | None) -> dict[str, Any]:
    """Select a league from the list, prompting user if necessary."""
    if league_num is not None:
        if league_num < 1 or league_num > len(leagues):
            print(f"Error: League number must be between 1 and {len(leagues)}", file=sys.stderr)
            sys.exit(1)
        return leagues[league_num - 1]

    if len(leagues) == 1:
        return leagues[0]

    # Multiple leagues, prompt for selection
    print(f"\nFound {len(leagues)} leagues for {username}:")
    for i, league in enumerate(leagues, 1):
        print(f"  {i}. {league['name']}")
    print()

    while True:
        try:
            choice = input(f"Select league (1-{len(leagues)}): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= len(leagues):
                print()
                return leagues[choice_num - 1]
            print(f"Please enter a number between 1 and {len(leagues)}")
        except ValueError:
            print("Please enter a valid number")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled")
            sys.exit(0)


def build_results(
    player_owners: dict[str, str],
    player_tenure: dict[str, int],
    all_players: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build the results list from player data."""
    results: list[dict[str, Any]] = []

    for player_id, owner in player_owners.items():
        tenure = player_tenure.get(player_id, 0)
        if tenure > 0:
            player_info = all_players.get(player_id, {})
            first_name = player_info.get("first_name", "")
            last_name = player_info.get("last_name", player_id)
            position = player_info.get("position", "")

            # Handle team defenses
            if not first_name and not position:
                first_name = player_info.get("team", "")
                last_name = "DEF"
                position = "DEF"

            results.append({
                "player": f"{first_name} {last_name}".strip(),
                "position": position,
                "owner": owner,
                "tenure": tenure + 1,  # Projected tenure for next season
            })

    # Sort by owner ascending, then by tenure descending
    results.sort(key=lambda x: (x["owner"].lower(), -x["tenure"]))
    return results


def print_table(results: list[dict[str, Any]], next_season: int) -> None:
    """Print results as a formatted table."""
    tenure_header = f"Tenure ({next_season})"
    col_player = max(len("Player"), max((len(r["player"]) for r in results), default=0))
    col_pos = max(len("Pos"), max((len(r["position"]) for r in results), default=0))
    col_owner = max(len("Owner"), max((len(r["owner"]) for r in results), default=0))
    col_tenure = len(tenure_header)

    print()
    header = f"{'Player':<{col_player}}  {'Pos':<{col_pos}}  {'Owner':<{col_owner}}  {tenure_header:>{col_tenure}}"
    print(header)
    print("=" * len(header))

    for r in results:
        print(f"{r['player']:<{col_player}}  {r['position']:<{col_pos}}  {r['owner']:<{col_owner}}  {r['tenure']:>{col_tenure}}")

    print()
    print(f"Total players with tenure greater than 1: {len(results)}")


def print_csv(results: list[dict[str, Any]], next_season: int) -> None:
    """Print results as CSV."""
    writer = csv.writer(sys.stdout)
    writer.writerow(["Player", "Pos", "Owner", f"Tenure ({next_season})"])
    for r in results:
        writer.writerow([r["player"], r["position"], r["owner"], r["tenure"]])


def main() -> None:
    global _quiet

    parser = argparse.ArgumentParser(
        description="Calculate player tenure for Sleeper fantasy football leagues"
    )
    parser.add_argument("username", help="Sleeper username")
    parser.add_argument(
        "season",
        nargs="?",
        default=str(datetime.now().year),
        help=f"Season year (default: {datetime.now().year})"
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output in CSV format"
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force refresh of cached player database"
    )
    parser.add_argument(
        "--league",
        type=int,
        metavar="N",
        help="Select league number N (use with --csv to skip prompt)"
    )
    args = parser.parse_args()

    _quiet = args.csv

    # Get user and their leagues
    log(f"Fetching data for {args.username}...", end=" ", flush=True)
    user = get_user(args.username)
    log("OK")

    leagues = get_user_leagues(user["user_id"], "nfl", args.season)
    if not leagues:
        print(f"No NFL leagues found for {args.username} in {args.season}", file=sys.stderr)
        sys.exit(1)

    # Select league
    current_league = select_league(leagues, args.username, args.league)
    log(f"League: {current_league['name']}")

    # Get league history
    log("Tracing league history...", end=" ", flush=True)
    league_history = get_league_history(current_league["league_id"])
    seasons_list = [league['season'] for league in league_history]
    log(f"OK ({len(league_history)} seasons: {', '.join(seasons_list)})")

    # Calculate tenure
    log("Calculating tenure...", end=" ", flush=True)
    player_tenure = calculate_tenure(league_history)
    log("OK")

    # Get current roster info
    log("Fetching current rosters...", end=" ", flush=True)
    player_owners = get_current_roster_info(current_league["league_id"])
    log("OK")

    # Get player details
    log("Fetching player database...", end=" ", flush=True)
    all_players, was_cached = get_all_players(refresh=args.refresh)
    cache_status = " (cached)" if was_cached else ""
    log(f"OK{cache_status}")

    # Build and output results
    results = build_results(player_owners, player_tenure, all_players)
    next_season = int(args.season) + 1

    if args.csv:
        print_csv(results, next_season)
    else:
        print_table(results, next_season)


if __name__ == "__main__":
    main()
