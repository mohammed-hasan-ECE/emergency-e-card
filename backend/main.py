import uuid
import math
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# --- Database Setup ---
import os

SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./emergency_ecard.db"
)

if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- SQLAlchemy Models ---
def generate_uuid():
    return str(uuid.uuid4())

class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True, index=True, default=generate_uuid)
    full_name = Column(String, index=True)
    phone_number = Column(String)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    blood_group = Column(String)
    allergies = Column(Text)
    medical_conditions = Column(Text)
    medications = Column(Text)
    # Storing emergency contacts as a simple string or JSON string for MVP
    emergency_contacts = Column(Text)
class EmergencyAlert(Base):
    __tablename__ = "emergency_alerts"

    id = Column(String, primary_key=True, index=True, default=generate_uuid)
    profile_id = Column(String, nullable=False)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    status = Column(String, default="active")
# Create the tables
Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas ---
class ProfileBase(BaseModel):
    full_name: str
    phone_number: str
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    medical_conditions: Optional[str] = None
    medications: Optional[str] = None
    emergency_contacts: Optional[str] = None

class ProfileCreate(ProfileBase):
    pass

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    blood_group: Optional[str] = None
    allergies: Optional[str] = None
    medical_conditions: Optional[str] = None
    medications: Optional[str] = None
    emergency_contacts: Optional[str] = None

class ProfileResponse(ProfileBase):
    id: str

    model_config = ConfigDict(from_attributes=True)


# --- FastAPI App ---
app = FastAPI(title="Emergency E-Card API")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance between two GPS coordinates in kilometers.
    Uses the Haversine formula.
    """
    R = 6371.0  # Earth's radius in kilometers

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
# --- Endpoints ---

@app.post("/profiles/", response_model=ProfileResponse, status_code=201)
def create_profile(profile: ProfileCreate, db: Session = Depends(get_db)):
    """
    Create a new emergency profile.
    """
    db_profile = Profile(**profile.model_dump())
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile

@app.get("/profiles/{profile_id}", response_model=ProfileResponse)
def get_profile(profile_id: str, db: Session = Depends(get_db)):
    """
    Retrieve an emergency profile using a unique profile ID.
    """
    db_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if db_profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return db_profile

@app.put("/profiles/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: str, profile: ProfileUpdate, db: Session = Depends(get_db)):
    """
    Update an existing profile.
    """
    db_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if db_profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    update_data = profile.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_profile, key, value)
        
    db.commit()
    db.refresh(db_profile)
    return db_profile

@app.get("/sos/{profile_id}")
def sos_alert(profile_id: str, db: Session = Depends(get_db)):
    """
    Trigger an SOS alert, save the emergency event,
    and find nearby registered users.
    """

    db_profile = db.query(Profile).filter(
        Profile.id == profile_id
    ).first()

    if db_profile is None:
        raise HTTPException(
            status_code=404,
            detail="Profile not found"
        )

    if db_profile.latitude is None or db_profile.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Profile location is not available"
        )

    # Create and save emergency alert
    emergency_alert = EmergencyAlert(
        profile_id=db_profile.id,
        latitude=db_profile.latitude,
        longitude=db_profile.longitude,
        status="active"
    )

    db.add(emergency_alert)
    db.commit()
    db.refresh(emergency_alert)

    # Find nearby users
    all_profiles = db.query(Profile).filter(
        Profile.id != profile_id
    ).all()

    nearby_users = []

    for profile in all_profiles:
        if profile.latitude is None or profile.longitude is None:
            continue

        distance = calculate_distance(
            db_profile.latitude,
            db_profile.longitude,
            profile.latitude,
            profile.longitude
        )

        if distance <= 1.0:
            nearby_users.append({
                "profile_id": profile.id,
                "full_name": profile.full_name,
                "distance_km": round(distance, 2)
            })

    return {
        "message": "SOS Alert Triggered",
        "alert_id": emergency_alert.id,
        "profile_id": db_profile.id,
        "full_name": db_profile.full_name,
        "latitude": db_profile.latitude,
        "longitude": db_profile.longitude,
        "blood_group": db_profile.blood_group,
        "allergies": db_profile.allergies,
        "medical_conditions": db_profile.medical_conditions,
        "emergency_contacts": db_profile.emergency_contacts,
        "nearby_users": nearby_users
    }
@app.get("/nearby/{profile_id}")
def find_nearby_users(
    profile_id: str,
    radius_km: float = 1.0,
    db: Session = Depends(get_db)
):
    """
    Find registered users within a given radius of the specified profile.
    """

    emergency_profile = db.query(Profile).filter(
        Profile.id == profile_id
    ).first()

    if emergency_profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if emergency_profile.latitude is None or emergency_profile.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Profile location is not available"
        )

    all_profiles = db.query(Profile).filter(
        Profile.id != profile_id
    ).all()

    nearby_users = []

    for profile in all_profiles:
        if profile.latitude is None or profile.longitude is None:
            continue

        distance = calculate_distance(
            emergency_profile.latitude,
            emergency_profile.longitude,
            profile.latitude,
            profile.longitude
        )

        if distance <= radius_km:
            nearby_users.append({
                "profile_id": profile.id,
                "full_name": profile.full_name,
                "distance_km": round(distance, 2)
            })

    return {
        "emergency_profile_id": profile_id,
        "radius_km": radius_km,
        "nearby_users": nearby_users
    }
@app.get("/alerts/{profile_id}")
def get_nearby_alerts(
    profile_id: str,
    radius_km: float = 1.0,
    db: Session = Depends(get_db)
):
    """
    Find active emergency alerts near a registered user.
    """

    responder = db.query(Profile).filter(
        Profile.id == profile_id
    ).first()

    if responder is None:
        raise HTTPException(
            status_code=404,
            detail="Profile not found"
        )

    if responder.latitude is None or responder.longitude is None:
        raise HTTPException(
            status_code=400,
            detail="Responder location is not available"
        )

    active_alerts = db.query(EmergencyAlert).filter(
        EmergencyAlert.status == "active"
    ).all()

    nearby_alerts = []

    for alert in active_alerts:
        if alert.latitude is None or alert.longitude is None:
            continue

        if alert.profile_id == profile_id:
            continue

        distance = calculate_distance(
            responder.latitude,
            responder.longitude,
            alert.latitude,
            alert.longitude
        )

        if distance <= radius_km:
            emergency_profile = db.query(Profile).filter(
                Profile.id == alert.profile_id
            ).first()

            nearby_alerts.append({
                "alert_id": alert.id,
                "profile_id": alert.profile_id,
                "full_name": emergency_profile.full_name if emergency_profile else None,
                "latitude": alert.latitude,
                "longitude": alert.longitude,
                "distance_km": round(distance, 2)
            })

    return {
        "responder_profile_id": profile_id,
        "radius_km": radius_km,
        "nearby_alerts": nearby_alerts
    }


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, db: Session = Depends(get_db)):
    """
    Mark an emergency alert as resolved.
    """
    alert = db.query(EmergencyAlert).filter(
        EmergencyAlert.id == alert_id
    ).first()

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    alert.status = "resolved"
    db.commit()
    db.refresh(alert)

    return {
        "message": "Alert resolved successfully",
        "alert_id": alert.id,
        "status": alert.status
    }