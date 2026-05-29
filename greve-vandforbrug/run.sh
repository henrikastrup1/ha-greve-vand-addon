#!/usr/bin/env bash
# Greve Vandforbrug Add-on
# Kører scraper.py i en evig løkke med konfigurerbart interval

set -e

CONFIG_PATH=/data/options.json

echo "Greve Vandforbrug add-on starter..."

while true; do
    # Læs config (Supervisor gemmer options i /data/options.json)
    EMAIL=$(jq -r '.email // ""' $CONFIG_PATH)
    PASSWORD=$(jq -r '.password // ""' $CONFIG_PATH)
    INTERVAL=$(jq -r '.interval_minutes // 120' $CONFIG_PATH)

    if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
        echo "⚠️ Email eller password mangler i add-on config!"
        echo "   Gå til Supervisor → Add-ons → Greve Vandforbrug → Configuration"
        sleep 60
        continue
    fi

    echo "📡 Henter vandforbrugsdata..."
    python3 /app/scraper.py "$EMAIL" "$PASSWORD"

    echo "😴 Venter ${INTERVAL} minutter til næste aflæsning..."
    sleep $((INTERVAL * 60))
done
