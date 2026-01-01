#!/usr/bin/env python3
"""
Player Tenure Tracker for Sleeper Fantasy Football Leagues

Calculates how many consecutive seasons a player has been kept (not drafted)
while remaining on a roster in the league.
"""

import requests
import sys

API_BASE = "https://api.sleeper.app/v1"


def get_user(username):
    """Get user info by username."""
    resp = requests.get(f"{API_BASE}/user/{username}")
    resp.raise_for_status()
    return resp.json()


def get_user_leagues(user_id, sport, season):
    """Get all leagues for a user in a given season."""
    resp = requests.get(f"{API_BASE}/user/{user_id}/leagues/{sport}/{season}")
    resp.raise_for_status()
    return resp.json()


def get_league(league_id):
    """Get league details."""
    resp = requests.get(f"{API_BASE}/league/{league_id}")
    resp.raise_for_status()
    return resp.json()


def get_league_users(league_id):
    """Get all users in a league."""
    resp = requests.get(f"{API_BASE}/league/{league_id}/users")
    resp.raise_for_status()
    return resp.json()


def get_league_rosters(league_id):
    """Get all rosters in a league."""
    resp = requests.get(f"{API_BASE}/league/{league_id}/rosters")
    resp.raise_for_status()
    return resp.json()


def get_league_drafts(league_id):
    """Get drafts for a league."""
    resp = requests.get(f"{API_BASE}/league/{league_id}/drafts")
    resp.raise_for_status()
    return resp.json()


def get_draft_picks(draft_id):
    """Get all picks from a draft."""
    resp = requests.get(f"{API_BASE}/draft/{draft_id}/picks")
    resp.raise_for_status()
    return resp.json()


def get_matchups(league_id, week):
    """Get matchups for a given week."""
    resp = requests.get(f"{API_BASE}/league/{league_id}/matchups/{week}")
    resp.raise_for_status()
    return resp.json()


def get_all_players():
    """Get all NFL players (cached locally due to size)."""
    resp = requests.get(f"{API_BASE}/players/nfl")
    resp.raise_for_status()
    return resp.json()


def get_league_history(league_id):
    """Trace back through all seasons of a league, returns list from oldest to newest."""
    leagues = []
    current_id = league_id

    while current_id:
        league = get_league(current_id)
        leagues.append(league)
        current_id = league.get("previous_league_id")

    return list(reversed(leagues))  # Oldest first


def get_season_data(league):
    """Get draft picks and week 1 rosters for a season."""
    league_id = league["league_id"]

    # Get draft picks
    drafts = get_league_drafts(league_id)
    drafted_players = set()

    if drafts:
        draft_id = drafts[0]["draft_id"]
        picks = get_draft_picks(draft_id)
        drafted_players = {pick["player_id"] for pick in picks}

    # Get week 1 rosters
    matchups = get_matchups(league_id, 1)
    week1_players = set()

    for matchup in matchups:
        if matchup.get("players"):
            week1_players.update(matchup["players"])

    return {
        "season": league["season"],
        "drafted": drafted_players,
        "week1_roster": week1_players,
    }


