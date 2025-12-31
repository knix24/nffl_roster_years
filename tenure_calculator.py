#!/usr/bin/env python3
"""
Sleeper Player Tenure Calculator

Calculates consecutive seasons a player has been rostered across all teams
in a league without being drafted as a free agent.

Usage: python tenure_calculator.py <username>
"""

import sys
import json
import os
from pathlib import Path
from collections import defaultdict

import requests
from rich.console import Console
from rich.table import Table

BASE_URL = "https://api.sleeper.app/v1"
CACHE_FILE = Path(__file__).parent / "players_cache.json"
START_SEASON = 2017
END_SEASON = 2025


def fetch_user(username: str) -> dict | None:
    """Fetch user data by username."""
    resp = requests.get(f"{BASE_URL}/user/{username}")
    if resp.status_code == 200 and resp.json():
        return resp.json()
    return None


def fetch_state() -> dict:
    """Fetch current NFL state (season, week, etc.)."""
    resp = requests.get(f"{BASE_URL}/state/nfl")
    return resp.json()


def fetch_leagues(user_id: str, season: int) -> list:
    """Fetch all NFL leagues for a user in a given season."""
    resp = requests.get(f"{BASE_URL}/user/{user_id}/leagues/nfl/{season}")
    if resp.status_code == 200:
        return resp.json() or []
    return []


def fetch_rosters(league_id: str) -> list:
    """Fetch all rosters for a league."""
    resp = requests.get(f"{BASE_URL}/league/{league_id}/rosters")
    if resp.status_code == 200:
        return resp.json() or []
    return []


def fetch_league_users(league_id: str) -> list:
    """Fetch all users in a league."""
    resp = requests.get(f"{BASE_URL}/league/{league_id}/users")
    if resp.status_code == 200:
        return resp.json() or []
    return []


def fetch_drafts(league_id: str) -> list:
    """Fetch all drafts for a league."""
    resp = requests.get(f"{BASE_URL}/league/{league_id}/drafts")
    if resp.status_code == 200:
        return resp.json() or []
    return []


def fetch_draft_picks(draft_id: str) -> list:
    """Fetch all picks from a draft."""
    resp = requests.get(f"{BASE_URL}/draft/{draft_id}/picks")
    if resp.status_code == 200:
        return resp.json() or []
    return []


def fetch_league(league_id: str) -> dict | None:
    """Fetch league details."""
    resp = requests.get(f"{BASE_URL}/league/{league_id}")
    if resp.status_code == 200:
        return resp.json()
    return None


def get_players() -> dict:
    """Get player data, using cache if available."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)

    print("Fetching player database (this may take a moment)...")
    resp = requests.get(f"{BASE_URL}/players/nfl")
    if resp.status_code == 200:
        players = resp.json()
        with open(CACHE_FILE, 'w') as f:
            json.dump(players, f)
        return players
    return {}


def get_player_name(players: dict, player_id: str) -> str:
    """Get player's full name from player ID."""
    if player_id in players:
        p = players[player_id]
        return f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    return player_id


def trace_league_history(league_id: str, target_season: int) -> dict:
    """
    Trace a league's history backwards using previous_league_id.
    Returns a dict mapping season -> league_id.
    """
    history = {}
    current_id = league_id
    current_season = target_season

    while current_id and current_season >= START_SEASON:
        history[current_season] = current_id
        league = fetch_league(current_id)
        if not league:
            break
        prev_id = league.get('previous_league_id')
        if prev_id:
            current_id = prev_id
            current_season -= 1
        else:
            break

    return history


def find_user_roster(rosters: list, user_id: str) -> dict | None:
    """Find the roster belonging to a specific user."""
    for roster in rosters:
        if roster.get('owner_id') == user_id:
            return roster
    return None


def get_drafted_players(league_id: str) -> dict:
    """Get dict of player IDs that were drafted, mapped to roster_id that drafted them."""
    drafted = {}  # player_id -> roster_id
    drafts = fetch_drafts(league_id)
    for draft in drafts:
        draft_id = draft.get('draft_id')
        if draft_id:
            picks = fetch_draft_picks(draft_id)
            for pick in picks:
                player_id = pick.get('player_id')
                roster_id = pick.get('roster_id')
                if player_id:
                    drafted[player_id] = roster_id
    return drafted


