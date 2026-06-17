#!/usr/bin/env python3
"""
Prishtina Bus Data Collector
Polls the Arvento bus API and saves timestamped snapshots.
All folders share the same poll number (001, 002...)
"""

import json
import csv
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Configuration
API_URL = "https://arvento-buses.onrender.com/api"
LINES_URL = f"{API_URL}/lines"
BUSES_URL = f"{API_URL}/buses"
DATA_DIR = Path("/home/pc-agent/prishtina-bus-data")
STALE_THRESHOLD_MINUTES = 2

# Kosovo timezone (CEST = UTC+2)
KOSOVO_TZ = timezone(timedelta(hours=2))

def get_local_time():
    """Get current time in Kosovo local timezone."""
    return datetime.now(KOSOVO_TZ)

def get_poll_counter():
    """Get next poll number for this day (001, 002...). Counter resets each new day.
    Also handles subfolder creation every 1000 files (001-999 -> subfolder 001, 1000-1999 -> subfolder 002, etc.)"""
    today = datetime.now(KOSOVO_TZ).strftime('%Y%m%d')
    counter_file = DATA_DIR / f".poll_counter_{today}"
    
    if counter_file.exists():
        with open(counter_file, 'r') as f:
            count = int(f.read().strip())
    else:
        count = 0
    
    count += 1
    
    with open(counter_file, 'w') as f:
        f.write(str(count))
    
    # Calculate subfolder number (every 1000 files creates a new subfolder)
    subfolder_num = (count - 1) // 1000 + 1  # 1-999 -> 1, 1000-1999 -> 2, etc.
    poll_num = count
    
    return f"{subfolder_num:03d}", f"{poll_num:03d}"

def fetch_data():
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

def process_bus_record(bus, poll_time, include_stale=False):
    """Process a bus record, converting UTC to local time. Optionally filter stale."""
    utc_time_str = bus.get('time', '')
    is_stale = False
    status = bus.get('derivedStatus', '')
    
    # A bus is considered stale if:
    # 1. Timestamp is older than threshold, OR
    # 2. Status is 'offline' (not reporting at all), OR  
    # 3. Status is 'longIdle' (stopped for a long time)
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

def save_snapshot_json(buses, lines, poll_time, poll_num, day_folder, subfolder_num):
    """Save raw JSON snapshot. Creates subfolder every 1000 files."""
    # Structure: snapshots/001/001/001.json (day_folder/subfolder_num/poll_num)
    day_dir = DATA_DIR / "snapshots" / day_folder / subfolder_num
    day_dir.mkdir(parents=True, exist_ok=True)
    
    snapshot = {
        'poll_timestamp': int(poll_time.timestamp()),
        'poll_time_iso': poll_time.isoformat(),
        'poll_number': poll_num,
        'subfolder': subfolder_num,
        'buses': buses,
        'total_buses': len(buses),
        'moving_count': sum(1 for b in buses if b.get('derivedStatus') == 'moving')
    }
    
    snapshot_file = day_dir / f"{poll_num}.json"
    with open(snapshot_file, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    return snapshot_file

def save_snapshot_csv(buses, poll_time, poll_num, day_folder, subfolder_num, folder, include_stale=True):
    """Save CSV snapshot. Creates subfolder every 1000 files."""
    # Structure: csv_snapshots/001/001/001.csv (day_folder/subfolder_num/poll_num)
    day_dir = folder / day_folder / subfolder_num
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

def main():
    """Main collection function."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "csv_snapshots").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "csv_active").mkdir(parents=True, exist_ok=True)
    
    poll_time = get_local_time()
    # Use a sequential day counter (01, 02, 03...) instead of actual day of month
    # This counter increments each new day, starting from 01
    today_str = datetime.now(KOSOVO_TZ).strftime('%Y%m%d')
    day_counter_file = DATA_DIR / ".day_counter"
    
    if day_counter_file.exists():
        with open(day_counter_file, 'r') as f:
            saved_date, day_num = f.read().strip().split(',')
            if saved_date == today_str:
                day_folder = day_num
            else:
                # New day, increment (support 3+ digits: 01, 02... 99, 100...)
                day_folder = f"{int(day_num) + 1:03d}"
                with open(day_counter_file, 'w') as f:
                    f.write(f"{today_str},{day_folder}")
    else:
        # First run, start at 001
        day_folder = "001"
        with open(day_counter_file, 'w') as f:
            f.write(f"{today_str},{day_folder}")
    
    poll_num = get_poll_counter()  # Returns (subfolder_num, poll_num), resets each day
    
    print(f"[{poll_time.strftime('%Y-%m-%d %H:%M:%S')}] Polling API...")
    
    buses, lines = fetch_data()
    
    if buses:
        # Unpack the subfolder and poll number
        subfolder_num, poll_num = poll_num
        
        # 1. Save raw JSON snapshot
        snap_file = save_snapshot_json(buses, lines, poll_time, poll_num, day_folder, subfolder_num)
        print(f"  Snapshot: snapshots/{day_folder}/{subfolder_num}/{snap_file.name}")
        
        # 2. Save CSV snapshot (all buses) - same poll number
        csv_file, _ = save_snapshot_csv(buses, poll_time, poll_num, day_folder, subfolder_num,
                                        DATA_DIR / "csv_snapshots", include_stale=True)
        print(f"  CSV (all): csv_snapshots/{day_folder}/{subfolder_num}/{csv_file.name}")
        
        # 3. Save CSV active (only recently updated, <2 min) - same poll number
        csv_active, active_count = save_snapshot_csv(buses, poll_time, poll_num, day_folder, subfolder_num,
                                                      DATA_DIR / "csv_active", include_stale=False)
        print(f"  CSV (active): csv_active/{day_folder}/{subfolder_num}/{csv_active.name} ({active_count} buses)")
        
        # Save lines
        save_lines_static(lines, poll_time)
        
        # Status
        moving = sum(1 for b in buses if b.get('derivedStatus') == 'moving')
        print(f"  Status: {moving} moving, {len(buses)} total, {active_count} active")
    else:
        print("  No data received!")

if __name__ == "__main__":
    main()