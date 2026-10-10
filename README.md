# 🚨 Emergency E-Card

### Critical medical information and location-aware SOS response when every second counts.

**Emergency E-Card** is a full-stack web prototype for creating an emergency medical profile, raising an SOS alert, finding nearby registered responders, sharing live/latest-known location through a time-limited tracking link, and updating the affected person when a responder is on the way.

- **Live demo:** https://emergency-e-card-1.onrender.com
- **This repository:** https://github.com/mohammed-hasan-ECE/emergency-e-card


> **Prototype and delivery note:** This project is not a substitute for official emergency services. The WhatsApp/SMS notification providers in the current code are mocks, and the voice-call integration defaults to a mock provider. Browser Web Push for notifications while the website is closed is not implemented in the current pushed `main` branch. Do not assume that any real notification or call was delivered unless it has been verified separately.

---

## What it does

Emergency E-Card focuses on three core pieces of an emergency:

| Need | Current implementation |
|---|---|
| **Medical information** | A reusable profile containing contact details, blood group, allergies, medical conditions, medications, and emergency-contact information |
| **Nearby help** | SOS alerts, location-based responder discovery, acknowledgement, and live status updates |
| **Contact tracking** | An opaque, time-limited tracking link with current, last-known, or unavailable location status |

## Features in the pushed `main` branch

### 🪪 Emergency medical profile
- Create and edit a profile with personal and essential medical information.
- Store emergency-contact name/relationship separately from a structured emergency-contact phone number.
- Validate the structured phone number in international E.164 format and reject the owner's own number as the emergency-contact destination.
- Keep the browser's current profile ID in local storage for this prototype; there is no full account/login system.

### 🆘 SOS and nearby responder discovery
- Trigger an SOS using the profile's current coordinates.
- Store an alert with an expiry time (currently 10 minutes).
- Discover nearby registered profiles and active alerts within the configured radius; the SOS flow uses a 1 km proximity boundary.
- Let another registered profile acknowledge an alert as “on the way.”
- Prevent a responder from acknowledging the same alert more than once; the database enforces uniqueness per alert/responder pair.
- Let the SOS owner resolve their alert.
- Suppress repeated SOS dispatch when the backend finds an existing active, unexpired alert for that profile. This is application-level duplicate suppression, not a guarantee against every possible concurrent-request race.

### ⚡ Real-time updates
- Use WebSockets to send newly created alerts to connected nearby profiles.
- Update the SOS owner's screen when a responder acknowledges.
- Broadcast alert resolution to connected nearby profiles so the alert can be removed from the responder dashboard.
- Use REST endpoints to load profiles and nearby alerts; the responder dashboard includes manual refresh and navigation to the SOS location via Google Maps.

### 📍 Live and latest-known location tracking
- The frontend requests browser geolocation permission and publishes updated coordinates while the app is open and location access is available.
- Location writes use `PUT /profiles/{profile_id}/location` and require the profile's location-publish token in the `X-Location-Token` header.
- The raw publish token is issued at profile creation or token rotation; the database stores its hash. The token used for location publishing is separate from the emergency-contact tracking token.
- Each SOS can have an opaque tracking token and a tracking page at `/track/{token}`.
- The tracking page refreshes tracking data periodically and distinguishes **Live location**, **Last known location**, and **Location unavailable**.
- A tracking link works only while its alert is active and unexpired. An ended, expired, or unknown link returns no location data.
- The location status becomes stale after the configured threshold (default: 300 seconds). The page offers an embedded map and a link to open the location in Google Maps.

**Location caveat:** Browser geolocation depends on device permission, connectivity, and the application being able to publish updates. It does not guarantee continuous background tracking.

### 📞 Optional Edesy voice-call integration
- A provider-independent communication layer separates the SOS flow from its voice/message providers.
- An Edesy Calls API provider is present in the code and can be selected with `COMMUNICATION_VOICE_PROVIDER=edesy`.
- The structured `emergency_contact_phone` field is used as the destination; the free-form emergency-contact text and the owner's own phone number are not used for dialing.
- The Edesy request passes the person's name as a dynamic variable; coordinates and medical details are not included in the voice API request.
- API/network failures, timeouts, malformed responses, missing keys, and missing destinations have structured outcomes.

**Important:** `COMMUNICATION_VOICE_PROVIDER=mock` is the default. The mock provider logs a simulated attempt and never places a call. Real calls require valid provider credentials/configuration and separate end-to-end verification.