def get_free_agent_adds(league_id: str) -> set:
    """Get set of player IDs that were added via free_agent or waiver transactions."""
    fa_adds = set()
    for week in range(0, 19):
        resp = requests.get(f"{BASE_URL}/league/{league_id}/transactions/{week}")
        if resp.status_code == 200:
            txns = resp.json() or []
            for txn in txns:
                txn_type = txn.get('type')
                status = txn.get('status')
                # Only count completed free_agent or waiver adds
                if status == 'complete' and txn_type in ('free_agent', 'waiver'):
                    adds = txn.get('adds') or {}
                    for player_id in adds.keys():
                        fa_adds.add(player_id)
    return fa_adds


def get_owner_name(users: list, owner_id: str) -> str:
    """Get owner display name from user list."""
    for user in users:
        if user.get('user_id') == owner_id:
            return user.get('display_name') or user.get('username') or owner_id
    return owner_id or "Unknown"


def calculate_league_tenure(league_id: str, league_name: str, console) -> dict:
    """
    Calculate league-wide player tenure (how long rostered anywhere in the league).

    Returns dict: {
        (owner_name, player_id): {
            'tenure': int,
            'first_season': int,
            'owner_id': str
        }
    }
    """
    # Get the full history of this league
    league_history = trace_league_history(league_id, END_SEASON)
    console.print(f"  Found {len(league_history)} seasons of history: {sorted(league_history.keys())}")

    # Get current league users for display names
    current_users = fetch_league_users(league_id)

    # Track league-wide tenure per player
    player_tenure = {}  # player_id -> tenure
    player_first_season = {}  # player_id -> first_season

    # Track last known owner and current roster status
    last_owner = {}  # player_id -> owner_id (last team they were on)
    currently_rostered = set()  # players on a roster in the final season

    # Track players rostered in the previous season
    rostered_last_season = set()

    # Process seasons from oldest to newest
    sorted_seasons = sorted(league_history.keys())

    for season in sorted_seasons:
        season_league_id = league_history[season]
        console.print(f"  Processing {season}...")

        # Get all rosters for this season
        rosters = fetch_rosters(season_league_id)

        # Get players drafted this season
        drafted_players = get_drafted_players(season_league_id)

        # Get players added via free agent or waiver this season
        fa_adds = get_free_agent_adds(season_league_id)

        # Collect all rostered players this season
        all_rostered_this_season = set()
        player_to_owner = {}  # player_id -> owner_id for this season

        for roster in rosters:
            owner_id = roster.get('owner_id')
            roster_players = set(roster.get('players') or [])

            for player_id in roster_players:
                all_rostered_this_season.add(player_id)
                player_to_owner[player_id] = owner_id

        # Build roster_id -> owner_id mapping for this season
        roster_to_owner = {}
        for roster in rosters:
            roster_to_owner[roster.get('roster_id')] = roster.get('owner_id')

        # Update tenure for each rostered player
        for player_id in all_rostered_this_season:
            if player_id in drafted_players:
                # Player was drafted this season - tenure starts at 0
                player_tenure[player_id] = 0
                player_first_season[player_id] = season
            elif player_id in fa_adds:
                # Player was added via free agent/waiver - tenure = 0
                player_tenure[player_id] = 0
                player_first_season[player_id] = season
            elif player_id in rostered_last_season:
                # Player was kept from last season (not drafted, not FA pickup) - increment tenure
                player_tenure[player_id] = player_tenure.get(player_id, 0) + 1
            else:
                # First time seeing this player - tenure = 0
                player_tenure[player_id] = 0
                player_first_season[player_id] = season

            # Track last known owner
            last_owner[player_id] = player_to_owner[player_id]

        # Also handle drafted players who are NOT currently rostered (dropped after draft)
        for player_id, draft_roster_id in drafted_players.items():
            if player_id not in all_rostered_this_season:
                # Player was drafted but dropped - reset tenure to 0
                player_tenure[player_id] = 0
                player_first_season[player_id] = season
                # Track the drafting team as last owner
                last_owner[player_id] = roster_to_owner.get(draft_roster_id)

        # Handle players who were rostered last season but are NOT rostered this season
        # and were NOT drafted (they were dropped) - reset their tenure to 0
        for player_id in rostered_last_season:
            if player_id not in all_rostered_this_season and player_id not in drafted_players:
                # Player was dropped and not re-drafted - reset tenure to 0
                player_tenure[player_id] = 0

        # Update for next iteration
        rostered_last_season = all_rostered_this_season

    # Track who is currently rostered (in the final season)
    currently_rostered = all_rostered_this_season

    # Build final tenure data with owner names (only players with tenure > 0)
    tenure_data = {}
    for player_id, tenure in player_tenure.items():
        if tenure > 0:  # Only include players with non-zero tenure
            owner_id = last_owner.get(player_id)
            owner_name = get_owner_name(current_users, owner_id)
            first_season = player_first_season.get(player_id)
            is_rostered = player_id in currently_rostered

            key = (owner_name, player_id)
            tenure_data[key] = {
                'tenure': tenure,
                'first_season': first_season,
                'owner_id': owner_id,
                'rostered': is_rostered
            }

    return tenure_data


