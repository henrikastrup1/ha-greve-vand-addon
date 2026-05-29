#!/usr/bin/env python3
"""Greve Vandforbrug — scraper til HA add-on.
   Bruger Playwright til at logge ind på minvandforsyning.dk og POST'e til HA API."""

import sys
import os
import json
import urllib.request
import re
from datetime import datetime

# Playwright import (installeret i Docker)
from playwright.sync_api import sync_playwright

# --- Konfiguration (fra supervisor) ---
HA_BASE = "http://supervisor/core/api"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SENSOR_ID = "sensor.vandforbrug"
STATE_FILE = "/data/vandforbrug-state.json"
TARGET_URL = "https://www.minvandforsyning.dk/?SK=grv"

now = datetime.now()
now_iso = now.isoformat()
today_str = now.strftime("%Y-%m-%d")


def ha_post(entity_id, state, attrs):
    """POST sensor state til Home Assistant REST API via Supervisor."""
    if not SUPERVISOR_TOKEN:
        print("⚠️ SUPERVISOR_TOKEN ikke sat — kan ikke POST'e til HA")
        return
    try:
        data = json.dumps({"state": state, "attributes": attrs}).encode()
        req = urllib.request.Request(
            f"{HA_BASE}/states/{entity_id}", data=data, method="POST"
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {SUPERVISOR_TOKEN}")
        urllib.request.urlopen(req, timeout=10)
        print(f"✅ Sensor {entity_id} opdateret til {state}")
    except Exception as e:
        print(f"⚠️ HA POST fejl: {e}")


def parse_danish_number(s):
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except (ValueError, AttributeError):
        return None


def load_state():
    default = {"previous_reading": None, "previous_date": None,
               "midnight_reading": None, "midnight_date": None}
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return default


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def fetch_consumption(email, password):
    """Log ind og hent vandforbrugsdata via Playwright."""
    data = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 960})
        page = ctx.new_page()

        page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        page.locator("button:has-text('Log på')").click()
        page.wait_for_timeout(3000)

        page.locator("button:has-text('e-mail og adgangskode')").click()
        page.wait_for_timeout(2000)

        page.fill("#signInName", email)
        page.fill("#password", password)
        page.wait_for_timeout(500)

        page.click("#next")
        page.wait_for_timeout(8000)

        body_text = page.evaluate("() => document.body.innerText")

        m = re.search(r"aflæst til:\s*([\d.,]+)", body_text)
        if m:
            data["latest_reading"] = parse_danish_number(m.group(1))

        m = re.search(r"måler:\s*(\d+)", body_text)
        if m:
            data["meter_id"] = m.group(1)

        browser.close()

    return data


def main():
    if len(sys.argv) < 3:
        print("⚠️ Brug: scraper.py <email> <password>")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]

    data = fetch_consumption(email, password)
    if not data or not data.get("latest_reading"):
        print("⚠️ Kunne ikke hente data")
        ha_post(SENSOR_ID, "fejl",
                {"last_updated": now_iso, "error": "fetch_failed"})
        return

    latest = data["latest_reading"]

    # Delta-beregning
    state = load_state()
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

    state["previous_reading"] = latest
    state["previous_date"] = today_str
    save_state(state)

    if midnight_date != today_str:
        state["midnight_reading"] = latest
        state["midnight_date"] = today_str
        save_state(state)
        today_m3 = 0.0

    attrs = {
        "last_updated": now_iso,
        "last_updated_pretty": now.strftime("%d.%m.%Y kl. %H:%M"),
        "meter_id": data.get("meter_id", "74698313"),
        "unit_of_measurement": "m³",
        "state_class": "total_increasing",
        "last_2h_m3": last_2h_m3,
        "today_m3": today_m3,
        "source": "minvandforsyning.dk",
    }

    ha_post(SENSOR_ID, str(latest), attrs)


if __name__ == "__main__":
    main()
