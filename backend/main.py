import uuid
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
    blood_group = Column(String)
    allergies = Column(Text)
    medical_conditions = Column(Text)
    medications = Column(Text)
    # Storing emergency contacts as a simple string or JSON string for MVP
    emergency_contacts = Column(Text)

# Create the tables
Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas ---
class ProfileBase(BaseModel):
    full_name: str
    phone_number: str
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
    Emergency SOS endpoint that returns the user's emergency contacts and relevant medical information.
    """
    db_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if db_profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {
        "message": "SOS Alert Triggered",
        "profile_id": db_profile.id,
        "full_name": db_profile.full_name,
        "blood_group": db_profile.blood_group,
        "allergies": db_profile.allergies,
        "medical_conditions": db_profile.medical_conditions,
        "emergency_contacts": db_profile.emergency_contacts
    }
