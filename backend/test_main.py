import pytest
import main
from services.communication import (
    CommunicationService,
    MockMessageProvider,
    MockVoiceProvider,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app, Base, get_db

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

def test_create_profile():
    response = client.post(
        "/profiles/",
        json={
            "full_name": "John Doe",
            "phone_number": "1234567890",
            "blood_group": "O+",
            "allergies": "Peanuts",
            "medical_conditions": "None",
            "medications": "None",
            "emergency_contacts": "Jane Doe (0987654321)"
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "John Doe"
    assert "id" in data
    return data["id"]

def test_get_profile():
    profile_id = test_create_profile()
    response = client.get(f"/profiles/{profile_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "John Doe"
    
def test_sos_alert():
    profile_id = test_create_profile()
    response = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "SOS Alert Triggered"
    assert data["emergency_contacts"] == "Jane Doe (0987654321)"
    assert "communications" in data
    assert data["communications"]["voice"]["status"] == "mock-sent"
    assert data["communications"]["message"]["status"] == "mock-sent"

def test_post_sos_returns_communication_results():
    profile_id = test_create_profile()
    response = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert response.status_code == 200
    data = response.json()
    comms = data["communications"]
    assert comms["voice"]["channel"] == "voice"
    assert comms["voice"]["provider"] == "mock"
    assert comms["message"]["channel"] == "message"
    assert comms["message"]["provider"] == "mock"

def test_sos_communication_failure_does_not_block_alert(monkeypatch):
    class FailingVoiceProvider(MockVoiceProvider):
        async def place_call(self, context):
            raise RuntimeError("mock voice failure")

    class FailingMessageProvider(MockMessageProvider):
        async def send(self, context):
            raise RuntimeError("mock message failure")

    def failing_service():
        return CommunicationService(
            voice_provider=FailingVoiceProvider(),
            message_provider=FailingMessageProvider(),
        )

    monkeypatch.setattr(main, "get_communication_service", failing_service)

    profile_id = test_create_profile()
    response = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    # Alert must still be created even though comms failed
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "SOS Alert Triggered"
    assert "alert_id" in data
    assert data["communications"]["voice"]["status"] == "failed"
    assert data["communications"]["message"]["status"] == "failed"

def test_repeated_sos_does_not_create_second_alert():
    profile_id = test_create_profile()
    first = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert first.status_code == 200
    first_data = first.json()

    second = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert second.status_code == 200
    second_data = second.json()

    assert second_data["message"] == "SOS Alert already active"
    assert second_data["alert_id"] == first_data["alert_id"]
    # Repeat must not re-dispatch external communications
    assert second_data["communications"]["voice"]["status"] == "skipped"
    assert second_data["communications"]["message"]["status"] == "skipped"

    db = TestingSessionLocal()
    try:
        count = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.profile_id == profile_id,
            main.EmergencyAlert.status == "active",
        ).count()
    finally:
        db.close()
    assert count == 1

def test_get_sos_compatibility_shim():
    profile_id = test_create_profile()
    response = client.get(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert response.status_code == 200
    assert response.headers.get("deprecation") == "true"
    data = response.json()
    assert data["message"] == "SOS Alert Triggered"
    assert "communications" in data

    # Repeat GET returns the existing alert without duplicate dispatch
    repeat = client.get(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert repeat.status_code == 200
    repeat_data = repeat.json()
    assert repeat_data["message"] == "SOS Alert already active"
    assert repeat_data["alert_id"] == data["alert_id"]
    assert repeat_data["communications"]["voice"]["status"] == "skipped"
    assert repeat_data["communications"]["message"]["status"] == "skipped"

def _create_profile_payload(**overrides):
    payload = {
        "full_name": "Jane Contact",
        "phone_number": "+14155550001",
        "blood_group": "A+",
        "allergies": "None",
        "medical_conditions": "None",
        "medications": "None",
        "emergency_contacts": "John Doe - Brother - +14155559999",
    }
    payload.update(overrides)
    return payload

def test_create_profile_with_contact_phone():
    response = client.post(
        "/profiles/",
        json=_create_profile_payload(emergency_contact_phone="+14155550002"),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["emergency_contact_phone"] == "+14155550002"
    # Existing free-form field remains untouched
    assert data["emergency_contacts"] == "John Doe - Brother - +14155559999"

def test_get_profile_returns_contact_phone():
    created = client.post(
        "/profiles/",
        json=_create_profile_payload(emergency_contact_phone="+14155550003"),
    ).json()
    response = client.get(f"/profiles/{created['id']}")
    assert response.status_code == 200
    assert response.json()["emergency_contact_phone"] == "+14155550003"

def test_update_contact_phone():
    profile_id = client.post("/profiles/", json=_create_profile_payload()).json()["id"]
    response = client.put(
        f"/profiles/{profile_id}",
        json=_create_profile_payload(emergency_contact_phone="+14155550004"),
    )
    assert response.status_code == 200
    assert response.json()["emergency_contact_phone"] == "+14155550004"

def test_profile_without_contact_phone_still_works():
    response = client.post("/profiles/", json=_create_profile_payload())
    assert response.status_code == 201
    assert response.json()["emergency_contact_phone"] is None

def test_invalid_contact_phone_rejected():
    for bad in ["abc", "12345", "919876543210", "+0", "+123", "+919876543210123456"]:
        response = client.post(
            "/profiles/", json=_create_profile_payload(emergency_contact_phone=bad)
        )
        assert response.status_code == 422, bad

def test_contact_phone_cannot_be_own_number():
    payload = _create_profile_payload(
        phone_number="+14155550005", emergency_contact_phone="+14155550005"
    )
    assert client.post("/profiles/", json=payload).status_code == 422

    profile_id = client.post("/profiles/", json=_create_profile_payload()).json()["id"]
    stored = client.get(f"/profiles/{profile_id}").json()
    response = client.put(
        f"/profiles/{profile_id}",
        json={"emergency_contact_phone": stored["phone_number"]},
    )
    assert response.status_code == 400

class _CapturingService:
    """Test stand-in for CommunicationService. Records contexts, never dials."""

    def __init__(self):
        self.contexts = []

    async def dispatch(self, context):
        from services.communication import CommunicationResult

        self.contexts.append(context)
        return {
            "voice": CommunicationResult(
                channel="voice", provider="test", status="sent", external_id="ext-1"
            ),
            "message": CommunicationResult(
                channel="message", provider="test", status="sent"
            ),
        }

def test_sos_passes_structured_destination_phone(monkeypatch):
    service = _CapturingService()
    monkeypatch.setattr(main, "get_communication_service", lambda: service)
    profile_id = client.post(
        "/profiles/",
        json=_create_profile_payload(emergency_contact_phone="+14155550006"),
    ).json()["id"]

    response = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")

    assert response.status_code == 200
    assert len(service.contexts) == 1
    context = service.contexts[0]
    # Structured field is used verbatim; free-form text is never parsed.
    assert context.destination_phone == "+14155550006"
    assert context.destination_phone != "+14155559999"
    assert response.json()["communications"]["voice"]["external_id"] == "ext-1"

def test_sos_without_contact_phone_has_no_destination(monkeypatch):
    service = _CapturingService()
    monkeypatch.setattr(main, "get_communication_service", lambda: service)
    profile_id = client.post("/profiles/", json=_create_profile_payload()).json()["id"]

    response = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")

    assert response.status_code == 200
    assert service.contexts[0].destination_phone is None

def test_sos_responses_include_structured_contact():
    profile_id = client.post(
        "/profiles/",
        json=_create_profile_payload(
            emergency_contacts="Tim — Husband",
            emergency_contact_phone="+14155550007",
        ),
    ).json()["id"]

    first = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["emergency_contacts"] == "Tim — Husband"
    assert first_data["emergency_contact_phone"] == "+14155550007"

    second = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["message"] == "SOS Alert already active"
    assert second_data["emergency_contact_phone"] == "+14155550007"

def test_sos_responses_include_medications():
    profile_id = client.post(
        "/profiles/",
        json=_create_profile_payload(medications="Insulin 10mg daily"),
    ).json()["id"]

    first_data = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()
    assert first_data["medications"] == "Insulin 10mg daily"

    second_data = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()
    assert second_data["message"] == "SOS Alert already active"
    assert second_data["medications"] == "Insulin 10mg daily"

def _profile_with_token(**overrides):
    data = client.post("/profiles/", json=_create_profile_payload(**overrides)).json()
    assert data["location_publish_token"]
    return data["id"], data["location_publish_token"]

def _publish_location(profile_id, token, latitude, longitude):
    return client.put(
        f"/profiles/{profile_id}/location",
        json={"latitude": latitude, "longitude": longitude},
        headers={"X-Location-Token": token},
    )

def test_create_profile_returns_publish_token_once():
    profile_id, token = _profile_with_token()
    assert isinstance(token, str) and len(token) >= 16
    # Subsequent reads never re-expose it.
    assert client.get(f"/profiles/{profile_id}").json()["location_publish_token"] is None
    # Only the hash is stored.
    db = TestingSessionLocal()
    try:
        stored = db.query(main.Profile).filter(main.Profile.id == profile_id).first()
        assert stored.location_publish_token_hash != token
        assert len(stored.location_publish_token_hash) == 64
    finally:
        db.close()

def test_publish_location_with_token():
    profile_id, token = _profile_with_token()
    response = _publish_location(profile_id, token, 12.5, 77.5)
    assert response.status_code == 200
    data = response.json()
    assert data["latitude"] == "12.5"
    assert data["longitude"] == "77.5"
    assert data["location_updated_at"] is not None

def test_publish_location_auth():
    profile_id, token = _profile_with_token()
    assert client.put(
        f"/profiles/{profile_id}/location",
        json={"latitude": 12.5, "longitude": 77.5},
    ).status_code == 401
    assert _publish_location(profile_id, "wrong-token", 12.5, 77.5).status_code == 403
    assert _publish_location(profile_id, token, 12.5, 77.5).status_code == 200

def test_publish_location_rejects_invalid_coordinates():
    profile_id, token = _profile_with_token()
    assert _publish_location(profile_id, token, 999, 77.5).status_code == 422
    response = client.put(
        f"/profiles/{profile_id}/location",
        json={"latitude": "not-a-number", "longitude": 77.5},
        headers={"X-Location-Token": token},
    )
    assert response.status_code == 422

def test_general_update_rejects_coordinates():
    profile_id, token = _profile_with_token()
    response = client.put(
        f"/profiles/{profile_id}", json={"latitude": "12.5", "longitude": "77.5"}
    )
    assert response.status_code == 422

def test_rotate_token_invalidates_old():
    profile_id, token = _profile_with_token()
    stored_phone = client.get(f"/profiles/{profile_id}").json()["phone_number"]
    assert client.post(
        f"/profiles/{profile_id}/location-token/rotate",
        json={"phone_number": "+10000000000"},
    ).status_code == 403
    new_token = client.post(
        f"/profiles/{profile_id}/location-token/rotate",
        json={"phone_number": stored_phone},
    ).json()["location_publish_token"]
    assert new_token and new_token != token
    assert _publish_location(profile_id, token, 12.5, 77.5).status_code == 403
    assert _publish_location(profile_id, new_token, 12.5, 77.5).status_code == 200

def test_profile_location_update_sets_timestamp():
    profile_id, token = _profile_with_token()
    before = client.get(f"/profiles/{profile_id}").json()["location_updated_at"]
    response = _publish_location(profile_id, token, 12.5, 77.5)
    assert response.status_code == 200
    data = response.json()
    assert data["latitude"] == "12.5"
    assert data["location_updated_at"] is not None
    assert data["location_updated_at"] != before

def test_create_profile_with_location_sets_timestamp():
    payload = _create_profile_payload(latitude="12.5", longitude="77.5")
    data = client.post("/profiles/", json=payload).json()
    assert data["location_updated_at"] is not None

def test_sos_trigger_refreshes_profile_location():
    profile_id, token = _profile_with_token()
    _publish_location(profile_id, token, "10.0", "70.0")

    response = client.post(f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946")
    assert response.status_code == 200

    stored = client.get(f"/profiles/{profile_id}").json()
    assert stored["latitude"] == "12.9716"
    assert stored["longitude"] == "77.5946"
    assert stored["location_updated_at"] is not None
    # Alert keeps the trigger snapshot.
    assert response.json()["latitude"] == "12.9716"
    assert response.json()["longitude"] == "77.5946"

def _edesy_sent_service(external_id):
    from services.communication import CommunicationResult

    class _SentService:
        async def dispatch(self, context):
            return {
                "voice": CommunicationResult(
                    channel="voice",
                    provider="edesy",
                    status="sent",
                    external_id=external_id,
                ),
                "message": CommunicationResult(
                    channel="message", provider="mock", status="mock-sent"
                ),
            }

    return _SentService()

def test_conversation_id_persisted_on_edesy_success(monkeypatch):
    monkeypatch.setattr(
        main, "get_communication_service", lambda: _edesy_sent_service("conv-ABC")
    )
    profile_id = client.post("/profiles/", json=_create_profile_payload()).json()["id"]
    alert_id = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()["alert_id"]

    db = TestingSessionLocal()
    try:
        alert = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.id == alert_id
        ).first()
        assert alert.edesy_conversation_id == "conv-ABC"
    finally:
        db.close()

def test_no_conversation_id_without_external_id(monkeypatch):
    service = _CapturingService()
    monkeypatch.setattr(main, "get_communication_service", lambda: service)
    profile_id = client.post("/profiles/", json=_create_profile_payload()).json()["id"]
    alert_id = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()["alert_id"]

    db = TestingSessionLocal()
    try:
        alert = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.id == alert_id
        ).first()
        assert alert.edesy_conversation_id is None
    finally:
        db.close()

def _sos_profile_with_contact(phone="+14155550100"):
    payload = _create_profile_payload(emergency_contact_phone=phone)
    return client.post("/profiles/", json=payload).json()["id"]

def _tracking_token_from_url(url):
    assert "/track/" in url
    return url.rsplit("/track/", 1)[1]

def test_sos_creates_tracking_and_notifies():
    profile_id = _sos_profile_with_contact()
    data = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()
    assert data["tracking_url"].endswith(
        _tracking_token_from_url(data["tracking_url"])
    )
    assert len(_tracking_token_from_url(data["tracking_url"])) >= 16
    whatsapp = data["notifications"]["whatsapp"]
    assert whatsapp["status"] == "sent"
    assert whatsapp["provider"] == "mock-whatsapp"
    assert whatsapp["external_id"]

    db = TestingSessionLocal()
    try:
        alert = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.id == data["alert_id"]
        ).first()
        assert alert.tracking_token
        assert alert.notification_status == "sent"
        assert alert.notified_at is not None
    finally:
        db.close()

def test_duplicate_sos_reuses_tracking_without_redispatch():
    profile_id = _sos_profile_with_contact()
    first = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()
    second = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()
    assert second["tracking_url"] == first["tracking_url"]
    assert second["notifications"]["whatsapp"]["status"] == "sent"

    import json as json_mod

    db = TestingSessionLocal()
    try:
        alert = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.id == first["alert_id"]
        ).first()
        entries = json_mod.loads(alert.notification_log)
        assert [e for e in entries if e["channel"] == "whatsapp"] and len(entries) == 1
    finally:
        db.close()

def test_whatsapp_failure_triggers_sms_fallback(monkeypatch):
    from services.notification import (
        MockSMSProvider,
        NotificationService,
    )

    class FailingWhatsApp:
        provider_name = "mock-whatsapp"

        async def send(self, context):
            raise RuntimeError("mock whatsapp down")

    monkeypatch.setattr(
        main,
        "get_notification_service",
        lambda: NotificationService(
            whatsapp_provider=FailingWhatsApp(),
            sms_provider=MockSMSProvider(),
        ),
    )
    profile_id = _sos_profile_with_contact()
    data = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()
    assert data["notifications"]["whatsapp"]["status"] == "failed"
    assert data["notifications"]["sms"]["status"] == "sent"
    assert data["notifications"]["sms"]["provider"] == "mock-sms"

def test_notify_skipped_without_destination_phone():
    profile_id = client.post("/profiles/", json=_create_profile_payload()).json()["id"]
    data = client.post(
        f"/sos/{profile_id}?latitude=12.9716&longitude=77.5946"
    ).json()
    assert data["notifications"]["whatsapp"]["status"] == "skipped"
    assert "sms" not in data["notifications"]

def test_track_endpoint_happy_path():
    profile_id = _sos_profile_with_contact()
    data = client.post(
        f"/sos/{profile_id}?latitude=12.5&longitude=77.5"
    ).json()
    token = _tracking_token_from_url(data["tracking_url"])

    response = client.get(f"/track/{token}")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    body = response.json()
    assert set(body.keys()) == {
        "person_name",
        "tracking_active",
        "location_status",
        "location_updated_at",
        "has_location",
        "maps_url",
        "map_embed_url",
    }
    assert body["tracking_active"] is True
    assert body["location_status"] == "current"
    assert body["has_location"] is True
    assert "openstreetmap.org" in (body["map_embed_url"] or "")
    assert "latitude" not in body and "longitude" not in body

def test_track_reflects_profile_moves():
    profile_id, token = _profile_with_token()
    data = client.post(
        f"/sos/{profile_id}?latitude=12.5&longitude=77.5"
    ).json()
    track_token = _tracking_token_from_url(data["tracking_url"])

    _publish_location(profile_id, token, "13.9", "78.9")
    body = client.get(f"/track/{track_token}").json()
    assert body["location_status"] == "current"

    db = TestingSessionLocal()
    try:
        alert = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.id == data["alert_id"]
        ).first()
        assert (alert.latitude, alert.longitude) != ("13.9", "78.9")
    finally:
        db.close()

def test_track_stale_and_unavailable():
    import datetime as dt_mod

    profile_id = _sos_profile_with_contact()
    token = _tracking_token_from_url(
        client.post(f"/sos/{profile_id}?latitude=12.5&longitude=77.5").json()[
            "tracking_url"
        ]
    )
    db = TestingSessionLocal()
    try:
        profile = db.query(main.Profile).filter(main.Profile.id == profile_id).first()
        profile.location_updated_at = dt_mod.datetime.now(
            dt_mod.timezone.utc
        ) - dt_mod.timedelta(seconds=main.LOCATION_STALE_AFTER_SECONDS + 60)
        db.commit()
    finally:
        db.close()
    assert client.get(f"/track/{token}").json()["location_status"] == "stale"

    profile_id2 = _sos_profile_with_contact(phone="+14155550102")
    token2 = _tracking_token_from_url(
        client.post(f"/sos/{profile_id2}?latitude=12.5&longitude=77.5").json()[
            "tracking_url"
        ]
    )
    db = TestingSessionLocal()
    try:
        profile = db.query(main.Profile).filter(main.Profile.id == profile_id2).first()
        profile.latitude = None
        profile.longitude = None
        db.commit()
    finally:
        db.close()
    body = client.get(f"/track/{token2}").json()
    assert body["location_status"] == "unavailable"
    assert body["has_location"] is False
    assert body["maps_url"] is None
    assert body["map_embed_url"] is None

def test_track_unknown_resolved_expired():
    profile_id = _sos_profile_with_contact()
    token = _tracking_token_from_url(
        client.post(f"/sos/{profile_id}?latitude=12.5&longitude=77.5").json()[
            "tracking_url"
        ]
    )
    assert client.get("/track/does-not-exist").status_code == 404

    db = TestingSessionLocal()
    try:
        alert = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.tracking_token == token
        ).first()
        alert.status = "resolved"
        db.commit()
    finally:
        db.close()
    resolved = client.get(f"/track/{token}")
    assert resolved.status_code == 410
    assert "maps_url" not in resolved.json()
    assert "map_embed_url" not in resolved.json()

def test_track_expired_alert_rejected():
    import datetime as dt_mod

    profile_id = _sos_profile_with_contact(phone="+14155550103")
    token = _tracking_token_from_url(
        client.post(f"/sos/{profile_id}?latitude=12.5&longitude=77.5").json()[
            "tracking_url"
        ]
    )
    db = TestingSessionLocal()
    try:
        alert = db.query(main.EmergencyAlert).filter(
            main.EmergencyAlert.tracking_token == token
        ).first()
        alert.expires_at = dt_mod.datetime.now(dt_mod.timezone.utc) - dt_mod.timedelta(
            minutes=1
        )
        db.commit()
    finally:
        db.close()
    assert client.get(f"/track/{token}").status_code == 410

def test_notify_retry_endpoint(monkeypatch):
    from services.notification import (
        MockSMSProvider,
        NotificationService,
        get_notification_service,
    )

    class FailingWhatsApp:
        provider_name = "mock-whatsapp"

        async def send(self, context):
            raise RuntimeError("mock whatsapp down")

    class FailingSMS:
        provider_name = "mock-sms"

        async def send(self, context):
            raise RuntimeError("mock sms down")

    monkeypatch.setattr(
        main,
        "get_notification_service",
        lambda: NotificationService(
            whatsapp_provider=FailingWhatsApp(),
            sms_provider=FailingSMS(),
        ),
    )
    profile_id = _sos_profile_with_contact(phone="+14155550104")
    sos_data = client.post(
        f"/sos/{profile_id}?latitude=12.5&longitude=77.5"
    ).json()
    alert_id = sos_data["alert_id"]
    assert sos_data["notifications"]["whatsapp"]["status"] == "failed"
    assert sos_data["notifications"]["sms"]["status"] == "failed"

    import json as json_mod

    def _log_length():
        db = TestingSessionLocal()
        try:
            return len(
                json_mod.loads(
                    db.query(main.EmergencyAlert).filter(
                        main.EmergencyAlert.id == alert_id
                    ).first().notification_log
                )
            )
        finally:
            db.close()

    assert _log_length() == 2

    # Retry with working providers succeeds and appends attempts.
    monkeypatch.setattr(main, "get_notification_service", get_notification_service)
    retry = client.post(f"/alerts/{alert_id}/notify?profile_id={profile_id}").json()
    assert retry["notifications"]["whatsapp"]["status"] == "sent"
    assert _log_length() == 3

    # Already-sent guard: further retries dispatch nothing new.
    again = client.post(f"/alerts/{alert_id}/notify?profile_id={profile_id}").json()
    assert again["message"] == "Notification already sent"
    assert _log_length() == 3

    assert client.post(f"/alerts/{alert_id}/notify?profile_id=nope").status_code == 403
    assert client.post("/alerts/nope/notify?profile_id=nope").status_code == 404

def test_notify_completes_despite_slow_voice(monkeypatch):
    import asyncio as asyncio_mod
    import time as time_mod
    from services.communication import CommunicationResult, CommunicationService

    events = {}

    class SlowVoice:
        provider_name = "mock"

        async def place_call(self, context):
            events["voice_start"] = time_mod.monotonic()
            await asyncio_mod.sleep(2)
            events["voice_end"] = time_mod.monotonic()
            return CommunicationResult(
                channel="voice", provider="mock", status="mock-sent"
            )

    from services.notification import NotificationService

    class RecordingNotify(NotificationService):
        async def send_with_fallback(self, context):
            events["notify_done"] = time_mod.monotonic()
            return await super().send_with_fallback(context)

    monkeypatch.setattr(
        main,
        "get_communication_service",
        lambda: CommunicationService(voice_provider=SlowVoice()),
    )
    monkeypatch.setattr(main, "get_notification_service", lambda: RecordingNotify())
    profile_id = _sos_profile_with_contact(phone="+14155550105")
    data = client.post(
        f"/sos/{profile_id}?latitude=12.5&longitude=77.5"
    ).json()
    assert data["notifications"]["whatsapp"]["status"] == "sent"
    assert events["notify_done"] < events["voice_end"]

def test_tracking_token_never_logged(monkeypatch, caplog):
    import logging as logging_mod

    profile_id = _sos_profile_with_contact(phone="+14155550106")
    with caplog.at_level(logging_mod.INFO):
        data = client.post(
            f"/sos/{profile_id}?latitude=12.5&longitude=77.5"
        ).json()
    token = _tracking_token_from_url(data["tracking_url"])
    for record in caplog.records:
        assert token not in record.getMessage()
