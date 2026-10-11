# Update scraper v2 (docs/design-v2.md). Build context: parts-interchange/parts-direct/, so the shared
# parser in singlethreaded-scraper/src/utils is copied alongside. Built via the gyopart repo's compose.
# No browser in the image: it drives scrape-stack's browserless over CDP (BROWSERLESS_URL).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY update-scraper/requirements.txt ./update-scraper/
RUN pip install --no-cache-dir -r update-scraper/requirements.txt
COPY singlethreaded-scraper/src/utils ./singlethreaded-scraper/src/utils
COPY update-scraper/*.py ./update-scraper/

WORKDIR /app/update-scraper
USER 10001
CMD ["python", "run_v2.py"]
