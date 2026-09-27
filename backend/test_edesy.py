import asyncio
import logging

import httpx

from services.communication import (
    CommunicationService,
    EdesyVoiceProvider,
    EmergencyContext,
    MockMessageProvider,
    MockVoiceProvider,
    get_communication_service,
)

TEST_API_KEY = "test-dummy-key-not-real"  # Test-only dummy, never a real key.


def _context(destination_phone="+919876543210"):
    return EmergencyContext(
        alert_id="alert-123",
        profile_id="profile-123",
        full_name="John Doe",
        latitude="12.9716",
        longitude="77.5946",
        destination_phone=destination_phone,
    )


class FakeResponse:
    def __init__(self, status_code=200, payload=None, json_error=False):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self._json_error = json_error
        self.text = str(self._payload)

    def json(self):
        if self._json_error:
            raise ValueError("not JSON")
        return self._payload


class FakeHttp:
    """Injectable stand-in for httpx.post. Records calls, never hits network."""

    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        return self.response


def _provider(fake_http, monkeypatch, agent_id=None):
    monkeypatch.setenv("EDESY_API_KEY", TEST_API_KEY)
    if agent_id is not None:
        monkeypatch.setenv("EDESY_AGENT_ID", agent_id)
    else:
        monkeypatch.delenv("EDESY_AGENT_ID", raising=False)
    return EdesyVoiceProvider(http_post=fake_http)


def test_edesy_success_sends_correct_request(monkeypatch):
    fake = FakeHttp(
        FakeResponse(200, {"conversationId": "conv-1", "callSid": "CA123", "status": "initiated"})
    )
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context()))

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://voice-agent.edesy.in/api/v1/calls"
    assert call["headers"] == {"Authorization": "Bearer " + TEST_API_KEY}
    assert call["json"] == {
        "agentId": 49976,
        "phoneNumber": "+919876543210",
        "variables": {"person_name": "John Doe"},
    }
    assert call["timeout"] == 10.0
    assert result.channel == "voice"
    assert result.provider == "edesy"
    assert result.status == "sent"
    assert result.external_id == "conv-1"


def test_edesy_custom_agent_id(monkeypatch):
    fake = FakeHttp(FakeResponse(200, {"conversationId": "conv-9"}))
    provider = _provider(fake, monkeypatch, agent_id="12345")

    result = asyncio.run(provider.place_call(_context()))

    assert fake.calls[0]["json"]["agentId"] == 12345
    assert result.status == "sent"


def test_edesy_invalid_agent_id_falls_back(monkeypatch):
    fake = FakeHttp(FakeResponse(200, {}))
    provider = _provider(fake, monkeypatch, agent_id="not-a-number")

    result = asyncio.run(provider.place_call(_context()))

    assert fake.calls[0]["json"]["agentId"] == 49976
    assert result.status == "sent"
    assert result.external_id is None


def test_edesy_parses_nested_response(monkeypatch):
    fake = FakeHttp(
        FakeResponse(200, {"data": {"callSid": "CA999", "status": "queued"}})
    )
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context()))

    assert result.status == "sent"
    assert result.external_id == "CA999"


def test_edesy_api_failure(monkeypatch):
    fake = FakeHttp(FakeResponse(401, {"message": "unauthorized"}))
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context()))

    assert result.status == "failed"
    assert "401" in (result.error or "")
    assert TEST_API_KEY not in (result.error or "")


def test_edesy_server_error(monkeypatch):
    fake = FakeHttp(FakeResponse(500, {"message": "boom"}))
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context()))

    assert result.status == "failed"
    assert "500" in (result.error or "")


def test_edesy_network_failure(monkeypatch):
    fake = FakeHttp(error=httpx.ConnectError("connection refused"))
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context()))

    assert result.status == "failed"
    assert "network error" in (result.error or "").lower()


def test_edesy_timeout(monkeypatch):
    fake = FakeHttp(error=httpx.TimeoutException("timed out"))
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context()))

    assert result.status == "failed"
    assert "timed out" in (result.error or "").lower()


def test_edesy_malformed_response(monkeypatch):
    fake = FakeHttp(FakeResponse(200, {}, json_error=True))
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context()))

    assert result.status == "failed"
    assert "malformed" in (result.error or "").lower()


def test_edesy_missing_api_key(monkeypatch):
    fake = FakeHttp()
    monkeypatch.delenv("EDESY_API_KEY", raising=False)
    provider = EdesyVoiceProvider(http_post=fake)

    result = asyncio.run(provider.place_call(_context()))

    assert result.status == "failed"
    assert "EDESY_API_KEY" in (result.error or "")
    assert fake.calls == []


def test_edesy_missing_destination_phone_skips(monkeypatch):
    fake = FakeHttp()
    provider = _provider(fake, monkeypatch)

    result = asyncio.run(provider.place_call(_context(destination_phone=None)))

    assert result.status == "skipped"
    assert fake.calls == []


def test_edesy_api_key_never_leaks(monkeypatch, caplog):
    fake = FakeHttp(FakeResponse(500, {"message": "denied"}))
    provider = _provider(fake, monkeypatch)

    with caplog.at_level(logging.INFO):
        result = asyncio.run(provider.place_call(_context()))

    assert TEST_API_KEY not in result.model_dump_json()
    for record in caplog.records:
        assert TEST_API_KEY not in record.getMessage()


def test_provider_selection(monkeypatch):
    monkeypatch.delenv("COMMUNICATION_VOICE_PROVIDER", raising=False)
    assert isinstance(get_communication_service().voice_provider, MockVoiceProvider)

    monkeypatch.setenv("COMMUNICATION_VOICE_PROVIDER", "mock")
    assert isinstance(get_communication_service().voice_provider, MockVoiceProvider)

    monkeypatch.setenv("COMMUNICATION_VOICE_PROVIDER", "edesy")
    service = get_communication_service()
    assert isinstance(service.voice_provider, EdesyVoiceProvider)
    assert isinstance(service.message_provider, MockMessageProvider)

    monkeypatch.setenv("COMMUNICATION_VOICE_PROVIDER", "something-else")
    assert isinstance(get_communication_service().voice_provider, MockVoiceProvider)


def test_default_mock_behavior_unchanged():
    service = CommunicationService(
        voice_provider=MockVoiceProvider(),
        message_provider=MockMessageProvider(),
    )
    results = asyncio.run(service.dispatch(_context()))
    assert results["voice"].status == "mock-sent"
    assert results["message"].status == "mock-sent"
