# Emergency E-Card Backend MVP

This is the backend for the Emergency E-Card hackathon project. It provides a RESTful API using FastAPI and SQLite to manage emergency profiles.

## Requirements
- Python 3.8+

## Setup Instructions

1. **Create a virtual environment (optional but recommended):**
   ```bash
   python -m venv venv
   ```

2. **Activate the virtual environment:**
   - On Windows:
     ```bash
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```

3. **Install the dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the backend server:**
   ```bash
   uvicorn main:app --reload
   ```

5. **Access the API:**
   - The API will be running at `http://127.0.0.1:8000`
   - You can view the interactive Swagger API documentation at `http://127.0.0.1:8000/docs`

## API Endpoints

- `POST /profiles/`: Create a new profile.
- `GET /profiles/{profile_id}`: Retrieve a profile.
- `PUT /profiles/{profile_id}`: Update an existing profile.
- `POST /sos/{profile_id}`: Trigger an SOS alert (preferred). `GET /sos/{profile_id}` is kept as a deprecated shim.

## Emergency Voice Calls (Edesy)

Outbound voice calls use the Edesy Voice Agent through Edesy's Calls API.
The integration is provider-independent: `EdesyVoiceProvider` implements the
`VoiceProvider` contract in `services/communication.py` and is selected via
environment variables. `MockVoiceProvider` remains the default so tests and
normal development never place a real call.

Environment variables:

```bash
EDESY_API_KEY=your_vp_live_api_key_here   # Edesy API Key (Bearer token). Never commit a real key.
EDESY_AGENT_ID=49976                       # Edesy Voice Agent ID (Agent ID of the Emergency E-Card SOS Agent).
COMMUNICATION_VOICE_PROVIDER=mock          # `mock` (default) or `edesy`.
```

Behavior:

- `EDESY_API_KEY` holds the Edesy API Key sent as `Authorization: Bearer <API Key>`.
- `EDESY_AGENT_ID` identifies the Edesy Voice Agent used by the Calls API.
- `COMMUNICATION_VOICE_PROVIDER=edesy` enables real Calls API requests;
  anything else falls back to the mock provider.
- The Dynamic Variable `person_name` (SOS profile full name) is passed to the
  Voice Agent through the Calls API `variables` object.
- Successful Calls API responses expose `conversationId` / `callSid`, which are
  preserved as the communication result's external ID. The API Key is never
  logged, returned, or stored.
- The call destination must be a structured emergency-contact phone number,
  supplied as the profile's `emergency_contact_phone` field (E.164 format,
  e.g. `+919876543210`). `emergency_contacts` is free-form text and is never
  parsed for dialing; when no structured number is present, voice dispatch
  reports `skipped` instead of guessing a number. The owner's own
  `phone_number` is never used as the call destination.

## Live Location Tracking + Contact Notification

 SOS creates a secure tracking session for the emergency contact:

 - `Profile.location_updated_at` records when coordinates were last updated
   (profile creation, the device publish endpoint, and the SOS trigger itself
   when it carries coordinates). The SOS trigger snapshot on
   `EmergencyAlert` is preserved for responder proximity.
 - Each alert mints one opaque `tracking_token`; the contact opens
   `/track/{token}` (no login), which polls `GET /track/{token}` and shows a
   map marker plus live/latest-known/unavailable states. Tracking is valid
   only while the alert is active and unexpired; afterwards the link returns
   410 with zero location data. Coordinates are never rendered as text.
 - Device location publishing uses `PUT /profiles/{id}/location` with the
   per-profile publish token (`X-Location-Token` header; hash stored, raw
   shown once at creation/rotation). The general profile endpoint no longer
   accepts coordinates, and the tracking token can never authorize writes.
 - Notifications are mock-only via `services/notification.py` (WhatsApp
   preferred, single SMS fallback, best-effort duplicate prevention). No
   coordinates appear in message content — only the tracking link.

 Environment (placeholders only, never real secrets):

 ```bash
 COMMUNICATION_VOICE_PROVIDER=mock   # `mock` (default) or `edesy`.
 TRACKING_BASE_URL=                  # e.g. https://<tunnel-url> for absolute
                                     # tracking links; empty keeps /track/…
 LOCATION_STALE_AFTER_SECONDS=300    # live vs latest-known threshold.
 ```

 The Edesy Voice Agent carries no location: the voice payload contains only
 the `person_name` Dynamic Variable, and the former `/voice/location` tool
 endpoint has been retired in favor of the tracking system above.

 Local end-to-end testing:

 1. Run the backend (`uvicorn main:app --reload`) and frontend locally.
 2. Expose the backend through a temporary HTTPS tunnel (e.g. a tunnel
    service of your choice). The tunnel URL is temporary: never hard-code or
    commit it; set it as `TRACKING_BASE_URL` only in the local environment.
 3. Trigger SOS from a test profile, open the returned `tracking_url` in a
    separate browser, update the profile location mid-SOS, and confirm the
    tracking page shows the new position. Resolve the SOS and confirm the
    link reports tracking ended.
