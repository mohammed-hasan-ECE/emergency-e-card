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
- `GET /sos/{profile_id}`: Emergency SOS endpoint retrieving critical medical info and contacts.
