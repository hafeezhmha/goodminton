# Playo Badminton Court Finder

This project is an automated script that finds available badminton courts on the [Playo](https://playo.co/) app, with a special focus on venues located near Bangalore's Namma Metro stations. It sends a daily summary of available court slots directly to your Telegram.

The primary goal of this tool is to simplify the process of finding and booking courts for a private group, by prioritizing convenience (metro proximity) and providing key information like the number of available courts.

![WhatsApp-Image-2024-05-15-at-12-09-17-PM](https://github.com/user-attachments/assets/b83a67d5-83c3-42e7-a9a7-951c277b73c8)


## Features

- **Venue-Focused Search**: Instead of looking for games hosted by others, it specifically finds empty court slots that you can book directly.
- **Metro Proximity Prioritization**: Automatically calculates the distance to the nearest Namma Metro station for each venue and sorts the results to show the closest ones first.
- **Court Availability Count**: Groups results to show exactly how many courts are available at a specific venue for a given time slot.
- **Automated Notifications**: Uses GitHub Actions to run on a daily schedule and sends a formatted message to a Telegram chat.
- **Customizable**: Easily change the search location, time window, and schedule directly within the GitHub Actions workflow file.

## How It Works

The project consists of three main components:

1.  **`finder.py`**: The core Python script that:
    - Makes a POST request to the Playo public API to fetch available booking slots.
    - Loads Bangalore metro station data from `metro_stations.json`.
    - Filters slots based on the desired time.
    - Calculates the distance from each venue to the nearest metro station.
    - Groups slots to count available courts.
    - Sends the final, sorted list to Telegram.
2.  **`metro_stations.json`**: A simple JSON file containing the names and GPS coordinates of Namma Metro stations.
3.  **`.github/workflows/badminton-checker.yml`**: A GitHub Actions workflow that automates the execution of the Python script on a schedule.

## Setup Instructions

To get this running, you just need a GitHub account and a Telegram account.

### Step 1: Get the Code

[Fork this repository](https://github.com/your-username/playo-api/fork) into your own GitHub account. Alternatively, you can clone it and push it to a new repository of your own.

### Step 2: Create a Telegram Bot & Get Credentials

You need two pieces of information from Telegram: a **Bot Token** and your **Chat ID**.

1.  **Create a Bot and Get the Token**:
    - Open Telegram and start a chat with the official `@BotFather`.
    - Send the `/newbot` command.
    - Follow the prompts to choose a name and username for your bot.
    - `@BotFather` will give you an **API Token**. Copy it.

2.  **Start Your Bot**:
    - Find your newly created bot in Telegram and send it a `/start` message. This is essential for the bot to be able to message you.

3.  **Get Your Chat ID**:
    - In Telegram, start a chat with `@userinfobot`.
    - It will instantly reply with your details. Copy the number listed as your **Id**.

### Step 3: Configure GitHub Secrets

You need to securely store your Telegram credentials in your GitHub repository so the workflow can use them.

1.  In your forked GitHub repository, go to **Settings** > **Secrets and variables** > **Actions**.
2.  Click **New repository secret** and add the following:
    - **Name**: `TELEGRAM_BOT_TOKEN`
    - **Secret**: Paste the API Token you got from `@BotFather`.
3.  Click **New repository secret** again and add your Chat ID:
    - **Name**: `TELEGRAM_CHAT_ID`
    - **Secret**: Paste the Chat ID you got from `@userinfobot`.

## Usage

### Automatic Scheduling

The script is configured to run automatically at 12:00 PM IST (6:30 AM UTC) every day from Monday to Friday. You can change this schedule by editing the `cron` expression in the `.github/workflows/badminton-checker.yml` file.

### Manual Trigger

You can also run the script manually at any time.

1.  Go to the **Actions** tab in your GitHub repository.
2.  Click on **Badminton Game Checker Base** in the left sidebar.
3.  Click the **Run workflow** dropdown on the right. Here you can customize the parameters for a one-time run (e.g., change the time or location).
4.  Click the green **Run workflow** button.

## Customization

- **Search Area & Time**: To permanently change the default search parameters (latitude, longitude, time, etc.) for the scheduled runs, edit the `env` section in `.github/workflows/badminton-checker.yml`.
- **Metro Stations**: If new metro stations open, you can add their name and coordinates to the `metro_stations.json` file.

## Local Development

To run the script on your local machine:

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/playo-api.git
    cd playo-api
    ```
2.  **Set up a virtual environment** (recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```
3.  **Install dependencies**:
    The script is configured to be run with `uv`, a fast Python installer.
    ```bash
    pip install uv
    uv pip install -r requirements.txt
    ```
4.  **Run the script**:
    You can pass arguments directly. Use `--help` to see all options.
    ```bash
    uv run finder.py --start-time "19:00" --end-time "21:00"
    ```
    To send Telegram notifications from your local machine, you'll need to set the environment variables:
    ```bash
    export TELEGRAM_BOT_TOKEN="your-token"
    export TELEGRAM_CHAT_ID="your-chat-id"
    uv run finder.py --telegram
    ``` 