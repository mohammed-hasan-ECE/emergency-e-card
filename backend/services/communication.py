"""Provider-independent emergency communication layer (Milestone 1: mock-only).

No external API is ever contacted here. Mock providers only log safe,
non-sensitive fields and return structured results. Real providers
(Twilio/Asterisk/Firebase/...) can later implement the same
VoiceProvider / MessageProvider contracts without changing core SOS logic.

Never log: allergies, medical_conditions, medications, emergency_contacts,
credentials, or full medical records.
"""

import logging
import asyncio
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
    `destination_phone` is the verified emergency-contact number to dial.
    It is None when no structured number is available; providers must
    report "skipped" in that case and must never guess a number from
    free-form text.
    """

    alert_id: str
    profile_id: str
    full_name: str
    latitude: str
    longitude: str
    destination_phone: Optional[str] = None


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


EDESY_CALLS_URL = "https://voice-agent.edesy.in/api/v1/calls"
EDESY_DEFAULT_AGENT_ID = 49976
EDESY_HTTP_TIMEOUT_SECONDS = 10.0


def parse_coordinates(latitude, longitude) -> Optional[tuple]:
    """Parse stored string coordinates into (lat, lon) floats.

    Returns None when missing, non-numeric, or out of range.
    Shared by the SOS flow, the Edesy provider, and the voice tool so
    Milestone 4 can reuse the same source.
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return None
    return (lat, lon)


def google_maps_url(latitude, longitude) -> Optional[str]:
    """Public Google Maps URL for coordinates, or None when invalid."""
    coords = parse_coordinates(latitude, longitude)
    if coords is None:
        return None
    return f"https://www.google.com/maps?q={coords[0]},{coords[1]}"


def map_embed_url(latitude, longitude) -> Optional[str]:
    """Keyless OpenStreetMap embed URL with a marker, or None when invalid.

    Coordinates stay render data: callers must never present them as text.
    Tile fetches inherently reveal the viewed area to the tile provider;
    documented tradeoff of a keyless free map.
    """
    coords = parse_coordinates(latitude, longitude)
    if coords is None:
        return None
    lat, lon = coords
    delta = 0.01
    return (
        "https://www.openstreetmap.org/export/embed.html"
        f"?bbox={lon - delta}%2C{lat - delta}%2C{lon + delta}%2C{lat + delta}"
        f"&layer=mapnik&marker={lat}%2C{lon}"
    )


def _read_edesy_agent_id() -> int:
    raw = os.getenv("EDESY_AGENT_ID", str(EDESY_DEFAULT_AGENT_ID)).strip()
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid EDESY_AGENT_ID=%r; falling back to %d", raw, EDESY_DEFAULT_AGENT_ID)
        return EDESY_DEFAULT_AGENT_ID


def _find_first_present(payload: object, keys: tuple) -> Optional[str]:
    """Defensively extract the first present string value for given keys.

    Looks at the top level and one level inside common wrappers
    ("data", "call", "result") to tolerate Edesy response variations.
    """
    if not isinstance(payload, dict):
        return None
    candidates = [payload]
    for wrapper in ("data", "call", "result"):
        nested = payload.get(wrapper)
        if isinstance(nested, dict):
            candidates.append(nested)
    for candidate in candidates:
        for key in keys:
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


class EdesyVoiceProvider(VoiceProvider):
    """Real voice provider using Edesy's Calls API (Voice Agent).

    Sends POST {EDESY_CALLS_URL} with the Voice Agent's Agent ID, the
    emergency-contact phone number, and the `person_name` Dynamic Variable.
    Location is handled separately by the tracking system, never by voice.
    Never logs or returns the API Key.
    """

    provider_name = "edesy"

    def __init__(self, http_post=None):
        # `http_post` is injectable for tests; defaults to httpx.post.
        # Imported lazily so the module never requires network access.
        import httpx as _httpx

        self._http_post = http_post or _httpx.post
        self._httpx_errors = _httpx

    async def place_call(self, context: EmergencyContext) -> CommunicationResult:
        if not (context.destination_phone or "").strip():
            return CommunicationResult(
                channel="voice",
                provider=self.provider_name,
                status="skipped",
                error="No structured emergency-contact phone number available",
            )

        api_key = os.getenv("EDESY_API_KEY", "").strip()
        if not api_key:
            return CommunicationResult(
                channel="voice",
                provider=self.provider_name,
                status="failed",
                error="EDESY_API_KEY is not configured",
            )

        agent_id = _read_edesy_agent_id()
        destination = context.destination_phone.strip()
        body = {
            "agentId": agent_id,
            "phoneNumber": destination,
            "variables": {
                "person_name": context.full_name,
            },
        }

        try:
            # Sync httpx call runs in a thread so a slow provider cannot
            # stall the event loop (and delay parallel channels in gather).
            response = await asyncio.to_thread(
                self._http_post,
                EDESY_CALLS_URL,
                json=body,
                headers={"Authorization": "Bearer " + api_key},
                timeout=EDESY_HTTP_TIMEOUT_SECONDS,
            )
        except self._httpx_errors.TimeoutException:
            return CommunicationResult(
                channel="voice",
                provider=self.provider_name,
                status="failed",
                error="Edesy Calls API request timed out",
            )
        except self._httpx_errors.HTTPError as exc:
            return CommunicationResult(
                channel="voice",
                provider=self.provider_name,
                status="failed",
                error=f"Edesy Calls API network error: {type(exc).__name__}",
            )

        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int) or not 200 <= status_code < 300:
            return CommunicationResult(
                channel="voice",
                provider=self.provider_name,
                status="failed",
                error=f"Edesy Calls API error: HTTP {status_code}",
            )

        try:
            payload = response.json()
        except Exception:  # noqa: BLE001 - malformed body, report safely
            return CommunicationResult(
                channel="voice",
                provider=self.provider_name,
                status="failed",
                error="Edesy Calls API returned a malformed response",
            )

        external_id = _find_first_present(
            payload, ("conversationId", "conversation_id", "callSid", "call_sid", "id")
        )
        edesy_status = _find_first_present(payload, ("status", "callStatus", "state"))
        print(
            f"[EDESY VOICE] alert_id={context.alert_id} agent_id={agent_id} "
            f"external_id={external_id} status={edesy_status}",
            flush=True,
        )
        return CommunicationResult(
            channel="voice",
            provider=self.provider_name,
            status="sent",
            external_id=external_id,
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

    Voice provider selection is environment-controlled:

        COMMUNICATION_VOICE_PROVIDER=mock   -> MockVoiceProvider (default)
        COMMUNICATION_VOICE_PROVIDER=edesy  -> EdesyVoiceProvider

    Mock remains the default so tests and normal development can never
    accidentally place a real call. Edesy credentials come from
    EDESY_API_KEY / EDESY_AGENT_ID and are never hardcoded.
    """
    voice_provider_name = os.getenv("COMMUNICATION_VOICE_PROVIDER", "mock").strip().lower()
    if voice_provider_name == "edesy":
        voice_provider: VoiceProvider = EdesyVoiceProvider()
    else:
        if voice_provider_name not in ("mock", ""):
            logger.warning(
                "Unknown COMMUNICATION_VOICE_PROVIDER=%r; falling back to mock",
                voice_provider_name,
            )
        voice_provider = MockVoiceProvider()
    return CommunicationService(
        voice_provider=voice_provider,
        message_provider=MockMessageProvider(),
    )