### 🔔 Emergency-contact notification attempt tracking
- SOS generates a tracking link and passes it to the notification layer.
- The current notification layer attempts WhatsApp first and defines one SMS fallback if the first attempt fails.
- Attempt results and timestamps are stored with the alert; a manual retry endpoint includes a best-effort sent-status guard.
- Sensitive coordinates are not included in the contact-facing message body.

**These WhatsApp and SMS providers are mock-only in the current code.** A mock result must not be interpreted as a real message being sent or received. Delivery of actual WhatsApp/SMS notifications is not implemented in this branch.

---

## How the main flow works

```text
Create / edit emergency profile
              |
              v
   Trigger SOS with location
              |
              v
 Save alert (10-minute expiry)
              |
              +----> Discover nearby profiles (1 km)
              |                |
              |                v
              |      WebSocket: ALERT_CREATED
              |                |
              |                v
              |       Responder acknowledges
              |                |
              |                v
              |    Owner gets live responder update
              |
              +----> Create tokenized tracking link
              |
              +----> Run configured communication providers
                              |
                              v
                 Record attempt/result status
                              |
                              v
                   Owner resolves the alert
                              |
                              v
              Tracking ends; resolution broadcasts
```

The core SOS alert is saved before best-effort communication dispatch. A failed optional communication attempt should not roll back the saved alert.

---

## Architecture

```text
React + TypeScript + Vite frontend
  - Profile creation/editing and medical card
  - SOS screen and responder dashboard
  - Browser geolocation publisher
  - Public tracking page
               |
               | REST API + WebSocket
               v
FastAPI backend
  - Profiles and location validation
  - SOS lifecycle and proximity checks
  - Responder acknowledgements
  - Token-based tracking
  - Communication / notification provider layers
               |
               | SQLAlchemy
               v
SQLite for local fallback / PostgreSQL via DATABASE_URL
```

### Technology stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite, Tailwind CSS, React Router, Axios |
| Backend | Python, FastAPI, Uvicorn, Pydantic |
| Persistence | SQLAlchemy, SQLite local fallback, PostgreSQL support |
| Real-time updates | WebSockets |
| Maps | Google Maps links and embedded map |
| Voice provider option | Edesy Calls API; mock provider is default |
| Deployment | Render is the configured demo host |
| Testing | pytest, httpx, provider and API tests |

The backend creates tables through SQLAlchemy's `Base.metadata.create_all()` and includes startup-time schema adjustments for earlier database versions. The current repository does not contain a versioned Alembic migration history.

---

## Repository layout

```text
emergency-e-card/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── services/
│   │   ├── communication.py
│   │   └── notification.py
│   ├── test_main.py
│   ├── test_communication.py
│   ├── test_edesy.py
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   └── Layout.tsx
│   │   ├── pages/
│   │   │   ├── CreateProfile.tsx
│   │   │   ├── EditProfile.tsx
│   │   │   ├── EmergencyDetails.tsx
│   │   │   ├── Home.tsx
│   │   │   ├── MyCard.tsx
│   │   │   ├── ResponderDashboard.tsx
│   │   │   ├── SOS.tsx
│   │   │   └── TrackPage.tsx
│   │   ├── services/
│   │   │   ├── api.ts
│   │   │   └── storage.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

---

## Run locally

### 1. Backend

Use Python 3.10 or later for a modern environment.

Linux / macOS / WSL:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell (from the repository root):

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### 2. Frontend

Open another terminal from the repository root:

```bash
cd frontend
npm install
```

Create a local `.env.local` file inside `frontend/`:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Then start Vite:

```bash
npm run dev -- --host 0.0.0.0
```

Open the frontend URL printed by Vite. If testing from a phone or another device, `VITE_API_URL` must point to a backend URL that device can reach; `localhost` on the phone refers to the phone itself. Use HTTPS and correctly configure allowed origins for externally reachable tests.

### 3. Backend configuration

The backend reads configuration from environment variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Database connection string. If unset, local SQLite is used. PostgreSQL URLs are supported. |
| `TRACKING_BASE_URL` | Public frontend base URL used to make full tracking links, e.g. `https://your-frontend.example`. Leave empty to return an app-relative tracking path. |
| `LOCATION_STALE_AFTER_SECONDS` | Age threshold for labelling a location as stale; defaults to `300`. |
| `COMMUNICATION_VOICE_PROVIDER` | `mock` by default; set to `edesy` to select the Edesy voice provider. |
| `EDESY_API_KEY` | Secret API key required when using the Edesy provider. Never commit it. |
| `EDESY_AGENT_ID` | Optional Edesy agent ID override. |

