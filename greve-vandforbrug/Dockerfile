ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache \
    python3 py3-pip \
    chromium chromium-chromedriver \
    nss freetype harfbuzz ca-certificates ttf-freefont \
    jq

ENV PLAYWRIGHT_BROWSERS_PATH=/usr/bin
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

WORKDIR /app
COPY scraper.py run.sh ./
RUN pip3 install --break-system-packages playwright
RUN chmod a+x run.sh

CMD ["/app/run.sh"]
