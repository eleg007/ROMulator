import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from argon2 import PasswordHasher
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "data" / "romulus.sqlite3"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
FRONTEND_DIR = BASE_DIR / "frontend"

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ph = PasswordHasher()
app = FastAPI(title="ROMulus")
SESSION_COOKIE = "romulus_session"
SESSION_TTL_HOURS = 24
PIN_RATE_WINDOW_SECONDS = 15 * 60
PIN_RATE_LIMIT = 5

_pin_attempts: dict[str, list[float]] = {}

STATUSES = ["Blocked", "Deleted", "Pending", "User", "Test User", "Admin", "Owner"]
STATUS_RANK = {s: i for i, s in enumerate(STATUSES)}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            role TEXT NOT NULL DEFAULT 'User',
            device_fingerprint TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS access_codes (
            code TEXT PRIMARY KEY,
            holder_name TEXT NOT NULL,
            issuing_admin_id TEXT REFERENCES users(id),
            device_fingerprint TEXT,
            status TEXT NOT NULL DEFAULT 'unused',
            created_at TEXT NOT NULL,
            used_at TEXT
        );
        CREATE TABLE IF NOT EXISTS pin_tokens (
            token TEXT PRIMARY KEY,
            code TEXT NOT NULL REFERENCES access_codes(code),
            holder_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            recipient_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            displayed_at TEXT,
            read_at TEXT
        );
        CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            author_id TEXT REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_badges (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            badge TEXT NOT NULL,
            awarded_by TEXT REFERENCES users(id),
            awarded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS library_items (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            system TEXT NOT NULL,
            drive_file_id TEXT,
            local_path TEXT,
            uploader_id TEXT REFERENCES users(id),
            visibility TEXT NOT NULL DEFAULT 'private',
            upvotes INTEGER NOT NULL DEFAULT 0,
            favorites INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS library_votes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, item_id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT
        );
        CREATE TABLE IF NOT EXISTS activity (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            game_id TEXT,
            system TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            duration_seconds INTEGER NOT NULL DEFAULT 0
        );
        """)
    seed_admin()

def seed_admin():
    email = os.getenv("ROMULUS_ADMIN_EMAIL", "admin@romulus.local")
    password = os.getenv("ROMULUS_ADMIN_PASSWORD", "ChangeMe123!")
    name = os.getenv("ROMULUS_ADMIN_NAME", "ROMulus Owner")
    with db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return
        user_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO users (id, full_name, email, username, password_hash, status, role, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'Owner', 'Owner', ?, ?)""",
            (user_id, name, email, "admin", ph.hash(password), now_iso(), now_iso()),
        )

def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"

def enforce_pin_rate_limit(request: Request):
    ip = client_ip(request)
    now = time.time()
    attempts = [t for t in _pin_attempts.get(ip, []) if now - t < PIN_RATE_WINDOW_SECONDS]
    if len(attempts) >= PIN_RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many PIN attempts. Try again later.")
    _pin_attempts[ip] = attempts

def record_pin_attempt(request: Request, success: bool):
    ip = client_ip(request)
    if ip not in _pin_attempts:
        _pin_attempts[ip] = []
    _pin_attempts[ip].append(time.time())

def get_session_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        row = conn.execute(
            """SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id
               WHERE sessions.token_hash = ? AND sessions.expires_at > ?""",
            (token_hash, now_iso()),
        ).fetchone()
    return dict(row) if row else None

def require_user(request: Request):
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user["status"] in ("Blocked", "Deleted"):
        raise HTTPException(status_code=403, detail="Access denied")
    return user

def require_status(user, minimum):
    if STATUS_RANK.get(user["status"], -1) < STATUS_RANK.get(minimum, 99):
        raise HTTPException(status_code=403, detail="Insufficient privileges")

def create_session(response: Response, user_id: str):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat()
    with db() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, token_hash, now_iso(), expires),
        )
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", max_age=SESSION_TTL_HOURS * 3600)
    return token

