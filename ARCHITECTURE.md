# VIP Application Approval & Gate Access System Architecture

## System Overview

```
┌────────────────────────────────────────────────────────────┐
│                      CLIENT LAYER                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐  │
│  │  Home Page  │    │ User Portal │    │ Admin Portal │  │
│  │             │    │             │    │              │  │
│  │ Credentials │    │ Register    │    │ Review Apps  │  │
│  │ Auth        │    │ Face        │    │ Approve/     │  │
│  │ Auto-Route  │    │ Capture     │    │ Reject       │  │
│  └─────────────┘    └─────────────┘    └──────────────┘  │
│         │                  │                  │           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │        Real-Time Gate Verification                 │  │
│  │  - WebSocket streaming (10 FPS)                    │  │
│  │  - Live face matching                              │  │
│  │  - Confidence scores                               │  │
│  └─────────────────────────────────────────────────────┘  │
│         │                  │                  │           │
│         └──────────────────┴──────────────────┘           │
│                      HTTP/HTTPS                            │
│                      WebSocket                             │
└────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────┐
│                   BACKEND API LAYER                         │
│                    FastAPI Server                           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │           Authentication & Routing                   │ │
│  │  POST /api/auth/login                               │ │
│  │    ├── Validate credentials against AUTH_USERS      │ │
│  │    ├── Auto-detect role (admin/user)                │ │
│  │    └── Return token + role → auto-route client     │ │
│  │  POST /api/auth/me                                  │ │
│  │    └── Verify & return session info                 │ │
│  │  POST /api/auth/logout                              │ │
│  │    └── Invalidate token                             │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │           User Registration Endpoint                 │ │
│  │  POST /api/register                                  │ │
│  │    ├── Extract face from image                       │ │
│  │    ├── Build embedding (64x64 → 4096D vector)       │ │
│  │    ├── Create application with status=pending        │ │
│  │    └── Log: REGISTRATION event                       │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │          Application Review Endpoints (Admin)         │ │
│  │  GET /api/applications?status=pending|approved|      │ │
│  │       rejected                                        │ │
│  │    └── List all applications filtered by status      │ │
│  │  POST /api/applications/decision                     │ │
│  │    ├── Validate admin token                          │ │
│  │    ├── Update application_status                     │ │
│  │    ├── Store review_note + reviewed_by + reviewed_at│ │
│  │    └── Log: DECISION event                           │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │        Gate Verification Endpoints                    │ │
│  │  POST /api/gate/verify                               │ │
│  │    ├── Single-frame face verification (HTTP)         │ │
│  │    ├── Extract face & build embedding                │ │
│  │    ├── Match against APPROVED VIP embeddings only    │ │
│  │    ├── Return ALLOW/DENY decision                    │ │
│  │    └── Log: GATE_ATTEMPT event                       │ │
│  │  WS /ws/gate-live                                    │ │
│  │    ├── Accept WebSocket connection                   │ │
│  │    ├── Receive base64 frames (~10 FPS)               │ │
│  │    ├── Process each frame:                           │ │
│  │    │  1. Decode image                                │ │
│  │    │  2. Detect face                                 │ │
│  │    │  3. Extract embedding                           │ │
│  │    │  4. Match against APPROVED VIPs                 │ │
│  │    │  5. Send result JSON                            │ │
│  │    └── Log: GATE_STREAM event                        │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │            Audit Log Endpoint                         │ │
│  │  GET /api/events                                      │ │
│  │    └── Return audit trail (admin only)               │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────┐
│                 PROCESSING LAYER                            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Face Service (face_service.py)                      │ │
│  │                                                       │ │
│  │  1. Face Detection                                   │ │
│  │     - OpenCV Haar Cascade (cascade_path)             │ │
│  │     - detectMultiScale() on grayscale image          │ │
│  │     - Returns largest face bounding box (x,y,w,h)    │ │
│  │                                                       │ │
│  │  2. Embedding Extraction                             │ │
│  │     - Crop face region from image                     │ │
│  │     - Convert to grayscale                            │ │
│  │     - Resize to 64x64 pixels                          │ │
│  │     - Normalize pixel values (0-1)                    │ │
│  │     - Flatten to 4096-dimensional vector             │ │
│  │                                                       │ │
│  │  3. Face Matching                                    │ │
│  │     - Compute cosine similarity vs stored embeddings  │ │
│  │     - Return top match + confidence score            │ │
│  │     - Threshold: 0.62 for positive match             │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Access Control Logic                                │ │
│  │                                                       │ │
│  │  Gate Decision = Face Match AND (Status==Approved)   │ │
│  │                                                       │ │
│  │  1. Extract face → get embedding                      │ │
│  │  2. Find best match in members table                  │ │
│  │  3. Check match member's application_status          │ │
│  │     - If status = 'approved' → ALLOW                 │ │
│  │     - If status = 'pending' → DENY                   │ │
│  │     - If status = 'rejected' → DENY                  │ │
│  │     - If no match → DENY                             │ │
│  │  4. Log decision                                      │ │
│  │  5. Return decision to client                         │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────┐
│                    DATA LAYER                               │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  SQLite Database (members.db)                        │ │
│  │                                                       │ │
│  │  Table: members                                      │ │
│  │  ├─ member_id (TEXT PRIMARY KEY)                     │ │
│  │  ├─ name (TEXT)                                      │ │
│  │  ├─ embedding (TEXT) - CSV of 4096 floats            │ │
│  │  ├─ face_image (BLOB) - Original image               │ │
│  │  ├─ application_status (TEXT)                        │ │
│  │  │  - 'pending': awaiting admin review               │ │
│  │  │  - 'approved': VIP approved, gates allow          │ │
│  │  │  - 'rejected': admin rejected                     │ │
│  │  ├─ review_note (TEXT) - Admin comment (optional)    │ │
│  │  ├─ reviewed_by (TEXT) - Admin username              │ │
│  │  ├─ reviewed_at (TEXT) - ISO datetime                │ │
│  │  ├─ created_at (TEXT) - ISO datetime                 │ │
│  │  └─ updated_at (TEXT) - ISO datetime                 │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │  Audit Log (events.log)                              │ │
│  │                                                       │ │
│  │  Format: JSON Lines (1 event per line)               │ │
│  │  {                                                    │ │
│  │    "timestamp": "2026-02-27T10:30:45.123456Z",       │ │
│  │    "event_type": "REGISTRATION|DECISION|GATE_ATTEMPT",│ │
│  │    "member_id": "...",                               │ │
│  │    "details": {...}                                  │ │
│  │  }                                                    │ │
│  │                                                       │ │
│  │  Examples:                                            │ │
│  │  - REGISTRATION: user submitted application          │ │
│  │  - DECISION: admin approved/rejected                 │ │
│  │  - GATE_ATTEMPT: gate access allowed/denied          │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagrams

### 1. User Registration Flow

```
User Portal (logged in as 'user')
        │
        ├─ Click "Capture Face"
        │
        ├─ Camera opens → video stream
        │
        ├─ Take snapshot
        │
        └─ Submit image to /api/register
                │
                ▼
        Backend:
        ├─ Receive image + username
        ├─ Extract face via OpenCV
        ├─ Build embedding (4096-dim)
        ├─ Create member record:
        │  ├─ member_id = username
        │  ├─ embedding = CSV string
        │  ├─ face_image = BLOB
        │  ├─ application_status = 'pending'
        │  └─ created_at = now
        ├─ Log: REGISTRATION event
        │
        └─ Return 200 OK
                │
                ▼
        User Portal displays: "Application submitted! Status: Pending"
        Admin Portal now shows this in "Pending" tab
