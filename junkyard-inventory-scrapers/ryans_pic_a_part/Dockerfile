# Build context: junkyard-inventory-scrapers/ (for scrape_contract.py). Built via docker compose.
# Playwright base image ships Chromium + system deps; its version must match requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY ryans_pic_a_part/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY scrape_contract.py ./
COPY ryans_pic_a_part/*.py ./

# pwuser is the image's non-root user; browsers are installed where it can read them.
USER pwuser
CMD ["python", "scraper.py"]
