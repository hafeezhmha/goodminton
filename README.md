# Goodminton 🏸

<p align="center">
  <img src="assets/bot-logo.jpeg" alt="Goodminton Bot Logo" width="200"/>
</p>

**Goodminton** is an intelligent, AI-powered Telegram bot that helps you find and book badminton courts on the [Playo](https://playo.co/) app. 

Powered by [Groq](https://groq.com/) for natural language understanding, you can chat with it conversationally to find courts on specific dates and times. The bot prioritizes venues near Bangalore's Namma Metro stations, making it the perfect tool for planning your next game.

## Demo

<p align="center">
  <img src="assets/demo.jpeg" alt="Goodminton Bot Demo" width="300"/>
</p>

## Features

- **Natural Language Processing**: Simply ask for what you want in plain English (e.g., "courts tomorrow from 8 to 10 pm").
- **Personalized Location Search**: Set your home or office location once, and the bot will always search for courts nearby.
- **Interactive Chat**: No more rigid commands. Have a conversation directly with your bot in Telegram.
- **Metro Proximity Prioritization**: Automatically finds the nearest Namma Metro station for each venue and sorts the results accordingly.
- **Court Availability Count**: See exactly how many courts are available at a venue for a given time slot, perfect for group bookings.
- **Serverless & Scalable**: Deployed as a serverless function on Vercel for high availability and zero maintenance.

## How It Works

Goodminton has been re-architected into an intelligent web application:

1.  **Vercel Hosting**: The project runs as a Python serverless function hosted on Vercel.
2.  **Flask Web Server**: A lightweight Flask app listens for incoming messages from Telegram via a webhook.
3.  **Location Storage**: To persist user locations across sessions in a serverless environment, the bot uses **Vercel Blob Storage**. It reads and writes a single `user_locations.json` file in the cloud, associating your Telegram chat ID with a latitude and longitude. This solves the "read-only filesystem" issue common in serverless platforms.
4.  **Groq LLM Parser**: When you send a `/find` command, the query is first sent to the Groq API. The `llama3-70b-8192` model parses your text and converts it into structured data (date, start time, end time).
5.  **Unofficial Playo API**: The bot queries an unofficial, public Playo API endpoint (`/activity-public/list/location`) that lists all public "activities". It uses your saved location for the search, or a default location if one hasn't been set.
6.  **Intelligent Filtering**: Since there is no official API for booking slots, the bot uses a custom filtering logic to sift through the activities. It identifies listings that are actually bookable court slots by filtering for activities that have a low number of participants (`joineeCount <= 1`) and are not skill-based games (`type: 0`).
7.  **Telegram Bot**: The final, formatted, and sorted list of courts is sent back to you in your Telegram chat.

## Setup Instructions

Deploying your own instance of Goodminton is fast and free.

### Step 1: Get the Code & API Keys

1.  **Fork the Repository**: [Fork this repository](https://github.com/your-username/goodminton/fork) into your own GitHub account.
2.  **Get a Telegram Bot Token**:
    - Chat with `@BotFather` on Telegram, send `/newbot`, and follow the prompts.
    - Copy the **API Token** it gives you.
    - **Crucially, start a chat with your new bot** by sending it a `/start` message.
3.  **Get a Groq API Key**:
    - Go to [console.groq.com/keys](https://console.groq.com/keys) and sign up for a free account.
    - Create and copy a new **API Key**.

### Step 2: Deploy to Vercel & Create Storage

1.  **Sign up:** Go to [vercel.com](https://vercel.com) and create an account by signing up with your GitHub profile.
2.  **Create a Blob Store:**
    - On your Vercel dashboard, go to the **Storage** tab.
    - Click **Create Database** and select **Blob**.
    - Link it to your project when prompted.
    - Go into your new Blob store's settings and generate a **Read-Write Token**. Copy this token.
3.  **Create a New Project:** On your Vercel dashboard, click "Add New..." -> "Project".
4.  **Import Your Repository:** Select your forked `goodminton` repository and click **Import**.
5.  **Configure Environment Variables:** Before deploying, expand the **Environment Variables** section and add the following three secrets:
    - **Name**: `TELEGRAM_BOT_TOKEN`, **Value**: *Your token from `@BotFather`*.
    - **Name**: `GROQ_API_KEY`, **Value**: *Your key from Groq*.
    - **Name**: `BLOB_READ_WRITE_TOKEN`, **Value**: *Your new Blob store token*.
6.  **Deploy:** Click the **Deploy** button. Vercel will build and deploy your application, which might take a few minutes.

### Step 3: Set the Telegram Webhook

Once Vercel gives you your public URL (e.g., `https://goodminton.vercel.app`), you need to tell Telegram where to send messages.

Simply open this URL in your browser, adding `/set_webhook` to the end:

**`https://your-vercel-url.vercel.app/set_webhook`**

You should see a message confirming the webhook was set. Your bot is now live!

## Usage

- Start a chat with your bot on Telegram.
- Use the `/start` command to see the welcome message.
- Use `/find <query>` to search for courts. For example:
  - `/find courts tomorrow evening`
  - `/find courts on July 20th from 5pm to 8pm`
- Use `/setlocation` to set your location. The bot will then prioritize venues closest to you in the search results.
- The bot will reply with a list of available courts.

## Customization & Local Development

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/goodminton.git
    cd goodminton
    ```
2.  **Set up a virtual environment**:
    ```bash
    python -m venv venv
    source venv/bin/activate
    # On Windows cmd, use `venv\Scripts\activate`
    ```
3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Set Environment Variables**:
    -   **On Linux/macOS/WSL**:
        ```bash
        export TELEGRAM_BOT_TOKEN="your-telegram-token"
        export GROQ_API_KEY="your-groq-key"
        export BLOB_READ_WRITE_TOKEN="your-vercel-blob-token"
        ```
    -   **On Windows Command Prompt**:
        ```cmd
        set TELEGRAM_BOT_TOKEN="your-telegram-token"
        set GROQ_API_KEY="your-groq-key"
        set BLOB_READ_WRITE_TOKEN="your-vercel-blob-token"
        ```
5.  **Run the local Flask server**:
    Open a terminal and run the following command. This makes the server accessible from your local network (and from WSL).
    ```bash
    flask run --host=0.0.0.0
    ```
6.  **Test with `curl`**:
    Open a **second terminal** (a WSL terminal if your server is running on Windows) and use `curl` to send a test message. Replace the IP with your machine's local IP if needed.
    ```bash
    curl -X POST http://127.0.0.1:5000/api/telegram -H "Content-Type: application/json" -d '{"update_id":12345,"message":{"message_id":54321,"date":1625987654,"chat":{"id":98765,"type":"private"},"text":"/find courts for tomorrow evening"}}'
    ```
    Check the terminal where Flask is running to see the detailed log output. 