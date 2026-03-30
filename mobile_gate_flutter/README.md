# Mobile Gate Verification (Flutter)

This Flutter app is for airport employees to run gate verification only.
It connects to your existing backend WebSocket endpoint:

- `ws://<SERVER_IP>:8000/ws/gate-live`

## Run

```powershell
cd "g:\Premium face recognition entry\mobile_gate_flutter"
flutter pub get
flutter run
```

## Use on phone

1. Connect phone and laptop to same Wi-Fi.
2. Ensure backend is running on laptop: `http://<LAPTOP_IP>:8000/api/health`.
3. Launch app on device.
4. Set WebSocket URL in app, for example:
   - `ws://192.168.1.25:8000/ws/gate-live`
5. Tap `Start`.

## Displayed results

- `ALLOW` / `DENY` / `NO FACE`
- Matched name
- Confidence percent
- ORB evidence (good matches + ratio)
- Decision reason from backend

## Notes

- This app is intentionally gate-only for employee workflow.
- For production rollout, add employee authentication and device policy controls.
