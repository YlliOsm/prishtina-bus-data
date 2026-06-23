#!/usr/bin/env python3
"""
Prishtina Bus and Weather Data Collector
Polls the Arvento bus API and WeatherAPI for Prishtina and saves timestamped snapshots.
Each scan day gets its own folder (001, 002, ...), and each poll is stored
directly inside that day folder as 001.json / 001.csv.
"""

import os
import json
import csv
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
API_URL = "https://arvento-buses.onrender.com/api"
LINES_URL = f"{API_URL}/lines"
BUSES_URL = f"{API_URL}/buses"

# Weather Configuration
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
WEATHER_URL = "http://api.weatherapi.com/v1/current.json"
WEATHER_CITY = "Prishtina"

DATA_DIR = Path("/home/pc-agent/prishtina-bus-data")
STATE_DIR = DATA_DIR / "state"
STALE_THRESHOLD_MINUTES = 2

# Kosovo timezone (CEST = UTC+2)
KOSOVO_TZ = timezone(timedelta(hours=2))

def get_local_time():
    """Get current time in Kosovo local timezone."""
    return datetime.now(KOSOVO_TZ)

def get_poll_counter():
    """Get next poll number for this day (001, 002...). Counter resets each new day."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(KOSOVO_TZ).strftime('%Y%m%d')
    state_counter_file = STATE_DIR / f"poll_counter_{today}"
    legacy_counter_file = DATA_DIR / f".poll_counter_{today}"

    if state_counter_file.exists():
        with open(state_counter_file, 'r') as f:
            count = int(f.read().strip())
    elif legacy_counter_file.exists():
        with open(legacy_counter_file, 'r') as f:
            count = int(f.read().strip())
    else:
        count = 0

    count += 1

    with open(state_counter_file, 'w') as f:
        f.write(str(count))

    return f"{count:03d}"

def fetch_bus_data():
    """Fetch bus and line data from the API."""
    buses_data = []
    lines_data = []
    
    try:
        resp = requests.get(BUSES_URL, timeout=30)
        resp.raise_for_status()
        buses_data = resp.json()
    except Exception as e:
        print(f"Error fetching buses: {e}")
    
    try:
        resp = requests.get(LINES_URL, timeout=30)
        resp.raise_for_status()
        lines_data = resp.json()
    except Exception as e:
        print(f"Error fetching lines: {e}")
    
    return buses_data, lines_data

def fetch_weather_data():
    """Fetch current weather for Prishtina."""
    try:
        params = {'key': WEATHER_API_KEY, 'q': WEATHER_CITY, 'aqi': 'no'}
        resp = requests.get(WEATHER_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching weather: {e}")
        return None

def process_bus_record(bus, poll_time, include_stale=False):
    """Process a bus record, converting UTC to local time. Optionally filter stale."""
    utc_time_str = bus.get('time', '')
    is_stale = False
    status = bus.get('derivedStatus', '')
    
    if status in ['offline', 'longIdle']:
        is_stale = True
    
    if utc_time_str:
        try:
            utc_dt = datetime.fromisoformat(utc_time_str.replace('Z', '+00:00'))
            local_time = utc_dt.astimezone(KOSOVO_TZ)
            local_time_str = local_time.isoformat()
            
            age_seconds = (poll_time.replace(tzinfo=KOSOVO_TZ) - local_time).total_seconds()
            if age_seconds > (STALE_THRESHOLD_MINUTES * 60):
                is_stale = True
        except:
            local_time_str = poll_time.isoformat()
            utc_time_str = poll_time.astimezone(timezone.utc).isoformat()
            is_stale = True
    else:
        local_time_str = poll_time.isoformat()
        utc_time_str = poll_time.astimezone(timezone.utc).isoformat()
        is_stale = True
    
    if is_stale and not include_stale:
        return None
    
    return {
        'poll_timestamp': int(poll_time.timestamp()),
        'poll_time': poll_time.strftime('%Y-%m-%d %H:%M:%S'),
        'local_time': local_time_str,
        'id': bus.get('id'),
        'plate': bus.get('plate', ''),
        'latitude': bus.get('latitude'),
        'longitude': bus.get('longitude'),
        'speed': bus.get('speed', 0),
        'address': bus.get('address', ''),
        'derived_status': bus.get('derivedStatus', ''),
        'utc_time': utc_time_str
    }

def save_snapshot_json(buses, lines, poll_time, poll_num, day_folder):
    """Save raw JSON snapshot directly under the day folder."""
    day_dir = DATA_DIR / "snapshots" / day_folder
    day_dir.mkdir(parents=True, exist_ok=True)
    
    snapshot = {
        'poll_timestamp': int(poll_time.timestamp()),
        'poll_time_iso': poll_time.isoformat(),
        'poll_number': poll_num,
        'buses': buses,
        'total_buses': len(buses),
        'moving_count': sum(1 for b in buses if b.get('derivedStatus') == 'moving')
    }
    
    snapshot_file = day_dir / f"{poll_num}.json"
    with open(snapshot_file, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    return snapshot_file

def save_snapshot_csv(buses, poll_time, poll_num, day_folder, folder, include_stale=True):
    """Save CSV snapshot directly under the day folder."""
    day_dir = folder / day_folder
    day_dir.mkdir(parents=True, exist_ok=True)
    
    csv_file = day_dir / f"{poll_num}.csv"
    
    processed = []
    for bus in buses:
        record = process_bus_record(bus, poll_time, include_stale)
        if record is not None:
            processed.append(record)
    
    if not processed:
        return csv_file, 0
    
    fieldnames = ['poll_timestamp', 'poll_time', 'local_time', 'id', 'plate', 'latitude', 
                  'longitude', 'speed', 'address', 'derived_status', 'utc_time']
    
    with open(csv_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed)
    
    return csv_file, len(processed)

def save_weather_snapshot(weather_data, poll_time, poll_num, day_folder):
    """Save weather data using the same sequential folder system."""
    if not weather_data:
        return None
    
    # Structure: weather_snapshots/001/001.json
    weather_dir = DATA_DIR / "weather_snapshots" / day_folder
    weather_dir.mkdir(parents=True, exist_ok=True)
    
    weather_file = weather_dir / f"{poll_num}.json"
    
    snapshot = {
        'poll_timestamp': int(poll_time.timestamp()),
        'poll_time': poll_time.strftime('%Y-%m-%d %H:%M:%S'),
        'poll_number': poll_num,
        'data': weather_data
    }
    
    with open(weather_file, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    return weather_file

def save_lines_static(lines, poll_time):
    """Save lines data (once)."""
    lines_file = DATA_DIR / "lines_static.json"
    if not lines_file.exists():
        with open(lines_file, 'w') as f:
            json.dump({
                'poll_time': poll_time.isoformat(),
                'lines': lines
            }, f, indent=2)
    
    lines_csv = DATA_DIR / "lines_static.csv"
    if not lines_csv.exists():
        processed = []
        for line in lines:
            processed.append({
                'line_id': line.get('_id'),
                'line_name': line.get('name'),
                'from_lat': line.get('from', {}).get('lat'),
                'from_lng': line.get('from', {}).get('lng'),
                'to_lat': line.get('to', {}).get('lat'),
                'to_lng': line.get('to', {}).get('lng'),
                'planned_journeys_weekday': line.get('plannedJourneysWeekdays', 0),
                'planned_journeys_weekend': line.get('plannedJourneysWeekend', 0)
            })
        
        fieldnames = ['line_id', 'line_name', 'from_lat', 'from_lng', 'to_lat', 'to_lng',
                      'planned_journeys_weekday', 'planned_journeys_weekend']
        
        with open(lines_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(processed)

def get_day_folder(today_str):
    """Get or advance the sequential day folder name."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_day_counter_file = STATE_DIR / "day_counter"
    legacy_day_counter_file = DATA_DIR / ".day_counter"

    counter_file = state_day_counter_file if state_day_counter_file.exists() else legacy_day_counter_file
    saved_date, day_num = today_str, "001"

    if counter_file.exists():
        try:
            saved_date, day_num = counter_file.read_text().strip().split(",", 1)
        except ValueError:
            saved_date, day_num = today_str, "001"

    if saved_date != today_str and counter_file.exists():
        day_num = f"{int(day_num) + 1:03d}"

    state_day_counter_file.write_text(f"{today_str},{day_num}")
    return day_num