def main():
    if len(sys.argv) < 2:
        print("Usage: python tenure_calculator.py <username>")
        sys.exit(1)

    username = sys.argv[1]
    console = Console()

    console.print(f"\n[bold]Fetching data for user: {username}[/bold]\n")

    # Get user
    user = fetch_user(username)
    if not user:
        console.print(f"[red]User '{username}' not found[/red]")
        sys.exit(1)

    user_id = user['user_id']
    display_name = user.get('display_name', username)
    console.print(f"Found user: {display_name} (ID: {user_id})")

    # Get player names
    players = get_players()
    console.print(f"Loaded {len(players)} players\n")

    # Get user's leagues
    leagues = fetch_leagues(user_id, END_SEASON)
    if not leagues:
        console.print("[yellow]No leagues found for this user.[/yellow]")
        sys.exit(0)

    # If multiple leagues, let user pick or process first one
    if len(leagues) == 1:
        selected_league = leagues[0]
    else:
        console.print("[bold]Available leagues:[/bold]")
        for i, league in enumerate(leagues, 1):
            console.print(f"  {i}. {league.get('name')}")
        console.print()
        # For now, use the first league - can add interactive selection later
        selected_league = leagues[0]
        console.print(f"[dim]Using first league: {selected_league.get('name')}[/dim]\n")

    league_id = selected_league.get('league_id')
    league_name = selected_league.get('name', 'Unknown League')

    # Calculate tenure for all teams
    console.print(f"[bold]Calculating tenure for all teams in: {league_name}[/bold]")
    tenure_data = calculate_league_tenure(league_id, league_name, console)

    if not tenure_data:
        console.print("[yellow]No tenure data found.[/yellow]")
        sys.exit(0)

    # Build table
    table = Table(title=f"\nPlayer Tenure - {league_name}")
    table.add_column("Player", style="cyan")
    table.add_column("Owner", style="green")
    table.add_column("Tenure", justify="right", style="magenta")
    table.add_column("First Kept", justify="right")

    # Sort by tenure descending, then by owner name
    sorted_data = sorted(
        tenure_data.items(),
        key=lambda x: (-x[1]['tenure'], x[0][0])
    )

    for (owner_name, player_id), data in sorted_data:
        player_name = get_player_name(players, player_id)
        tenure = str(data['tenure'])
        first_season = str(data['first_season']) if data['first_season'] else "N/A"

        table.add_row(player_name, owner_name, tenure, first_season)

    console.print(table)
    console.print(f"\n[dim]Total players with tenure: {len(tenure_data)}[/dim]")


if __name__ == "__main__":
    main()
