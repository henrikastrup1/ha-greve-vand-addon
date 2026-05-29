#!/usr/bin/env python3
"""MinVandforsyning Add-on Scraper
   Henter vandforbrugsdata fra minvandforsyning.dk via Playwright og POST'er til HA.
   Virker med alle vandværker på platformen (Greve, Hvidovre, m.fl.)."""

import sys
import os
import json
import urllib.request
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# --- Configuration via command-line arguments ---
# These are passed from run.sh which reads them from Supervisor's /data/options.json
HA_BASE = "http://supervisor/core/api"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

now = datetime.now()
now_iso = now.isoformat()
today_str = now.strftime("%Y-%m-%d")


def ha_post(entity_id, state, attrs):
    """POST sensor state til Home Assistant REST API via Supervisor."""
    if not SUPERVISOR_TOKEN:
        print("⚠️ SUPERVISOR_TOKEN not set — cannot POST to HA")
        return
    try:
        data = json.dumps({"state": state, "attributes": attrs}).encode()
        req = urllib.request.Request(
            f"{HA_BASE}/states/{entity_id}", data=data, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {SUPERVISOR_TOKEN}")
        urllib.request.urlopen(req, timeout=10)
        print(f"✅ Sensor {entity_id} updated to {state}")
    except Exception as e:
        print(f"⚠️ HA POST error: {e}")


def parse_danish_number(s):
    """Convert Danish number format (1320,082 or 539.901) to float."""
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, AttributeError):
        return None


def load_state(state_file):
    """Load previous readings from state file."""
    default = {"previous_reading": None, "previous_date": None,
               "midnight_reading": None, "midnight_date": None}
    if not os.path.exists(state_file):
        return default
    try:
        with open(state_file) as f:
            return json.load(f)
    except Exception:
        return default


def save_state(state_file, state):
    """Save state to file."""
    try:
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def scrape(url, email, password):
    """Log in and fetch water consumption data via Playwright."""
    data = {}

    with sync_playwright() as p:
        chromium_path = "/usr/bin/chromium-browser"
        browser = p.chromium.launch(
            executable_path=chromium_path,
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(viewport={"width": 1280, "height": 960})
        page = ctx.new_page()

        print(f"🌐 Opening {url}...")
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # Click "Log på" (login button on landing page)
        print("🔑 Clicking login button...")
        page.locator("button:has-text('Log på')").click()
        page.wait_for_timeout(3000)

        # Select "Log ind med e-mail og adgangskode"
        print("📧 Selecting email login...")
        page.locator("button:has-text('e-mail og adgangskode')").click()
        page.wait_for_timeout(2000)

        # Fill credentials
        print("👤 Filling credentials...")
        page.fill("#signInName", email)
        page.fill("#password", password)
        page.wait_for_timeout(500)

        # Submit
        print("🚀 Signing in...")
        page.click("#next")
        page.wait_for_timeout(8000)

        # Parse dashboard
        body_text = page.evaluate("() => document.body.innerText")

        # Latest meter reading
        m = re.search(r"aflæst til:\s*([\d.,]+)", body_text)
        if m:
            data["latest_reading"] = parse_danish_number(m.group(1))

        # Meter ID
        m = re.search(r"måler:\s*(\d+)", body_text)
        if m:
            data["meter_id"] = m.group(1)

        # Address
        m = re.search(r"adresse:\s*([^.\n]+)", body_text)
        if m:
            data["address"] = m.group(1).strip()

        browser.close()

    return data


def main():
    if len(sys.argv) < 4:
        print("⚠️ Usage: scraper.py <url> <email> <password> [sensor_name]")
        print("   Example: scraper.py 'https://www.minvandforsyning.dk/?SK=grv' user@example.com 'mypass' sensor.vandforbrug")
        sys.exit(1)

    url = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]
    sensor_id = sys.argv[4] if len(sys.argv) > 4 else "sensor.vandforbrug"

    # State file per sensor (supports multiple sensors/utilities)
    safe_name = sensor_id.replace("sensor.", "").replace(".", "_")
    state_file = f"/data/{safe_name}-state.json"

    print(f"📊 Target sensor: {sensor_id}")

    data = scrape(url, email, password)
    if not data or not data.get("latest_reading"):
        print("⚠️ Failed to fetch data — check credentials and URL")
        ha_post(sensor_id, "error",
                {"last_updated": now_iso, "error": "fetch_failed"})
        return

    latest = data["latest_reading"]
    print(f"📏 Latest reading: {latest} m³")

    # Calculate deltas
    state = load_state(state_file)
    prev_reading = state.get("previous_reading")
    prev_date = state.get("previous_date")
    midnight_reading = state.get("midnight_reading")
    midnight_date = state.get("midnight_date")

    last_2h_m3 = None
    if prev_reading is not None and prev_date is not None:
        last_2h_m3 = round(latest - prev_reading, 3)

    today_m3 = None
    if midnight_date == today_str and midnight_reading is not None:
        today_m3 = round(latest - midnight_reading, 3)

    # Update state
    state["previous_reading"] = latest
    state["previous_date"] = today_str
    save_state(state_file, state)

    if midnight_date != today_str:
        state["midnight_reading"] = latest
        state["midnight_date"] = today_str
        save_state(state_file, state)
        today_m3 = 0.0

    # Build attributes
    attrs = {
        "last_updated": now_iso,
        "last_updated_pretty": now.strftime("%d.%m.%Y kl. %H:%M"),
        "meter_id": data.get("meter_id", "N/A"),
        "address": data.get("address", "N/A"),
        "unit_of_measurement": "m³",
        "state_class": "total_increasing",
        "last_2h_m3": last_2h_m3,
        "today_m3": today_m3,
        "source": "minvandforsyning.dk",
    }

    if last_2h_m3 is not None:
        print(f"📈 Consumption last 2h: {last_2h_m3} m³")
    if today_m3 is not None:
        print(f"📈 Consumption today: {today_m3} m³")

    ha_post(sensor_id, str(latest), attrs)


if __name__ == "__main__":
    main()