def main():
    """Main collection function."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "csv_snapshots").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "csv_active").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "weather_snapshots").mkdir(parents=True, exist_ok=True)
    
    poll_time = get_local_time()
    today_str = poll_time.strftime('%Y%m%d')
    day_folder = get_day_folder(today_str)

    poll_num = get_poll_counter()  # Resets each day
    
    print(f"[{poll_time.strftime('%Y-%m-%d %H:%M:%S')}] Polling APIs...")
    
    # 1. Weather Collection
    weather_data = fetch_weather_data()
    if weather_data:
        weather_file = save_weather_snapshot(weather_data, poll_time, poll_num, day_folder)
        print(f"  Weather: weather_snapshots/{day_folder}/{weather_file.name}")
    else:
        print("  Weather: No data received!")

    # 2. Bus Collection
    buses, lines = fetch_bus_data()
    
    if buses:
        # Save raw JSON snapshot
        snap_file = save_snapshot_json(buses, lines, poll_time, poll_num, day_folder)
        print(f"  Bus Snapshot: snapshots/{day_folder}/{snap_file.name}")
        
        # Save CSV snapshot (all buses)
        csv_file, _ = save_snapshot_csv(buses, poll_time, poll_num, day_folder,
                                        DATA_DIR / "csv_snapshots", include_stale=True)
        print(f"  Bus CSV (all): csv_snapshots/{day_folder}/{csv_file.name}")
        
        # Save CSV active
        csv_active, active_count = save_snapshot_csv(buses, poll_time, poll_num, day_folder,
                                                     DATA_DIR / "csv_active", include_stale=False)
        print(f"  Bus CSV (active): csv_active/{day_folder}/{csv_active.name} ({active_count} buses)")
        
        # Save lines
        save_lines_static(lines, poll_time)
        
        # Status
        moving = sum(1 for b in buses if b.get('derivedStatus') == 'moving')
        print(f"  Bus Status: {moving} moving, {len(buses)} total, {active_count} active")
    else:
        print("  Bus Data: No data received!")

if __name__ == "__main__":
    main()
