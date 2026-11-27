"""Purely synthetic local budget tests: no network requests."""
import asyncio

from custom_components.fireservicerota import historical_request_budget as module


class FakeStore:
    state = {}

    def __init__(self, _hass, _version, key):
        self.key = key

    async def async_load(self):
        return self.state.get(self.key)

    async def async_save(self, value):
        self.state[self.key] = dict(value)


class FakeClient:
    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    async def async_api_get(self, _endpoint, _params):
        self.calls += 1
        if self.error:
            raise self.error
        return []


def test_historical_request_budget_survives_restart(monkeypatch):
    monkeypatch.setattr(module, "Store", FakeStore)
    monkeypatch.setattr(module, "HISTORICAL_REQUESTS_PER_UTC_DAY", 2)
    monkeypatch.setattr(module, "HISTORICAL_MIN_REQUEST_INTERVAL_SECONDS", 0)
    FakeStore.state.clear()

    async def scenario():
        first = module.HistoricalRequestBudget(None, "SYNTHETIC_ENTRY")
        await first.async_load()
        caller = FakeClient()
        await first.async_get(caller, "incidents", {"page": 1})
        await first.async_get(caller, "incidents", {"page": 2})
        assert first.status()["historical_attempts_remaining"] == 0
        reloaded = module.HistoricalRequestBudget(None, "SYNTHETIC_ENTRY")
        await reloaded.async_load()
        try:
            await reloaded.async_get(caller, "incidents", {"page": 3})
        except module.HistoricalRequestBudgetExceeded:
            pass
        else:
            raise AssertionError("Expected daily budget guard")
        assert caller.calls == 2
    asyncio.run(scenario())


def test_provider_denial_pauses_historical_calls(monkeypatch):
    monkeypatch.setattr(module, "Store", FakeStore)
    monkeypatch.setattr(module, "HISTORICAL_REQUESTS_PER_UTC_DAY", 40)
    monkeypatch.setattr(module, "HISTORICAL_MIN_REQUEST_INTERVAL_SECONDS", 0)
    FakeStore.state.clear()

    class ProviderDenied(Exception):
        status = 429

    async def scenario():
        budget = module.HistoricalRequestBudget(None, "SYNTHETIC_ENTRY_DENIED")
        await budget.async_load()
        client = FakeClient(error=ProviderDenied())
        try:
            await budget.async_get(client, "incidents", {"page": 1})
        except ProviderDenied:
            pass
        assert budget.status()["historical_requests_paused_today"] is True
        reloaded = module.HistoricalRequestBudget(None, "SYNTHETIC_ENTRY_DENIED")
        await reloaded.async_load()
        try:
            await reloaded.async_get(client, "incidents", {"page": 2})
        except module.HistoricalRequestBudgetExceeded:
            pass
        else:
            raise AssertionError("Expected provider cooldown")
        assert client.calls == 1
    asyncio.run(scenario())
