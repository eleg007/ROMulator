# ROMulator — Components

Retro-game ROM library/streaming stack: a FastAPI backend (`romulus-project/`),
a static emulator frontend, and a legacy Firebase Cloud Functions snapshot.

## systemd services

Unit files live in `systemd/` (not necessarily installed on this host).

| Unit | Type | Purpose |
|---|---|---|
| `romulus-backend.service` | simple | Runs the FastAPI backend via uvicorn on `127.0.0.1:8010`, with proxy headers. Runs as `debian`, `WorkingDirectory=/home/debian/projects/romulus`, `EnvironmentFile=.../romulus/.env`. `Restart=always`. |
| `romulus-ngrok.service` | simple | Public ngrok tunnel for port 8010, using `ngrok.yml`. Ordered after / wants `romulus-backend.service`. `Restart=always`. |

Note: the units reference legacy paths (`/home/debian/projects/romulus`) and
reuse the `orbit-chat` project's venv for uvicorn.

## Libraries / dependencies

### Python (`romulus-project/requirements.txt`)
- fastapi `>=0.115,<1`
- uvicorn `>=0.34,<1`
- python-dotenv `>=1,<2`
- argon2-cffi `>=23,<26` (password hashing)
- python-multipart `>=0.0.9,<1` (uploads)
- google-api-python-client `>=2.150,<3`
- google-auth `>=2.35,<3`

### Node (`emulation2k-v3-snapshot/package.json` — FLASHBACK Cloud Functions, Node 18)
- firebase-admin `^12.0.0`
- firebase-functions `^5.0.0`
- nodemailer `^6.9.7`

## Other components

- `romulus-project/backend/main.py` — FastAPI application (single module).
- `romulus-project/frontend/` — static frontend (`index.html`, `app.js`, `style.css`).
- `romulus-project/data/` — SQLite DB (`romulus.sqlite3`) + `uploads/`.
- `romulus-project/.env` / `.env.example` — runtime configuration.
- `romulus-project/ngrok.yml`, `ngrok.yml` — ngrok tunnel config.
- `cuban-zip-extracted/` — extracted static emulator PWA (`index.html`, `app.js`, `game.js`, `sw.js`, `style.css`, `DEBUG_REPORT.md`).
- `emulation2k-v3-snapshot/` — archived Firebase Cloud Functions code.
- `ROMulus.txt` — project notes.
