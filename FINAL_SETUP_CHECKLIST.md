# Final Setup Checklist

## Current Project Scope (Final)

- Public user registration with face capture and email
- Admin approval/rejection workflow
- Gate live verification via WebSocket
- Recognition backend switch (`legacy`, `ml`, `hybrid`, `lbph`)
- SMTP email notification on approval/rejection

---

## Quick URLs

- Main Portal: http://127.0.0.1:8000
- User Portal: http://127.0.0.1:8000/web/user.html
- Admin Portal: http://127.0.0.1:8000/web/admin.html
- Gate Live: http://127.0.0.1:8000/web/gate-live.html

---

## Default Admin Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |

---

## Pre-Run Setup

### 1) Configure SMTP (required for decision emails)

PowerShell (Gmail example):

```powershell
$env:SMTP_HOST = "smtp.gmail.com"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "tak68701@gmail.com"
$env:SMTP_PASSWORD = "<YOUR_APP_PASSWORD>"
$env:SMTP_FROM_EMAIL = "tak68701@gmail.com"
$env:SMTP_USE_TLS = "true"
```

### 2) (Optional) Select recognition backend

```powershell
$env:EMBEDDING_BACKEND = "lbph"   # or: hybrid / ml / legacy
```

### 3) Start server

```powershell
cd "g:\Premium face recognition entry"
& ".venv/Scripts/python.exe" app_server.py
```

### 4) Verify health

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health"
```

Expected:

```json
{"status":"ok","service":"vip-face-access-api"}
```

---

## End-to-End Functional Check

1. Open User Portal and register with:
   - Full Name
   - Email
   - Captured face
2. Open Admin Portal and login.
3. Select the user and set decision to `approved` or `rejected`.
4. Confirm:
   - Status updated in admin UI
   - Email is attempted immediately
   - Audit event appears in Events panel
5. Open Gate Live page and verify ALLOW/DENY behavior.

---

## What To Verify Before Evaluation

- [ ] Health API responds
- [ ] Registration accepts name + email + face
- [ ] Admin list shows user email
- [ ] Admin can edit email/name/status/note
- [ ] Approval/rejection triggers decision email
- [ ] Gate live updates confidence + decision
- [ ] Selected backend (`EMBEDDING_BACKEND`) behaves as expected

---

## Troubleshooting

### Email not sent

- Check SMTP env vars are set in the same terminal running server.
- For Gmail, ensure 2-Step Verification and App Password are correct.
- Check Events panel for `APPLICATION_EMAIL_NOTIFICATION` messages.

### Server won’t start on 8000

```powershell
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if($conns){
  $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
  foreach($pid in $pids){ Stop-Process -Id $pid -Force }
}
```

Then start again with `app_server.py`.

### Gate live not matching well

- Improve front lighting
- Keep face centered and steady
- Re-register users if backend mode changed significantly

---

## Key Files

- `app_server.py` - API routes + decision/email triggers + gate endpoints
- `src/database.py` - members table + email persistence
- `src/face_service.py` - recognition pipeline (legacy/ml/hybrid/lbph)
- `src/email_service.py` - SMTP sender
- `web/user.html` - registration (name + email + face)
- `web/admin.html` - admin review/update/dashboard
- `web/gate-live.html` - live gate verification UI

---

## Repository

GitHub: https://github.com/vrath1708-lab/Face-Recognition-Entry