```

### 2. Admin Review Flow

```
Admin Portal (logged in as 'admin')
        │
        ├─ View "Pending" applications tab
        │  └─ Lists all members with status='pending'
        │
        ├─ For each pending application:
        │  ├─ Show: member_id, name, face thumbnail
        │  ├─ Two buttons: [Approve] [Reject]
        │  └─ Optional: review_note input field
        │
        ├─ Click [Approve] button
        │
        └─ POST /api/applications/decision
                │
                ▼
        Backend:
        ├─ Validate admin token
        ├─ Update member record:
        │  ├─ application_status = 'approved'
        │  ├─ reviewed_by = 'admin'
        │  ├─ reviewed_at = now
        │  └─ review_note = optional text
        ├─ Log: DECISION event (approved)
        │
        └─ Return 200 OK
                │
                ▼
        Admin Portal:
        ├─ Move from Pending → Approved tab
        └─ Display confirmation: "Approved by admin at HH:MM"

        Gate now recognizes this member as ALLOW
```

### 3. Gate Live Verification Flow

```
Gate Device (gate-live.html, public)
        │
        ├─ Click "Start Camera"
        │
        ├─ Request camera permission
        │
        ├─ Establish WebSocket to /ws/gate-live
        │  └─ ws://server:8000/ws/gate-live
        │
        ├─ Continuous loop (every 100ms = 10 FPS):
        │
        │  Step 1: Capture frame from video element
        │  ├─ canvas.getContext('2d').drawImage(video, ...)
        │  └─ Get ImageData
        │
        │  Step 2: Convert to JPEG base64
        │  ├─ canvas.toBlob() → Blob
        │  └─ FileReader.readAsDataURL() → base64 string
        │
        │  Step 3: Send frame via WebSocket
        │  └─ ws.send(base64String)
        │
        │  Step 4: Receive result JSON
        │  ├─ Parse event.data
        │  └─ Extract: face_detected, matched_member_id, name, 
        │             score, confidence_pct, decision
        │
        │  Step 5: Update UI
        │  ├─ <div id="status">Face detected: ✅</div>
        │  ├─ <div id="confidence">85%</div>
        │  ├─ <div id="memberName">John Doe</div>
        │  └─ <div id="decision" class="allow">ALLOW ✅</div>
        │
        └─ Continue until camera stopped or disconnected
                │
                ▼
        Backend (WebSocket handler):
        ├─ Receive base64 frame
        ├─ Decode to image
        ├─ Extract face via Haar Cascade
        │
        ├─ If face found:
        │  ├─ Crop face region
        │  ├─ Build embedding
        │  ├─ Find best match in APPROVED members only
        │  │  ├─ Iterate through members.db WHERE application_status='approved'
        │  │  ├─ Compute cosine similarity vs each embedding
        │  │  └─ Keep top match if score > 0.62
        │  ├─ If match found:
        │  │  ├─ Decision = 'ALLOW'
        │  │  └─ Include member_id, name, score
        │  └─ Else:
        │     └─ Decision = 'DENY' (unknown person)
        │
        ├─ If face not found:
        │  └─ Decision = 'DENY', face_detected=false
        │
        ├─ Log: GATE_STREAM event
        │
        └─ Send JSON response:
                │
                ├─ {
                │    "face_detected": true,
                │    "matched_member_id": "john123",
                │    "name": "John Doe",
                │    "score": 0.87,
                │    "confidence_pct": 87,
                │    "decision": "ALLOW"
                │  }
                │
                └─ OR if denied:
                   {
                     "face_detected": true,
                     "matched_member_id": null,
                     "name": null,
                     "score": 0,
                     "confidence_pct": 0,
                     "decision": "DENY"
                   }
