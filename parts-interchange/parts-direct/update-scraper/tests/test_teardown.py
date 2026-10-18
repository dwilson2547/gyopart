import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import run_v2  # noqa: E402


class _Updater:
    def __init__(self, blocks: bool):
        self.blocks = blocks
        self.release = threading.Event()
        self.closed = False

    def close(self):
        if self.blocks:
            self.release.wait(5)  # a browser close that never returns
        self.closed = True


def test_teardown_that_returns_does_not_exit(monkeypatch):
    exits = []
    monkeypatch.setattr(run_v2.os, "_exit", exits.append)
    u = _Updater(blocks=False)
    run_v2.close_within(u, 0.2, 75)
    assert u.closed and exits == []


def test_blocked_teardown_exits_with_the_runs_code(monkeypatch, capsys):
    exited = threading.Event()
    codes = []
    u = _Updater(blocks=True)

    def fake_exit(code):
        codes.append(code)
        exited.set()
        u.release.set()  # the real os._exit never returns; let the blocked close finish so the test ends

    monkeypatch.setattr(run_v2.os, "_exit", fake_exit)
    run_v2.close_within(u, 0.2, 75)
    assert exited.is_set() and codes == [75]
    assert "browser teardown still blocked" in capsys.readouterr().out
