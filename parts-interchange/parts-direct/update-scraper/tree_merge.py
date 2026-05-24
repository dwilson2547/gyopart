import copy
from typing import Dict

from bootstrap import ensure_singlethreaded_src_path

ensure_singlethreaded_src_path()

from utils.Constants import keys


def merge_recent_tree(existing_tree: Dict, recent_tree: Dict) -> Dict:
    if not existing_tree:
        return copy.deepcopy(recent_tree)

    merged_tree = copy.deepcopy(existing_tree)
    for year_key, recent_year in recent_tree.items():
        if year_key not in merged_tree:
            merged_tree[year_key] = copy.deepcopy(recent_year)
            continue
        merged_tree[year_key] = _merge_branch(merged_tree[year_key], recent_year, keys.MAKES)
    return merged_tree


def _merge_branch(existing_branch: Dict, recent_branch: Dict, child_key: str) -> Dict:
    merged_branch = copy.deepcopy(existing_branch)

    for key_name, value in recent_branch.items():
        if key_name == child_key:
            continue
        merged_branch[key_name] = copy.deepcopy(value)

    if child_key not in recent_branch:
        return merged_branch

    merged_children = copy.deepcopy(existing_branch.get(child_key, {}))
    next_child_lookup = {
        keys.MAKES: keys.MODELS,
        keys.MODELS: keys.TRIMS,
        keys.TRIMS: keys.ENGINES,
    }

    for child_name, recent_child in recent_branch[child_key].items():
        if child_name not in merged_children:
            merged_children[child_name] = copy.deepcopy(recent_child)
            continue

        next_child_key = next_child_lookup.get(child_key)
        if next_child_key:
            merged_children[child_name] = _merge_branch(merged_children[child_name], recent_child, next_child_key)
        else:
            merged_children[child_name] = copy.deepcopy(recent_child)

    merged_branch[child_key] = merged_children
    return merged_branch