```

---

## Authentication & Session Management

```
Login (Credential-Based Auto-Detection)
├─ Client: POST /api/auth/login
│  └─ Body: {username: "admin", password: "admin123"}
│
└─ Server:
   ├─ Check AUTH_USERS dict:
   │  ├─ Look for username in dict keys
   │  └─ Verify password matches
   │
   ├─ If match found (e.g., 'admin' role):
   │  ├─ Generate token = secrets.token_urlsafe(32)
   │  ├─ Store in TOKENS dict: TOKENS[token] = {
   │  │    'username': 'admin',
   │  │    'role': 'admin',
   │  │    'expires_at': now + 480 minutes
   │  │  }
   │  └─ Return: {
   │       "token": "...",
   │       "role": "admin",  ← KEY: Client uses this to route
   │       "expires_in": 480
   │     }
   │
   ├─ Client receives response:
   │  ├─ If role='admin':
   │  │  ├─ localStorage.adminToken = token
   │  │  └─ window.location = '/web/admin.html'
   │  └─ Else if role='user':
   │     ├─ localStorage.userToken = token
   │     └─ window.location = '/web/user.html'
   │
   └─ Portal loads:
      ├─ On page load, check localStorage for token
      ├─ Call POST /api/auth/me with token in header
      │  └─ Authorization: Bearer {token}
      ├─ Server validates token + checks expiry
      ├─ If invalid: redirect to home page /
      └─ If valid: Load portal with full access
