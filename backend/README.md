# CitizenPriority — Phase 1: Multilingual Ingestion API

Google Cloud Hackathon prototype. All tooling is **free** — no payment details needed.

---

## Free tools used

| Tool | What for | Free tier |
|---|---|---|
| **Gemini 1.5 Flash** (Google AI Studio) | Transcription, translation, classification, image analysis | 15 RPM, 1M tokens/min, 1500 req/day |
| **Firebase Firestore** (Spark plan) | Store submissions + override audit log | 50K reads, 20K writes/day |

---

## Project structure

```
citizen-priority/
├── phase1/
│   └── app/
│       ├── main.py                  # FastAPI entrypoint
│       ├── routes/
│       │   └── submissions.py       # All HTTP endpoints
│       ├── services/
│       │   ├── gemini_service.py    # All Gemini API calls
│       │   ├── firebase_service.py  # Firestore reads/writes
│       │   └── ingestion_service.py # Pipeline orchestrator (streaming)
│       ├── models/
│       │   └── schemas.py           # Pydantic request/response models
│       └── utils/
│           ├── config.py            # Settings from .env
│           └── confidence.py        # Confidence scoring + guardrails
├── tests/
│   └── test_confidence.py           # Unit tests (no API key needed)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Setup (Windows + Python 3.13)

### Step 1 — Get a free Gemini API key

1. Go to https://aistudio.google.com/app/apikey
2. Sign in with a Google account (no payment needed)
3. Click **Create API key** → copy it

### Step 2 — Set up Firebase (free Spark plan)

1. Go to https://console.firebase.google.com
2. **Add project** → give it a name (e.g. `citizen-priority`)
3. Disable Google Analytics (not needed)
4. In the project: **Build → Firestore Database → Create database**
   - Choose **Native mode**
   - Pick any region (e.g. `asia-south1` for India)
5. **Project Settings (⚙️) → Service Accounts → Generate new private key**
6. Download the JSON file → save it as `firebase-credentials.json` in the project root

### Step 3 — Environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and fill in:
#   GEMINI_API_KEY=<your key from Step 1>
#   FIREBASE_PROJECT_ID=<your project ID from Firebase console>
#   FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
```

### Step 4 — Install and run

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Run the API (from project root)
uvicorn phase1.app.main:app --reload --port 8000
```

### Step 5 — Verify

- Swagger UI: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## API endpoints

### POST `/api/v1/submissions/text`
Submit citizen grievance as text. Returns **SSE stream**.

```json
{
  "text": "Sarak mein bahut gadhhe hain aur paani nahi aa raha",
  "constituency": "Ambala",
  "submitter_name": "Ramesh Kumar"
}
```

### POST `/api/v1/submissions/audio`
Multipart form. Fields: `constituency`, `submitter_name` (optional), `file` (audio).

### POST `/api/v1/submissions/image`
Multipart form. Fields: `constituency`, `submitter_name` (optional), `caption` (optional), `file` (image).

### GET `/api/v1/submissions/{id}`
Fetch a processed submission by ID.

### GET `/api/v1/submissions?constituency=Ambala&limit=50`
List recent submissions.

### PATCH `/api/v1/submissions/{id}/override`
Human label correction.
```json
{
  "submission_id": "...",
  "field_path": "issues[0].category",
  "corrected_value": "road",
  "override_by": "mp_user_id",
  "reason": "Misclassified"
}
```

---

## SSE stream format

Each event is a JSON `StreamChunk`:

```json
{ "step": "translating", "status": "in_progress", "message": "Detecting language...", "progress": 15, "data": null }
{ "step": "extracting",  "status": "complete",    "message": "Found 2 issues. Confidence: high (87%)", "progress": 65, "data": {"issue_count": 2} }
{ "step": "done",        "status": "complete",    "message": "Submission processed.", "progress": 100, "data": { ...full SubmissionResponse... } }
```

Final sentinel: `data: [DONE]`

---

## Design principles

| Principle | Implementation |
|---|---|
| **Deterministic shell** | Every AI call ends with a strict JSON schema in the prompt. Output is always the same shape regardless of model mood. |
| **Confidence scores** | Every AI field carries `score` (0.0–1.0) + `level` (high/medium/low). |
| **Labels + override** | Every label has an `override` field. MP can correct without re-running AI. |
| **Silent fallback** | If Gemini fails, rule-based keyword matching runs instead. Frontend still gets valid JSON. |
| **Guardrails** | Content checked before hitting the model. Blocked content returns `CONTENT_GUARDRAIL_HIT` flag. |
| **Streaming** | All ingest endpoints stream step-by-step SSE so frontend shows live progress. |
| **Human override** | PATCH endpoint + Firestore audit subcollection for full traceability. |

---

## Running tests (no API key needed)

```bash
# From project root
python -m pytest phase1/tests/test_confidence.py -v
```

---

## What Phase 2 will add

- Duplicate complaint clustering (vector embeddings via Gemini Embeddings API — also free)
- Vertex AI classification (if Google Cloud trial is available)
- Firestore-based cluster grouping
