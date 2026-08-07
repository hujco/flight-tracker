import logging

import pytest

from tracker import collect, config, notify, run


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """run.main() píše do DB/reportu/logu — presmeruj všetko do tmp."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "prices.db")
    monkeypatch.setattr(config, "REPORT_PATH", tmp_path / "report.html")
    monkeypatch.setattr(config, "LOG_PATH", tmp_path / "run.log")
    monkeypatch.setattr(notify, "maybe_notify", lambda *a, **k: (False, "test"))
    # basicConfig je no-op ked uz handlery existuju -> zhod ich medzi testami
    logging.getLogger().handlers.clear()
    return tmp_path


def test_run_exits_nonzero_when_collect_fails(isolated, monkeypatch):
    # Toto bola tichá chyba: beh skončil zeleno, nezapísal nič a v dátach
    # ostala diera na nerozoznanie od "Ryanair nemá let".
    def boom(*a, **k):
        raise RuntimeError("HTTP 503")

    monkeypatch.setattr(collect, "collect_once", boom)
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert "zber zlyhal" in str(exc.value)


def test_run_still_writes_report_when_collect_fails(isolated, monkeypatch):
    # report sa má pregenerovať z existujúcich dát aj po zlyhaní zberu
    monkeypatch.setattr(collect, "collect_once", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("boom")))
    with pytest.raises(SystemExit):
        run.main()
    assert config.REPORT_PATH.exists()


def test_run_succeeds_and_writes_report(isolated, monkeypatch):
    monkeypatch.setattr(collect, "collect_once", lambda conn, ts, **k: 0)
    run.main()   # bez SystemExit
    assert config.REPORT_PATH.exists()


def test_run_observed_at_is_utc_aware(isolated, monkeypatch):
    seen = {}

    def capture(conn, observed_at, **k):
        seen["ts"] = observed_at
        return 0

    monkeypatch.setattr(collect, "collect_once", capture)
    run.main()
    # naivný lokálny čas by pri lokálnom (launchd) behu bol CEST a miešal by sa
    # s UTC z GitHub Actions v tej istej tabuľke
    assert seen["ts"].endswith("+00:00")
