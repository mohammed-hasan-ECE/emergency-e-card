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