Keep real credentials in local environment configuration or deployment secrets. Never commit API keys, database credentials, real tracking links, or device tokens. If using a temporary HTTPS tunnel, do not hard-code its changing URL into source code.

---

## API overview

The backend exposes these main endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/profiles/` | Create an emergency profile |
| `GET` | `/profiles/{profile_id}` | Retrieve a profile |
| `PUT` | `/profiles/{profile_id}` | Update profile details |
| `PUT` | `/profiles/{profile_id}/location` | Publish location using `X-Location-Token` |
| `POST` | `/profiles/{profile_id}/location-token/rotate` | Rotate the device location-publish token |
| `POST` | `/sos/{profile_id}` | Trigger SOS (preferred method) |
| `GET` | `/sos/{profile_id}` | Deprecated SOS compatibility route |
| `GET` | `/nearby/{profile_id}` | Find nearby profiles |
| `GET` | `/alerts/{profile_id}` | Retrieve nearby active alerts |
| `POST` | `/alerts/{alert_id}/respond?profile_id=...` | Acknowledge an alert |
| `POST` | `/alerts/{alert_id}/resolve?profile_id=...` | Resolve an alert as its owner |
| `POST` | `/alerts/{alert_id}/notify?profile_id=...` | Retry the configured contact-notification attempt |
| `GET` | `/track/{token}` | Retrieve tracking data while the alert is active |
| `WS` | `/ws/alerts/{profile_id}` | Receive real-time alert events |

---

## Tests

The repository contains backend tests in:

- `backend/test_main.py` — profile, SOS lifecycle, location publishing, tracking, notification handling and retry behaviour.
- `backend/test_communication.py` — provider abstraction, mock defaults, and failure isolation.
- `backend/test_edesy.py` — Edesy request/response handling and failure cases.

Run the backend suite from the `backend/` directory with:

```bash
pytest
```

These are automated tests; they do not prove that an external provider placed a real call or delivered a real message. Real-provider and deployed behaviour must be verified separately.

---

## Limitations and security notes

- **Prototype only:** Do not rely on this project as the sole means of emergency assistance. It does not contact official emergency services such as India's 112 service.
- **No full account authentication:** The current application stores a profile ID in browser local storage and uses profile-ID-based API flows. This is not equivalent to a production account/identity system.
- **Token-sensitive tracking:** A tracking URL acts as a bearer link. Share it only with the intended contact; tracking ends when the alert is resolved or expires.
- **Notification channels:** WhatsApp/SMS providers are mock-only in this branch. The voice provider defaults to mock as well; configuring a real provider requires credentials and end-to-end verification.
- **No browser Web Push in current `main`:** The current branch has no committed service-worker push handler, browser subscription endpoint, or VAPID/pywebpush implementation. Closed-site phone notifications remain future work.
- **Location limits:** Geolocation requires browser permission, and freshness depends on the device being able to publish updates. A map marker is not a guarantee of a person's exact current position.
- **Deployment hardening:** Review authentication, CORS, rate limiting, secrets management, database migrations, observability and provider failure handling before any production or real-emergency use.
- **Data privacy:** Use test profiles for demos. Do not put real medical information, phone numbers, API keys or tokens in source control or screenshots.

---

## Future work

Potential next improvements include:

- Reliable browser push delivery and real-device testing.
- Real provider integrations for emergency-contact messaging, with explicit delivery status and safe retries.
- Stronger ownership and contact authentication.
- Contact invitation/acceptance, revocation and notification inbox.
- Authenticated acknowledgement and carefully tested escalation rules.
- Better deployment hardening, monitoring and migration management.

---

## Team BIT-CRAFT

| Member | Role |
|---|---|
| **Mohammed Hasan** | Team Leader & Backend Developer |
| **Niranjan S J** | Team Member |
| **Jaiabner N** | Team Member |

**Hackathon:** Morrow 1.0 by Makers Need More  
**Round:** Round 2 — Project & Prototype Submission

> 🚨 *Because sometimes the nearest help is just around the corner.*
