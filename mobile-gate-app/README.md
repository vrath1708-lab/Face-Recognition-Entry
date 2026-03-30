# Mobile Gate Verification App (Employees)

This mobile app is focused only on gate verification for airport staff.
It connects to your existing backend WebSocket endpoint:

- `ws://<SERVER_IP>:8000/ws/gate-live`

## 1. Install

```powershell
cd "g:\Premium face recognition entry\mobile-gate-app"
npm install
```

## 2. Start app

```powershell
npm start
```

Then scan the QR code using Expo Go on Android/iOS.

## 3. Set backend URL

Inside the app, set WebSocket URL to your backend host, for example:

- `ws://192.168.1.50:8000/ws/gate-live`

Both phone and backend machine must be on the same Wi-Fi.

## 4. Current features

- Live camera capture
- Frame streaming to `/ws/gate-live`
- Decision display (`ALLOW`, `DENY`, `NO FACE`)
- Confidence + ORB evidence display
- Start/Stop controls

## Notes

- This app is intentionally gate-only (employee use case).
- For production deployment, add staff login and MDM policy controls.
