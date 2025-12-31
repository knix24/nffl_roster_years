#!/usr/bin/env python3
"""
Sleeper Player Tenure Calculator

Calculates consecutive seasons a player has been kept (not drafted or picked
up from free agency) in a Sleeper fantasy football league.

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
    """Get player's full name and position from player ID."""
    if player_id in players:
        p = players[player_id]
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        pos = p.get('position', '')
        return f"{name} ({pos})" if pos else name
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


def get_not_kept_players(league_id: str, prev_season_rosters: dict) -> set:
    """
    Get players who were NOT kept from the previous season.

    A player is NOT kept if:
    - They were picked up via FA/waiver AND their previous owner never dropped them, OR
    - Their previous owner dropped them pre-draft (weeks 0-1 in Sleeper API)

    Note: Sleeper API weeks 0-1 represent the pre-draft period, after the previous
    season ends but before the new season's draft occurs.

    Args:
        league_id: Current season's league ID
        prev_season_rosters: Dict mapping player_id -> roster_id from end of previous season

    Returns:
        Set of player IDs that were not kept
    """
    drops_by_roster = {}  # player_id -> set of roster_ids that dropped them
    pre_draft_drops = {}  # player_id -> set of roster_ids that dropped them pre-draft
    fa_adds = set()

    for week in range(0, 19):
        for txn in api_get(f"league/{league_id}/transactions/{week}", []):
            if txn.get('status') != 'complete':
                continue

            # Track drops
            for player_id, roster_id in (txn.get('drops') or {}).items():
                drops_by_roster.setdefault(player_id, set()).add(roster_id)
                # Weeks 0-1 in Sleeper = pre-draft period
                if week <= 1:
                    pre_draft_drops.setdefault(player_id, set()).add(roster_id)

            # Track FA/waiver adds
            if txn.get('type') in ('free_agent', 'waiver'):
                for player_id in (txn.get('adds') or {}).keys():
                    fa_adds.add(player_id)

    not_kept = set()
    for player_id in fa_adds:
        prev_roster = prev_season_rosters.get(player_id)
        if prev_roster is not None:
            # Player was rostered last season
            # Not kept if: prev owner dropped them pre-draft
            if player_id in pre_draft_drops and prev_roster in pre_draft_drops[player_id]:
                not_kept.add(player_id)
            # Not kept if: prev owner never dropped them (went straight to FA pool)
            elif player_id not in drops_by_roster or prev_roster not in drops_by_roster[player_id]:
                not_kept.add(player_id)

    return not_kept


def get_owner_name(users: list, owner_id: str) -> str:
    """Get owner display name from user list."""
    for user in users:
        if user.get('user_id') == owner_id:
            return user.get('display_name') or user.get('username') or owner_id
    return owner_id or "Unknown"


def calculate_league_tenure(league_id: str, console) -> dict:
    """
    Calculate how many consecutive seasons each player has been kept.

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
    prev_season_rosters = {}  # player_id -> roster_id from previous season

    for season in sorted(league_history.keys()):
        season_league_id = league_history[season]
        console.print(f"  Processing {season}...")

        rosters = api_get(f"league/{season_league_id}/rosters", [])
        drafted_players = get_drafted_players(season_league_id)
        not_kept = get_not_kept_players(season_league_id, prev_season_rosters)

        # Build current season's roster data
        player_to_owner = {}
        player_to_roster = {}
        for roster in rosters:
            owner_id = roster.get('owner_id')
            roster_id = roster.get('roster_id')
            for player_id in (roster.get('players') or []):
                player_to_owner[player_id] = owner_id
                player_to_roster[player_id] = roster_id

        # Update tenure: increment only if kept (rostered last season, not drafted, not in not-kept list)
        for player_id in player_to_roster:
            was_kept = (player_id in prev_season_rosters
                        and player_id not in drafted_players
                        and player_id not in not_kept)

            if was_kept:
                player_tenure[player_id] = player_tenure.get(player_id, 0) + 1
            else:
                player_tenure.pop(player_id, None)  # Remove any previous tenure
                player_first_season[player_id] = season

            last_owner[player_id] = player_to_owner[player_id]

        prev_season_rosters = player_to_roster

    # Build final tenure data (only players with tenure > 0 who are currently rostered)
    tenure_data = {}
    for player_id, tenure in player_tenure.items():
        if player_id in prev_season_rosters:
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
    tenure_data = calculate_league_tenure(league_id, console)

    if not tenure_data:
        console.print("[yellow]No tenure data found.[/yellow]")
        sys.exit(0)

    # Build table
    table = Table(title=f"\nPlayer Tenure - {league_name}")
    table.add_column("Player", style="cyan")
    table.add_column("Owner", style="green")
    table.add_column("Tenure", justify="right", style="magenta")
    table.add_column("First Kept", justify="right")

    # Sort by owner name ascending, then by tenure descending
    sorted_data = sorted(
        tenure_data.items(),
        key=lambda x: (x[0][0].lower(), -x[1]['tenure'])
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
