#!/usr/bin/env python3
"""
Sleeper Player Tenure Calculator

Calculates consecutive seasons a player has been rostered across all teams
in a league without being drafted as a free agent.

Usage: python tenure_calculator.py <username>
"""

import sys
import json
from pathlib import Path

import requests
from rich.console import Console
from rich.table import Table

BASE_URL = "https://api.sleeper.app/v1"
CACHE_FILE = Path(__file__).parent / "players_cache.json"
START_SEASON = 2017
END_SEASON = 2025


def api_get(endpoint: str, default=None):
    """Generic API fetch from Sleeper."""
    resp = requests.get(f"{BASE_URL}/{endpoint}")
    if resp.status_code == 200 and resp.json():
        return resp.json()
    return default


def get_players() -> dict:
    """Get player data, using cache if available."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)

    print("Fetching player database (this may take a moment)...")
    players = api_get("players/nfl", {})
    if players:
        with open(CACHE_FILE, 'w') as f:
            json.dump(players, f)
    return players


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
        league = api_get(f"league/{current_id}")
        if not league:
            break
        prev_id = league.get('previous_league_id')
        if prev_id:
            current_id = prev_id
            current_season -= 1
        else:
            break

    return history


def get_drafted_players(league_id: str) -> set:
    """Get set of player IDs that were drafted in this league."""
    drafted = set()
    for draft in api_get(f"league/{league_id}/drafts", []):
        draft_id = draft.get('draft_id')
        if draft_id:
            for pick in api_get(f"draft/{draft_id}/picks", []):
                if pick.get('player_id'):
                    drafted.add(pick['player_id'])
    return drafted


def get_free_agent_adds(league_id: str) -> set:
    """Get set of player IDs that were added via free_agent or waiver transactions."""
    fa_adds = set()
    for week in range(0, 19):
        for txn in api_get(f"league/{league_id}/transactions/{week}", []):
            if txn.get('status') == 'complete' and txn.get('type') in ('free_agent', 'waiver'):
                for player_id in (txn.get('adds') or {}).keys():
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
    league_history = trace_league_history(league_id, END_SEASON)
    console.print(f"  Found {len(league_history)} seasons of history: {sorted(league_history.keys())}")

    current_users = api_get(f"league/{league_id}/users", [])

    player_tenure = {}
    player_first_season = {}
    last_owner = {}
    rostered_last_season = set()

    for season in sorted(league_history.keys()):
        season_league_id = league_history[season]
        console.print(f"  Processing {season}...")

        rosters = api_get(f"league/{season_league_id}/rosters", [])
        drafted_players = get_drafted_players(season_league_id)
        fa_adds = get_free_agent_adds(season_league_id)

        # Build current season's roster data
        rostered_this_season = set()
        player_to_owner = {}
        for roster in rosters:
            owner_id = roster.get('owner_id')
            for player_id in (roster.get('players') or []):
                rostered_this_season.add(player_id)
                player_to_owner[player_id] = owner_id

        # Update tenure: increment only if kept (not drafted/FA and was rostered last season)
        for player_id in rostered_this_season:
            was_kept = (player_id in rostered_last_season
                        and player_id not in drafted_players
                        and player_id not in fa_adds)

            if was_kept:
                player_tenure[player_id] = player_tenure.get(player_id, 0) + 1
            else:
                player_tenure[player_id] = 0
                player_first_season[player_id] = season

            last_owner[player_id] = player_to_owner[player_id]

        rostered_last_season = rostered_this_season

    # Build final tenure data (only players with tenure > 0 who are currently rostered)
    tenure_data = {}
    for player_id, tenure in player_tenure.items():
        if tenure > 0 and player_id in rostered_last_season:
            owner_id = last_owner.get(player_id)
            owner_name = get_owner_name(current_users, owner_id)
            tenure_data[(owner_name, player_id)] = {
                'tenure': tenure,
                'first_season': player_first_season.get(player_id),
                'owner_id': owner_id,
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
    user = api_get(f"user/{username}")
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
    leagues = api_get(f"user/{user_id}/leagues/nfl/{END_SEASON}", [])
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
