ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python + Playwright + Chromium
RUN apk add --no-cache python3 py3-pip chromium chromium-chromedriver && \
    pip3 install --break-system-packages playwright && \
    playwright install chromium

# Copy app
WORKDIR /app
COPY scraper.py run.sh ./
RUN chmod a+x run.sh

CMD [ "/app/run.sh" ]