```

---

## Database Schema

### Members Table

```sql
CREATE TABLE members (
  member_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  embedding TEXT NOT NULL,  -- CSV: "0.1,0.2,0.3,..."
  face_image BLOB,          -- Original image bytes
  application_status TEXT DEFAULT 'pending',  -- pending|approved|rejected
  review_note TEXT,         -- Optional admin comment
  reviewed_by TEXT,         -- Admin username
  reviewed_at TEXT,         -- ISO 8601 datetime
  created_at TEXT NOT NULL, -- ISO 8601 datetime
  updated_at TEXT           -- ISO 8601 datetime
);
```

---

## Key Concepts

### Application Status States

| Status | Meaning | Gate Access |
|--------|---------|-------------|
| `pending` | Awaiting admin review | ❌ DENY |
| `approved` | Admin approved, VIP status | ✅ ALLOW (if face matches) |
| `rejected` | Admin rejected application | ❌ DENY |

### Face Matching Algorithm

```
For probe face (from gate):
  1. Extract face from image
  2. Build embedding (4096-dim vector)
  3. For each APPROVED member in database:
     - Load stored embedding
     - Compute cosine similarity: score = dot(probe, stored) / (||probe|| * ||stored||)
     - If score > 0.62: record match
  4. Return best match (highest score)
  5. If no match found or best < 0.62: return DENY
  6. If match found AND status='approved': return ALLOW
```

### Real-Time Performance

- **Face Detection**: 20-50ms (OpenCV Haar Cascade)
- **Embedding Extraction**: 10-20ms (simple resize + flatten)
- **Database Lookup**: <1ms per member (NumPy cosine similarity)
- **WebSocket Send/Receive**: 10-30ms (LAN latency)
- **Total E2E Latency**: ~100-150ms (very responsive)

---

## Security Features

1. **Token-Based Authentication**
   - Bearer tokens stored server-side in `TOKENS` dict
   - Expiry: 480 minutes by default
   - Used for both admin and user portals

2. **Role-Based Access Control**
   - Admin endpoints check `role='admin'` from token
   - User endpoints check `role='user'` from token
   - Unauthenticated requests return 401/403

3. **Credential-Based Auto-Routing**
   - No explicit role selector on login form
   - Role determined by credentials (admin/user in AUTH_USERS)
   - Admin portal hidden from home—only accessible via admin login

4. **Audit Logging**
   - Every action logged: registration, decision, gate attempt
   - JSON lines format in events.log
   - Includes timestamp, actor, action, outcome

5. **One-Way Hashing (Future)**
   - Current: passwords stored in plaintext in AUTH_USERS (dev only)
   - Production: Use bcrypt.hashpw() + bcrypt.checkpw()

---

## Deployment Considerations

### Development (Current)
- Single FastAPI server on port 8000
- In-memory token storage (lost on restart)
- SQLite database (single file)
- Suitable for: 1-10 concurrent gates, 100-1000 members

### Production (Recommended)
- **Multiple servers**: Load balancer (Nginx) + N FastAPI instances
- **Token storage**: Redis cluster (distributed sessions)
- **Database**: PostgreSQL with replication
- **HTTPS/WSS**: TLS certificates, secure WebSocket
- **Monitoring**: Prometheus metrics, ELK logging stack
- **Scaling**: Supports 100+ concurrent gates, 100K+ members

---

## File Organization

| File | Purpose |
|------|---------|
| `app_server.py` | FastAPI backend, all endpoints & WebSocket |
| `src/config.py` | Constants: THRESHOLD, CASCADE_PATH, etc. |
| `src/database.py` | SQLite CRUD operations |
| `src/face_service.py` | OpenCV face detection & matching |
| `web/index.html` | Home: credential login, hidden admin portal |
| `web/user.html` | User portal: registration, audit logs |
| `web/admin.html` | Admin portal: applications, decisions |
| `web/gate-live.html` | Gate: WebSocket real-time verification |
| `data/members.db` | SQLite database (persisted) |
| `data/events.log` | Audit trail (JSON lines) |

---

## Conclusion

This architecture provides a **clean, scalable** VIP application approval system with:

✅ Simple credential-based authentication with auto-role detection  
✅ Transparent application workflow (register → review → approve)  
✅ Real-time gate verification via WebSocket (10 FPS, ~150ms latency)  
✅ Comprehensive audit trail for compliance  
✅ Face recognition with OpenCV (fast, no ML frameworks needed)  
✅ SQLite for simplicity, PostgreSQL-ready for scale  

**Key Design Decisions:**
- Approved-only gate access (no pending/rejected members allowed)
- Single-frame AND multi-frame gate options (HTTP + WebSocket)
- In-memory tokens for speed (Redis-ready for scale)
- JSON logs for easy integration with ELK/Splunk

See [README.md](README.md) for quick start instructions.
