# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "click",
#     "requests",
#     "pytz",
#     "rich",
#     "python-dateutil",
#     "python-telegram-bot",
# ]
# ///

import click
import requests
import json
import datetime
import pytz
import os
import sys
from rich.console import Console
from rich.table import Table
from dateutil import parser
from telegram import Bot
from telegram.constants import ParseMode
import asyncio
from math import sin, cos, sqrt, atan2, radians

console = Console()

def load_metro_stations(file_path='metro_stations.json'):
    """Loads metro station data from a JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        console.print(f"[bold red]Error:[/bold red] Could not load or parse '{file_path}'.")
        return []

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the distance between two points in km."""
    R = 6371.0  # Radius of Earth in kilometers

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance

def find_nearest_metro(venue_lat, venue_lng, metro_stations):
    """Find the nearest metro station to a given venue."""
    if not metro_stations:
        return None, float('inf')

    min_distance = float('inf')
    nearest_station = None

    for station in metro_stations:
        dist = calculate_haversine_distance(venue_lat, venue_lng, station['lat'], station['lng'])
        if dist < min_distance:
            min_distance = dist
            nearest_station = station['name']
    
    return nearest_station, min_distance

@click.command()
@click.option("--lat", default=12.9783692, help="Latitude for search")
@click.option("--lng", default=77.6408356, help="Longitude for search")
@click.option("--radius", default=50, help="City radius in km")
@click.option("--sport", default="SP5", help="Sport ID (default: SP5 for Badminton)")
@click.option("--start-time", default="19:00", help="Desired start time (24-hour format HH:MM)")
@click.option("--end-time", default="20:00", help="Desired end time (24-hour format HH:MM)")
@click.option("--timezone", default="Asia/Kolkata", help="Your timezone")
@click.option("--verbose", is_flag=True, help="Show detailed information including exact UTC/IST times")
@click.option("--include-full", is_flag=True, help="Include games that are full")
@click.option("--telegram", is_flag=True, help="Send results to Telegram")
@click.option("--telegram-token", envvar="TELEGRAM_BOT_TOKEN", help="Telegram Bot Token")
@click.option("--telegram-chat-id", envvar="TELEGRAM_CHAT_ID", help="Telegram Chat ID")
def find_games(lat, lng, radius, sport, start_time, end_time, timezone, verbose, include_full, telegram, telegram_token, telegram_chat_id):
    """Find available badminton courts on Playo, prioritized by metro proximity."""
    metro_stations = load_metro_stations()
    if not metro_stations:
        return # Stop if metro stations couldn't be loaded

    # Get today's date in the specified timezone
    local_tz = pytz.timezone(timezone)
    now = datetime.datetime.now(local_tz)
    today_date = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # Parse desired time window
    try:
        desired_start = datetime.datetime.strptime(start_time, "%H:%M").time()
        desired_end = datetime.datetime.strptime(end_time, "%H:%M").time()
    except ValueError:
        console.print("[bold red]Error:[/bold red] Invalid time format. Please use HH:MM (24-hour format).")
        return

    console.print(f"[bold green]Searching for badminton courts around your location...[/bold green]")
    console.print(f"Looking for games between [bold]{start_time}[/bold] and [bold]{end_time}[/bold] IST today")

    if verbose:
        console.print(f"[dim]Search parameters: lat={lat}, lng={lng}, radius={radius}km[/dim]")
        console.print(f"[dim]Current time in {timezone}: {now.strftime('%Y-%m-%d %H:%M:%S')}[/dim]")

    # Prepare API request
    url = "https://api.playo.io/activity-public/list/location"
    payload = {
        "lat": lat,
        "lng": lng,
        "cityRadius": radius,
        "gameTimeActivities": False,
        "page": 0,
        "lastId": "",
        "sportId": [sport],
        "booking": True, # Changed to TRUE to find bookable slots
        "date": [today_date]
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if data.get("requestStatus") != 1 or "data" not in data:
            console.print("[bold red]Error:[/bold red] Failed to get valid response from Playo API")
            return

        activities = data["data"]
        grouped_venues = {}

        console.print(f"Found {len(activities)} total slots nearby. Grouping by venue and time, then sorting by metro proximity...")

        # Get the desired time window in the local timezone
        today = now.date()
        start_datetime_local = local_tz.localize(datetime.datetime.combine(today, desired_start))
        end_datetime_local = local_tz.localize(datetime.datetime.combine(today, desired_end))

        if verbose:
            console.print(f"[dim]Desired time window (UTC): {start_datetime_local.astimezone(pytz.utc).strftime('%H:%M:%S')} to {end_datetime_local.astimezone(pytz.utc).strftime('%H:%M:%S')}[/dim]")
            console.print(f"[dim]Desired time window ({timezone}): {start_datetime_local.strftime('%H:%M:%S')} to {end_datetime_local.strftime('%H:%M:%S')}[/dim]")

        for activity in activities:
            # Parse game's start and end time (assuming UTC from API)
            try:
                start_time_utc = parser.isoparse(activity["startTime"])
                end_time_utc = parser.isoparse(activity["endTime"])
            except (KeyError, ValueError) as e:
                if verbose:
                    console.print(f"[dim]Skipping activity {activity.get('id', 'N/A')} due to missing/invalid time: {e}[/dim]")
                continue

            # Convert game time to user's local timezone
            start_time_local = start_time_utc.astimezone(local_tz)
            end_time_local = end_time_utc.astimezone(local_tz)

            # --- Filtering Logic ---
            # Condition 1: Check if the game time is within the desired window
            is_time_match = (start_time_local >= start_datetime_local) and \
                            (start_time_local.time() <= desired_end)

            if verbose:
                duration_minutes = (end_time_utc - start_time_utc).total_seconds() / 60
                time_info = f"[dim]Venue ID {activity['id']} at '{activity['location']}' " + \
                           f"starts at {start_time_utc.strftime('%H:%M')} UTC / {start_time_local.strftime('%H:%M')} {timezone}. " + \
                           f"Duration: {duration_minutes} min, " + \
                           f"Time match: {'Yes' if is_time_match else 'No'}[/dim]"
                console.print(time_info)

            # Both conditions must be true
            if is_time_match:
                venue_id = activity.get("venueId")
                start_time_str = activity.get("startTime")
                end_time_str = activity.get("endTime")
                
                grouping_key = (venue_id, start_time_str, end_time_str)

                if grouping_key not in grouped_venues:
                    venue_lat = activity.get("lat")
                    venue_lng = activity.get("lng")
                    nearest_metro, distance_to_metro = find_nearest_metro(venue_lat, venue_lng, metro_stations)
                    
                    grouped_venues[grouping_key] = {
                        "venue_name": activity.get("venueName", "N/A"),
                        "start": start_time_local.strftime("%I:%M %p"),
                        "end": end_time_local.strftime("%I:%M %p"),
                        "venue_id": venue_id,
                        "nearest_metro": nearest_metro,
                        "distance_to_metro": distance_to_metro,
                        "court_count": 0
                    }
                
                grouped_venues[grouping_key]["court_count"] += 1

        # Convert the grouped dictionary to a list for sorting and display
        matching_venues = list(grouped_venues.values())

        # Sort venues by distance to the nearest metro station
        matching_venues.sort(key=lambda x: x['distance_to_metro'])

        # Display results
        if matching_venues:
            table = Table(title=f"Available Badminton Courts ({len(matching_venues)} unique slots found, sorted by Metro proximity)")

            table.add_column("Venue", style="cyan")
            table.add_column("Time Slot", style="green")
            table.add_column("Courts", style="blue")
            table.add_column("Nearest Metro", style="yellow")
            table.add_column("Distance", style="magenta")
            table.add_column("Booking Link", style="bright_blue")

            for venue in matching_venues:
                table.add_row(
                    f"{venue['venue_name']}",
                    f"{venue['start']} - {venue['end']}",
                    str(venue["court_count"]),
                    venue["nearest_metro"],
                    f"{venue['distance_to_metro']:.2f} km",
                    f"https://playo.co/venue/{venue['venue_id']}"
                )

            console.print(table)

            # Send to Telegram if requested
            if telegram:
                if not telegram_token or not telegram_chat_id:
                    console.print("[bold red]Error:[/bold red] Telegram token and chat ID are required for Telegram notifications.")
                    console.print("[dim]Set them with --telegram-token and --telegram-chat-id or via environment variables.[/dim]")
                else:
                    try:
                        send_to_telegram(matching_venues, telegram_token, telegram_chat_id)
                        console.print("[green]Results sent to Telegram successfully![/green]")
                    except Exception as e:
                        console.print(f"[bold red]Error sending to Telegram:[/bold red] {e}")
        else:
            console.print("[yellow]No courts found matching your criteria[/yellow]")
            if telegram and telegram_token and telegram_chat_id:
                try:
                    asyncio.run(send_telegram_message(
                        "No badminton courts found matching your criteria for today.",
                        telegram_token,
                        telegram_chat_id
                    ))
                    console.print("[green]Empty results notification sent to Telegram[/green]")
                except Exception as e:
                    console.print(f"[bold red]Error sending to Telegram:[/bold red] {e}")

    except requests.RequestException as e:
        console.print(f"[bold red]Error:[/bold red] Failed to connect to Playo API: {e}")
    except json.JSONDecodeError:
        console.print("[bold red]Error:[/bold red] Failed to parse API response")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] An unexpected error occurred: {e}")

def send_to_telegram(venues, token, chat_id):
    """Send venue information to Telegram as a nicely formatted message."""
    if not venues:
        return

    # Create a formatted message for Telegram
    message = "🏸 *Available Badminton Courts (sorted by Metro proximity)* 🏸\n\n"
    for i, venue in enumerate(venues, 1):
        message += f"*{i}. {venue['venue_name']}*\n"
        message += f"⏰ {venue['start']} - {venue['end']}\n"
        message += f"🏟️ Courts Available: {venue['court_count']}\n"
        message += f"🚇 {venue['nearest_metro']} ({venue['distance_to_metro']:.2f} km away)\n"
        message += f"🔗 [Book on Playo](https://playo.co/venue/{venue['venue_id']})\n\n"

    # Send the message
    asyncio.run(send_telegram_message(message, token, chat_id))

async def send_telegram_message(message, token, chat_id):
    """Send a message to Telegram using the Bot API."""
    bot = Bot(token=token)
    await bot.send_message(
        chat_id=chat_id,
        text=message,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


if __name__ == "__main__":
    find_games()