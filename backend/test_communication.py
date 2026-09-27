import asyncio
import logging

from services.communication import (
    CommunicationService,
    EmergencyContext,
    MockMessageProvider,
    MockVoiceProvider,
    get_communication_service,
)


def _context() -> EmergencyContext:
    return EmergencyContext(
        alert_id="alert-123",
        profile_id="profile-123",
        full_name="John Doe",
        latitude="12.9716",
        longitude="77.5946",
    )


def test_mock_voice_provider():
    result = asyncio.run(MockVoiceProvider().place_call(_context()))
    assert result.channel == "voice"
    assert result.provider == "mock"
    assert result.status == "mock-sent"
    assert result.error is None


def test_mock_message_provider():
    result = asyncio.run(MockMessageProvider().send(_context()))
    assert result.channel == "message"
    assert result.provider == "mock"
    assert result.status == "mock-sent"
    assert result.error is None


def test_communication_service_dispatch():
    service = CommunicationService(
        voice_provider=MockVoiceProvider(),
        message_provider=MockMessageProvider(),
    )
    results = asyncio.run(service.dispatch(_context()))
    assert set(results.keys()) == {"voice", "message"}
    assert results["voice"].status == "mock-sent"
    assert results["message"].status == "mock-sent"


def test_communication_failure_isolation():
    class FailingVoiceProvider(MockVoiceProvider):
        async def place_call(self, context):
            raise RuntimeError("mock voice boom")

    class FailingMessageProvider(MockMessageProvider):
        async def send(self, context):
            raise RuntimeError("mock message boom")

    # Voice fails, message still succeeds
    service = CommunicationService(
        voice_provider=FailingVoiceProvider(),
        message_provider=MockMessageProvider(),
    )
    results = asyncio.run(service.dispatch(_context()))
    assert results["voice"].status == "failed"
    assert "mock voice boom" in (results["voice"].error or "")
    assert results["message"].status == "mock-sent"

    # Both fail: dispatch still returns structured results, never raises
    service = CommunicationService(
        voice_provider=FailingVoiceProvider(),
        message_provider=FailingMessageProvider(),
    )
    results = asyncio.run(service.dispatch(_context()))
    assert results["voice"].status == "failed"
    assert results["message"].status == "failed"


def test_factory_defaults_to_mock():
    service = get_communication_service()
    assert isinstance(service, CommunicationService)
    assert service.voice_provider.provider_name == "mock"
    assert service.message_provider.provider_name == "mock"


def test_mock_providers_do_not_log_sensitive_data(caplog):
    # EmergencyContext carries no medical fields by design.
    context = _context()
    assert not hasattr(context, "allergies")
    assert not hasattr(context, "medical_conditions")
    assert not hasattr(context, "medications")
    assert not hasattr(context, "emergency_contacts")

    with caplog.at_level(logging.INFO):
        asyncio.run(get_communication_service().dispatch(context))

    sensitive = ["Peanuts", "Diabetes", "Insulin", "Jane Doe (0987654321)"]
    for record in caplog.records:
        message = record.getMessage()
        for term in sensitive:
            assert term not in message
