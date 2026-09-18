"""XVF3800 tuning helper — parsing and the daemon-first / USB-fallback write order (no hardware)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import xmos_audio as x  # noqa: E402


def test_parse_params():
    assert x.parse_params("PP_NLATTENONOFF=0") == [("PP_NLATTENONOFF", 0.0)]
    assert x.parse_params(" pp_gamma_enl = 1.1 ,bogus, X=abc, PP_DTSENSITIVE=1") == [
        ("PP_GAMMA_ENL", 1.1), ("PP_DTSENSITIVE", 1.0)]
    assert x.parse_params("") == [] and x.parse_params(None) == []


def test_apply_skips_when_already_set(monkeypatch):
    monkeypatch.setattr(x, "read_param", lambda n, timeout=5.0: [0])
    monkeypatch.setattr(x, "_write_via_daemon", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not write")))
    assert x.apply_params("PP_NLATTENONOFF=0", log=lambda *a, **k: None) == {"PP_NLATTENONOFF": "already"}


def test_apply_falls_back_to_usb_and_verifies(monkeypatch):
    state = {"v": 1}
    monkeypatch.setattr(x, "read_param", lambda n, timeout=5.0: [state["v"]])
    monkeypatch.setattr(x, "_write_via_daemon", lambda n, v, timeout=10.0: False)   # Pollen's float→int bug
    def usb(n, v, timeout=60.0):
        state["v"] = int(v); return True
    monkeypatch.setattr(x, "_write_via_usb", usb)
    assert x.apply_params("PP_NLATTENONOFF=0", log=lambda *a, **k: None) == {"PP_NLATTENONOFF": "ok"}


def test_apply_reports_failure(monkeypatch):
    monkeypatch.setattr(x, "read_param", lambda n, timeout=5.0: [1])
    monkeypatch.setattr(x, "_write_via_daemon", lambda *a, **k: False)
    monkeypatch.setattr(x, "_write_via_usb", lambda *a, **k: False)
    assert x.apply_params("PP_NLATTENONOFF=0", log=lambda *a, **k: None) == {"PP_NLATTENONOFF": "failed"}


def test_empty_spec_is_a_no_op(monkeypatch):
    monkeypatch.setenv("VOICE_XMOS_PARAMS", "")
    assert x.apply_params(log=lambda *a, **k: None) == {}
