# Build context: junkyard-inventory-scrapers/ (for scrape_contract.py). Built via docker compose.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY u-pull-n-save/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY scrape_contract.py ./
COPY u-pull-n-save/*.py ./

USER 10001
CMD ["python", "scraper.py"]
