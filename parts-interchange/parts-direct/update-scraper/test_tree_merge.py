import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tree_merge import merge_recent_tree


def test_merge_recent_tree_preserves_old_years_and_replaces_recent_engines():
    existing_tree = {
        "2019": {"makes": {"ford": {"models": {}}}},
        "2024": {
            "makes": {
                "ford": {
                    "models": {
                        "mustang": {
                            "trims": {
                                "gt": {
                                    "engines": {
                                        "v8": {
                                            "page_url": "old-url",
                                            "done": True,
                                            "cat_links": [{"url": "old-cat", "done": True}],
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
    }

    recent_tree = {
        "2024": {
            "makes": {
                "ford": {
                    "models": {
                        "mustang": {
                            "trims": {
                                "gt": {
                                    "engines": {
                                        "v8": {
                                            "page_url": "new-url",
                                            "categories": {},
                                        },
                                        "ecoboost": {
                                            "page_url": "eco-url",
                                            "categories": {},
                                        },
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    merged_tree = merge_recent_tree(existing_tree, recent_tree)

    assert "2019" in merged_tree
    assert merged_tree["2024"]["makes"]["ford"]["models"]["mustang"]["trims"]["gt"]["engines"]["v8"] == {
        "page_url": "new-url",
        "categories": {},
    }
    assert merged_tree["2024"]["makes"]["ford"]["models"]["mustang"]["trims"]["gt"]["engines"]["ecoboost"] == {
        "page_url": "eco-url",
        "categories": {},
    }
