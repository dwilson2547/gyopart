import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def captured():
    return json.loads((Path(__file__).parent / "fixtures/ferrari-crankcase.json").read_text())
