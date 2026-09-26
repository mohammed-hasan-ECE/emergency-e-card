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
