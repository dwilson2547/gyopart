import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from run_v2 import normalise_args  # noqa: E402


def test_operator_params_map_onto_the_cli():
    # What scrape-job-manager renders for {config: gm, refresh: false, discovery_interval_days: 30}
    argv = ["--config=gm", "--discovery_interval_days=30", "--refresh=false"]
    assert normalise_args(argv) == ["--config=gm", "--discovery-interval-days=30", "--no-refresh"]


def test_refresh_true_is_the_default_and_plain_flags_pass_through():
    assert normalise_args(["--refresh=true", "--max-vehicles", "2"]) == ["--max-vehicles", "2"]


def test_discovery_years_param():
    # A site whose catalogue starts further back than the default 7 years (Alfa: 2017).
    assert normalise_args(["--discovery_years=10"]) == ["--discovery-years=10"]
