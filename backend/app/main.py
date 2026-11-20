import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Literal
import sqlite3
import os
import hmac
import hashlib
import secrets
import base64
import json
import time
from pathlib import Path
from contextlib import contextmanager

from pydantic import BaseModel, Field
from fastapi.openapi.utils import get_openapi

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from app.biotwin.router import router as biotwin_router
from app.biotwin.heat_health_evidence import build_heat_health_dataset_context
from app.biotwin.vital_risk import assess_dataset_vital_risk, model_status as vital_model_status

DB_PATH = Path(__file__).resolve().parent.parent / "heatshield.db"



# Authentication: signed, expiring bearer tokens + PBKDF2 password hashes.
AUTH_SECRET = os.getenv("HEATSHIELD_AUTH_SECRET", "CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT")
TOKEN_TTL_SECONDS = int(os.getenv("HEATSHIELD_TOKEN_TTL_SECONDS", "28800"))
ROLE_NAMES = {"admin", "executive", "supervisor", "health_safety", "researcher", "worker"}

class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)

class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=256)
    role: str

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return f"pbkdf2_sha256$310000${_b64(salt)}${_b64(digest)}"

def _verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt, expected = encoded.split("$")
        if scheme != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt + "=="), int(rounds))
        return hmac.compare_digest(_b64(actual), expected)
    except Exception:
        return False

def _issue_token(user: dict) -> str:
    payload = {"sub": user["id"], "email": user["email"], "role": user["role"], "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{signature}"

def _decode_token(token: str) -> dict | None:
    try:
        body, signature = token.split(".", 1)
        expected = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=="))
        if int(payload.get("exp", 0)) < int(time.time()): return None
        return payload
    except Exception:
        return None


class WorksiteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    city: str = Field(min_length=2, max_length=80)
    industry: str = Field(min_length=2, max_length=80)
    worker_count: int = Field(ge=0, le=100000)

class WorksiteUpdate(WorksiteCreate):
    pass


class ZoneCreate(BaseModel):
    worksite_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=80)
    activity_type: str = Field(default="general", min_length=2, max_length=80)
    exposure_category: Literal["low", "moderate", "high"] = "moderate"
    worker_capacity: int = Field(default=0, ge=0, le=10000)


class WorkerCreate(BaseModel):
    worksite_id: int = Field(gt=0)
    zone_id: int | None = Field(default=None, gt=0)
    worker_code: str = Field(min_length=2, max_length=40)
    role: str = Field(default="worker", min_length=2, max_length=80)


class ExposureRecordCreate(BaseModel):
    worksite_id: int = Field(gt=0)
    zone_id: int | None = Field(default=None, gt=0)
    worker_code: str | None = Field(default=None, max_length=40)
    exposure_minutes: int = Field(ge=0, le=1440)
    source: Literal["weather_estimate", "onsite_sensor"] = "weather_estimate"
    risk_level: Literal["low", "moderate", "high", "critical"]
    air_temperature_c: float | None = None
    relative_humidity_pct: float | None = Field(default=None, ge=0, le=100)
    measured_wbgt_c: float | None = None
    notes: str | None = Field(default=None, max_length=500)


class WorkerVitalsCreate(BaseModel):
    worksite_id: int = Field(gt=0)
    worker_code: str = Field(min_length=2, max_length=80)

    body_temperature_c: float | None = Field(default=None, ge=30, le=45)
    temperature_type: Literal["core", "oral", "skin"] = "skin"

    heart_rate_bpm: int | None = Field(default=None, ge=20, le=260)
    respiratory_rate_bpm: int | None = Field(default=None, ge=4, le=80)
    spo2_pct: float | None = Field(default=None, ge=50, le=100)

    systolic_bp_mmhg: int | None = Field(default=None, ge=50, le=260)
    diastolic_bp_mmhg: int | None = Field(default=None, ge=30, le=180)

    # Additional features required for BioTwin ML model
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    height_m: float | None = Field(default=None, gt=0.3, le=2.8)

    symptoms: str = Field(default="", max_length=1000)
    source: Literal["manual_demo", "wearable", "clinical_device"] = "manual_demo"

class InterventionCreate(BaseModel):
    worksite_id: int = Field(gt=0)
    zone_id: int | None = Field(default=None, gt=0)
    intervention_type: Literal["rest_break", "task_rotation", "shade_transition", "work_pause", "hydration_reminder"]
    reason: str = Field(min_length=5, max_length=500)
    status: Literal["recommended", "approved", "completed", "dismissed"] = "recommended"
    affected_crew_count: int = Field(default=0, ge=0, le=100000)

