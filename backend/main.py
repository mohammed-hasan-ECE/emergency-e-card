import uuid
import math
import os
import re
import hmac
import json
import asyncio
import secrets
import hashlib
import time
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import create_engine, Column, String, Text, DateTime, inspect, text, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from services.communication import EmergencyContext, get_communication_service
from services.communication import parse_coordinates as parse_stored_coordinates
from services.communication import google_maps_url as build_google_maps_url
from services.communication import map_embed_url as build_map_embed_url
from services.notification import (
    NotificationContext,
    NotificationResult,
    build_attempt_log,
    final_notification_status,
    get_notification_service,
)

# --- Voice tool configuration ---
# Seconds after which a stored location is reported as "stale" instead of
# "current". Configurable; not a magic number buried in business logic.
# Shared by the tracking page so live/latest-known states stay consistent.
LOCATION_STALE_AFTER_SECONDS = int(os.getenv("LOCATION_STALE_AFTER_SECONDS", "300"))

# Header carrying the device location-publish token. Writes only; the
# emergency-contact tracking token is never accepted here.
LOCATION_TOKEN_HEADER = "X-Location-Token"

# Per-channel timeout (seconds) for the SOS fan-out. A slow provider cannot
# delay the other independent channels beyond this bound.
CHANNEL_TIMEOUT_SECONDS = 20.0

# Public tracking-link rate limit: requests per token per 60 seconds.
# In-memory (same single-process scope as the WebSocket manager).
TRACK_RATE_LIMIT_PER_MINUTE = 60
_track_request_times: Dict[str, list] = {}


def build_tracking_url(token: str) -> str:
    """Absolute tracking URL when TRACKING_BASE_URL is configured,
    otherwise the app-relative path (frontend serves /track/:token)."""
    base = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/")
    if base:
        return f"{base}/track/{token}"
    return f"/track/{token}"


def _normalize_notify_models(value) -> dict:
    """gather() outcome -> {channel: NotificationResult}. Never raises."""
    if isinstance(value, dict):
        return value
    reason = (
        f"{type(value).__name__}: channel timed out or failed"
        if isinstance(value, BaseException)
        else "Channel dispatch failed"
    )
    return {
        "whatsapp": NotificationResult(
            channel="whatsapp",
            provider="mock-whatsapp",
            status="failed",
            error=reason,
        )
    }


def _normalize_voice_models(value) -> dict:
    """gather() outcome -> {channel: CommunicationResult}. Never raises."""
    from services.communication import CommunicationResult

    if isinstance(value, dict):
        return value
    reason = (
        f"{type(value).__name__}: channel timed out or failed"
        if isinstance(value, BaseException)
        else "Channel dispatch failed"
    )
    return {
        channel: CommunicationResult(
            channel=channel, provider="mock", status="failed", error=reason
        )
        for channel in ("voice", "message")
    }


def _stored_notification_summary(alert) -> dict:
    """Rebuild the notifications block from the persisted attempt log.

    Uses the LATEST attempt per channel: earlier failures must not shadow
    a later successful retry in the reported summary.
    """
    try:
        entries = json.loads(alert.notification_log) if alert.notification_log else []
    except Exception:  # noqa: BLE001 - corrupt log degrades to skipped
        entries = []
    summary = {}
    for channel in ("whatsapp", "sms"):
        match = next(
            (e for e in reversed(entries) if e.get("channel") == channel), None
        )
        summary[channel] = match or {
            "channel": channel,
            "provider": f"mock-{channel}",
            "status": "skipped",
            "error": "No notification dispatched for this alert",
        }
    return summary


def _persist_notification_outcome(db, alert, results: dict) -> None:
    """Append attempts + rollup final status. Isolated; never breaks SOS."""
    try:
        try:
            existing = json.loads(alert.notification_log) if alert.notification_log else []
        except Exception:  # noqa: BLE001
            existing = []
        existing.extend(build_attempt_log(results))
        alert.notification_log = json.dumps(existing)
        alert.notification_status = final_notification_status(results)
        alert.notified_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def mint_location_publish_token() -> tuple:
    """Mint (raw_token, sha256_hex). Raw is shown once, hash is stored."""
    raw = secrets.token_urlsafe(24)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest


def publish_token_matches(provided: str, stored_hash) -> bool:
    if not provided or not stored_hash:
        return False
    candidate = hashlib.sha256(provided.encode("utf-8")).hexdigest()
    return hmac.compare_digest(candidate, stored_hash)


