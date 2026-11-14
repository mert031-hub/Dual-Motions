"""429 bekleme/yeniden deneme mantığı (gerçek bekleme ve API yok)."""
import pytest

import llm_factory


class Err429(Exception):
    status_code = 429

    def __init__(self, retry_after=None):
        super().__init__("rate limit")
        if retry_after is not None:
            self.response = type("R", (), {"headers": {"retry-after": str(retry_after)}})()


@pytest.fixture
def sleeps(monkeypatch):
    log = []
    monkeypatch.setattr(llm_factory, "_sleep", log.append)
    return log


def test_429_bekler_ve_basarir(sleeps):
    n = {"i": 0}

    def fn():
        n["i"] += 1
        if n["i"] < 3:
            raise Err429(retry_after=5)
        return "ok"

    assert llm_factory.call_with_retry(fn) == "ok"
    assert sleeps == [6.0, 6.0]  # retry-after + 1 sn pay


def test_retry_after_yoksa_ustel_bekleme(sleeps):
    n = {"i": 0}

    def fn():
        n["i"] += 1
        if n["i"] < 3:
            raise Err429()
        return "ok"

    llm_factory.call_with_retry(fn)
    assert sleeps == [16.0, 31.0]


def test_uzun_bekleme_beklenmez_hemen_firlar(sleeps):
    def fn():
        raise Err429(retry_after=3600)  # günlük kota

    with pytest.raises(Err429):
        llm_factory.call_with_retry(fn, retries=0)
    assert sleeps == []


def test_429_siniri_asilinca_firlar(sleeps, monkeypatch):
    monkeypatch.setattr(llm_factory, "RATE_LIMIT_RETRIES", 2)
    calls = {"i": 0}

    def fn():
        calls["i"] += 1
        raise Err429(retry_after=1)

    with pytest.raises(Err429):
        llm_factory.call_with_retry(fn, retries=0)
    assert len(sleeps) == 2 and calls["i"] == 3  # 1 ilk + 2 bekleyerek yeniden deneme


def test_429_olmayan_hata_beklemez(sleeps):
    def fn():
        raise ValueError("şema")

    with pytest.raises(ValueError):
        llm_factory.call_with_retry(fn, retries=1)
    assert sleeps == []
