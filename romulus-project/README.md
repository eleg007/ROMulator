# ROMulus

ROMulus is a browser-based ROM and Shockwave Flash emulator platform built with FastAPI, SQLite, and a FLASHBACK-inspired frontend.

## Local development

1. Use the shared Python environment:

```bash
cd /home/debian/projects/romulus
/home/debian/projects/orbit-chat/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

2. Open http://127.0.0.1:8010

## Configuration

Copy `.env.example` to `.env` and edit as needed. The default admin account is:

- Username: `admin`
- Password: `ChangeMe123!` (or `ROMULUS_ADMIN_PASSWORD`)

Change the admin password immediately in production.

## Google Drive cloud library (optional)

Set these values in `.env` to enable Drive uploads:

```env
GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
GOOGLE_DRIVE_FOLDER_ID=your-drive-folder-id
```

If unset, ROMulus falls back to local file storage under `data/uploads`.

## ngrok

Free ngrok plans usually allow one active endpoint. If Orbit is already using your endpoint, stop that tunnel or use a different ngrok account/domain before exposing ROMulus publicly.

```bash
ngrok http 8010
```

## Notes

- NES ROMs are launched with EmulatorJS.
- SWF files are launched with Ruffle.
- Device binding uses a lightweight browser fingerprint.
- Admin messages are displayed exactly once in a locked 5-second modal.
