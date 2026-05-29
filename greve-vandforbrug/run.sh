#!/usr/bin/env bash
# MinVandforsyning Add-on
# Henter vandforbrug fra minvandforsyning.dk i en evig løkke
#
# Configuration (set i Supervisor UI):
#   url         - Forsyningens URL (default: https://www.minvandforsyning.dk/?SK=grv)
#   email       - Din login e-mail
#   password    - Din adgangskode
#   sensor_name - HA sensor entity ID (default: sensor.vandforbrug)
#   interval_minutes - Hvor ofte der hentes data (default: 120)

set -e

CONFIG_PATH=/data/options.json

echo "================================================"
echo "  MinVandforsyning add-on v1.0.0"
echo "  Starter op..."
echo "================================================"

while true; do
    # Læs config (Supervisor gemmer options i /data/options.json)
    URL=$(jq -r '.url // "https://www.minvandforsyning.dk/?SK=grv"' $CONFIG_PATH)
    EMAIL=$(jq -r '.email // ""' $CONFIG_PATH)
    PASSWORD=$(jq -r '.password // ""' $CONFIG_PATH)
    SENSOR_NAME=$(jq -r '.sensor_name // "sensor.vandforbrug"' $CONFIG_PATH)
    INTERVAL=$(jq -r '.interval_minutes // 120' $CONFIG_PATH)

    if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
        echo "⚠️  Email eller password mangler i add-on config!"
        echo "   Gå til Supervisor → Add-ons → MinVandforsyning → Configuration"
        sleep 60
        continue
    fi

    echo "📡  Henter vandforbrugsdata..."
    echo "    URL: $URL"
    echo "    Sensor: $SENSOR_NAME"

    python3 /app/scraper.py "$URL" "$EMAIL" "$PASSWORD" "$SENSOR_NAME"

    echo "😴  Venter ${INTERVAL} minutter til næste aflæsning..."
    sleep $((INTERVAL * 60))
done
