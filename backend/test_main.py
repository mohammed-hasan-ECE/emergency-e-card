import pytest
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
    response = client.get(f"/sos/{profile_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "SOS Alert Triggered"
    assert data["emergency_contacts"] == "Jane Doe (0987654321)"