def notify_admins(message: str, notif_type: str = "alert"):
    with db() as conn:
        conn.execute(
            "INSERT INTO notifications (id, type, message, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), notif_type, message, now_iso()),
        )

def drive_service():
    if not GOOGLE_SERVICE_ACCOUNT_FILE or not GOOGLE_DRIVE_FOLDER_ID:
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=DRIVE_SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None

def upload_to_drive(title, content, system):
    service = drive_service()
    if service is None:
        return None
    metadata = {"name": title}
    if GOOGLE_DRIVE_FOLDER_ID:
        metadata["parents"] = [GOOGLE_DRIVE_FOLDER_ID]
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/octet-stream", resumable=True)
    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    file_id = created.get("id")
    # Make public (anyone with link)
    service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
    return file_id

@app.on_event("startup")
def startup():
    init_db()

@app.post("/api/pin/entry")
def pin_entry(payload: dict, request: Request):
    enforce_pin_rate_limit(request)
    pin = (payload.get("pin") or "").strip()
    fingerprint = payload.get("device_fingerprint")
    with db() as conn:
        code = conn.execute("SELECT * FROM access_codes WHERE code = ?", (pin,)).fetchone()
    if not code:
        record_pin_attempt(request, False)
        raise HTTPException(status_code=401, detail="Invalid PIN")
    code = dict(code)
    if code["status"] == "void":
        record_pin_attempt(request, False)
        raise HTTPException(status_code=403, detail="PIN voided")
    if code["status"] != "unused":
        record_pin_attempt(request, False)
        raise HTTPException(status_code=403, detail="PIN already used")
    if code["device_fingerprint"] and fingerprint and code["device_fingerprint"] != fingerprint:
        with db() as conn:
            conn.execute("UPDATE access_codes SET status = 'void' WHERE code = ?", (pin,))
        notify_admins(f"PIN {pin} attempted on a different device; code voided and holder blocked.")
        # block any user tied to this code by name is not directly linked; attempt by username not available
        record_pin_attempt(request, False)
        raise HTTPException(status_code=403, detail="Device mismatch. PIN voided.")
    record_pin_attempt(request, True)
    token = secrets.token_urlsafe(24)
    with db() as conn:
        conn.execute(
            "INSERT INTO pin_tokens (token, code, holder_name, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (token, pin, code["holder_name"], now_iso(), (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()),
        )
        if not code["device_fingerprint"] and fingerprint:
            conn.execute("UPDATE access_codes SET device_fingerprint = ? WHERE code = ?", (fingerprint, pin))
    return {"token": token, "holder_name": code["holder_name"]}

