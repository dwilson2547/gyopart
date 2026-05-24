import json


with open('/home/daniel/documents/selenium_test_project/parts-direct-data/vw/parts.json') as f:
    data = json.load(f)

detail_keys = []

for item in list(data.keys()):
    part = data[item]

    if part['title']:
        print('found')

    deets = list(part['details'].keys())

    stats = {}

    for item in deets:
        if item not in detail_keys:
            detail_keys.append(item)
        
        length = len(part['details'][item])

        if item not in stats:
            stats[item] = {'max': length}
        else:
            if length > stats[item]['max']:
                stats[item]['max'] = length

print(detail_keys)
print(stats)