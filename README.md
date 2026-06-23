# Prishtina Bus & Weather Data Collector

## Overview
This project implements a high-frequency data collection pipeline to archive real-time public transit (bus) GPS data and current weather conditions for Prishtina, Kosovo. This dataset is designed for subsequent machine learning training, specifically for analyzing the impact of weather on urban transit dynamics.

## Features
- **Bus Data Collection**: Polls the Arvento bus API every minute for real-time GPS coordinates, speeds, and statuses of all buses.
- **Weather Archiving**: Integrated with WeatherAPI.com to capture current weather conditions (temperature, humidity, condition) in Prishtina every minute.
- **Spatio-Temporal Synchronization**: Both datasets share an identical sequential archiving structure, allowing 1:1 alignment of weather and bus data per poll.
- **Archival Structure**: 
  - Sequential day folders (`001/`, `002/`, etc.) to track collection duration.
  - Sequential poll files (`001.json`, `002.json`...) resetting daily.
  - Support for 1,440 polls per day.
- **Automated Pipeline**: Managed via systemd timers and services for reliable minute-by-minute execution on boot.

## Project Structure
```
/home/pc-agent/prishtina-bus-data/
├── collect.py             # Main collection logic (Bus & Weather)
├── .env                  # API keys (ignored by git)
├── .gitignore            # Files to exclude from version control
├── run_tracker.sh        # Execution wrapper with file locking
├── prishtina-bus-tracker.service # systemd service definition
├── prishtina-bus-tracker.timer    # systemd timer (1m interval)
├── snapshots/            # Raw JSON bus snapshots
├── csv_snapshots/        # CSV format of all bus polls
├── csv_active/            # CSV of only active buses (<2m old)
├── weather_snapshots/    # Raw JSON weather snapshots
└── state/                 # Poll and day counters
```

## Setup & Configuration
1. **Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   WEATHER_API_KEY='your_api_key_here'
   ```

2. **Installation**:
   The project is configured to run as a system service. Ensure the `run_tracker.sh` is executable and the systemd unit is enabled.

3. **Dependencies**:
   Requires `requests`, `pandas`, and `python-dotenv`.
   ```bash
   pip install requests pandas python-dotenv
   ```

## Data Formats
- **Bus Snapshots**: JSON containing `poll_timestamp`, `poll_time_iso`, and an array of bus records.
- **Weather Snapshots**: JSON containing `poll_timestamp`, `poll_time`, and current weather details from WeatherAPI.
- **CSV Active**: Filtered CSV containing only buses that have reported data within the last 2 minutes.
