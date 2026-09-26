"""Provider-independent emergency communication layer (Milestone 1: mock-only).

No external API is ever contacted here. Mock providers only log safe,
non-sensitive fields and return structured results. Real providers
(Twilio/Asterisk/Firebase/...) can later implement the same
VoiceProvider / MessageProvider contracts without changing core SOS logic.

Never log: allergies, medical_conditions, medications, emergency_contacts,
credentials, or full medical records.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmergencyContext:
    """Minimal safe context passed to communication providers.

    Only non-sensitive routing fields. No medical details.
    """

    alert_id: str
    profile_id: str
    full_name: str
    latitude: str
    longitude: str


class CommunicationResult(BaseModel):
    channel: str  # "voice" | "message"
    provider: str  # e.g. "mock"
    status: str  # "mock-sent" | "skipped" | "failed" | "sent" | "queued"
    external_id: Optional[str] = None
    error: Optional[str] = None


class VoiceProvider(ABC):
    @abstractmethod
    async def place_call(self, context: EmergencyContext) -> CommunicationResult:
        raise NotImplementedError


class MessageProvider(ABC):
    @abstractmethod
    async def send(self, context: EmergencyContext) -> CommunicationResult:
        raise NotImplementedError


class MockVoiceProvider(VoiceProvider):
    """Mock-only voice provider. Never dials or calls any external API."""

    provider_name = "mock"

    async def place_call(self, context: EmergencyContext) -> CommunicationResult:
        print(
            f"[MOCK VOICE] alert_id={context.alert_id} "
            f"profile_id={context.profile_id} provider={self.provider_name}",
            flush=True,
        )
        return CommunicationResult(
            channel="voice",
            provider=self.provider_name,
            status="mock-sent",
        )


class MockMessageProvider(MessageProvider):
    """Mock-only message provider. Never sends any real message."""

    provider_name = "mock"

    async def send(self, context: EmergencyContext) -> CommunicationResult:
        print(
            f"[MOCK MESSAGE] alert_id={context.alert_id} "
            f"profile_id={context.profile_id} provider={self.provider_name}",
            flush=True,
        )
        return CommunicationResult(
            channel="message",
            provider=self.provider_name,
            status="mock-sent",
        )


def _skipped(channel: str, reason: str) -> CommunicationResult:
    return CommunicationResult(
        channel=channel,
        provider="mock",
        status="skipped",
        error=reason,
    )


def _failed(channel: str, provider: str, error: str) -> CommunicationResult:
    return CommunicationResult(
        channel=channel,
        provider=provider,
        status="failed",
        error=error,
    )


class CommunicationService:
    """Orchestrates outbound voice + message dispatch.

    Best-effort: per-channel failures are captured as structured results
    and never raised, so callers must not roll back the alert on failure.
    """

    def __init__(
        self,
        voice_provider: Optional[VoiceProvider] = None,
        message_provider: Optional[MessageProvider] = None,
    ):
        self.voice_provider = voice_provider or MockVoiceProvider()
        self.message_provider = message_provider or MockMessageProvider()

    async def dispatch(self, context: EmergencyContext) -> Dict[str, CommunicationResult]:
        results: Dict[str, CommunicationResult] = {}
        try:
            results["voice"] = await self.voice_provider.place_call(context)
        except Exception as exc:  # noqa: BLE001 - must never propagate
            logger.warning(
                "Voice dispatch failed: alert_id=%s error=%s",
                context.alert_id,
                type(exc).__name__,
            )
            provider = getattr(self.voice_provider, "provider_name", "mock")
            results["voice"] = _failed("voice", provider, f"{type(exc).__name__}: {exc}")
        try:
            results["message"] = await self.message_provider.send(context)
        except Exception as exc:  # noqa: BLE001 - must never propagate
            logger.warning(
                "Message dispatch failed: alert_id=%s error=%s",
                context.alert_id,
                type(exc).__name__,
            )
            provider = getattr(self.message_provider, "provider_name", "mock")
            results["message"] = _failed("message", provider, f"{type(exc).__name__}: {exc}")
        return results


def get_communication_service() -> CommunicationService:
    """Factory for the active communication service.

    Milestone 1 supports mock-only. COMM_PROVIDER env is accepted for
    forward-compatibility ("mock" default); any other value falls back
    to mock so no real provider can be activated accidentally.
    """
    provider = os.getenv("COMM_PROVIDER", "mock").strip().lower()
    if provider not in ("mock", "log"):
        logger.warning("Unknown COMM_PROVIDER=%r; falling back to mock", provider)
    return CommunicationService(
        voice_provider=MockVoiceProvider(),
        message_provider=MockMessageProvider(),
    )
