import os
import json
import datetime
import pytz
import requests
import asyncio
from flask import Flask, request
from telegram import Bot, Update
from telegram.constants import ParseMode
from dateutil import parser
from math import sin, cos, sqrt, atan2, radians
from groq import Groq

app = Flask(__name__)

# --- Groq LLM Parsing Logic ---
def parse_query_with_groq(query_text):
    """
    Uses Groq's Llama 3.1 to parse natural language queries into structured data.
    """
    try:
        groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        system_prompt = f"""
        You are a smart assistant that helps users find badminton courts.
        Your task is to parse the user's query and extract the start time, end time, and a specific date.
        The current date is {datetime.date.today().strftime('%Y-%m-%d')}.
        - If the user does not specify a date, assume they mean today.
        - Convert all times to 24-hour HH:MM format.
        - Return the date in YYYY-MM-DD format.
        - Your response MUST be ONLY a valid JSON object. Do not add any other text, commentary, or markdown formatting like ```json.
        
        Example 1:
        User query: "10pm to 11pm on wednesday"
        JSON output: {{"start_time": "22:00", "end_time": "23:00", "date": "2024-07-03"}} (assuming today is before that Wednesday)

        Example 2:
        User query: "tomorrow from 7am to 9am"
        JSON output: {{"start_time": "07:00", "end_time": "09:00", "date": "{ (datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d') }"}}
        
        Example 3:
        User query: "8 to 9 pm"
        JSON output: {{"start_time": "20:00", "end_time": "21:00", "date": "{datetime.date.today().strftime('%Y-%m-%d')}"}}
        """

        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query_text}
            ],
            model="llama3-70b-8192",
            temperature=0.0,
        )
        response_content = chat_completion.choices[0].message.content
        return json.loads(response_content)
    except Exception as e:
        print(f"Groq parsing error: {e}")
        return None


# --- Re-usable Logic from our original script ---

def load_metro_stations():
    """Loads metro station data from a JSON file."""
    try:
        # Assumes metro_stations.json is in the root directory
        with open('metro_stations.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def find_nearest_metro(venue_lat, venue_lng, metro_stations):
    if not metro_stations: return None, float('inf')
    return min(
        ((s['name'], calculate_haversine_distance(venue_lat, venue_lng, s['lat'], s['lng'])) for s in metro_stations),
        key=lambda x: x[1]
    )

def find_courts_logic(search_date_str, start_time_str, end_time_str, lat=12.9783692, lng=77.6408356, radius=5, sport="SP5", timezone="Asia/Kolkata"):
    """
    This function contains the core logic to find courts.
    It returns a formatted string message with the results.
    """
    metro_stations = load_metro_stations()
    if not metro_stations:
        return "Error: Could not load metro station data."

    local_tz = pytz.timezone(timezone)
    
    try:
        search_date = datetime.datetime.strptime(search_date_str, "%Y-%m-%d").date()
        desired_start = datetime.datetime.strptime(start_time_str, "%H:%M").time()
        desired_end = datetime.datetime.strptime(end_time_str, "%H:%M").time()
    except ValueError:
        return "Invalid time/date format received from parser."

    start_datetime_local = local_tz.localize(datetime.datetime.combine(search_date, desired_start))
    end_datetime_local = local_tz.localize(datetime.datetime.combine(search_date, desired_end))

    # Convert the search date to the specific format Playo API expects
    playo_date_str = start_datetime_local.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    payload = {
        "lat": lat, "lng": lng, "cityRadius": radius, "gameTimeActivities": False,
        "page": 0, "lastId": "", "sportId": [sport], "booking": True,
        "date": [playo_date_str]
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"Sending payload to Playo API: {json.dumps(payload)}")

    try:
        response = requests.post("https://api.playo.io/activity-public/list/location", headers=headers, json=payload)
        response.raise_for_status()
        
        print(f"Received raw response from Playo API: {response.text}")
        
        data = response.json()
        activities = data.get("data", [])
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"Error communicating with Playo API: {e}")
        return "Sorry, there was an error contacting the Playo API."

    grouped_venues = {}
    for activity in activities:
        if not isinstance(activity, dict): continue
        
        try:
            start_time_utc = parser.isoparse(activity["startTime"])
            start_time_local = start_time_utc.astimezone(local_tz)

            if not (start_datetime_local <= start_time_local and start_time_local.time() <= desired_end):
                continue
            
            venue_id = activity.get("venueId")
            grouping_key = (venue_id, activity.get("startTime"), activity.get("endTime"))

            if grouping_key not in grouped_venues:
                nearest_metro, dist_to_metro = find_nearest_metro(activity.get("lat"), activity.get("lng"), metro_stations)
                grouped_venues[grouping_key] = {
                    "venue_name": activity.get("venueName", "N/A"),
                    "start": start_time_local.strftime("%I:%M %p"),
                    "end": parser.isoparse(activity.get("endTime")).astimezone(local_tz).strftime("%I:%M %p"),
                    "venue_id": venue_id, "nearest_metro": nearest_metro, "distance_to_metro": dist_to_metro, "court_count": 0
                }
            grouped_venues[grouping_key]["court_count"] += 1
        except (KeyError, ValueError):
            continue
            
    matching_venues = sorted(grouped_venues.values(), key=lambda x: x['distance_to_metro'])

    if not matching_venues:
        return f"No courts found for {search_date_str} between {start_time_str} and {end_time_str}."

    message = f"🏸 *Available Courts ({search_date_str}, {start_time_str} - {end_time_str})*\n\n"
    for i, venue in enumerate(matching_venues[:10], 1): # Limit to top 10 results
        message += f"*{i}. {venue['venue_name']}*\n"
        message += f"⏰ {venue['start']} - {venue['end']}\n"
        message += f"🏟️ Courts: {venue['court_count']}\n"
        message += f"🚇 {venue['nearest_metro']} ({venue['distance_to_metro']:.2f} km away)\n"
        message += f"🔗 [Book on Playo](https://playo.co/venue/{venue['venue_id']})\n\n"
        
    return message

