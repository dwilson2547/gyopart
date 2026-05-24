from typing import List

class ScrapeUrls:

    locations_url = 'https://enterpriseservice.pullapart.com/Location?siteTypeID=-1'
    all_makes_url = 'https://inventoryservice.pullapart.com/Make/'
    inventory_url = 'https://inventoryservice.pullapart.com/Vehicle/Search'
    vehicle_details_url = 'https://inventoryservice.pullapart.com/VehicleExtendedInfo/{location_id}/{ticket_id}/{line_id}'

    def get_locations_url(self):
        return self.locations_url
    
    def get_makes_url(self):
        return self.all_makes_url
    
    def get_inventory_url(self):
        return self.inventory_url
    
    def build_inventory_request_payload(self, locations: List[int], make_id: int):
        return {
            "Locations": locations,
            "MakeID": make_id,
            "Models": [],
            "Years": []
        }

    def get_vehicle_details_url(self, loc_id: int, ticket_id: int, line_id: int):
        return self.vehicle_details_url.format(location_id=str(loc_id), ticket_id=str(ticket_id), line_id=str(line_id))
