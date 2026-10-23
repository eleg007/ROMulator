# ROMulus

Browser-based ROM & Shockwave Flash emulator platform.

## Stack

- **Backend:** FastAPI + SQLite (Python), auth with admin approval, uploads, optional Google Drive cloud library
- **Frontend:** EmulatorJS + Ruffle (Shockwave Flash), Bebas Neue / Space Mono UI
- **Deployment:** self-hosted behind ngrok (systemd units in `systemd/`)

## Run locally

```bash
cd /home/debian/projects/romulus
/home/debian/projects/orbit-chat/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

Open http://127.0.0.1:8010. Copy `.env.example` to `.env` and edit as needed; default admin is `admin` / `ChangeMe123!`.

## Dependencies

See `romulus-project/requirements.txt` (FastAPI, uvicorn, argon2-cffi, google-api-python-client, google-auth, python-multipart, python-dotenv).

## Components

See `COMPONENTS.md`.
