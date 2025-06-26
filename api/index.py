import os
import json
import datetime
import pytz
import requests
import asyncio
from flask import Flask, request
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram import ReplyKeyboardMarkup, KeyboardButton
from dateutil import parser
from math import sin, cos, sqrt, atan2, radians
from groq import Groq
import vercel_blob

app = Flask(__name__)

# --- Location Storage (Now using Vercel Blob) ---
BLOB_FILENAME = 'user_locations.json'

def get_user_locations():
    """Reads all user locations from the Vercel Blob."""
    try:
        all_blobs = vercel_blob.list().get('blobs', [])
        user_locations_blob = next((b for b in all_blobs if b.get('pathname') == BLOB_FILENAME), None)
        
        if user_locations_blob:
            response = requests.get(user_locations_blob['url'])
            response.raise_for_status()
            return response.json()
        else:
            app.logger.info(f"'{BLOB_FILENAME}' not found in blob storage. Returning empty dict.")
            return {}
    except (requests.RequestException, json.JSONDecodeError) as e:
        app.logger.error(f"Error fetching or parsing user locations from blob: {e}")
        return {}
    except Exception as e:
        app.logger.error(f"An unexpected error occurred with Vercel Blob storage: {e}")
        return {}

def save_user_location(chat_id, lat, lng):
    """Saves a single user's location to the Vercel Blob."""
    locations = get_user_locations()
    locations[str(chat_id)] = {"lat": lat, "lng": lng}
    try:
        file_content_bytes = json.dumps(locations, indent=4).encode('utf-8')
        vercel_blob.put(BLOB_FILENAME, file_content_bytes)
        app.logger.info(f"Successfully saved user locations to blob for chat_id {chat_id}")
    except Exception as e:
        app.logger.error(f"Failed to save user locations to blob: {e}")

def get_user_location(chat_id):
    """Retrieves a single user's location."""
    locations = get_user_locations()
    return locations.get(str(chat_id))

def get_address_from_coords(lat, lng):
    """Converts coordinates to a human-readable address using OpenStreetMap."""
    try:
        headers = {"User-Agent": "GoodmintonTelegramBot/1.0"}
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Extract a user-friendly address string, preferring more specific parts
        address = data.get('address', {})
        parts = [
            address.get('suburb'),
            address.get('city_district'),
            address.get('city'),
            address.get('state'),
            address.get('country')
        ]
        # Filter out None values and join the first 2-3 parts for a concise name
        display_address = ", ".join(filter(None, parts[:2]))
        if not display_address:
             display_address = data.get('display_name')

        return display_address
    except Exception as e:
        app.logger.error(f"Reverse geocoding failed: {e}")
        return None

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
        app.logger.error(f"Groq parsing error: {e}")
        return None


# --- Re-usable Logic from our original script ---

