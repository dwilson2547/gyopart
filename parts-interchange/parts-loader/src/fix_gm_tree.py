import json
import os

base_path = '/home/daniel/kube-data/pvc-c9c3aff2-5e41-46eb-bce5-3192026b2cb5/gm'
split_tree_path = 'tree_split.json'

tree = {}

with open(os.path.join(base_path, split_tree_path)) as f:
    data = json.load(f)

for year, path in data.items():
    year_data = {}
    with open(os.path.join(base_path, path)) as f:
        year_data = json.load(f)
    
    tree[year] = year_data[year]

with open(os.path.join(base_path, 'tree.json'), 'w') as f:
    f.write(json.dumps(tree))