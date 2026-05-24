import json
import os


base_path = '/home/daniel/kube-data/pvc-c9c3aff2-5e41-46eb-bce5-3192026b2cb5/gm/save_file_backups'

new_parts_file = 'parts.json'

existing_parts_file = 'parts_run2_part1.json'

new_parts = {}
old_parts = {}

with open(os.path.join(base_path, new_parts_file)) as f:
    new_parts = json.load(f)

with open(os.path.join(base_path, existing_parts_file)) as f:
    old_parts = json.load(f)

for key, entry in new_parts.items():
    if entry is not None:
        if key not in old_parts:
            old_parts[key] = entry

with open(os.path.join(base_path, 'parts_complete_v2.json'), 'w') as f:
    f.write(json.dumps(old_parts))
