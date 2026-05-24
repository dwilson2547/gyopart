main website: https://www.picknpull.com/

locations: https://www.picknpull.com/locations

seems inventory can be pulled by location or at least a radius around the location, may need special parsing to handle it https://www.picknpull.com/check-inventory/vehicle-search?distance=10&zip=60501

Expected output: 
1. Web scraper build using this skill /home/daniel/documents/workspace/skills/scraper-development-skill/SKILL.md
2. persist inventory of all locations in common format stored at ../common
3. script should be designed to run daily/weekly to keep the inventory table up to date
4. use webcache/request-auth libs to cache info and limit request rate like the other scrapers do
   1. request-auth handles rate limiting and 429 back off, no need to do that manually 
5. use sqlalchemy to connect to the db, use sqlite for local runs
6. output script and db stored in this directory (pic-n-pull)