# --- Flask Web Application ---

# A simple health check route
@app.route('/')
def home():
    return "Bot is alive!"

@app.route('/api/telegram', methods=['POST'])
def telegram_webhook():
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        bot = Bot(token=token)
        update = Update.de_json(request.get_json(force=True), bot)
        
        chat_id = update.message.chat_id
        text = update.message.text.strip()

        if text.startswith("/start"):
            reply_text = "Welcome! Find courts with:\n`/find <query>`\n(e.g., `/find courts from 8pm to 10pm tomorrow`)"
        elif text.startswith("/find"):
            query = text.replace("/find", "").strip()
            if not query:
                reply_text = "Please provide a query. For example:\n`/find courts from 8pm to 10pm tomorrow`"
            else:
                parsed_data = parse_query_with_groq(query)
                if parsed_data and "start_time" in parsed_data and "end_time" in parsed_data and "date" in parsed_data:
                    reply_text = find_courts_logic(
                        search_date_str=parsed_data["date"],
                        start_time_str=parsed_data["start_time"],
                        end_time_str=parsed_data["end_time"]
                    )
                else:
                    reply_text = "Sorry, I couldn't understand the date and time from your query. Please be more specific."
        else:
            reply_text = "Sorry, I didn't understand that. Use `/start` for help."

        async def _send_message_async():
            await bot.send_message(chat_id=chat_id, text=reply_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        
        asyncio.run(_send_message_async())

    except Exception as e:
        print(f"Error handling update: {e}")
        
    return 'ok'

# A manual setup route for convenience during development
@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    async def _async_set_webhook():
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            return "TELEGRAM_BOT_TOKEN environment variable not set!", 400
            
        host = os.environ.get("VERCEL_URL")
        if not host:
            return "VERCEL_URL environment variable not set!", 400

        bot = Bot(token=token)
        webhook_url = f"https://{host}/api/telegram"
        
        try:
            webhook_info = await bot.get_webhook_info()
            if webhook_info.url != webhook_url:
                await bot.set_webhook(webhook_url)
                return f"Webhook set to {webhook_url}", 200
            else:
                return f"Webhook is already set to {webhook_url}", 200
        except Exception as e:
            return str(e), 500

    try:
        return asyncio.run(_async_set_webhook())
    except Exception as e:
        # This catches potential runtime errors with asyncio itself
        return f"Error running async setup: {str(e)}", 500 