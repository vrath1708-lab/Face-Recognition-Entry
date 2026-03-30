# Premium Airport Lounge Face Recognition Entry

Credential-based VIP application approval system with real-time face recognition gate access. Users self-register with face capture, admins review applications, and approved VIPs gain gate access.

## Core Features

- **User Self-Registration**: Capture face via webcam, submit as VIP application (status: pending)
- **Admin Review Portal**: Review pending applications, approve/reject with notes
- **Real-Time Gate Verification**: Live WebSocket streaming, continuous face matching against approved VIPs only
- **Access Decision**: ALLOW only for approved VIP members with matching face
- **Credential-Based Hidden Admin**: Single login page detects role from credentials; admin portal hidden from home
- **Event Audit Trail**: All actions logged (registration, approvals, gate attempts, denials)

## Workflow

1. **User Registration**: User captures face → submit application (status: pending)
2. **Admin Review**: Admin views pending applications → approve or reject with optional note
3. **Gate Access**: User stands before camera → approved-only face embedding matches → ALLOW

## Quick Start

**Prerequisites:**
- Python 3.9+
- Virtual environment activated
- Dependencies installed: `pip install -r requirements.txt`

**Start Server:**
```powershell
cd "g:\Premium face recognition entry"
& ".venv/Scripts/python.exe" -m uvicorn app_server:app --host 0.0.0.0 --port 8000
```

**Access Portals:**
- **Home (with hidden admin routing)**: http://127.0.0.1:8000
- **User Portal** (after login): http://127.0.0.1:8000/web/user.html
- **Admin Portal** (after admin login): http://127.0.0.1:8000/web/admin.html
- **Gate Live Verification**: http://127.0.0.1:8000/web/gate-live.html

**From Other Devices on Same Wi-Fi:**
```powershell
ipconfig  # Find your laptop LAN IP (e.g., 192.168.x.x)
```
Then open: http://<LAPTOP_LAN_IP>:8000

## Default Credentials

- **Admin**: username `admin`, password `admin123`
- **User**: username `user`, password `user123`

## Key Features Explained

### Credential-Based Hidden Admin Portal

- Single login page at `/` detects role from credentials
- Admin credentials automatically route to `/web/admin.html`
- User credentials automatically route to `/web/user.html`
- Admin portal is **not visible** from home page—only accessible via admin login

### User Registration Flow

1. User logs in with credentials (auto-routes to user portal)
2. Click **"Capture Face"** to open camera
3. Take snapshot of face via live video feed
4. Submit application (status: **pending**)
5. Application appears in admin portal for review

### Admin Review Flow

1. Admin logs in with credentials (auto-routes to admin portal)
2. Review **Pending** applications tab
3. For each application: approve (status: **approved**) or reject (status: **rejected**)
4. Optional review note
5. All decisions logged in event audit trail

### Gate Live Verification

1. Open gate-live.html URL (public, no auth required)
2. Click **"Start Camera"** button
3. Stand before camera for continuous face matching
4. Real-time display shows:
   - ✅ Face detected or ❌ no face
   - Matching confidence (0-100%)
   - Member name (if matched)
   - **Decision**: ALLOW (approved VIP only) or DENY
5. WebSocket streams ~10 FPS for responsive feedback

## API Endpoints

### Authentication
- `POST /api/auth/login` — Login with username/password, auto-detect role (returns `role` + `token`)
- `POST /api/auth/me` — Verify current session (returns user info)
- `POST /api/auth/logout` — Invalidate token

### User Registration
- `POST /api/register` — Submit face image (creates pending application)

### Admin Review
- `GET /api/applications?status=pending|approved|rejected` — List applications by status
- `POST /api/applications/decision` — Approve/reject application with optional note
- `GET /api/events` — Audit log (all actions)

### Gate Verification
- `POST /api/gate/verify` — Single-frame face verification (HTTP)
- `WS /ws/gate-live` — Real-time frame streaming via WebSocket

### Health Check
- `GET /api/health` — Service status

## Demo Flow

1. **Start Server**: Server running at http://127.0.0.1:8000
2. **User Signup**: 
   - Navigate to home, login as `user`/`user123`
   - Capture face via camera
   - Submit application → **Pending** status
3. **Admin Review**:
   - Login as `admin`/`admin123` (redirects to hidden admin portal)
   - View **Pending** applications
   - Approve user (status: **Approved**)
   - Check **Approved** tab to verify
4. **Gate Access**:
   - Open gate-live.html
   - Start camera
   - Approved user's face matches → **ALLOW** ✅
   - Unknown/rejected user → **DENY** ❌
5. **Audit Trail**:
   - Admin portal shows all events (registrations, approvals, gate attempts)

## Folder Structure

```
Premium face recognition entry/
├── app_server.py              # FastAPI backend + WebSocket
├── requirements.txt           # Python dependencies
├── README.md                  # (This file)
├── ARCHITECTURE.md            # Technical architecture
├── src/
│   ├── config.py              # Configuration & thresholds
│   ├── database.py            # SQLite operations
│   └── face_service.py        # OpenCV face detection & matching
├── web/
│   ├── index.html             # Home: credential login (hidden admin routing)
│   ├── user.html              # User portal: registration + audit logs
│   ├── admin.html             # Admin portal: applications + decisions
│   └── gate-live.html         # Gate: real-time WebSocket streaming ⭐
├── data/
│   ├── members.db             # SQLite database (VIP applications)
│   └── events.log             # Audit trail (JSON lines format)
└── .venv/                     # Python virtual environment
```

