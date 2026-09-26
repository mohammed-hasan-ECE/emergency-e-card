import uuid
import math
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, String, Text, DateTime, inspect, text, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from services.communication import EmergencyContext, get_communication_service

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=True)

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
            if "latitude" not in columns:
                db.execute(text("ALTER TABLE profiles ADD COLUMN latitude VARCHAR"))
            if "longitude" not in columns:
                db.execute(text("ALTER TABLE profiles ADD COLUMN longitude VARCHAR"))
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
            "emergency_contacts": db_profile.emergency_contacts,
            "nearby_users": [],  # Existing logic wouldn't re-notify
            "acknowledged_responders": acknowledged_responders,
            "communications": _skipped_communications(
                "Alert already active; duplicate dispatch suppressed"
            ),
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

    # Provider-independent outbound communication (best-effort, mock-only).
    # The alert is already committed above; failures here must not roll it back.
    try:
        comm_service = get_communication_service()
        comm_context = EmergencyContext(
            alert_id=emergency_alert.id,
            profile_id=db_profile.id,
            full_name=db_profile.full_name,
            latitude=trigger_latitude,
            longitude=trigger_longitude,
        )
        comm_results = await comm_service.dispatch(comm_context)
        communications = {
            key: value.model_dump() for key, value in comm_results.items()
        }
    except Exception as exc:  # noqa: BLE001 - comms must never break SOS
        communications = {
            "voice": {
                "channel": "voice",
                "provider": "mock",
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            },
            "message": {
                "channel": "message",
                "provider": "mock",
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            },
        }

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
        "emergency_contacts": db_profile.emergency_contacts,
        "nearby_users": nearby_users,
        "acknowledged_responders": acknowledged_responders,
        "communications": communications,
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