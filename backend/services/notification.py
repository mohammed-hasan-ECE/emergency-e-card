"""Provider-neutral emergency-contact notification layer (mock-only).

Sends the SOS tracking link to the emergency contact, preferring WhatsApp
with a single SMS fallback. Mock providers never touch a network; real
provider selection will plug in here only after explicit approval.

Never include raw coordinates in notification content. Never log tokens,
phone numbers, credentials, or message bodies.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NotificationContext:
    """Minimum data needed to notify the emergency contact."""

    alert_id: str
    profile_name: str
    tracking_url: str
    destination_phone: str


class NotificationResult(BaseModel):
    channel: str  # "whatsapp" | "sms"
    provider: str  # e.g. "mock-whatsapp"
    status: str  # "sent" | "failed" | "skipped"
    external_id: Optional[str] = None
    error: Optional[str] = None


class MessageProvider(ABC):
    @abstractmethod
    async def send(self, context: NotificationContext) -> NotificationResult:
        raise NotImplementedError


def _emergency_message(context: NotificationContext) -> str:
    # No coordinates, IDs, or technical details in contact-facing content.
    return (
        "EMERGENCY ALERT\n\n"
        f"{context.profile_name} has triggered an SOS and needs urgent help.\n\n"
        "Track their current/latest location:\n"
        f"{context.tracking_url}\n\n"
        f"Please reach {context.profile_name} as soon as possible."
    )


class MockWhatsAppProvider(MessageProvider):
    """Mock-only WhatsApp provider. Never sends anything."""

    provider_name = "mock-whatsapp"

    async def send(self, context: NotificationContext) -> NotificationResult:
        print(
            f"[MOCK WHATSAPP] alert_id={context.alert_id} "
            f"provider={self.provider_name}",
            flush=True,
        )
        return NotificationResult(
            channel="whatsapp",
            provider=self.provider_name,
            status="sent",
            external_id=f"mock-wa-{context.alert_id}",
        )


class MockSMSProvider(MessageProvider):
    """Mock-only SMS provider. Never sends anything."""

    provider_name = "mock-sms"

    async def send(self, context: NotificationContext) -> NotificationResult:
        print(
            f"[MOCK SMS] alert_id={context.alert_id} "
            f"provider={self.provider_name}",
            flush=True,
        )
        return NotificationResult(
            channel="sms",
            provider=self.provider_name,
            status="sent",
            external_id=f"mock-sms-{context.alert_id}",
        )


class NotificationService:
    """Sends WhatsApp first, then exactly one SMS fallback on failure.

    Best-effort duplicate prevention (not exactly-once delivery): callers
    must check the persisted final status before dispatching, and record
    every attempt. A crash between provider success and status persistence
    could still duplicate on manual retry; real provider idempotency keys
    are the future fix at provider-integration time.
    """

    def __init__(
        self,
        whatsapp_provider: Optional[MessageProvider] = None,
        sms_provider: Optional[MessageProvider] = None,
    ):
        self.whatsapp_provider = whatsapp_provider or MockWhatsAppProvider()
        self.sms_provider = sms_provider or MockSMSProvider()

    async def _attempt(
        self, provider: MessageProvider, context: NotificationContext
    ) -> NotificationResult:
        try:
            return await provider.send(context)
        except Exception as exc:  # noqa: BLE001 - never propagate
            logger.warning(
                "Notification dispatch failed: alert_id=%s error=%s",
                context.alert_id,
                type(exc).__name__,
            )
            provider_name = getattr(provider, "provider_name", "mock")
            channel = "whatsapp" if "whatsapp" in provider_name else "sms"
            return NotificationResult(
                channel=channel,
                provider=provider_name,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
            )

    async def send_with_fallback(
        self, context: NotificationContext
    ) -> Dict[str, NotificationResult]:
        results: Dict[str, NotificationResult] = {}
        results["whatsapp"] = await self._attempt(self.whatsapp_provider, context)
        if results["whatsapp"].status == "sent":
            return results
        results["sms"] = await self._attempt(self.sms_provider, context)
        return results


def get_notification_service() -> NotificationService:
    """Factory. Mock-only for this milestone; real provider selection plugs
    in here only after explicit approval."""
    return NotificationService(
        whatsapp_provider=MockWhatsAppProvider(),
        sms_provider=MockSMSProvider(),
    )


def build_attempt_log(results: Dict[str, NotificationResult]) -> List[dict]:
    """Append-only attempt entries for the notification_log column."""
    entries = []
    now = datetime.now(timezone.utc).isoformat()
    for channel in ("whatsapp", "sms"):
        result = results.get(channel)
        if result is None:
            continue
        entries.append(
            {
                "channel": result.channel,
                "provider": result.provider,
                "status": result.status,
                "external_id": result.external_id,
                "error": result.error,
                "at": now,
            }
        )
    return entries


def final_notification_status(results: Dict[str, NotificationResult]) -> str:
    if any(r.status == "sent" for r in results.values()):
        return "sent"
    if any(r.status == "failed" for r in results.values()):
        return "failed"
    return "skipped"
