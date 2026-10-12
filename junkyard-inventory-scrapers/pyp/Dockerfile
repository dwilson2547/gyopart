# Build context: junkyard-inventory-scrapers/ (for scrape_contract.py). Built via docker compose.
# Playwright's image ships Chromium and its system libraries; the pip version must match the image tag.
FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyp/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY scrape_contract.py ./
COPY pyp/*.py ./

USER pwuser
CMD ["python", "scraper.py"]