def _ensure_aware(value):
    """Treat naive SQLite datetimes as UTC for safe comparison."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value

# --- Database Setup ---
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
    # Structured emergency-contact phone used for automated SOS voice calls.
    # Never parsed from emergency_contacts; never the owner's own number.
    emergency_contact_phone = Column(String, nullable=True)
    # Freshness of latitude/longitude (live-location source of truth).
    location_updated_at = Column(DateTime, nullable=True)
    # SHA-256 hex of the device location-publish token. Writes only;
    # never the tracking token. Raw value shown once at mint/rotate.
    location_publish_token_hash = Column(String, nullable=True, index=True)
class EmergencyAlert(Base):
    __tablename__ = "emergency_alerts"

    id = Column(String, primary_key=True, index=True, default=generate_uuid)
    profile_id = Column(String, nullable=False)
    latitude = Column(String, nullable=True)
    longitude = Column(String, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)
    # Edesy Calls API conversationId correlating the voice call with this SOS.
    edesy_conversation_id = Column(String, nullable=True, index=True)
    # Opaque emergency-contact tracking token (raw; single-purpose, TTL-bound
    # to this alert). Never logged.
    tracking_token = Column(String, nullable=True, index=True)
    # Append-only JSON attempt log + final rollup for duplicate prevention.
    notification_log = Column(Text, nullable=True)
    notification_status = Column(String, nullable=True)
    notified_at = Column(DateTime, nullable=True)

class AlertAcknowledgement(Base):
    __tablename__ = "alert_acknowledgements"
    __table_args__ = (
        UniqueConstraint(
            'alert_id',
            'responder_profile_id',
            name='uix_alert_responder'
        ),
    )

    id = Column(String, primary_key=True, index=True, default=generate_uuid)
    alert_id = Column(String, nullable=False, index=True)
    responder_profile_id = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Create the tables
Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas ---
# E.164 international format: leading '+', country code without 0, 8-15 digits
# total. Country-agnostic. Only surrounding whitespace is stripped; the
# digits themselves are never transformed.
EMERGENCY_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_emergency_contact_phone(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not EMERGENCY_PHONE_PATTERN.match(value):
        raise ValueError(
            "emergency_contact_phone must be in E.164 format, e.g. +919876543210"
        )
    return value


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
    emergency_contact_phone: Optional[str] = None
    location_updated_at: Optional[datetime] = None

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_contact_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_emergency_contact_phone(v)

class ProfileCreate(ProfileBase):
    @model_validator(mode="after")
    def check_contact_phone_not_own(self):
        if (
            self.emergency_contact_phone
            and self.phone_number
            and self.emergency_contact_phone == self.phone_number.strip()
        ):
            raise ValueError(
                "emergency_contact_phone must be an emergency contact's number, "
                "not your own phone_number"
            )
        return self

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
    emergency_contact_phone: Optional[str] = None
    location_updated_at: Optional[datetime] = None

    @field_validator("emergency_contact_phone")
    @classmethod
    def validate_emergency_contact_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_emergency_contact_phone(v)

class ProfileResponse(ProfileBase):
    id: str
    # Raw device location-publish token. Only ever populated on profile
    # creation (shown once); all other responses return None.
    location_publish_token: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- Connection Manager for WebSockets ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, profile_id: str):
        await websocket.accept()
        self.active_connections[profile_id] = websocket

    def disconnect(self, profile_id: str):
        if profile_id in self.active_connections:
            del self.active_connections[profile_id]

    async def send_personal_message(self, message: dict, profile_id: str):
        if profile_id in self.active_connections:
            try:
                await self.active_connections[profile_id].send_json(message)
            except Exception:
                self.disconnect(profile_id)

manager = ConnectionManager()


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

@app.on_event("startup")
def migrate_database():
    inspector = inspect(engine)
    if "emergency_alerts" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("emergency_alerts")]
        db = SessionLocal()
        try:
            is_postgres = engine.name == "postgresql"
            dt_type = "TIMESTAMP WITH TIME ZONE" if is_postgres else "DATETIME"

            if "created_at" not in columns:
                db.execute(text(f"ALTER TABLE emergency_alerts ADD COLUMN created_at {dt_type}"))
            if "expires_at" not in columns:
                db.execute(text(f"ALTER TABLE emergency_alerts ADD COLUMN expires_at {dt_type}"))
            if "edesy_conversation_id" not in columns:
                db.execute(text("ALTER TABLE emergency_alerts ADD COLUMN edesy_conversation_id VARCHAR"))
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_emergency_alerts_edesy_conversation_id ON emergency_alerts (edesy_conversation_id)"))
            if "tracking_token" not in columns:
                db.execute(text("ALTER TABLE emergency_alerts ADD COLUMN tracking_token VARCHAR"))
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_emergency_alerts_tracking_token ON emergency_alerts (tracking_token)"))
            if "notification_log" not in columns:
                db.execute(text("ALTER TABLE emergency_alerts ADD COLUMN notification_log TEXT"))
            if "notification_status" not in columns:
                db.execute(text("ALTER TABLE emergency_alerts ADD COLUMN notification_status VARCHAR"))
            if "notified_at" not in columns:
                db.execute(text(f"ALTER TABLE emergency_alerts ADD COLUMN notified_at {dt_type}"))

            db.commit()

            # Backfill existing active records to prevent NULL expires_at bugs
            current_time = datetime.now(timezone.utc)
            db.execute(
                text("""
                UPDATE emergency_alerts
                SET
                    created_at = :current_time,
                    expires_at = :future_time
                WHERE status = 'active' AND (created_at IS NULL OR expires_at IS NULL)
                """),
                {"current_time": current_time, "future_time": current_time + timedelta(minutes=10)}
            )

            # For historically resolved alerts, we don't care about expires_at being NULL
            # but setting created_at to current_time is better than NULL for schema consistency
            db.execute(
                text("""
                UPDATE emergency_alerts
                SET created_at = :current_time
                WHERE status != 'active' AND created_at IS NULL
                """),
                {"current_time": current_time}
            )

            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Failed to migrate emergency_alerts schema: {e}")
            raise e
        finally:
            db.close()

    if "alert_acknowledgements" in inspector.get_table_names():
        constraints = [c["name"] for c in inspector.get_unique_constraints("alert_acknowledgements")]
        if "uix_alert_responder" not in constraints:
            db = SessionLocal()
            try:
                # SQLite ALTER TABLE ADD CONSTRAINT is limited, so we use a safe fallback index creation
                # which acts identically for enforcing uniqueness at the database level without dropping the table.
                db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uix_alert_responder ON alert_acknowledgements (alert_id, responder_profile_id)"))
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Failed to add unique constraint to alert_acknowledgements: {e}")
            finally:
                db.close()

    if "profiles" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("profiles")]
        db = SessionLocal()
        try:
            is_postgres = engine.name == "postgresql"
            dt_type = "TIMESTAMP WITH TIME ZONE" if is_postgres else "DATETIME"
            if "latitude" not in columns:
                db.execute(text("ALTER TABLE profiles ADD COLUMN latitude VARCHAR"))
            if "longitude" not in columns:
                db.execute(text("ALTER TABLE profiles ADD COLUMN longitude VARCHAR"))
            if "emergency_contact_phone" not in columns:
                db.execute(text("ALTER TABLE profiles ADD COLUMN emergency_contact_phone VARCHAR"))
            if "location_updated_at" not in columns:
                db.execute(text(f"ALTER TABLE profiles ADD COLUMN location_updated_at {dt_type}"))
            if "location_publish_token_hash" not in columns:
                db.execute(text("ALTER TABLE profiles ADD COLUMN location_publish_token_hash VARCHAR"))
                db.execute(text("CREATE INDEX IF NOT EXISTS ix_profiles_location_publish_token_hash ON profiles (location_publish_token_hash)"))
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Failed to migrate profiles schema: {e}")
            raise e
        finally:
            db.close()


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

@app.websocket("/ws/alerts/{profile_id}")
async def websocket_endpoint(websocket: WebSocket, profile_id: str):
    await manager.connect(websocket, profile_id)
    try:
        while True:
            # Keep connection alive, though client only receives
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(profile_id)


@app.post("/profiles/", response_model=ProfileResponse, status_code=201)
def create_profile(profile: ProfileCreate, db: Session = Depends(get_db)):
    """
    Create a new emergency profile.
    """
    db_profile = Profile(**profile.model_dump())
    if db_profile.latitude is not None and db_profile.longitude is not None:
        # Server-owned freshness: ignore any client-supplied timestamp.
        db_profile.location_updated_at = datetime.now(timezone.utc)
    else:
        db_profile.location_updated_at = None
    raw_token, token_hash = mint_location_publish_token()
    db_profile.location_publish_token_hash = token_hash
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    result = ProfileResponse.model_validate(db_profile)
    result.location_publish_token = raw_token
    return result

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
    if update_data.get("emergency_contact_phone"):
        owner_phone = update_data.get("phone_number", db_profile.phone_number)
        if owner_phone and update_data["emergency_contact_phone"] == owner_phone.strip():
            raise HTTPException(
                status_code=400,
                detail="emergency_contact_phone must be an emergency contact's number, "
                "not your own phone_number",
            )
    if "latitude" in update_data or "longitude" in update_data:
        # Location writes moved to the dedicated publish endpoint, which
        # requires the device publish token. This keeps tracking reads
        # (tracking token) and location writes (publish token) separate.
        raise HTTPException(
            status_code=422,
            detail="Use PUT /profiles/{profile_id}/location with the device publish token",
        )
    for key, value in update_data.items():
        setattr(db_profile, key, value)

    db.commit()
    db.refresh(db_profile)
    return db_profile


class LocationPublish(BaseModel):
    latitude: float
    longitude: float


class TokenRotate(BaseModel):
    phone_number: str


@app.put("/profiles/{profile_id}/location")
def publish_location(
    profile_id: str, payload: LocationPublish, request: Request, db: Session = Depends(get_db)
):
    """
    Device location-publish endpoint (live-tracking ingest).

    Requires the per-profile publish token in the X-Location-Token header.
    The emergency-contact tracking token is never accepted here.
    """
    db_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if db_profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    provided = request.headers.get(LOCATION_TOKEN_HEADER, "")
    if not provided:
        raise HTTPException(status_code=401, detail="Location publish token required")
    if not publish_token_matches(provided, db_profile.location_publish_token_hash):
        raise HTTPException(status_code=403, detail="Invalid location publish token")

    coords = parse_stored_coordinates(payload.latitude, payload.longitude)
    if coords is None:
        raise HTTPException(status_code=422, detail="Invalid GPS coordinates")

    db_profile.latitude = str(payload.latitude)
    db_profile.longitude = str(payload.longitude)
    db_profile.location_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(db_profile)
    return {
        "profile_id": db_profile.id,
        "latitude": db_profile.latitude,
        "longitude": db_profile.longitude,
        "location_updated_at": db_profile.location_updated_at.isoformat(),
    }


@app.post("/profiles/{profile_id}/location-token/rotate")
def rotate_location_token(
    profile_id: str, payload: TokenRotate, db: Session = Depends(get_db)
):
    """
    Mint a fresh device location-publish token, invalidating any previous
    one. Gated on the owner's phone number (bootstrap for existing devices
    and recovery for lost tokens). Returns the raw token once; only its
    hash is stored and it is never logged.
    """
    db_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if db_profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    if not payload.phone_number or payload.phone_number.strip() != (db_profile.phone_number or "").strip():
        raise HTTPException(status_code=403, detail="Phone number does not match profile")

    raw_token, token_hash = mint_location_publish_token()
    db_profile.location_publish_token_hash = token_hash
    db.commit()
    return {"profile_id": db_profile.id, "location_publish_token": raw_token}

def _skipped_communications(reason: str) -> dict:
    """Communications payload used when no new outbound dispatch occurs."""
    return {
        "voice": {
            "channel": "voice",
            "provider": "mock",
            "status": "skipped",
            "error": reason,
        },
        "message": {
            "channel": "message",
            "provider": "mock",
            "status": "skipped",
            "error": reason,
        },
    }


async def _process_sos(
    profile_id: str,
    latitude: Optional[float],
    longitude: Optional[float],
    db: Session,
):
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

    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=400,
            detail="Both latitude and longitude are required"
        )

    if latitude is not None and longitude is not None:
        if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
            raise HTTPException(
                status_code=400,
                detail="Invalid GPS coordinates"
            )

        trigger_latitude = str(latitude)
        trigger_longitude = str(longitude)
    else:
        if db_profile.latitude is None or db_profile.longitude is None:
            raise HTTPException(
                status_code=400,
                detail="Profile location is not available"
            )

        trigger_latitude = db_profile.latitude
        trigger_longitude = db_profile.longitude

    current_time = datetime.now(timezone.utc)

    if latitude is not None and longitude is not None:
        # The SOS request carries fresher coordinates than the background
        # watcher may have stored: make them the profile's current location
        # immediately so the Edesy announcement uses them.
        db_profile.latitude = trigger_latitude
        db_profile.longitude = trigger_longitude
        db_profile.location_updated_at = current_time
        db.commit()
        db.refresh(db_profile)

    # Check for existing active, unexpired alert
    existing_alert = db.query(EmergencyAlert).filter(
        EmergencyAlert.profile_id == profile_id,
        EmergencyAlert.status == "active",
        EmergencyAlert.expires_at > current_time
    ).first()

    if existing_alert:
        # Fetch acknowledgements for existing alert
        acknowledged_responders = []
        acks = db.query(AlertAcknowledgement).filter(AlertAcknowledgement.alert_id == existing_alert.id).all()
        for ack in acks:
            responder_profile = db.query(Profile).filter(Profile.id == ack.responder_profile_id).first()
            if responder_profile:
                acknowledged_responders.append({
                    "profile_id": responder_profile.id,
                    "full_name": responder_profile.full_name,
                    "responder_phone": responder_profile.phone_number,
                    "status": "on_the_way"
                })

        return {
            "message": "SOS Alert already active",
            "alert_id": existing_alert.id,
            "profile_id": db_profile.id,
            "full_name": db_profile.full_name,
            "latitude": existing_alert.latitude,
            "longitude": existing_alert.longitude,
            "blood_group": db_profile.blood_group,
            "allergies": db_profile.allergies,
            "medical_conditions": db_profile.medical_conditions,
            "medications": db_profile.medications,
            "emergency_contacts": db_profile.emergency_contacts,
            "emergency_contact_phone": db_profile.emergency_contact_phone,
            "tracking_url": build_tracking_url(existing_alert.tracking_token or ""),
            "nearby_users": [],  # Existing logic wouldn't re-notify
            "acknowledged_responders": acknowledged_responders,
            "communications": _skipped_communications(
                "Alert already active; duplicate dispatch suppressed"
            ),
            "notifications": _stored_notification_summary(existing_alert),
        }

    # Create and save new emergency alert
    expires_at = current_time + timedelta(minutes=10)
    emergency_alert = EmergencyAlert(
        profile_id=db_profile.id,
        latitude=trigger_latitude,
        longitude=trigger_longitude,
        status="active",
        created_at=current_time,
        expires_at=expires_at
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
            trigger_latitude,
            trigger_longitude,
            profile.latitude,
            profile.longitude
        )

        if distance <= 1.0:
            nearby_users.append({
                "profile_id": profile.id,
                "full_name": profile.full_name,
                "distance_km": round(distance, 2)
            })

            # Broadcast via WebSocket if the nearby user is connected
            ws_payload = {
                "type": "ALERT_CREATED",
                "data": {
                    "alert_id": emergency_alert.id,
                    "profile_id": db_profile.id,
                    "full_name": db_profile.full_name,
                    "latitude": trigger_latitude,
                    "longitude": trigger_longitude,
                    "distance_km": round(distance, 2),
                    "expires_at": expires_at.isoformat(),
                    "has_acknowledged": False
                }
            }
            await manager.send_personal_message(ws_payload, profile.id)

    # Fetch any existing acknowledgements just in case it's an existing alert returned
    acknowledged_responders = []
    if existing_alert:
        acks = db.query(AlertAcknowledgement).filter(AlertAcknowledgement.alert_id == existing_alert.id).all()
        for ack in acks:
            responder_profile = db.query(Profile).filter(Profile.id == ack.responder_profile_id).first()
            if responder_profile:
                acknowledged_responders.append({
                    "profile_id": responder_profile.id,
                    "full_name": responder_profile.full_name,
                    "responder_phone": responder_profile.phone_number,
                    "status": "on_the_way"
                })

    # Tracking token: minted once per alert so the duplicate-SOS path can
    # re-affirm the same URL without re-issuing or re-notifying.
    if not emergency_alert.tracking_token:
        emergency_alert.tracking_token = secrets.token_urlsafe(32)
        try:
            db.commit()
        except Exception:  # noqa: BLE001 - SOS itself is already safe
            db.rollback()
    tracking_url = build_tracking_url(emergency_alert.tracking_token or "")

    # NOTE: emergency_contacts is free-form text and is never parsed for
    # dialing. destination_phone comes only from the structured
    # `emergency_contact_phone` field; when absent, outbound channels
    # report "skipped" instead of guessing a number. phone_number is the
    # owner's own number and is never used as the emergency contact.
    destination_phone = db_profile.emergency_contact_phone or None

    # Independent best-effort channels. The alert is already committed;
    # failures here must not roll it back, and a slow/failing provider
    # must not delay the other channels.
    comm_context = EmergencyContext(
        alert_id=emergency_alert.id,
        profile_id=db_profile.id,
        full_name=db_profile.full_name,
        latitude=trigger_latitude,
        longitude=trigger_longitude,
        destination_phone=destination_phone,
    )
    notify_context = NotificationContext(
        alert_id=emergency_alert.id,
        profile_name=db_profile.full_name,
        tracking_url=tracking_url,
        destination_phone=destination_phone or "",
    )
    notify_service = get_notification_service()
    comm_service = get_communication_service()

    async def _run_notify():
        if not destination_phone:
            return {
                "whatsapp": NotificationResult(
                    channel="whatsapp",
                    provider="mock-whatsapp",
                    status="skipped",
                    error="No structured emergency-contact phone number available",
                )
            }
        return await notify_service.send_with_fallback(notify_context)

    try:
        notify_models, comm_models = await asyncio.gather(
            asyncio.wait_for(_run_notify(), timeout=CHANNEL_TIMEOUT_SECONDS),
            asyncio.wait_for(
                comm_service.dispatch(comm_context), timeout=CHANNEL_TIMEOUT_SECONDS
            ),
            return_exceptions=True,
        )
    except Exception:  # noqa: BLE001 - gather itself must never break SOS
        notify_models, comm_models = None, None

    notify_models = _normalize_notify_models(notify_models)
    comm_models = _normalize_voice_models(comm_models)
    _persist_notification_outcome(db, emergency_alert, notify_models)
    notifications = {
        key: value.model_dump() for key, value in notify_models.items()
    }
    communications = {
        key: value.model_dump() for key, value in comm_models.items()
    }
    # Correlate the voice call with this SOS as soon as Edesy returns
    # its conversation ID. Best-effort: never breaks the SOS response.
    voice_result = comm_models.get("voice")
    external_id = getattr(voice_result, "external_id", None)
    if (
        getattr(voice_result, "provider", None) == "edesy"
        and getattr(voice_result, "status", None) == "sent"
        and external_id
    ):
        try:
            emergency_alert.edesy_conversation_id = external_id
            db.commit()
        except Exception:
            db.rollback()

    return {
        "message": "SOS Alert Triggered",
        "alert_id": emergency_alert.id if not existing_alert else existing_alert.id,
        "profile_id": db_profile.id,
        "full_name": db_profile.full_name,
        "latitude": trigger_latitude,
        "longitude": trigger_longitude,
        "blood_group": db_profile.blood_group,
        "allergies": db_profile.allergies,
        "medical_conditions": db_profile.medical_conditions,
        "medications": db_profile.medications,
        "emergency_contacts": db_profile.emergency_contacts,
        "emergency_contact_phone": db_profile.emergency_contact_phone,
        "tracking_url": tracking_url,
        "nearby_users": nearby_users,
        "acknowledged_responders": acknowledged_responders,
        "communications": communications,
        "notifications": notifications,
    }


@app.post("/sos/{profile_id}")
async def sos_alert_post(
    profile_id: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """
    Trigger an SOS alert (preferred endpoint).
    Uses the existing latitude/longitude query parameters.
    """
    return await _process_sos(profile_id, latitude, longitude, db)


@app.get("/sos/{profile_id}", deprecated=True)
async def sos_alert(
    profile_id: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    db: Session = Depends(get_db),
    response: Response = None,
):
    """
    Deprecated backward-compatible SOS shim. Prefer POST /sos/{profile_id}.
    Repeat calls within the active-alert window return the existing alert
    without triggering duplicate external communications.
    """
    if response is not None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "POST /sos/{profile_id} is preferred"
    return await _process_sos(profile_id, latitude, longitude, db)
@app.get("/track/{token}")
def track_location(token: str, response: Response, db: Session = Depends(get_db)):
    """
    Emergency-contact tracking page data. Token possession plus an active,
    unexpired alert is the authorization: no login, no profile IDs, no
    coordinates as user-facing text (map URLs only).

    Ended/expired/unknown links expose zero location data.
    """
    response.headers["Cache-Control"] = "no-store"

    if token:
        now = time.monotonic()
        hits = [t for t in _track_request_times.get(token, []) if now - t < 60]
        if len(hits) >= TRACK_RATE_LIMIT_PER_MINUTE:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        hits.append(now)
        _track_request_times[token] = hits

    alert = db.query(EmergencyAlert).filter(
        EmergencyAlert.tracking_token == token
    ).first() if token else None
    if alert is None:
        raise HTTPException(
            status_code=404, detail="Tracking link not found"
        )

    current_time = datetime.now(timezone.utc)
    expires_at = _ensure_aware(alert.expires_at)
    if alert.status != "active" or (expires_at and expires_at < current_time):
        raise HTTPException(
            status_code=410, detail="Tracking has ended"
        )

    affected = db.query(Profile).filter(Profile.id == alert.profile_id).first()
    if affected is None:
        raise HTTPException(status_code=410, detail="Tracking has ended")

    coords = parse_stored_coordinates(affected.latitude, affected.longitude)
    updated_at = _ensure_aware(affected.location_updated_at)
    if coords is None:
        location_status = "unavailable"
    elif updated_at is None or (current_time - updated_at).total_seconds() > LOCATION_STALE_AFTER_SECONDS:
        location_status = "stale"
    else:
        location_status = "current"

    has_location = coords is not None
    return {
        "person_name": affected.full_name,
        "tracking_active": True,
        "location_status": location_status,
        "location_updated_at": updated_at.isoformat() if updated_at else None,
        "has_location": has_location,
        "maps_url": build_google_maps_url(affected.latitude, affected.longitude) if has_location else None,
        "map_embed_url": build_map_embed_url(affected.latitude, affected.longitude) if has_location else None,
    }


@app.post("/alerts/{alert_id}/notify")
async def notify_alert(alert_id: str, profile_id: str, db: Session = Depends(get_db)):
    """
    Owner-gated manual notification retry. Honors the sent-guard:
    best-effort duplicate prevention, never a blind re-dispatch.
    """
    alert = db.query(EmergencyAlert).filter(
        EmergencyAlert.id == alert_id
    ).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.profile_id != profile_id:
        raise HTTPException(
            status_code=403, detail="Only the SOS owner can retry notification"
        )

    owner = db.query(Profile).filter(Profile.id == alert.profile_id).first()
    if alert.notification_status == "sent":
        return {
            "message": "Notification already sent",
            "alert_id": alert.id,
            "notifications": _stored_notification_summary(alert),
        }

    if not alert.tracking_token:
        alert.tracking_token = secrets.token_urlsafe(32)
        try:
            db.commit()
        except Exception:
            db.rollback()
    context = NotificationContext(
        alert_id=alert.id,
        profile_name=owner.full_name if owner else "Unknown",
        tracking_url=build_tracking_url(alert.tracking_token or ""),
        destination_phone=(owner.emergency_contact_phone or "") if owner else "",
    )
    if not context.destination_phone:
        results = {
            "whatsapp": NotificationResult(
                channel="whatsapp",
                provider="mock-whatsapp",
                status="skipped",
                error="No structured emergency-contact phone number available",
            )
        }
    else:
        try:
            results = await asyncio.wait_for(
                get_notification_service().send_with_fallback(context),
                timeout=CHANNEL_TIMEOUT_SECONDS,
            )
            if not isinstance(results, dict):
                results = _normalize_notify_models(results)
        except Exception as exc:  # noqa: BLE001
            results = _normalize_notify_models(exc)
    _persist_notification_outcome(db, alert, results)
    return {
        "message": "Notification dispatch attempted",
        "alert_id": alert.id,
        "notifications": {key: value.model_dump() for key, value in results.items()},
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

    current_time = datetime.now(timezone.utc)
    active_alerts = db.query(EmergencyAlert).filter(
        EmergencyAlert.status == "active",
        EmergencyAlert.expires_at > current_time
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

            has_acknowledged = db.query(AlertAcknowledgement).filter(
                AlertAcknowledgement.alert_id == alert.id,
                AlertAcknowledgement.responder_profile_id == profile_id
            ).first() is not None

            nearby_alerts.append({
                "alert_id": alert.id,
                "profile_id": alert.profile_id,
                "full_name": emergency_profile.full_name if emergency_profile else None,
                "latitude": alert.latitude,
                "longitude": alert.longitude,
                "distance_km": round(distance, 2),
                "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
                "has_acknowledged": has_acknowledged
            })

    return {
        "responder_profile_id": profile_id,
        "radius_km": radius_km,
        "nearby_alerts": nearby_alerts
    }


@app.post("/alerts/{alert_id}/respond")
async def respond_to_alert(alert_id: str, profile_id: str, db: Session = Depends(get_db)):
    """
    Indicate that a responder is on the way to help with an active alert.
    """
    alert = db.query(EmergencyAlert).filter(
        EmergencyAlert.id == alert_id
    ).first()

    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    current_time = datetime.now(timezone.utc)
    # SQLAlchemy SQLite returns naive datetimes. Convert to aware for comparison.
    expires_at = alert.expires_at.replace(tzinfo=timezone.utc) if alert.expires_at and alert.expires_at.tzinfo is None else alert.expires_at
    if alert.status != "active" or (expires_at and expires_at < current_time):
        raise HTTPException(status_code=400, detail="Alert is no longer active")

    if alert.profile_id == profile_id:
        raise HTTPException(status_code=400, detail="Cannot respond to your own SOS")

    responder = db.query(Profile).filter(Profile.id == profile_id).first()
    if responder is None:
        raise HTTPException(status_code=404, detail="Responder profile not found")

    if not alert.latitude or not alert.longitude:
        raise HTTPException(status_code=400, detail="Alert location is missing")

    if not responder.latitude or not responder.longitude:
        raise HTTPException(status_code=400, detail="Responder location is missing")

    distance = calculate_distance(
        alert.latitude, alert.longitude,
        responder.latitude, responder.longitude
    )

    if distance > 1.0:
        raise HTTPException(status_code=403, detail="Responder is too far away to acknowledge")

    # Check for existing acknowledgement (Idempotency)
    existing_ack = db.query(AlertAcknowledgement).filter(
        AlertAcknowledgement.alert_id == alert_id,
        AlertAcknowledgement.responder_profile_id == profile_id
    ).first()

    if not existing_ack:
        new_ack = AlertAcknowledgement(
            alert_id=alert_id,
            responder_profile_id=profile_id
        )
        db.add(new_ack)
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            # If concurrent request already inserted it, catch the unique constraint violation
            # and gracefully fall through to sending the response (idempotent success)
            if "UNIQUE constraint failed" not in str(e) and "Duplicate entry" not in str(e):
                raise HTTPException(status_code=500, detail="Database error occurred")
            pass
        else:
            # Broadcast to SOS sender only if we actually inserted it
            ws_payload = {
                "type": "ALERT_RESPONDER_ACKNOWLEDGED",
                "data": {
                    "alert_id": alert.id,
                    "responder_profile_id": responder.id,
                    "responder_name": responder.full_name,
                    "responder_phone": responder.phone_number,
                    "status": "on_the_way"
                }
            }
            await manager.send_personal_message(ws_payload, alert.profile_id)

    return {
        "message": "Acknowledgement recorded successfully",
        "alert_id": alert_id,
        "responder_profile_id": profile_id
    }

@app.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, profile_id: str, db: Session = Depends(get_db)):
    """
    Mark an emergency alert as resolved. Only the SOS owner can do this.
    """
    alert = db.query(EmergencyAlert).filter(
        EmergencyAlert.id == alert_id
    ).first()

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    if alert.profile_id != profile_id:
        raise HTTPException(
            status_code=403,
            detail="Only the SOS owner can resolve this alert"
        )

    alert.status = "resolved"
    db.commit()
    db.refresh(alert)

    # Broadcast resolution to nearby connected users
    all_profiles = db.query(Profile).all()
    for profile in all_profiles:
        if profile.latitude and profile.longitude and alert.latitude and alert.longitude:
            distance = calculate_distance(
                alert.latitude, alert.longitude,
                profile.latitude, profile.longitude
            )
            if distance <= 1.0:
                ws_payload = {
                    "type": "ALERT_RESOLVED",
                    "data": {
                        "alert_id": alert.id
                    }
                }
                await manager.send_personal_message(ws_payload, profile.id)

    return {
        "message": "Alert resolved successfully",
        "alert_id": alert.id,
        "status": alert.status
    }