@contextmanager
def get_db():
    """Yield a configured SQLite connection and always close it after use."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS worksites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                industry TEXT NOT NULL,
                worker_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS zones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worksite_id INTEGER NOT NULL REFERENCES worksites(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                activity_type TEXT NOT NULL DEFAULT 'general',
                exposure_category TEXT NOT NULL DEFAULT 'moderate',
                worker_capacity INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(worksite_id, name)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worksite_id INTEGER NOT NULL REFERENCES worksites(id) ON DELETE CASCADE,
                zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
                worker_code TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'worker',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(worksite_id, worker_code)
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS exposure_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worksite_id INTEGER NOT NULL REFERENCES worksites(id) ON DELETE CASCADE,
                zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
                worker_code TEXT,
                exposure_minutes INTEGER NOT NULL,
                source TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                air_temperature_c REAL,
                relative_humidity_pct REAL,
                measured_wbgt_c REAL,
                notes TEXT,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worksite_id INTEGER NOT NULL REFERENCES worksites(id) ON DELETE CASCADE,
                zone_id INTEGER REFERENCES zones(id) ON DELETE SET NULL,
                intervention_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'recommended',
                affected_crew_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS worker_health_demo_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worksite_id INTEGER NOT NULL REFERENCES worksites(id) ON DELETE CASCADE,
                worker_code TEXT NOT NULL,
                profile_label TEXT NOT NULL,
                vulnerability_domain TEXT NOT NULL,
                demo_note TEXT NOT NULL DEFAULT 'SYNTHETIC DEMO PROFILE - NOT A REAL WORKER OR DIAGNOSIS',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(worksite_id, worker_code, vulnerability_domain)
            )
        """)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS worker_vitals_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worksite_id INTEGER NOT NULL REFERENCES worksites(id) ON DELETE CASCADE,
                worker_code TEXT NOT NULL,
                body_temperature_c REAL,
                temperature_type TEXT NOT NULL DEFAULT 'skin',
                heart_rate_bpm INTEGER,
                respiratory_rate_bpm INTEGER,
                spo2_pct REAL,
                systolic_bp_mmhg INTEGER,
                diastolic_bp_mmhg INTEGER,
                weight_kg REAL,
                height_m REAL,
                symptoms TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual_demo',
                alert_level TEXT NOT NULL DEFAULT 'review',
                alert_reason TEXT NOT NULL DEFAULT '',
                ai_assessment TEXT NOT NULL DEFAULT '',
                ai_status TEXT NOT NULL DEFAULT 'pending',
                ai_model TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Backward-compatible schema migration for existing demo databases.
        vitals_columns = {
            row[1]
            for row in db.execute(
                "PRAGMA table_info(worker_vitals_readings)"
            ).fetchall()
        }

        for column, definition in (
            ("respiratory_rate_bpm", "INTEGER"),
            ("systolic_bp_mmhg", "INTEGER"),
            ("diastolic_bp_mmhg", "INTEGER"),
            ("weight_kg", "REAL"),
            ("height_m", "REAL"),
            ("ai_assessment", "TEXT NOT NULL DEFAULT ''"),
            ("ai_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("ai_model", "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in vitals_columns:
                db.execute(
                    f"ALTER TABLE worker_vitals_readings ADD COLUMN {column} {definition}"
                )


        db.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS offline_alert_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                worksite_id INTEGER NOT NULL,
                zone_id INTEGER,
                worker_code TEXT,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                synced_at TEXT
            )
        """)


init_db()
with get_db() as _db:
    if not _db.execute("SELECT 1 FROM app_users LIMIT 1").fetchone():
        _email = os.getenv("HEATSHIELD_BOOTSTRAP_ADMIN_EMAIL", "admin@heatshield.ai").strip().lower()
        _password = os.getenv("HEATSHIELD_BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe123!")
        _db.execute("INSERT INTO app_users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                    (_email, "HeatShield System Administrator", _hash_password(_password), "admin"))

# Fictional health-profile examples linked only to SIM-WKR identities.
# They are not clinical diagnoses or model predictions.
with get_db() as _db:
    _demo_profiles = [
        (2, "SIM-WKR-001", "Renal vulnerability example", "renal"),
        (2, "SIM-WKR-002", "Metabolic vulnerability example", "metabolic"),
        (2, "SIM-WKR-003", "Cardiovascular vulnerability example", "cardiovascular"),
        (2, "SIM-WKR-004", "No health profile supplied", "not_provided"),
        (2, "SIM-WKR-005", "Respiratory vulnerability example", "respiratory"),
        (2, "SIM-WKR-006", "Multiple-condition example", "multi_condition"),
    ]
    for _profile in _demo_profiles:
        _worksite_exists = _db.execute("SELECT 1 FROM worksites WHERE id=?", (_profile[0],)).fetchone()
        if _worksite_exists:
            _db.execute(
                """INSERT OR IGNORE INTO worker_health_demo_profiles
                   (worksite_id, worker_code, profile_label, vulnerability_domain)
                   VALUES (?, ?, ?, ?)""",
                _profile,
            )


# Clearly labelled fictional vital-sign examples for the Abu Dhabi demo worksite.
# These rows exist only to demonstrate supervisor alert workflows; they are not patient data.
with get_db() as _db:
    _demo_vitals = [
        (2, "SIM-WKR-001", 38.2, "oral", 124, 22, 97, 128, 82, "Dizziness and heavy sweating", "urgent", "Synthetic demo: elevated temperature with reported dizziness; stop work and arrange prompt medical assessment."),
        (2, "SIM-WKR-002", 37.4, "oral", 112, 21, 98, 132, 84, "Headache and nausea", "review", "Synthetic demo: symptoms with elevated heart rate; move to a cool area, rest, repeat readings and seek clinical review if persistent."),
        (2, "SIM-WKR-003", 36.9, "oral", 88, 16, 96, 122, 78, "No symptoms reported", "review", "Synthetic demo: no configured urgent trigger; continue routine monitoring and do not interpret as a clean bill of health."),
        (2, "SIM-WKR-004", 36.8, "skin", 78, 14, 99, 118, 76, "No symptoms reported", "review", "Synthetic demo: skin temperature is not core temperature; no configured screening trigger detected."),
        (2, "SIM-WKR-005", 37.1, "oral", 104, 24, 94, 126, 80, "Breathlessness after exertion", "review", "Synthetic demo: reported breathlessness and reading require supervisor review and clinical re-check if persistent."),
        (2, "SIM-WKR-006", 38.5, "core", 132, 26, 93, 146, 94, "Confusion and weakness", "urgent", "Synthetic demo: concerning symptoms and readings; stop work and arrange immediate emergency assessment."),
    ]
    for _reading in _demo_vitals:
        exists = _db.execute(
            "SELECT 1 FROM worker_vitals_readings WHERE worksite_id=? AND worker_code=? AND source='synthetic_demo' LIMIT 1",
            (_reading[0], _reading[1]),
        ).fetchone()
        worker_exists = _db.execute(
            "SELECT 1 FROM workers WHERE worksite_id=? AND worker_code=? AND active=1",
            (_reading[0], _reading[1]),
        ).fetchone()
        if not exists and worker_exists:
            _db.execute(
                """INSERT INTO worker_vitals_readings
                   (worksite_id, worker_code, body_temperature_c, temperature_type,
                    heart_rate_bpm, respiratory_rate_bpm, spo2_pct, systolic_bp_mmhg,
                    diastolic_bp_mmhg, symptoms, source, alert_level, alert_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'synthetic_demo', ?, ?)""",
                _reading,
            )

app = FastAPI(
    title="HeatShield AI API",
    version="0.5.3",
    description="Environmental weather context API. Not a medical or WBGT measurement service.",
)

allowed_origins = [origin.strip() for origin in os.getenv("HEATSHIELD_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_authentication(request: Request, call_next):
    # Browser CORS preflight requests must pass without authentication.
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    # Public endpoints
    if path.startswith("/api/") and path not in {
        "/api/auth/login",
        "/api/health"
    }:
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""

        claims = _decode_token(token) if token else None

        if not claims:
            from starlette.responses import JSONResponse
            return JSONResponse(
                {"detail": "Authentication required or session expired."},
                status_code=401
            )

        with get_db() as db:
            current_account = db.execute(
                "SELECT role, active FROM app_users WHERE id = ?",
                (claims.get("sub"),)
            ).fetchone()

        if not current_account or not current_account["active"]:
            from starlette.responses import JSONResponse
            return JSONResponse(
                {"detail": "User account is inactive or no longer exists."},
                status_code=401
            )

        # Use the current database role so role changes take effect immediately.
        claims["role"] = current_account["role"]
        request.state.user = claims

        # Enforce server-side workspace permissions. Frontend navigation is
        # presentation only and must never be the security boundary.
        role = claims.get("role", "")
        allowed_roles = None
        method = request.method.upper()

        if path.startswith("/api/auth/users"):
            allowed_roles = {"admin"}
        elif path.startswith("/api/biotwin/vitals"):
            allowed_roles = {"admin", "supervisor", "health_safety", "researcher"}
        elif path.startswith("/api/biotwin/"):
            allowed_roles = {"admin", "researcher"}
        elif path.startswith("/api/mesh/"):
            allowed_roles = {"admin", "supervisor"}
        elif path == "/api/dashboard/summary":
            allowed_roles = {"admin", "executive", "supervisor"}
        elif path.startswith("/api/worksites"):
            allowed_roles = (
                {"admin", "executive", "supervisor", "health_safety"}
                if method == "GET" else {"admin", "supervisor"}
            )
        elif path.startswith("/api/zones"):
            allowed_roles = (
                {"admin", "executive", "supervisor", "health_safety"}
                if method == "GET" else {"admin", "supervisor"}
            )
        elif path.startswith("/api/workers"):
            allowed_roles = (
                {"admin", "executive", "supervisor", "health_safety"}
                if method == "GET" else {"admin", "supervisor", "health_safety"}
            )
        elif path.startswith("/api/exposure-records"):
            allowed_roles = (
                {"admin", "executive", "supervisor", "health_safety"}
                if method == "GET" else {"admin", "supervisor", "health_safety"}
            )
        elif path.startswith("/api/interventions"):
            allowed_roles = (
                {"admin", "executive", "supervisor", "health_safety"}
                if method == "GET" else {"admin", "supervisor", "health_safety"}
            )
        elif path.startswith(("/api/risk/", "/api/optimization/")):
            allowed_roles = {"admin", "supervisor", "health_safety"}
        elif path.startswith(("/api/cities", "/api/weather/")):
            allowed_roles = {"admin", "executive", "supervisor", "health_safety", "researcher", "worker"}

        if allowed_roles is not None and role not in allowed_roles:
            from starlette.responses import JSONResponse
            return JSONResponse(
                {"detail": "Your account role is not authorised for this workspace."},
                status_code=403
            )

    return await call_next(request)


@app.post("/api/auth/login")
async def auth_login(payload: LoginPayload):
    with get_db() as db:
        row = db.execute("SELECT id,email,full_name,password_hash,role,active FROM app_users WHERE email = ?", (payload.email.strip().lower(),)).fetchone()
    if not row or not row["active"] or not _verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    user = {"id": row["id"], "email": row["email"], "full_name": row["full_name"], "role": row["role"]}
    return {"access_token": _issue_token(user), "token_type": "bearer", "expires_in": TOKEN_TTL_SECONDS, "user": user}

@app.get("/api/auth/me")
async def auth_me(request: Request):
    claims = request.state.user
    with get_db() as db:
        row = db.execute("SELECT id,email,full_name,role,active FROM app_users WHERE id = ?", (claims["sub"],)).fetchone()
    if not row or not row["active"]:
        raise HTTPException(status_code=401, detail="User account is inactive.")
    return dict(row)

@app.post("/api/auth/users", status_code=201)
async def auth_create_user(payload: UserCreate, request: Request):
    if request.state.user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can create users.")
    role = payload.role.strip().lower()
    if role not in ROLE_NAMES: raise HTTPException(status_code=422, detail="Unsupported role.")
    try:
        with get_db() as db:
            cur = db.execute("INSERT INTO app_users (email,full_name,password_hash,role) VALUES (?,?,?,?)",
                             (payload.email.strip().lower(), payload.full_name.strip(), _hash_password(payload.password), role))
            row = db.execute("SELECT id,email,full_name,role,active,created_at FROM app_users WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

@app.get("/api/auth/users")
async def auth_list_users(request: Request):
    if request.state.user.get("role") != "admin": raise HTTPException(status_code=403, detail="Administrator access required.")
    with get_db() as db:
        rows = db.execute("SELECT id,email,full_name,role,active,created_at FROM app_users ORDER BY id").fetchall()
    return {"users": [dict(row) for row in rows]}

app.include_router(biotwin_router)

CITIES = {
    "islamabad": {"name": "Islamabad", "latitude": 33.6844, "longitude": 73.0479, "timezone": "Asia/Karachi"},
    "lahore": {"name": "Lahore", "latitude": 31.5204, "longitude": 74.3587, "timezone": "Asia/Karachi"},
    "karachi": {"name": "Karachi", "latitude": 24.8607, "longitude": 67.0011, "timezone": "Asia/Karachi"},
    "multan": {"name": "Multan", "latitude": 30.1575, "longitude": 71.5249, "timezone": "Asia/Karachi"},
    "peshawar": {"name": "Peshawar", "latitude": 34.0151, "longitude": 71.5249, "timezone": "Asia/Karachi"},
    "quetta": {"name": "Quetta", "latitude": 30.1798, "longitude": 66.9750, "timezone": "Asia/Karachi"},
    "faisalabad": {"name": "Faisalabad", "latitude": 31.4504, "longitude": 73.1350, "timezone": "Asia/Karachi"},
    "abu_dhabi": {"name": "Abu Dhabi", "latitude": 24.4539, "longitude": 54.3773, "timezone": "Asia/Dubai"},
    "dubai": {"name": "Dubai", "latitude": 25.2048, "longitude": 55.2708, "timezone": "Asia/Dubai"},
    "sharjah": {"name": "Sharjah", "latitude": 25.3463, "longitude": 55.4209, "timezone": "Asia/Dubai"},
    "al_ain": {"name": "Al Ain", "latitude": 24.1917, "longitude": 55.7606, "timezone": "Asia/Dubai"},
}

HOURLY_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "wind_speed_10m",
    "wet_bulb_temperature_2m",
    "shortwave_radiation",
]

def number_or_none(values: dict[str, Any], key: str, index: int):
    series = values.get(key) or []
    return series[index] if index < len(series) else None

@app.get("/api/worksites")
async def list_worksites():
    with get_db() as db:
        rows = db.execute(
            "SELECT id, name, city, industry, worker_count, created_at FROM worksites ORDER BY id DESC"
        ).fetchall()
    return {"worksites": [dict(row) for row in rows]}

@app.post("/api/worksites", status_code=201)
async def create_worksite(payload: WorksiteCreate):
    with get_db() as db:
        cursor = db.execute(
            "INSERT INTO worksites (name, city, industry, worker_count) VALUES (?, ?, ?, ?)",
            (payload.name.strip(), payload.city.strip(), payload.industry.strip(), payload.worker_count),
        )
        row = db.execute(
            "SELECT id, name, city, industry, worker_count, created_at FROM worksites WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)

@app.put("/api/worksites/{worksite_id}")
async def update_worksite(worksite_id: int, payload: WorksiteUpdate):
    with get_db() as db:
        cursor = db.execute(
            "UPDATE worksites SET name = ?, city = ?, industry = ?, worker_count = ? WHERE id = ?",
            (payload.name.strip(), payload.city.strip(), payload.industry.strip(), payload.worker_count, worksite_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Worksite not found")
        row = db.execute(
            "SELECT id, name, city, industry, worker_count, created_at FROM worksites WHERE id = ?",
            (worksite_id,),
        ).fetchone()
    return dict(row)

@app.delete("/api/worksites/{worksite_id}", status_code=204)
async def delete_worksite(worksite_id: int):
    with get_db() as db:
        cursor = db.execute("DELETE FROM worksites WHERE id = ?", (worksite_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Worksite not found")
    return None

@app.get("/api/zones")
async def list_zones(worksite_id: int | None = Query(default=None, gt=0)):
    with get_db() as db:
        if worksite_id:
            rows = db.execute("SELECT * FROM zones WHERE worksite_id = ? ORDER BY id DESC", (worksite_id,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM zones ORDER BY id DESC").fetchall()
    return {"zones": [dict(row) for row in rows]}


@app.post("/api/zones", status_code=201)
async def create_zone(payload: ZoneCreate):
    with get_db() as db:
        if not db.execute("SELECT id FROM worksites WHERE id = ?", (payload.worksite_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Worksite not found")
        try:
            cursor = db.execute(
                "INSERT INTO zones (worksite_id, name, activity_type, exposure_category, worker_capacity) VALUES (?, ?, ?, ?, ?)",
                (payload.worksite_id, payload.name.strip(), payload.activity_type.strip(), payload.exposure_category, payload.worker_capacity),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="A zone with this name already exists at this worksite") from exc
        row = db.execute("SELECT * FROM zones WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.get("/api/workers")
async def list_workers(worksite_id: int | None = Query(default=None, gt=0)):
    with get_db() as db:
        if worksite_id:
            rows = db.execute("SELECT id, worksite_id, zone_id, worker_code, role, active, created_at FROM workers WHERE worksite_id = ? ORDER BY id DESC", (worksite_id,)).fetchall()
        else:
            rows = db.execute("SELECT id, worksite_id, zone_id, worker_code, role, active, created_at FROM workers ORDER BY id DESC").fetchall()
    return {"workers": [dict(row) for row in rows]}


@app.post("/api/workers", status_code=201)
async def create_worker(payload: WorkerCreate):
    with get_db() as db:
        if not db.execute("SELECT id FROM worksites WHERE id = ?", (payload.worksite_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Worksite not found")
        if payload.zone_id and not db.execute("SELECT id FROM zones WHERE id = ? AND worksite_id = ?", (payload.zone_id, payload.worksite_id)).fetchone():
            raise HTTPException(status_code=400, detail="Zone does not belong to this worksite")
        try:
            cursor = db.execute(
                "INSERT INTO workers (worksite_id, zone_id, worker_code, role) VALUES (?, ?, ?, ?)",
                (payload.worksite_id, payload.zone_id, payload.worker_code.strip(), payload.role.strip()),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Worker code already exists at this worksite") from exc
        row = db.execute("SELECT id, worksite_id, zone_id, worker_code, role, active, created_at FROM workers WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.get("/api/exposure-records")
async def list_exposure_records(worksite_id: int | None = Query(default=None, gt=0), limit: int = Query(default=100, ge=1, le=500)):
    with get_db() as db:
        if worksite_id:
            rows = db.execute("SELECT * FROM exposure_records WHERE worksite_id = ? ORDER BY id DESC LIMIT ?", (worksite_id, limit)).fetchall()
        else:
            rows = db.execute("SELECT * FROM exposure_records ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {"records": [dict(row) for row in rows]}


@app.post("/api/exposure-records", status_code=201)
async def create_exposure_record(payload: ExposureRecordCreate):
    with get_db() as db:
        if not db.execute("SELECT id FROM worksites WHERE id = ?", (payload.worksite_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Worksite not found")
        if payload.zone_id and not db.execute("SELECT id FROM zones WHERE id = ? AND worksite_id = ?", (payload.zone_id, payload.worksite_id)).fetchone():
            raise HTTPException(status_code=400, detail="Zone does not belong to this worksite")
        if payload.measured_wbgt_c is not None and payload.source != "onsite_sensor":
            raise HTTPException(status_code=400, detail="Measured WBGT can only be recorded from an onsite_sensor source")
        if payload.worker_code and not db.execute("SELECT id FROM workers WHERE worksite_id = ? AND worker_code = ? AND active = 1", (payload.worksite_id, payload.worker_code)).fetchone():
            raise HTTPException(status_code=400, detail="Worker code is not registered and active at this worksite")
        if payload.measured_wbgt_c is not None and not (-10 <= payload.measured_wbgt_c <= 60):
            raise HTTPException(status_code=422, detail="Measured WBGT value is outside the accepted input range")
        cursor = db.execute("""INSERT INTO exposure_records
            (worksite_id, zone_id, worker_code, exposure_minutes, source, risk_level, air_temperature_c, relative_humidity_pct, measured_wbgt_c, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.worksite_id, payload.zone_id, payload.worker_code, payload.exposure_minutes, payload.source, payload.risk_level, payload.air_temperature_c, payload.relative_humidity_pct, payload.measured_wbgt_c, payload.notes))
        row = db.execute("SELECT * FROM exposure_records WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.get("/api/interventions")
async def list_interventions(worksite_id: int | None = Query(default=None, gt=0)):
    with get_db() as db:
        if worksite_id:
            rows = db.execute("SELECT * FROM interventions WHERE worksite_id = ? ORDER BY id DESC", (worksite_id,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM interventions ORDER BY id DESC").fetchall()
    return {"interventions": [dict(row) for row in rows]}


@app.post("/api/interventions", status_code=201)
async def create_intervention(payload: InterventionCreate):
    with get_db() as db:
        if not db.execute("SELECT id FROM worksites WHERE id = ?", (payload.worksite_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Worksite not found")
        if payload.zone_id and not db.execute("SELECT id FROM zones WHERE id = ? AND worksite_id = ?", (payload.zone_id, payload.worksite_id)).fetchone():
            raise HTTPException(status_code=400, detail="Zone does not belong to this worksite")
        cursor = db.execute("""INSERT INTO interventions
            (worksite_id, zone_id, intervention_type, reason, status, affected_crew_count)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (payload.worksite_id, payload.zone_id, payload.intervention_type, payload.reason.strip(), payload.status, payload.affected_crew_count))
        row = db.execute("SELECT * FROM interventions WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


@app.get("/api/risk/assessment")
async def risk_assessment(worksite_id: int = Query(gt=0)):
    with get_db() as db:
        workers = db.execute("""
            SELECT
                w.worker_code,
                w.zone_id,
                e.exposure_minutes,
                e.source,
                e.risk_level,
                e.air_temperature_c,
                e.relative_humidity_pct,
                e.recorded_at
            FROM workers w
            LEFT JOIN exposure_records e
                ON e.id = (
                    SELECT e2.id
                    FROM exposure_records e2
                    WHERE e2.worksite_id = w.worksite_id
                      AND e2.worker_code = w.worker_code
                    ORDER BY e2.id DESC
                    LIMIT 1
                )
            WHERE w.worksite_id = ? AND w.active = 1
            ORDER BY w.worker_code
        """, (worksite_id,)).fetchall()

    results = []

    for worker in workers:
        if worker["risk_level"] is None:
            results.append({
                "worker_code": worker["worker_code"],
                "zone_id": worker["zone_id"],
                "assessment_status": "no_exposure_data",
                "risk_score": None,
                "risk_band": "unknown",
                "reasons": ["No exposure record available"]
            })
            continue

        recorded_at = worker["recorded_at"]
        try:
            record_time = datetime.fromisoformat(str(recorded_at))
            age_hours = (datetime.now() - record_time).total_seconds() / 3600
        except (TypeError, ValueError):
            age_hours = None

        if worker["source"] == "demo_simulation":
            results.append({
                "worker_code": worker["worker_code"], "zone_id": worker["zone_id"],
                "assessment_status": "excluded_demo_data", "risk_score": None,
                "risk_band": "unknown", "reasons": ["Simulation data is excluded from worker assessment"],
                "source": worker["source"], "recorded_at": recorded_at
            })
            continue
        if age_hours is None or age_hours > 24:
            results.append({
                "worker_code": worker["worker_code"], "zone_id": worker["zone_id"],
                "assessment_status": "stale_or_unverified", "risk_score": None,
                "risk_band": "unknown", "reasons": ["Exposure record is missing a valid timestamp or is older than 24 hours"],
                "source": worker["source"], "recorded_at": recorded_at
            })
            continue

        level = worker["risk_level"]
        score = {
            "low": 10,
            "moderate": 35,
            "high": 60,
            "critical": 85
        }[level]

        reasons = [f"Recorded exposure risk: {level}"]

        temp = worker["air_temperature_c"]
        humidity = worker["relative_humidity_pct"]
        minutes = worker["exposure_minutes"]

        if temp is not None and temp >= 40:
            score += 15
            reasons.append("Air temperature is at least 40°C")
        elif temp is not None and temp >= 35:
            score += 10
            reasons.append("Air temperature is at least 35°C")

        if humidity is not None and humidity >= 60:
            score += 5
            reasons.append("Relative humidity is at least 60%")

        if minutes >= 240:
            score += 15
            reasons.append("Exposure duration is at least 4 hours")
        elif minutes >= 120:
            score += 10
            reasons.append("Exposure duration is at least 2 hours")

        score = min(score, 100)

        if score >= 85:
            band = "critical"
            action = "Immediate supervisor review and protective intervention recommended"
        elif score >= 60:
            band = "high"
            action = "Recommend shaded rest and supervisor review"
        elif score >= 35:
            band = "moderate"
            action = "Monitor exposure and schedule preventive breaks"
        else:
            band = "low"
            action = "Continue routine monitoring"

        results.append({
            "worker_code": worker["worker_code"],
            "zone_id": worker["zone_id"],
            "assessment_status": "assessed",
            "risk_score": score,
            "risk_band": band,
            "reasons": reasons,
            "suggested_action": action,
            "source": worker["source"],
            "recorded_at": worker["recorded_at"]
        })

    return {
        "worksite_id": worksite_id,
        "assessment_type": "prototype_heuristic",
        "notice": "Experimental decision-support logic, not a validated occupational safety or medical assessment.",
        "workers_assessed": len(results),
        "results": results
    }


@app.get("/api/optimization/shift-rotation")
async def shift_rotation_optimizer(worksite_id: int = Query(gt=0)):
    with get_db() as db:
        zones = db.execute("""
            SELECT id, name, exposure_category, worker_capacity
            FROM zones
            WHERE worksite_id = ?
        """, (worksite_id,)).fetchall()

        workers = db.execute("""
            SELECT
                w.worker_code,
                w.zone_id,
                e.exposure_minutes,
                e.source,
                e.risk_level,
                e.air_temperature_c,
                e.relative_humidity_pct
            FROM workers w
            LEFT JOIN exposure_records e
                ON e.id = (
                    SELECT e2.id
                    FROM exposure_records e2
                    WHERE e2.worksite_id = w.worksite_id
                      AND e2.worker_code = w.worker_code
                    ORDER BY e2.id DESC
                    LIMIT 1
                )
            WHERE w.worksite_id = ? AND w.active = 1
        """, (worksite_id,)).fetchall()

        occupancy = db.execute("""
            SELECT zone_id, COUNT(*) AS worker_count
            FROM workers
            WHERE worksite_id = ? AND active = 1
            GROUP BY zone_id
        """, (worksite_id,)).fetchall()

    zone_map = {z["id"]: dict(z) for z in zones}
    occupied = {r["zone_id"]: r["worker_count"] for r in occupancy}

    rest_zones = [
        z for z in zones
        if z["exposure_category"] == "low"
        and "rest" in z["name"].lower()
    ]

    if not rest_zones:
        return {
            "worksite_id": worksite_id,
            "status": "no_rest_zone",
            "recommendations": [],
            "message": "No low-exposure rest zone is configured."
        }

    destination = sorted(
        rest_zones,
        key=lambda z: z["id"]
    )[0]

    capacity = destination["worker_capacity"]
    current_occupancy = occupied.get(destination["id"], 0)
    available_capacity = max(0, capacity - current_occupancy)

    candidates = []

    excluded_simulated_workers = 0

    for worker in workers:

        # Never generate real-world rotation recommendations
        # from simulated or demo exposure records.
        if worker["source"] == "demo_simulation":
            excluded_simulated_workers += 1
            continue

        # Missing exposure data must not be treated as safe.
        if worker["risk_level"] is None:
            continue

        level = worker["risk_level"]
        score = {
            "low": 10,
            "moderate": 35,
            "high": 60,
            "critical": 85
        }[level]

        temp = worker["air_temperature_c"]
        humidity = worker["relative_humidity_pct"]
        minutes = worker["exposure_minutes"]

        if temp is not None and temp >= 40:
            score += 15
        elif temp is not None and temp >= 35:
            score += 10

        if humidity is not None and humidity >= 60:
            score += 5

        if minutes >= 240:
            score += 15
        elif minutes >= 120:
            score += 10

        score = min(score, 100)

        if score >= 60 and worker["zone_id"] != destination["id"]:
            candidates.append({
                "worker_code": worker["worker_code"],
                "current_zone_id": worker["zone_id"],
                "current_zone": zone_map.get(
                    worker["zone_id"], {}
                ).get("name", "Unassigned"),
                "risk_score": score,
                "risk_band": "critical" if score >= 85 else "high"
            })

    candidates.sort(
        key=lambda item: item["risk_score"],
        reverse=True
    )

    recommendations = []

    for candidate in candidates[:available_capacity]:
        recommendations.append({
            **candidate,
            "recommended_zone_id": destination["id"],
            "recommended_zone": destination["name"],
            "action": "temporary_rest_rotation",
            "priority": "urgent" if candidate["risk_band"] == "critical" else "high",
            "reason": (
                "Elevated recorded heat exposure. Recommend a temporary "
                "move to the shaded rest area, hydration, and supervisor review."
            ),
            "requires_supervisor_approval": True
        })

    return {
        "worksite_id": worksite_id,
        "optimizer": "capacity_aware_heuristic",
        "destination_zone": {
            "id": destination["id"],
            "name": destination["name"],
            "capacity": capacity,
            "current_occupancy": current_occupancy,
            "available_capacity": available_capacity
        },
        "eligible_workers": len(candidates),
        "excluded_simulated_workers": excluded_simulated_workers,
        "recommendations_generated": len(recommendations),
        "not_scheduled_due_to_capacity": (
            len(candidates) - len(recommendations)
        ),
        "recommendations": recommendations,
        "notice": (
            "Prototype decision support only. Recommendations do not "
            "automatically move workers or establish medical fitness."
        )
    }


@app.patch("/api/interventions/{intervention_id}/status")
async def update_intervention_status(
    intervention_id: int,
    status: Literal["approved", "dismissed", "completed"]
):
    with get_db() as db:
        intervention = db.execute(
            "SELECT * FROM interventions WHERE id = ?",
            (intervention_id,)
        ).fetchone()

        if not intervention:
            raise HTTPException(
                status_code=404,
                detail="Intervention not found"
            )

        current_status = intervention["status"]

        allowed_transitions = {
            "recommended": ["approved", "dismissed"],
            "approved": ["completed", "dismissed"],
            "completed": [],
            "dismissed": []
        }

        if status not in allowed_transitions.get(current_status, []):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot change status from {current_status} to {status}"
            )

        db.execute(
            "UPDATE interventions SET status = ? WHERE id = ?",
            (status, intervention_id)
        )

        updated = db.execute(
            "SELECT * FROM interventions WHERE id = ?",
            (intervention_id,)
        ).fetchone()

    return {
        "message": "Intervention status updated",
        "intervention": dict(updated)
    }


@app.get("/api/mesh/status")
async def get_mesh_status(worksite_id: int):
    with get_db() as db:
        workers = db.execute(
            """
            SELECT worker_code, zone_id, active
            FROM workers
            WHERE worksite_id = ?
            """,
            (worksite_id,)
        ).fetchall()

        latest_records = db.execute(
            """
            SELECT worker_code, source, recorded_at
            FROM exposure_records
            WHERE worksite_id = ?
            ORDER BY recorded_at DESC
            """,
            (worksite_id,)
        ).fetchall()

    latest_by_worker = {}

    for record in latest_records:
        code = record["worker_code"]
        if code and code not in latest_by_worker:
            latest_by_worker[code] = record

    worker_status = []

    for worker in workers:
        code = worker["worker_code"]
        record = latest_by_worker.get(code)

        if not worker["active"]:
            status = "inactive"
        elif record is None:
            status = "no_sensor_data"
        elif record["source"] == "demo_simulation":
            status = "simulated"
        elif record["source"] == "onsite_sensor":
            status = "connected"
        else:
            status = "unknown"

        worker_status.append({
            "worker_code": code,
            "zone_id": worker["zone_id"],
            "connection_status": status,
            "last_data_received": (
                record["recorded_at"] if record else None
            )
        })

    connected = sum(
        1 for w in worker_status
        if w["connection_status"] == "connected"
    )
    simulated = sum(
        1 for w in worker_status
        if w["connection_status"] == "simulated"
    )
    disconnected = sum(
        1 for w in worker_status
        if w["connection_status"] in ["no_sensor_data", "unknown"]
    )

    return {
        "worksite_id": worksite_id,
        "network_mode": "prototype_simulation",
        "total_workers": len(worker_status),
        "connected_workers": connected,
        "simulated_workers": simulated,
        "disconnected_or_unknown": disconnected,
        "workers": worker_status,
        "safety_note": (
            "Missing or stale sensor data must never be interpreted "
            "as evidence that a worker is safe."
        )
    }


class OfflineAlertCreate(BaseModel):
    worksite_id: int = Field(gt=0)
    zone_id: int | None = Field(default=None, gt=0)
    worker_code: str | None = Field(default=None, min_length=2, max_length=40)
    alert_type: str = Field(min_length=2, max_length=80)
    severity: Literal["low", "medium", "high", "critical"]
    message: str = Field(min_length=5, max_length=500)


@app.post("/api/mesh/offline-alerts", status_code=201)
async def create_offline_alert(alert: OfflineAlertCreate):
    with get_db() as db:
        if not db.execute("SELECT id FROM worksites WHERE id = ?", (alert.worksite_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Worksite not found")
        if alert.zone_id and not db.execute("SELECT id FROM zones WHERE id = ? AND worksite_id = ?", (alert.zone_id, alert.worksite_id)).fetchone():
            raise HTTPException(status_code=400, detail="Zone does not belong to this worksite")
        if alert.worker_code and not db.execute("SELECT id FROM workers WHERE worksite_id = ? AND worker_code = ?", (alert.worksite_id, alert.worker_code)).fetchone():
            raise HTTPException(status_code=400, detail="Worker code is not registered at this worksite")
        cursor = db.execute(
            """
            INSERT INTO offline_alert_queue (
                worksite_id, zone_id, worker_code,
                alert_type, severity, message
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alert.worksite_id,
                alert.zone_id,
                alert.worker_code,
                alert.alert_type,
                alert.severity,
                alert.message
            )
        )

        alert_id = cursor.lastrowid

        saved = db.execute(
            "SELECT * FROM offline_alert_queue WHERE id = ?",
            (alert_id,)
        ).fetchone()

    return {
        "message": "Offline alert queued successfully",
        "alert": dict(saved)
    }


@app.get("/api/mesh/offline-alerts")
async def get_offline_alerts(worksite_id: int):
    with get_db() as db:
        alerts = db.execute(
            """
            SELECT * FROM offline_alert_queue
            WHERE worksite_id = ?
            ORDER BY created_at DESC
            """,
            (worksite_id,)
        ).fetchall()

    return {
        "worksite_id": worksite_id,
        "pending_alerts": sum(
            1 for a in alerts if a["sync_status"] == "pending"
        ),
        "alerts": [dict(a) for a in alerts]
    }


@app.post("/api/mesh/sync")
async def sync_offline_alerts(worksite_id: int):
    with get_db() as db:
        pending = db.execute(
            """
            SELECT id FROM offline_alert_queue
            WHERE worksite_id = ?
            AND sync_status = 'pending'
            """,
            (worksite_id,)
        ).fetchall()

        if not pending:
            return {
                "message": "No pending alerts to synchronize",
                "synced_count": 0
            }

        db.execute(
            """
            UPDATE offline_alert_queue
            SET sync_status = 'synced',
                synced_at = CURRENT_TIMESTAMP
            WHERE worksite_id = ?
            AND sync_status = 'pending'
            """,
            (worksite_id,)
        )

    return {
        "message": "Offline alerts synchronized successfully",
        "worksite_id": worksite_id,
        "synced_count": len(pending)
    }


@app.post("/api/mesh/local-check")
async def run_local_safety_check(
    worksite_id: int,
    worker_code: str
):
    with get_db() as db:
        worker = db.execute(
            """
            SELECT * FROM workers
            WHERE worksite_id = ? AND worker_code = ?
            """,
            (worksite_id, worker_code)
        ).fetchone()

        if not worker:
            raise HTTPException(
                status_code=404,
                detail="Worker not found"
            )

        exposure = db.execute(
            """
            SELECT * FROM exposure_records
            WHERE worksite_id = ? AND worker_code = ?
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (worksite_id, worker_code)
        ).fetchone()

        if not exposure:
            return {
                "worker_code": worker_code,
                "assessment": "unknown",
                "action": "sensor_data_unavailable",
                "message": (
                    "No exposure data available. "
                    "Do not assume the worker is safe."
                ),
                "alert_created": False
            }

        risk = (exposure["risk_level"] or "").lower()

        if risk in ["critical", "high"]:
            alert_type = "high_heat_exposure"

            existing = db.execute(
                """
                SELECT id FROM offline_alert_queue
                WHERE worksite_id = ?
                AND worker_code = ?
                AND alert_type = ?
                AND sync_status = 'pending'
                LIMIT 1
                """,
                (worksite_id, worker_code, alert_type)
            ).fetchone()

            if existing:
                alert_id = existing["id"]
                created = False
            else:
                cursor = db.execute(
                    """
                    INSERT INTO offline_alert_queue (
                        worksite_id, zone_id, worker_code,
                        alert_type, severity, message
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        worksite_id,
                        worker["zone_id"],
                        worker_code,
                        alert_type,
                        "critical" if risk == "critical" else "high",
                        "Local rule triggered: high heat exposure. "
                        "Recommend shaded rest and supervisor review."
                    )
                )
                alert_id = cursor.lastrowid
                created = True

            return {
                "worker_code": worker_code,
                "assessment": risk,
                "action": "protection_alert_queued",
                "alert_id": alert_id,
                "alert_created": created,
                "source": exposure["source"],
                "message": (
                    "Exposure risk flag detected. "
                    "Supervisor review and protective action recommended."
                )
            }

        return {
            "worker_code": worker_code,
            "assessment": risk or "unknown",
            "action": "continue_monitoring",
            "alert_created": False,
            "message": (
                "No high or critical risk flag found in the latest record. "
                "This does not establish that the worker is safe."
            )
        }

@app.get("/api/biotwin/research-catalog")
async def get_biotwin_research_catalog():

    datasets = [
        {
            "domain": "metabolomics",
            "source_name": "Metabolomics Workbench",
            "description": "Public repository for metabolomics studies, experimental data and metadata.",
            "source_url": "https://www.metabolomicsworkbench.org/",
            "access": "Public repository",
            "integration_status": "identified_not_ingested",
            "heat_stress_specific": False,
            "research_note": "A heat-stress-specific study must be selected and its population and variables checked before analysis."
        },
        {
            "domain": "cardiovascular",
            "source_name": "PhysioNet",
            "description": "Research repository containing physiological and cardiovascular signal datasets.",
            "source_url": "https://physionet.org/content/",
            "access": "Varies by dataset",
            "integration_status": "identified_not_ingested",
            "heat_stress_specific": False,
            "research_note": "Dataset-level access requirements and relevance to heat exposure must be verified."
        },
        {
            "domain": "microbiome",
            "source_name": "Human Microbiome Project",
            "description": "Public human microbiome resources, including microbial sequencing and related analysis products.",
            "source_url": "https://ihmpdcc.org/data.php",
            "access": "Public and controlled-access resources",
            "integration_status": "identified_not_ingested",
            "heat_stress_specific": False,
            "research_note": "Existing microbiome cohorts are not automatically evidence of heat-stress effects."
        },
        {
            "domain": "thermoregulation",
            "source_name": "Human Heat Stress and Heat Acclimation Dataset",
            "description": "Physiological measurements and plasma protein data from 10 healthy adults before and during passive heat stress, before and after a 7-day heat-acclimation protocol.",
            "source_url": "https://www.nature.com/articles/s41597-023-02809-5",
            "access": "Public research dataset",
            "integration_status": "identified_not_ingested",
            "heat_stress_specific": True,
            "research_note": "Small study of healthy adults; population and study conditions limit generalisation to outdoor workers."
        }
    ]

    return {
        "module": "BioTwin",
        "status": "research_registry_initialized",
        "total_domains": 4,
        "datasets_identified": len(datasets),
        "datasets_ingested": 0,
        "domains": [
            "metabolomics",
            "cardiovascular",
            "microbiome",
            "thermoregulation"
        ],
        "datasets": datasets,
        "safety_note": (
            "Research findings represent population-level evidence. "
            "They must not be used as individual medical diagnoses "
            "or validated worker risk scores."
        )
    }

@app.get("/api/dashboard/summary")
async def dashboard_summary():
    with get_db() as db:
        worksites = db.execute("SELECT COUNT(*) AS count, COALESCE(SUM(worker_count), 0) AS declared_workers FROM worksites").fetchone()
        workers = db.execute("SELECT COUNT(*) AS count FROM workers WHERE active = 1").fetchone()
        zones = db.execute("SELECT COUNT(*) AS count FROM zones").fetchone()
        active_alerts = db.execute("SELECT COUNT(*) AS count FROM interventions WHERE status IN ('recommended', 'approved')").fetchone()
        latest_exposure = db.execute("SELECT risk_level, source, recorded_at FROM exposure_records ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "worksite_count": worksites["count"],
        "declared_worker_count": worksites["declared_workers"],
        "registered_worker_count": workers["count"],
        "zone_count": zones["count"],
        "pending_intervention_count": active_alerts["count"],
        "latest_exposure_record": dict(latest_exposure) if latest_exposure else None,
        "wbgt_status": "measured_only_when_onsite_sensor_record_exists",
    }


@app.get("/api/biotwin/worker-health-demo")
async def worker_health_demo(worksite_id: int | None = Query(default=None, gt=0)):
    """Synthetic worker health examples; not clinical diagnoses."""
    with get_db() as db:
        sql = """
            SELECT p.worker_code, p.profile_label, p.vulnerability_domain,
                   p.demo_note, p.created_at, w.role, w.zone_id,
                   e.risk_level AS exposure_band, e.air_temperature_c,
                   e.relative_humidity_pct, e.exposure_minutes, e.source AS exposure_source
            FROM worker_health_demo_profiles p
            LEFT JOIN workers w
              ON w.worksite_id = p.worksite_id AND w.worker_code = p.worker_code
            LEFT JOIN exposure_records e
              ON e.id = (
                SELECT e2.id FROM exposure_records e2
                WHERE e2.worksite_id = p.worksite_id AND e2.worker_code = p.worker_code
                ORDER BY e2.recorded_at DESC, e2.id DESC LIMIT 1
              )
            WHERE (? IS NULL OR p.worksite_id = ?)
            ORDER BY p.worker_code
        """
        rows = db.execute(sql, (worksite_id, worksite_id)).fetchall()
    return {
        "status": "synthetic_demo_only",
        "notice": "Fictional examples only; not real worker records, confirmed diagnoses, or model predictions. Vital readings are synthetic demo inputs; environmental exposure remains a separate recorded context.",
        "profiles": [dict(row) for row in rows],
    }


async def _generate_worker_ai_assessment(reading: dict, profile: dict | None, exposure: dict | None) -> tuple[str, str, str]:
    """Synthesize dataset-label screening + retrieved heat-health evidence for supervisors."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return "", "unavailable_no_api_key", ""
    try:
        from groq import AsyncGroq
        from app.biotwin.knowledge_base import retrieve_evidence
        dataset_screen = assess_dataset_vital_risk(reading)
        query_parts = [
            "occupational heat stress worker vital signs heat exhaustion heat stroke emergency response",
            f"temperature {reading.get('body_temperature_c')} {reading.get('temperature_type')}",
            f"heart rate {reading.get('heart_rate_bpm')} respiratory rate {reading.get('respiratory_rate_bpm')} oxygen saturation {reading.get('spo2_pct')}",
            f"blood pressure {reading.get('systolic_bp_mmhg')}/{reading.get('diastolic_bp_mmhg')}",
            f"reported symptoms {reading.get('symptoms', '')}",
        ]
        if exposure:
            query_parts.append(f"heat exposure WBGT {exposure.get('measured_wbgt_c')} ambient temperature {exposure.get('air_temperature_c')} humidity {exposure.get('relative_humidity_pct')} duration {exposure.get('exposure_minutes')}")
        evidence_items = retrieve_evidence(" ".join(query_parts), top_k=6)
        evidence_context = [
            {
                "title": item.get("title") or item.get("source") or "Indexed guidance",
                "organization": item.get("organization") or item.get("source") or "",
                "content": str(item.get("content", ""))[:1400],
                "source_url": item.get("source_url") or "",
            }
            for item in evidence_items[:6]
        ]
        dataset_evidence = build_heat_health_dataset_context(reading, exposure)
        prompt = {
            "worker_reading": reading,
            "available_health_context": profile or {"status": "not supplied"},
            "latest_environmental_exposure": exposure or {"status": "not available"},
            "kaggle_vital_sign_dataset_screening": dataset_screen,
            "retrieved_reference_material": evidence_context,
            "retrieved_research_dataset_context": dataset_evidence,
        }
        client = AsyncGroq(api_key=api_key, timeout=25.0, max_retries=1)
        response = await client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            temperature=0.2,
            max_completion_tokens=850,
            messages=[
                {"role": "system", "content": (
                    "You are an occupational heat-health decision-support assistant for workplace supervisors. "
                    "Synthesize the worker's actual recorded readings, symptoms, exposure context, Kaggle vital-sign dataset screening, project research datasets, and retrieved WHO/CDC/NIOSH/ILO evidence. "
                    "BioTwin numeric risk label mapping: 0 = Low Risk and 1 = High Risk. "
"Use the readable label when explaining results. Never interpret 0 or 1 as a probability. "
"The Kaggle High Risk/Low Risk target is threshold-derived and is NOT a disease label, clinical outcome, or calibrated probability. "
"State it only as dataset-label screening when present. "
                    "Use population research as context, never as an individual match. Do not diagnose or claim the worker has respiratory, cardiac, renal, or other disease. "
                    "You may identify possible areas of concern (heat-related, respiratory, cardiovascular) only when supported by the supplied values/evidence, and explain the specific observations. "
                    "Do not infer missing values; skin temperature is not core temperature; do not equate SpO2 or respiratory rate with a diagnosis. "
                    "If confusion, fainting, seizure, unconsciousness, chest pain, or severe breathlessness is reported, recommend stopping work and immediate local emergency response. "
                    "Otherwise recommend cool area/rest, repeat measurements with appropriate device, and prompt clinician assessment for persistent symptoms or concerning readings. "
                    "Clearly label synthetic demo inputs. Return concise plain text with exactly these headings: Overall screening; Possible areas of concern; Why this needs attention; Supervisor action; Evidence and limitations. "
                    "Cite only supplied source titles/organizations; never fabricate references."
                )},
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, default=str)},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return "", "empty_llm_response", ""
        return text[:8500], "generated", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    except Exception as exc:
        return f"AI explanation could not be generated ({type(exc).__name__}). Independent safety screening remains active.", "generation_error", os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


@app.get("/api/biotwin/vitals")
async def list_worker_vitals(worksite_id: int = Query(gt=0), limit: int = Query(default=100, ge=1, le=500)):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM worker_vitals_readings WHERE worksite_id = ? ORDER BY id DESC LIMIT ?",
            (worksite_id, limit),
        ).fetchall()
    readings = [dict(row) for row in rows]
    # Generate explanations for pre-seeded synthetic examples on first view as well.
    async def explain_pending(reading):
        if reading.get("ai_status") not in (None, "", "pending"):
            return
        with get_db() as db:
            profile = db.execute(
                "SELECT profile_label, vulnerability_domain, demo_note FROM worker_health_demo_profiles WHERE worksite_id=? AND worker_code=? ORDER BY id DESC LIMIT 1",
                (worksite_id, reading["worker_code"]),
            ).fetchone()
            exposure = db.execute(
                "SELECT exposure_minutes, risk_level, air_temperature_c, relative_humidity_pct, measured_wbgt_c, source, recorded_at FROM exposure_records WHERE worksite_id=? AND (worker_code=? OR worker_code IS NULL) ORDER BY recorded_at DESC LIMIT 1",
                (worksite_id, reading["worker_code"]),
            ).fetchone()
        ai_text, ai_status, ai_model = await _generate_worker_ai_assessment(
            reading, dict(profile) if profile else None, dict(exposure) if exposure else None
        )
        with get_db() as db:
            db.execute("UPDATE worker_vitals_readings SET ai_assessment=?, ai_status=?, ai_model=? WHERE id=?",
                       (ai_text, ai_status, ai_model, reading["id"]))
        reading.update({"ai_assessment": ai_text, "ai_status": ai_status, "ai_model": ai_model})

    await asyncio.gather(*(explain_pending(reading) for reading in readings))
    for reading in readings:
        with get_db() as db:
            exposure_row = db.execute(
                "SELECT exposure_minutes, risk_level, air_temperature_c, relative_humidity_pct, measured_wbgt_c, source, recorded_at FROM exposure_records WHERE worksite_id=? AND (worker_code=? OR worker_code IS NULL) ORDER BY recorded_at DESC LIMIT 1",
                (worksite_id, reading["worker_code"]),
            ).fetchone()
        reading["research_dataset_context"] = build_heat_health_dataset_context(
            reading, dict(exposure_row) if exposure_row else None
        ).get("sources", [])
        reading["dataset_vital_screening"] = assess_dataset_vital_risk(reading)
    return {"readings": readings, "notice": "AI explanations are decision support only, not a diagnosis or validated disease prediction. Synthetic demo records are fictional."}


@app.post("/api/biotwin/vitals", status_code=201)
async def create_worker_vitals(payload: WorkerVitalsCreate):
    symptoms = payload.symptoms.strip()
    symptom_text = symptoms.lower()
    emergency_terms = ("confusion", "faint", "unconscious", "seizure", "chest pain", "severe breathlessness")
    reasons = []
    level = "review"
    if any(term in symptom_text for term in emergency_terms):
        level = "urgent"
        reasons.append("Reported symptom requires immediate on-site emergency assessment")
    if payload.temperature_type == "core" and payload.body_temperature_c is not None and payload.body_temperature_c >= 38.0:
        level = "urgent"
        reasons.append("Recorded core temperature is elevated; stop work and arrange urgent medical assessment")
    if payload.spo2_pct is not None and payload.spo2_pct < 92:
        level = "urgent"
        reasons.append("Low recorded oxygen saturation requires urgent clinical re-check")
    if payload.heart_rate_bpm is not None and payload.heart_rate_bpm >= 130:
        if level != "urgent": level = "review"
        reasons.append("High recorded heart rate; repeat measurement after rest and seek clinical review if persistent or symptomatic")
    if not reasons:
        reasons.append("No configured screening trigger detected; this does not rule out illness")
    with get_db() as db:
        worker = db.execute(
            "SELECT id FROM workers WHERE worksite_id = ? AND worker_code = ? AND active = 1",
            (payload.worksite_id, payload.worker_code.strip()),
        ).fetchone()
        if not worker:
            raise HTTPException(status_code=400, detail="Worker code is not registered and active at this worksite")
        
        cursor = db.execute(
            """INSERT INTO worker_vitals_readings
            (
                worksite_id,
                worker_code,
                body_temperature_c,
                temperature_type,
                heart_rate_bpm,
                respiratory_rate_bpm,
                spo2_pct,
                systolic_bp_mmhg,
                diastolic_bp_mmhg,
                weight_kg,
                height_m,
                symptoms,
                source,
                alert_level,
                alert_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                payload.worksite_id,
                payload.worker_code.strip(),
                payload.body_temperature_c,
                payload.temperature_type,
                payload.heart_rate_bpm,
                payload.respiratory_rate_bpm,
                payload.spo2_pct,
                payload.systolic_bp_mmhg,
                payload.diastolic_bp_mmhg,
                payload.weight_kg,
                payload.height_m,
                symptoms,
                payload.source,
                level,
                "; ".join(reasons),
            ),
        )

        row = db.execute("SELECT * FROM worker_vitals_readings WHERE id = ?", (cursor.lastrowid,)).fetchone()
        reading = dict(row)
        profile_row = db.execute(
            "SELECT profile_label, vulnerability_domain, demo_note FROM worker_health_demo_profiles WHERE worksite_id=? AND worker_code=? ORDER BY id DESC LIMIT 1",
            (payload.worksite_id, payload.worker_code.strip()),
        ).fetchone()
        exposure_row = db.execute(
            "SELECT exposure_minutes, risk_level, air_temperature_c, relative_humidity_pct, measured_wbgt_c, source, recorded_at FROM exposure_records WHERE worksite_id=? AND (worker_code=? OR worker_code IS NULL) ORDER BY recorded_at DESC LIMIT 1",
            (payload.worksite_id, payload.worker_code.strip()),
        ).fetchone()
    ai_text, ai_status, ai_model = await _generate_worker_ai_assessment(
        reading, dict(profile_row) if profile_row else None, dict(exposure_row) if exposure_row else None
    )
    with get_db() as db:
        db.execute(
            "UPDATE worker_vitals_readings SET ai_assessment=?, ai_status=?, ai_model=? WHERE id=?",
            (ai_text, ai_status, ai_model, reading["id"]),
        )
        row = db.execute("SELECT * FROM worker_vitals_readings WHERE id = ?", (reading["id"],)).fetchone()
    return {**dict(row), "recommendation": "Stop work and arrange urgent medical/emergency assessment" if level == "urgent" else "Supervisor review; repeat/check readings and symptoms", "ai_assessment": ai_text, "ai_status": ai_status, "disclaimer": "AI-generated decision support, not a diagnosis or validated disease prediction. Verify readings and use qualified clinical judgement. Rule-based urgent screening remains active even if AI is unavailable.", "research_dataset_context": build_heat_health_dataset_context(reading, dict(exposure_row) if exposure_row else None).get("sources", []), "dataset_vital_screening": assess_dataset_vital_risk(reading)}


@app.get("/api/biotwin/vitals/model-status")
async def worker_vitals_model_status():
    return vital_model_status()


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "heatshield-api", "version": "0.5.3"}

@app.get("/api/cities")
async def cities():
    return {"cities": [{"id": key, **value} for key, value in CITIES.items()]}

@app.get("/api/weather/{city}")
async def weather(city: str):
    key = city.strip().lower()
    location = CITIES.get(key)
    if not location:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported city. Available cities: {', '.join(CITIES.keys())}"
        )

    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "hourly": ",".join(HOURLY_FIELDS),
        "forecast_days": 2,
        "timezone": location["timezone"],
        "wind_speed_unit": "kmh",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Weather provider unavailable: {exc}") from exc

    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        raise HTTPException(status_code=502, detail="Weather provider returned no hourly data")

    # Use the requested location timezone; choose the nearest available hourly timestamp.
    city_timezone = ZoneInfo(location["timezone"])
    now = datetime.now(city_timezone)
    parsed = [datetime.fromisoformat(t).replace(tzinfo=city_timezone) for t in times]
    index = min(range(len(parsed)), key=lambda i: abs((parsed[i] - now).total_seconds()))

    current = {
        "time_local": times[index],
        "temperature_c": number_or_none(hourly, "temperature_2m", index),
        "relative_humidity_pct": number_or_none(hourly, "relative_humidity_2m", index),
        "apparent_temperature_c": number_or_none(hourly, "apparent_temperature", index),
        "wind_speed_kmh": number_or_none(hourly, "wind_speed_10m", index),
        "wet_bulb_temperature_c": number_or_none(hourly, "wet_bulb_temperature_2m", index),
        "shortwave_radiation_wm2": number_or_none(hourly, "shortwave_radiation", index),
    }

    forecast = []
    for i, time_value in enumerate(times[:24]):
        forecast.append({
            "time_local": time_value,
            "temperature_c": number_or_none(hourly, "temperature_2m", i),
            "relative_humidity_pct": number_or_none(hourly, "relative_humidity_2m", i),
            "apparent_temperature_c": number_or_none(hourly, "apparent_temperature", i),
            "wind_speed_kmh": number_or_none(hourly, "wind_speed_10m", i),
            "wet_bulb_temperature_c": number_or_none(hourly, "wet_bulb_temperature_2m", i),
            "shortwave_radiation_wm2": number_or_none(hourly, "shortwave_radiation", i),
        })

    return {
        "location": location["name"],
        "coordinates": {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
        },
        "timezone": payload.get("timezone", location["timezone"]),
        "retrieved_at_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": {
            "name": "Open-Meteo",
            "url": "https://open-meteo.com/",
            "license": "CC BY 4.0",
            "data_type": "Numerical weather model forecast",
        },
        "measurement_notice": (
            "These are modelled weather variables for the grid location, not on-site sensor readings. "
            "Wet-bulb temperature is not WBGT. Do not use this response as a substitute for measured WBGT."
        ),
        "current": current,
        "hourly_forecast": forecast,
    }

# ==========================================
# SWAGGER BEARER AUTHENTICATION CONFIGURATION
# ==========================================

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Register Bearer Authentication
    openapi_schema.setdefault("components", {})
    openapi_schema["components"].setdefault(
        "securitySchemes", {}
    )

    openapi_schema["components"]["securitySchemes"][
        "BearerAuth"
    ] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter your HeatShield access token."
    }

    # Apply authentication to protected API endpoints
    public_paths = {
        "/api/auth/login",
        "/api/health",
    }

    protected_methods = {
        "get",
        "post",
        "put",
        "patch",
        "delete",
    }

    for path, methods in openapi_schema["paths"].items():

        if not path.startswith("/api/"):
            continue

        if path in public_paths:
            continue

        for method, operation in methods.items():

            if method.lower() in protected_methods:
                operation["security"] = [
                    {"BearerAuth": []}
                ]

    app.openapi_schema = openapi_schema

    return app.openapi_schema


app.openapi = custom_openapi