@app.post("/api/auth/signup")
def signup(payload: dict, response: Response):
    token = payload.get("token")
    full_name = (payload.get("full_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not all([token, full_name, email, username, password]):
        raise HTTPException(status_code=400, detail="All fields required")
    with db() as conn:
        pt = conn.execute("SELECT * FROM pin_tokens WHERE token = ? AND used = 0", (token,)).fetchone()
        if not pt:
            raise HTTPException(status_code=401, detail="Invalid or used token")
        pt = dict(pt)
        if datetime.fromisoformat(pt["expires_at"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="Token expired")
        if pt["holder_name"].strip().lower() != full_name.lower():
            raise HTTPException(status_code=400, detail="Name must match PIN holder name")
        existing = conn.execute("SELECT id FROM users WHERE email = ? OR username = ?", (email, username)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")
        user_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO users (id, full_name, email, username, password_hash, status, role, device_fingerprint, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'Pending', 'User', (SELECT device_fingerprint FROM access_codes WHERE code = ?), ?, ?)""",
            (user_id, full_name, email, username, ph.hash(password), pt["code"], now_iso(), now_iso()),
        )
        conn.execute("UPDATE access_codes SET status = 'used', used_at = ? WHERE code = ?", (now_iso(), pt["code"]))
        conn.execute("UPDATE pin_tokens SET used = 1 WHERE token = ?", (token,))
    create_session(response, user_id)
    return {"user_id": user_id, "status": "Pending"}

@app.post("/api/auth/login")
def login(payload: dict, request: Request, response: Response):
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    fingerprint = payload.get("device_fingerprint")
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, username.lower())).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = dict(user)
    try:
        ph.verify(user["password_hash"], password)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user["status"] in ("Blocked", "Deleted"):
        raise HTTPException(status_code=403, detail="Access denied")
    if user["device_fingerprint"] and fingerprint and user["device_fingerprint"] != fingerprint:
        notify_admins(f"User {user['username']} attempted login from a different device.")
        with db() as conn:
            conn.execute("UPDATE users SET status = 'Blocked' WHERE id = ?", (user["id"],))
        raise HTTPException(status_code=403, detail="Device mismatch. Account blocked.")
    create_session(response, user["id"])
    return {"status": user["status"], "role": user["role"]}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}

@app.get("/api/me")
def me(request: Request):
    user = require_user(request)
    with db() as conn:
        badges = [r["badge"] for r in conn.execute("SELECT badge FROM user_badges WHERE user_id = ?", (user["id"],)).fetchall()]
        messages = [dict(r) for r in conn.execute("SELECT * FROM messages WHERE recipient_user_id = ? AND displayed_at IS NULL ORDER BY created_at", (user["id"],)).fetchall()]
    return {"user": {k: user[k] for k in ("id","full_name","email","username","status","role")}, "badges": badges, "messages": messages}

@app.post("/api/messages/{message_id}/displayed")
def mark_displayed(message_id: str, request: Request):
    user = require_user(request)
    with db() as conn:
        conn.execute("UPDATE messages SET displayed_at = ? WHERE id = ? AND recipient_user_id = ?", (now_iso(), message_id, user["id"]))
    return {"ok": True}

@app.get("/api/users")
def list_users(request: Request):
    user = require_user(request)
    require_status(user, "Admin")
    with db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, full_name, email, username, status, role, created_at FROM users ORDER BY created_at DESC").fetchall()]
    return {"users": rows}

@app.post("/api/admin/users/{user_id}/status")
def update_status(user_id: str, payload: dict, request: Request):
    user = require_user(request)
    require_status(user, "Admin")
    new_status = payload.get("status")
    if new_status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    with db() as conn:
        conn.execute("UPDATE users SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_iso(), user_id))
    return {"ok": True}

@app.post("/api/admin/users/{user_id}/message")
def send_message(user_id: str, payload: dict, request: Request):
    user = require_user(request)
    require_status(user, "Admin")
    content = (payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content required")
    with db() as conn:
        conn.execute(
            "INSERT INTO messages (id, recipient_user_id, content, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, content, now_iso()),
        )
    return {"ok": True}

@app.post("/api/admin/users/{user_id}/badges")
def add_badge(user_id: str, payload: dict, request: Request):
    user = require_user(request)
    require_status(user, "Admin")
    badge = (payload.get("badge") or "").strip()
    if not badge:
        raise HTTPException(status_code=400, detail="Badge required")
    with db() as conn:
        conn.execute(
            "INSERT INTO user_badges (id, user_id, badge, awarded_by, awarded_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, badge, user["id"], now_iso()),
        )
    return {"ok": True}

@app.post("/api/admin/codes")
def create_code(payload: dict, request: Request):
    user = require_user(request)
    require_status(user, "Admin")
    holder_name = (payload.get("holder_name") or "").strip()
    if not holder_name:
        raise HTTPException(status_code=400, detail="Holder name required")
    code = str(secrets.randbelow(900000) + 100000)
    with db() as conn:
        conn.execute(
            "INSERT INTO access_codes (code, holder_name, issuing_admin_id, status, created_at) VALUES (?, ?, ?, 'unused', ?)",
            (code, holder_name, user["id"], now_iso()),
        )
    return {"code": code, "holder_name": holder_name}

@app.get("/api/library")
def list_library(request: Request, public: bool = False):
    user = require_user(request)
    with db() as conn:
        if public:
            rows = [dict(r) for r in conn.execute("SELECT * FROM library_items WHERE visibility IN ('public','approved') ORDER BY created_at DESC").fetchall()]
        else:
            rows = [dict(r) for r in conn.execute("SELECT * FROM library_items ORDER BY created_at DESC").fetchall()]
    return {"items": rows}

@app.post("/api/library/upload")
async def upload_library(request: Request):
    user = require_user(request)
    form = await request.form()
    title = (form.get("title") or "").strip()
    system = (form.get("system") or "NES").strip()
    upload = form.get("file")
    if not title or not upload:
        raise HTTPException(status_code=400, detail="Title and file required")
    filename = f"{uuid.uuid4()}_{upload.filename}"
    dest = UPLOAD_DIR / filename
    content = await upload.read()
    dest.write_bytes(content)
    drive_id = upload_to_drive(title, content, system)
    with db() as conn:
        item_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO library_items (id, title, system, drive_file_id, local_path, uploader_id, visibility, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'private', ?, ?)""",
            (item_id, title, system, drive_id, str(dest), user["id"], now_iso(), now_iso()),
        )
    return {"id": item_id, "title": title, "drive_file_id": drive_id}

@app.get("/api/library/{item_id}/download")
def download_library(item_id: str, request: Request):
    require_user(request)
    with db() as conn:
        row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row = dict(row)
    if row.get("drive_file_id"):
        return RedirectResponse(url=f"https://drive.google.com/uc?export=download&id={row['drive_file_id']}")
    if row.get("local_path"):
        return FileResponse(row["local_path"], filename=row["title"])
    raise HTTPException(status_code=404, detail="No file available")

@app.post("/api/library/{item_id}/visibility")
def set_visibility(item_id: str, payload: dict, request: Request):
    user = require_user(request)
    require_status(user, "Admin")
    visibility = payload.get("visibility")
    if visibility not in ("private", "public", "approved", "removed"):
        raise HTTPException(status_code=400, detail="Invalid visibility")
    with db() as conn:
        conn.execute("UPDATE library_items SET visibility = ?, updated_at = ? WHERE id = ?", (visibility, now_iso(), item_id))
    return {"ok": True}

@app.post("/api/library/{item_id}/vote")
def vote(item_id: str, request: Request):
    user = require_user(request)
    with db() as conn:
        existing = conn.execute("SELECT id FROM library_votes WHERE user_id = ? AND item_id = ?", (user["id"], item_id)).fetchone()
        if existing:
            return {"ok": True, "voted": True, "duplicate": True}
        conn.execute("INSERT INTO library_votes (id, user_id, item_id, created_at) VALUES (?, ?, ?, ?)", (str(uuid.uuid4()), user["id"], item_id, now_iso()))
        conn.execute("UPDATE library_items SET upvotes = upvotes + 1, updated_at = ? WHERE id = ?", (now_iso(), item_id))
    return {"ok": True, "voted": True, "duplicate": False}

@app.post("/api/activity/start")
def activity_start(payload: dict, request: Request):
    user = require_user(request)
    with db() as conn:
        act_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO activity (id, user_id, game_id, system, started_at) VALUES (?, ?, ?, ?, ?)",
            (act_id, user["id"], payload.get("game_id"), payload.get("system"), now_iso()),
        )
    return {"activity_id": act_id}

@app.post("/api/activity/{activity_id}/end")
def activity_end(activity_id: str, payload: dict, request: Request):
    require_user(request)
    with db() as conn:
        row = conn.execute("SELECT started_at FROM activity WHERE id = ?", (activity_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        start = datetime.fromisoformat(row["started_at"])
        duration = int((datetime.now(timezone.utc) - start).total_seconds())
        conn.execute("UPDATE activity SET ended_at = ?, duration_seconds = ? WHERE id = ?", (now_iso(), duration, activity_id))
    return {"duration": duration}

@app.get("/api/notifications")
def list_notifications(request: Request):
    user = require_user(request)
    require_status(user, "Admin")
    with db() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM notifications ORDER BY created_at DESC LIMIT 100").fetchall()]
    return {"notifications": rows}

if FRONTEND_DIR.exists():
    @app.get("/")
    def root():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
