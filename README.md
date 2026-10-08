# 🚨 Emergency E-Card

### The fastest help is often the person standing closest to you.

**Emergency E-Card** is a real-time emergency assistance platform which connects a person in distress with nearby willing responders.

**🚀 Live Demo:** https://emergency-e-card-1.onrender.com

**📦 Repository:** https://github.com/MakersNeedMore-MnM/Round2-BIT-CRAFT

**Morrow 1.0 · Round 2 · Team BIT-CRAFT**

---

## ⚡ THE IDEA

A person creates an **Emergency E-Card** once with essential emergency information.

When an emergency occurs:

**SOS → Nearby responders discover the alert → "I'm Coming to Help" → Real-time notification → Help is on the way**

The person requesting help can see who is responding without manually refreshing the application.

> **Our goal is simple: shrink the gap between "I need help" and "someone is on the way."**

---

## 🎯 THE PROBLEM

During an emergency, the closest available help may be only a few metres or minutes away.

The challenge is connecting the person who needs help with someone nearby who can actually respond.

Traditional communication can create several gaps:

* **Nobody Nearby Knows** — People who could help may not know that someone nearby needs assistance.
* **Details Cost Time** — Sharing identity, location, and emergency information manually takes valuable time.
* **No Response Feedback** — The person requesting help may not know whether anyone is actually coming.
* **Fragmented Communication** — Calls, messages, and different applications handle different parts of an emergency.

---

## 💡 THE SOLUTION

Emergency E-Card connects three critical pieces of information:

|                      |                             |
| -------------------- | --------------------------- |
| 🪪 **Who You Are**   | Emergency Profile           |
| 📍 **Where You Are** | Location-Aware SOS          |
| 🤝 **Who Is Coming** | Real-Time Responder Updates |

The user creates their emergency profile once.

When an SOS is triggered, nearby users can discover the active emergency based on location and respond with a single action.

The SOS owner then receives responder information instantly through a **WebSocket connection**.

---

## ✨ KEY FEATURES

### 🪪 Emergency Profile

Users create an emergency profile containing:

* Full name
* Phone number
* Blood group
* Location

This information is available when an emergency occurs instead of requiring everything to be entered under stress.

### 🆘 One-Tap SOS

A user can trigger an emergency alert with their location.

The alert remains active until the owner ends it or it expires.

### 📍 Nearby Emergency Detection

Active emergencies are filtered using location so responders can discover emergencies within the supported proximity range.

The current prototype uses a **1 km proximity boundary** for responder discovery and acknowledgement.

### 🤝 "I'm Coming to Help"

A nearby user can acknowledge an active emergency with a single action.

The backend validates and records the acknowledgement.

### ⚡ Real-Time Responder Updates

The SOS owner receives responder information through WebSockets without refreshing the application.

The owner can see:

* Responder name
* Responder phone number
* Number of responders
* Response status

### 👥 Multiple Responders

More than one nearby user can respond to the same emergency.

Each acknowledgement is stored separately and delivered to the SOS owner in real time.

### 🔐 Owner-Controlled SOS

Only the user who created the SOS can end it using:

**"End SOS (I'm Safe)"**

Responders cannot terminate another user's emergency.

---

## 🔄 HOW IT WORKS

```text
        CREATE EMERGENCY PROFILE
                  │
                  ▼
             TRIGGER SOS
                  │
                  ▼
        FIND NEARBY ACTIVE ALERT
                  │
                  ▼
       "I'M COMING TO HELP"
                  │
                  ▼
        SERVER-SIDE VALIDATION
                  │
                  ▼
       STORE ACKNOWLEDGEMENT
                  │
                  ▼
        WEBSOCKET NOTIFICATION
                  │
                  ▼
        SOS OWNER SEES RESPONDER
                  │
                  ▼
          ASSISTANCE ARRIVES
                  │
                  ▼
          OWNER ENDS THE SOS
```

### Emergency Flow

1. **Create Profile** — Save emergency information and location.
2. **Trigger SOS** — Create an active emergency alert.
3. **Discover Nearby Alerts** — Nearby users see relevant active emergencies.
4. **Respond** — A nearby user selects **"I'm Coming to Help."**
5. **Validate** — The backend verifies alert status, expiry, profile, location, proximity, and duplicate conditions.
6. **Store** — The acknowledgement is stored in PostgreSQL.
7. **Notify** — A WebSocket event is sent to the SOS owner's active connection.
8. **Responders Appear** — The owner sees responder details and responder count without refreshing.
9. **End the Emergency** — The SOS owner selects **"End SOS (I'm Safe)"** once safe.

---

## 🧠 TECHNICAL HIGHLIGHTS

### ⚡ Real-Time Communication

The application uses **WebSockets** to push responder information directly to the SOS owner's active session.

There is no need for continuous polling or manual page refreshes.

### 🔐 Server-Side Authorization

Emergency actions are enforced by the backend rather than relying only on frontend restrictions.

Only the profile that created an SOS can resolve it.

A responder cannot terminate someone else's emergency simply by manipulating the frontend.

### 📍 Location-Based Validation

The backend verifies that a responder has a valid location and is within the supported proximity range before accepting an acknowledgement.

### 👥 Multiple Responder Support

Multiple responders can acknowledge the same emergency.