## Technology Stack

- **Backend**: FastAPI (Python) + Uvicorn ASGI server
- **Frontend**: HTML5 + CSS3 (modern gradient design) + Vanilla JavaScript
- **Face Recognition**: OpenCV Haar Cascade + backend-selectable matching (legacy/ml/hybrid/lbph)
- **Database**: SQLite with application_status model
- **Real-Time**: WebSocket for ~10 FPS streaming
- **Security**: Bearer token sessions, credential-based role detection

## ML Face Identification (Optional Upgrade)

You can enable a safer ML-enhanced embedding backend without breaking existing data.

### Backends
- `legacy` (default): existing grayscale embedding (fastest)
- `ml`: ML-enhanced embedding (LBP + HOG features)
- `hybrid`: combines legacy + ML-enhanced embeddings
- `lbph`: LBPH recognizer using approved face images (`opencv-contrib-python`)

### Enable ML backend (PowerShell)
```powershell
$env:EMBEDDING_BACKEND = "ml"   # or "hybrid" or "legacy"
cd "g:\Premium face recognition entry"
& ".venv/Scripts/python.exe" app_server.py
```

Use `lbph` to enable LBPH mode:
```powershell
$env:EMBEDDING_BACKEND = "lbph"
cd "g:\Premium face recognition entry"
& ".venv/Scripts/python.exe" app_server.py
```

### Existing data compatibility
- Existing registered users remain usable.
- Mixed embedding sizes are handled safely during matching (dimension-alignment fallback).
- For best long-term accuracy consistency, re-register users after switching embedding backends.

## Email Notifications (SMTP)

Application decision emails (Approved/Rejected) are sent via SMTP when admin sets a final decision.

### Recommended generic SMTP variables
```powershell
$env:SMTP_HOST = "smtp.gmail.com"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "your_email@gmail.com"
$env:SMTP_PASSWORD = "<YOUR_APP_PASSWORD>"
$env:SMTP_FROM_EMAIL = "your_email@gmail.com"
$env:SMTP_USE_TLS = "true"
```

Use an app password for Gmail (regular account password will not work).

### Required environment variables (PowerShell)
```powershell
$env:RESEND_SMTP_HOST = "smtp.resend.com"
$env:RESEND_SMTP_PORT = "587"
$env:RESEND_SMTP_USERNAME = "resend"
$env:RESEND_SMTP_PASSWORD = "<YOUR_RESEND_API_KEY>"
$env:RESEND_FROM_EMAIL = "onboarding@resend.dev"   # or your verified sender
```

### Notes
- User registration now includes `email` and stores it with the application.
- Admin dashboard shows and allows updating user email.
- If SMTP is not configured, approval/rejection still works and logs email notification failure in events.

## Customization

### Change Default Credentials
Edit `app_server.py`, update `AUTH_USERS` dictionary:
```python
AUTH_USERS = {
    'admin': {'password': 'your_secure_password'},
    'user': {'password': 'your_secure_password'}
}
```

### Adjust Face Matching Threshold
Edit `src/config.py`:
```python
SIMILARITY_THRESHOLD_HYBRID = 0.72
MATCH_MARGIN_THRESHOLD = 0.08
SINGLE_CANDIDATE_EXTRA_THRESHOLD = 0.08
ORB_GOOD_MATCH_THRESHOLD = 8
ORB_EVIDENCE_RATIO_THRESHOLD = 0.08
```

- `SIMILARITY_THRESHOLD_HYBRID`: minimum score for the default hybrid backend.
- `MATCH_MARGIN_THRESHOLD`: minimum lead over the next best candidate before a match is trusted.
- `SINGLE_CANDIDATE_EXTRA_THRESHOLD`: extra strictness when only one approved user exists.
- `ORB_GOOD_MATCH_THRESHOLD`: minimum ORB local-feature matches required before gate can return ALLOW.
- `ORB_EVIDENCE_RATIO_THRESHOLD`: minimum normalized ORB evidence ratio required before gate can return ALLOW.

### Adjust Frame Rate
Edit `web/gate-live.html`, look for `setInterval(...)`:
```javascript
setInterval(..., 100);  // 100ms = 10 FPS (decrease for higher FPS)
```

## Troubleshooting

**Q: Server won't start on port 8000**
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Stop-Process -Force
```

**Q: Face not matching at gate despite approval**
- Ensure lighting is good (front-facing, no shadows)
- Verify member is in **Approved** status (check admin portal)
- Confidence might be low if angle differs significantly from registration
- If you changed matching thresholds, re-test with the approved user under the same camera and lighting used at enrollment

**Q: WebSocket connection fails**
- Ensure gate-live.html is opened after server is running
- Check browser console (F12) for errors
- Verify port 8000 is accessible from device

---

For detailed technical architecture, see [ARCHITECTURE.md](ARCHITECTURE.md).