def calculate_tenure(league_history):
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
        player_tenure: dict mapping player_id -> current tenure (int)
        player_first_drafted: dict mapping player_id -> year first drafted (str)
    """
    player_tenure = {}
    player_first_drafted = {}
    previous_week1_roster = set()
    previous_drafted = set()

    for league in league_history:
        season_data = get_season_data(league)
        season = season_data["season"]
        drafted = season_data["drafted"]
        week1_roster = season_data["week1_roster"]

        # Players eligible to be kept: were on previous week 1 roster OR were drafted previous season
        eligible_for_keeper = previous_week1_roster | previous_drafted

        # True keepers: on week 1 roster, not drafted, AND were in league previous season
        keepers = (week1_roster - drafted) & eligible_for_keeper if eligible_for_keeper else set()

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
            if player_id not in player_first_drafted:
                player_first_drafted[player_id] = season

        # Process keepers - increment tenure (only if they were in league last season)
        for player_id in keepers:
            if player_id in player_tenure:
                player_tenure[player_id] += 1
            else:
                # Player appeared as keeper without being drafted in our history
                # This can happen if they were drafted before our league history starts
                player_tenure[player_id] = 1
                player_first_drafted[player_id] = f"<{league_history[0]['season']}"

        # Update previous season tracking for next iteration
        previous_week1_roster = week1_roster
        previous_drafted = drafted

    return player_tenure, player_first_drafted


def get_current_roster_info(league_id):
    """Get current roster info: player_id -> owner display name mapping."""
    rosters = get_league_rosters(league_id)
    users = get_league_users(league_id)

    # Map owner_id to display_name
    owner_names = {user["user_id"]: user.get("display_name") or user.get("username", "Unknown") for user in users}

    # Map player_id to owner display_name
    player_owners = {}
    for roster in rosters:
        owner_name = owner_names.get(roster["owner_id"], "Unknown")
        for player_id in roster.get("players", []):
            player_owners[player_id] = owner_name

    return player_owners


def main():
    if len(sys.argv) < 2:
        print("Usage: python tenure_tracker.py <username> [season]")
        print("  username: Sleeper username")
        print("  season: (optional) Season year, defaults to 2025")
        sys.exit(1)

    username = sys.argv[1]
    season = sys.argv[2] if len(sys.argv) > 2 else "2025"

    # Get user and their leagues
    print(f"Fetching data for {username}...", end=" ", flush=True)
    user = get_user(username)
    user_id = user["user_id"]
    print("OK")

    leagues = get_user_leagues(user_id, "nfl", season)
    if not leagues:
        print(f"No NFL leagues found for {username} in {season}")
        sys.exit(1)

    # Use first league (or could prompt for selection)
    current_league = leagues[0]
    print(f"League: {current_league['name']}")

    # Get league history
    print("Tracing league history...", end=" ", flush=True)
    league_history = get_league_history(current_league["league_id"])
    seasons_list = [l['season'] for l in league_history]
    print(f"OK ({len(league_history)} seasons: {', '.join(seasons_list)})")

    # Calculate tenure
    print("Calculating tenure...", end=" ", flush=True)
    player_tenure, player_first_drafted = calculate_tenure(league_history)
    print("OK")

    # Get current roster info
    print("Fetching current rosters...", end=" ", flush=True)
    player_owners = get_current_roster_info(current_league["league_id"])
    print("OK")

    # Get player details
    print("Fetching player database...", end=" ", flush=True)
    all_players = get_all_players()
    print("OK")

    # Build output: players with tenure > 0 on current rosters
    results = []
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
                "tenure": tenure,
                "first_drafted": player_first_drafted.get(player_id, "Unknown")
            })

    # Sort by owner ascending, then by tenure descending
    results.sort(key=lambda x: (x["owner"].lower(), -x["tenure"]))

    # Calculate column widths
    col_player = max(len("Player"), max((len(r["player"]) for r in results), default=0))
    col_pos = max(len("Pos"), max((len(r["position"]) for r in results), default=0))
    col_owner = max(len("Owner"), max((len(r["owner"]) for r in results), default=0))
    col_tenure = len("Tenure")
    col_drafted = max(len("First Drafted"), max((len(str(r["first_drafted"])) for r in results), default=0))

    # Print table
    print()
    header = f"{'Player':<{col_player}}  {'Pos':<{col_pos}}  {'Owner':<{col_owner}}  {'Tenure':>{col_tenure}}  {'First Drafted':<{col_drafted}}"
    print(header)
    print("=" * len(header))

    for r in results:
        print(f"{r['player']:<{col_player}}  {r['position']:<{col_pos}}  {r['owner']:<{col_owner}}  {r['tenure']:>{col_tenure}}  {r['first_drafted']:<{col_drafted}}")

    print()
    print(f"Total players with tenure > 0: {len(results)}")


if __name__ == "__main__":
    main()