Each responder is stored independently, allowing the SOS owner to see everyone who is coming to help.

### 🛡️ Duplicate Protection

The backend prevents the same responder from acknowledging the same alert more than once.

A database uniqueness constraint provides an additional layer of protection against duplicate acknowledgements.

---

## 🏗️ ARCHITECTURE

Emergency E-Card is a full-stack system built around REST APIs, location-based alert discovery, PostgreSQL persistence, and WebSockets.

```text
┌─────────────────────────────────────┐
│            React Frontend           │
│         TypeScript + Vite           │
└──────────────────┬──────────────────┘
                   │
             REST API + WebSocket
                   │
                   ▼
┌─────────────────────────────────────┐
│           FastAPI Backend            │
│                                     │
│ Profiles · SOS · Proximity          │
│ Validation · Responders · Auth      │
│ Real-Time Notifications             │
└──────────────────┬──────────────────┘
                   │
                SQLAlchemy
                   │
                   ▼
┌─────────────────────────────────────┐
│        PostgreSQL Database          │
│          Neon Production            │
└─────────────────────────────────────┘
```

### Frontend

React and TypeScript provide the user interface. Axios handles REST communication, while WebSockets deliver real-time emergency updates.

### Backend

FastAPI handles:

* Profile management
* Emergency alerts
* Proximity checks
* Responder acknowledgements
* Authorization
* Alert resolution
* WebSocket notifications

### Database

PostgreSQL stores:

* Profiles
* Emergency alerts
* Responder acknowledgements

**Neon PostgreSQL** is used for the production database.

---

## 🛠️ TECHNOLOGY STACK

| Layer                       | Technologies                          |
| --------------------------- | ------------------------------------- |
| **Frontend**                | React, TypeScript, Vite, Tailwind CSS |
| **API Communication**       | REST, Axios                           |
| **Real-Time Communication** | WebSockets                            |
| **Backend**                 | Python, FastAPI, Uvicorn              |
| **ORM**                     | SQLAlchemy                            |
| **Database**                | PostgreSQL, Neon                      |
| **Deployment**              | Render                                |
| **Version Control**         | Git, GitHub                           |

---

## 🚀 LIVE APPLICATION

**Try Emergency E-Card:**
https://emergency-e-card-1.onrender.com

### For Someone Requesting Help

1. Create your Emergency E-Card.
2. Enter your name, phone number, blood group, and location.
3. Allow location access.
4. Trigger an SOS.
5. Watch responders appear in real time.
6. End the SOS using **"End SOS (I'm Safe)"** once safe.

### For Someone Helping

1. Open the application.
2. View active emergencies near you.
3. Select an emergency you can reach.
4. Tap **"I'm Coming to Help."**
5. The SOS owner immediately receives your responder information.

> **Prototype note:** The backend runs on Render's free tier. After inactivity, the first request may take some time while the service wakes up.

---

## 📊 DEPLOYMENT VERIFICATION

The deployed system has been tested through the complete emergency cycle:

**Profile Creation → SOS Trigger → Nearby Alert Detection → Responder Acknowledgement → Real-Time Notification → Responder Details → SOS Resolution**

The following production behaviours have been verified:

* Profile creation
* SOS creation
* Nearby alert detection
* 1 km proximity validation
* Responder acknowledgement
* Multiple responders
* Real-time WebSocket notifications
* Responder name and phone display
* Duplicate acknowledgement prevention
* Owner-only SOS resolution
* PostgreSQL persistence through Neon
* Frontend-to-backend communication through the deployed system

---

## 📂 PROJECT STRUCTURE

```text
Round2-BIT-CRAFT/
│
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── test_main.py
│   └── README.md
│
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
│
├── .gitignore
└── README.md
```

---

## ☁️ PRODUCTION DEPLOYMENT

The production architecture uses:

```text
Render Static Site
        │
        ▼
React Frontend
        │
        │ REST API + WebSocket
        ▼
Render Web Service
        │
        ▼
FastAPI Backend
        │
        ▼
Neon PostgreSQL
```

The deployed application is available at:

**https://emergency-e-card-1.onrender.com**

---

## 🔮 FUTURE SCOPE

The prototype can be extended with:

* Interactive emergency maps and live navigation
* Push notifications for nearby emergencies
* Automatic emergency contact notifications
* Ambulance and hospital integration
* Verified responder accounts
* Native mobile applications
* Offline emergency support
* Enhanced location tracking
* Emergency incident analytics

---

## ⚠️ PROTOTYPE DISCLAIMER

**Emergency E-Card is a hackathon prototype.**

It does **not** contact official emergency services such as police, ambulance, or fire services and is **not a replacement for official emergency services**.

Users should not rely on this prototype as their sole means of obtaining emergency assistance.

---

## 👥 TEAM BIT-CRAFT

| Member             | Role                            |
| ------------------ | ------------------------------- |
| **Mohammad Hasan** | Team Leader & Backend Developer |
| **Niranjan S J**   | Team Member                     |
| **Jaiabner N**     | Team Member                     |

**Hackathon:** Morrow 1.0 by Makers Need More
**Round:** Round 2 — Project & Prototype Submission

> 🚨 **Because sometimes the nearest help is just around the corner.**

**Built with ❤️ by Team BIT-CRAFT**
