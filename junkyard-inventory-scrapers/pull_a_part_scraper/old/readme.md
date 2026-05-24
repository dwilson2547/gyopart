Get locations
    Compare with db locations
    Update if needed
    URL: https://enterpriseservice.pullapart.com/Location?siteTypeID=-1
Get all makes
    Compare with db makes
    Update if needed
    URL: https://inventoryservice.pullapart.com/Make/
Get inventory for all locations, one query per make
    URL: https://inventoryservice.pullapart.com/Vehicle/Search
    Payload: {
        "Locations": [
            18
        ],
        "MakeID": 6,
        "Models": [],
        "Years": []
      }
    Response: [
            {
                "locationID": 18,
                "exact": [
                    {
                        "vinID": 95697,
                        "ticketID": 1081209,
                        "lineID": 1,
                        "locID": 18,
                        "locName": "Indianapolis",
                        "makeID": 6,
                        "makeName": "ACURA",
                        "modelID": 1098,
                        "modelName": "TSX",
                        "modelYear": 2004,
                        "row": 303,
                        "vin": "JH4CL95874C031434",
                        "dateYardOn": "2024-04-29T16:37:15.673",
                        "vinDecodedId": 23235,
                        "extendedInfo": null
                    }
                ],
                "other": [],
                "inventory": null
            }
        ]
For each Vehicle, get details
    URL: https://inventoryservice.pullapart.com/VehicleExtendedInfo/18/1081144/2
    First param is location
    Second param is vehicle ticketId
    Third param is vehicle lineId
Response: {
        "trim": "2.3 Premium",
        "vehicleType": "Car",
        "bodyType": "Coupe",
        "bodySubType": null,
        "doors": 2.0,
        "driveType": "FWD",
        "fuelType": "G",
        "engineBlock": "I",
        "engineCylinders": 4,
        "engineSize": 2.3,
        "engineAspiration": "N/A",
        "transType": "A",
        "transSpeeds": 4,
        "style": "2.3 Premium 2dr Coupe",
        "color": "White"
    }