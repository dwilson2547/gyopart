List of junkyard sites to scrape inventory for, for each site create a folder and a readme.md. use the playwright mcp to develop a strategy to persist the junkyard inventory and save that strategy to readme.md. some sites may have the inventory for multiple locations, we want all of it. 

> if persisting the inventory would require tedious api calls or isn't feasible for any reason, please document those findings instead.

> Once the folder and document are created check off the site in the list below.

> if the site doesn't return location details in the api try to extract the location details from the website, pull_a_part returns address, etc from a locations call but many others will only have a location id, i'd like to have the address and contact info persisted for each yard as well, it will help with the scraper creation. 

> Note - Vin has been designed to not be necessary in this system but not having vin makes things extremely difficult, if you aren't able to extract the vin for the inventory please call that out in the readme at the top in an un-missable block. 

> Some of the sites have a 'recent arrivals' page that might prove useful as a start point on subsequent runs, if the recent page has vins we've seen before then we can stop there i'd think.

> check notes to see if the site pattern has been seen before, similarly if you see any re-useable patterns other sites might employ, please document them at notes so future scrapers can save time from your findings. notes is intended to be minimal prose, non-strategy or pattern perscriptive, just the main learnings from the session that could save time in the future.


List of sites: 

- [x] https://tearapart.com/inventory/
- [x] https://speedwayap.com/search-inventory/
- [x] https://chesterfieldauto.com/search-our-inventory-by-location - https://chesterfieldauto.com/newest-cars
- [x] https://inventory.sturtevantauto.com/
- [x] https://fenixupull.com/inventory/
- [x] https://www.pyp.com/inventory/cincinnati-1253/
- [x] https://ipullupull.com/inventory-pricing/?ipull_inventory_pricing_page=2&ipull_inventory_pricing_freshest=all
- [x] https://centralfloridapickandpay.com/vehicle-inventory/
- [x] https://jacksusedautoparts.com/vehicle-inventory/
- [x] https://www.las-parts.com/
- [x] https://wegotused.com/our-inventory/
- [x] https://midwayupull.com/ - questionable
- [x] https://indyupullit.com/vehicle-inventory/
- [x] https://baughmansupullit.com/inventory/
- [x] https://budgetupullit.com/current-inventory/
- [x] https://strickerautoparts.com/
- [x] https://utpap.com/orem-inventory/
- [x] https://www.usedautopartsfl.com/parts
- [x] https://www.mcdonoughautoparts.com/used-vehicle-gallery - highly questionable
- [x] https://picknpullsa.com/vehicle-inventory/ - probable duplicate, suspected existing pull-a-part location 
- [x] https://arizonaautoparts.com/search-inventory/
- [x] https://coloradoautoandparts.com/inventory-search/
- [x] https://upullit.jksalvageco.com/cars/
- [x] https://wrenchapart.com/vehicle-search