def load_metro_stations():
    """Loads metro station data from a JSON file."""
    try:
        # Assumes metro_stations.json is in the root directory
        with open('metro_stations.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        app.logger.error(f"Error loading metro_stations.json: {e}")
        return []

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def find_nearest_metro(venue_lat, venue_lng):
    if not metro_stations: return None, float('inf')
    min_dist = float('inf')
    nearest_station_name = None
    for station in metro_stations:
        dist = calculate_haversine_distance(venue_lat, venue_lng, station['lat'], station['lng'])
        if dist < min_dist:
            min_dist = dist
            nearest_station_name = station['name']
    return nearest_station_name, min_dist

def find_courts_logic(search_date_str, start_time_str, end_time_str, lat=12.9783692, lng=77.6408356, radius=5, sport="SP5", timezone="Asia/Kolkata"):
    """
    This function contains the core logic to find courts.
    It returns a formatted string message with the results.
    """
    local_tz = pytz.timezone(timezone)
    
    try:
        search_date = datetime.datetime.strptime(search_date_str, "%Y-%m-%d").date()
        desired_start = datetime.datetime.strptime(start_time_str, "%H:%M").time()
        desired_end = datetime.datetime.strptime(end_time_str, "%H:%M").time()
    except ValueError:
        return "Invalid time/date format received from parser."

    start_datetime_local = local_tz.localize(datetime.datetime.combine(search_date, desired_start))

    # Convert the search date to the specific format Playo API expects
    playo_date_str = start_datetime_local.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    payload = {
        "lat": lat, "lng": lng, "cityRadius": radius, "gameTimeActivities": False,
        "page": 0, "lastId": "", "sportId": [sport], "booking": True,
        "date": [playo_date_str]
    }
    headers = {"Content-Type": "application/json"}
    
    app.logger.warning(f"Sending payload to Playo API: {json.dumps(payload)}")

    try:
        response = requests.post("https://api.playo.io/activity-public/list/location", headers=headers, json=payload)
        response.raise_for_status()
        
        app.logger.warning(f"Received raw response from Playo API: {response.text}")
        
        data = response.json()
        activities = data.get("data", {}).get("activities", [])
    except (requests.RequestException, json.JSONDecodeError) as e:
        app.logger.error(f"Error communicating with Playo API: {e}")
        return "Sorry, there was an error contacting the Playo API."

    grouped_venues = {}
    for activity in activities:
        if not isinstance(activity, dict): continue
        activity_id = activity.get('id', 'N/A')
        
        # --- FILTERING LOGIC WITH DEBUGGING ---
        if not activity.get("lat") or not activity.get("lng"):
            app.logger.warning(f"Skipping {activity_id}: Missing lat/lng.")
            continue

        if activity.get("type") != 0 or activity.get("joineeCount", 0) > 1:
            app.logger.warning(f"Skipping {activity_id}: type={activity.get('type')}, joinees={activity.get('joineeCount', 0)}.")
            continue
        
        try:
            start_time_utc = parser.isoparse(activity["startTime"])
            start_time_local = start_time_utc.astimezone(local_tz)

            if not (desired_start <= start_time_local.time() <= desired_end):
                app.logger.warning(f"Skipping {activity_id}: Time {start_time_local.time()} is outside window {desired_start}-{desired_end}.")
                continue
            
            app.logger.info(f"Activity {activity_id} passed filters, processing.")
            
            # Handle API inconsistency for venueId
            venue_id = activity.get("venueId") or activity.get("venueId d")
            if not venue_id:
                app.logger.error(f"Could not find venueId for activity {activity_id}")
                continue

            venue_lat = float(activity["lat"])
            venue_lng = float(activity["lng"])
            
            nearest_metro, dist_to_metro = find_nearest_metro(venue_lat, venue_lng)
            
            grouping_key = (venue_id, start_time_local.strftime('%H:%M'))
            
            if grouping_key not in grouped_venues:
                grouped_venues[grouping_key] = {
                    "venue_name": activity["venueName"],
                    "start_time": start_time_local.strftime('%I:%M %p'),
                    "location": activity.get("location", "N/A"),
                    "maps_link": f"https://www.google.com/maps/search/?api=1&query={venue_lat},{venue_lng}",
                    "venue_id": venue_id, "nearest_metro": nearest_metro, "distance_to_metro": dist_to_metro, "court_count": 0
                }
            grouped_venues[grouping_key]["court_count"] += 1
        except (KeyError, ValueError, TypeError) as e:
            app.logger.error(f"Error processing activity {activity_id}: {e}", exc_info=True)
            continue
            
    app.logger.warning(f"Found grouped venues: {json.dumps({str(k): v for k, v in grouped_venues.items()}, indent=2)}")
    matching_venues = sorted(grouped_venues.values(), key=lambda x: x['distance_to_metro'])

    if not matching_venues:
        return f"No courts found for {search_date_str} between {start_time_str} and {end_time_str}."

    message = f"🏸 *Available Courts ({search_date_str}, {start_time_str} - {end_time_str})*\n\n"
    for i, venue in enumerate(matching_venues[:10], 1): # Limit to top 10 results
        message += f"*{i}. {venue['venue_name']}*\n"
        message += f"⏰ {venue['start_time']}\n"
        message += f"🏟️ Courts: {venue['court_count']}\n"
        message += f"🚇 {venue['nearest_metro']} ({venue['distance_to_metro']:.2f} km away)\n"
        message += f"🔗 [Book on Playo](https://playo.co/venue/{venue['venue_id']})\n\n"
        
    return message

# --- Flask Web Application ---
metro_stations = load_metro_stations()

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
        
        if not update.message:
            return 'ok'

        chat_id = update.message.chat_id
        text = update.message.text
        location = update.message.location

        # Handle incoming location messages
        if location:
            lat, lng = location.latitude, location.longitude
            save_user_location(chat_id, lat, lng)
            
            # Get address for confirmation message
            address = get_address_from_coords(lat, lng)
            if address:
                reply_text = f"✅ Your location has been updated to: *{address}*"
            else:
                reply_text = "✅ Your location has been saved!"

            async def _send_confirmation():
                await bot.send_message(chat_id=chat_id, text=reply_text, parse_mode=ParseMode.MARKDOWN)
            asyncio.run(_send_confirmation())
            return 'ok'

        if not text:
            return 'ok'
        
        text = text.strip()

        if text.startswith("/start"):
            reply_text = "Welcome! Find courts with:\n`/find <query>`\n\nOr set your search location:\n`/setlocation`"
        elif text.startswith("/setlocation"):
            async def _send_location_request():
                location_keyboard = KeyboardButton(text="📍 Share My Location", request_location=True)
                custom_keyboard = [[location_keyboard]]
                reply_markup = ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True, one_time_keyboard=True)
                await bot.send_message(chat_id=chat_id, text="Please tap the button below to share your location for future searches.", reply_markup=reply_markup)
            asyncio.run(_send_location_request())
            return 'ok' # We don't send a text reply, just the keyboard
        elif text.startswith("/find"):
            query = text.replace("/find", "").strip()
            if not query:
                reply_text = "Please provide a query. For example:\n`/find courts from 8pm to 10pm tomorrow`"
            else:
                parsed_data = parse_query_with_groq(query)
                if parsed_data and "start_time" in parsed_data and "end_time" in parsed_data and "date" in parsed_data:
                    
                    user_location = get_user_location(chat_id)
                    search_lat = 12.9783692 # Default lat
                    search_lng = 77.6408356 # Default lng

                    if user_location:
                        search_lat = user_location['lat']
                        search_lng = user_location['lng']
                        app.logger.info(f"Using saved location for chat {chat_id}")

                    reply_text = find_courts_logic(
                        search_date_str=parsed_data["date"],
                        start_time_str=parsed_data["start_time"],
                        end_time_str=parsed_data["end_time"],
                        lat=search_lat,
                        lng=search_lng
                    )
                else:
                    reply_text = "Sorry, I couldn't understand the date and time from your query. Please be more specific."
        else:
            reply_text = "Sorry, I didn't understand that. Use `/start` for help."

        app.logger.info(f"Generated reply: {reply_text}")
        async def _send_message_async():
            await bot.send_message(chat_id=chat_id, text=reply_text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        
        asyncio.run(_send_message_async())

    except Exception as e:
        app.logger.error(f"Error handling update: {e}")
        
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