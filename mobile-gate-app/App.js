import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  SafeAreaView,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import { StatusBar } from "expo-status-bar";

const FRAME_INTERVAL_MS = 350;

function badgeStyle(decision) {
  if (decision === "ALLOW") return styles.allow;
  if (decision === "DENY") return styles.deny;
  return styles.pending;
}

export default function App() {
  const [permission, requestPermission] = useCameraPermissions();
  const [wsBaseUrl, setWsBaseUrl] = useState("ws://192.168.1.100:8000/ws/gate-live");
  const [connected, setConnected] = useState(false);
  const [running, setRunning] = useState(false);
  const [sending, setSending] = useState(false);
  const [decision, setDecision] = useState("WAITING");
  const [name, setName] = useState("-");
  const [confidence, setConfidence] = useState(0);
  const [orbText, setOrbText] = useState("0 matches (0%)");
  const [reason, setReason] = useState("No frame sent yet");

  const wsRef = useRef(null);
  const cameraRef = useRef(null);
  const inFlightRef = useRef(false);
  const timerRef = useRef(null);

  const canStart = useMemo(() => {
    return Boolean(permission?.granted && wsBaseUrl.trim().length > 0 && !running);
  }, [permission?.granted, wsBaseUrl, running]);

  const clearLoop = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const scheduleNext = (ms = FRAME_INTERVAL_MS) => {
    clearLoop();
    timerRef.current = setTimeout(() => {
      void sendFrame();
    }, ms);
  };

  const stopStreaming = () => {
    setRunning(false);
    setConnected(false);
    inFlightRef.current = false;
    clearLoop();

    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    setDecision("WAITING");
    setReason("Stopped");
  };

  const connectSocket = () => {
    const socket = new WebSocket(wsBaseUrl.trim());
    wsRef.current = socket;

    socket.onopen = () => {
      setConnected(true);
      setReason("Connected. Streaming frames...");
      scheduleNext(0);
    };

    socket.onmessage = (event) => {
      inFlightRef.current = false;
      setSending(false);
      try {
        const payload = JSON.parse(event.data);
        if (!payload.ok) {
          setDecision("WAITING");
          setReason(payload.error || "Unknown server error");
          scheduleNext();
          return;
        }

        if (!payload.face_detected) {
          setDecision("NO FACE");
          setName("-");
          setConfidence(0);
          setOrbText("0 matches (0%)");
          setReason("Face not detected");
          scheduleNext();
          return;
        }

        setDecision(payload.decision || "WAITING");
        setName(payload.name || "Unknown");
        setConfidence(payload.confidence_pct || 0);
        const ratioPct = typeof payload.orb_evidence_ratio === "number" ? Math.round(payload.orb_evidence_ratio * 100) : 0;
        const goodMatches = Number.isFinite(payload.orb_good_matches) ? payload.orb_good_matches : 0;
        setOrbText(`${goodMatches} matches (${ratioPct}%)`);
        setReason(payload.reason || "-");
      } catch {
        setReason("Unable to parse server response");
      }
      scheduleNext();
    };

    socket.onerror = () => {
      setReason("WebSocket error. Check URL or backend availability.");
      setConnected(false);
    };

    socket.onclose = () => {
      setConnected(false);
      inFlightRef.current = false;
      setSending(false);
      if (running) {
        setReason("Socket closed. Tap Start again.");
      }
    };
  };

  const sendFrame = async () => {
    if (!running || !connected || !cameraRef.current || !wsRef.current) return;
    if (inFlightRef.current) {
      scheduleNext(70);
      return;
    }

    try {
      inFlightRef.current = true;
      setSending(true);
      const photo = await cameraRef.current.takePictureAsync({
        base64: true,
        quality: 0.35,
        skipProcessing: true,
      });

      if (!photo?.base64 || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        inFlightRef.current = false;
        setSending(false);
        scheduleNext();
        return;
      }

      wsRef.current.send(photo.base64);
    } catch {
      inFlightRef.current = false;
      setSending(false);
      setReason("Frame capture failed");
      scheduleNext();
    }
  };

  const startStreaming = async () => {
    if (!permission?.granted) {
      const next = await requestPermission();
      if (!next.granted) return;
    }

    setRunning(true);
    setDecision("WAITING");
    setReason("Connecting...");
    connectSocket();
  };

  useEffect(() => {
    return () => stopStreaming();
  }, []);

  if (!permission) {
    return (
      <SafeAreaView style={styles.centered}>
        <ActivityIndicator size="large" color="#2563eb" />
      </SafeAreaView>
    );
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.centered}>
        <Text style={styles.title}>Camera Permission Required</Text>
        <TouchableOpacity style={styles.button} onPress={requestPermission}>
          <Text style={styles.buttonText}>Grant Camera Access</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <Text style={styles.title}>Airport Gate Verification</Text>

      <View style={styles.cameraWrap}>
        <CameraView ref={cameraRef} style={styles.camera} facing="front" />
      </View>

      <TextInput
        style={styles.input}
        value={wsBaseUrl}
        onChangeText={setWsBaseUrl}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder="ws://<server-ip>:8000/ws/gate-live"
      />

      <View style={styles.row}>
        <TouchableOpacity style={[styles.button, !canStart && styles.disabled]} onPress={startStreaming} disabled={!canStart}>
          <Text style={styles.buttonText}>Start</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.button, styles.stop]} onPress={stopStreaming}>
          <Text style={styles.buttonText}>Stop</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card}>
        <Text style={[styles.badge, badgeStyle(decision)]}>{decision}</Text>
        <Text style={styles.label}>Name: <Text style={styles.value}>{name}</Text></Text>
        <Text style={styles.label}>Confidence: <Text style={styles.value}>{confidence}%</Text></Text>
        <Text style={styles.label}>ORB: <Text style={styles.value}>{orbText}</Text></Text>
        <Text style={styles.label}>Status: <Text style={styles.value}>{connected ? "Connected" : "Disconnected"}</Text></Text>
        <Text style={styles.label}>Frame: <Text style={styles.value}>{sending ? "Sending..." : "Idle"}</Text></Text>
        <Text style={styles.reason}>{reason}</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0b1220",
    padding: 14,
    gap: 10,
  },
  centered: {
    flex: 1,
    backgroundColor: "#0b1220",
    justifyContent: "center",
    alignItems: "center",
    padding: 20,
  },
  title: {
    color: "#f8fafc",
    fontSize: 22,
    fontWeight: "700",
  },
  cameraWrap: {
    borderRadius: 14,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#1e293b",
  },
  camera: {
    width: "100%",
    height: 330,
    backgroundColor: "#111827",
  },
  input: {
    backgroundColor: "#f8fafc",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderColor: "#cbd5e1",
    borderWidth: 1,
  },
  row: {
    flexDirection: "row",
    gap: 10,
  },
  button: {
    flex: 1,
    backgroundColor: "#2563eb",
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 12,
  },
  stop: {
    backgroundColor: "#475569",
  },
  disabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: "white",
    fontWeight: "700",
  },
  card: {
    borderRadius: 12,
    backgroundColor: "#111827",
    borderWidth: 1,
    borderColor: "#334155",
    padding: 12,
    gap: 6,
  },
  badge: {
    alignSelf: "flex-start",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
    color: "#fff",
    fontWeight: "700",
  },
  allow: {
    backgroundColor: "#15803d",
  },
  deny: {
    backgroundColor: "#b91c1c",
  },
  pending: {
    backgroundColor: "#334155",
  },
  label: {
    color: "#cbd5e1",
    fontSize: 14,
  },
  value: {
    color: "#f8fafc",
    fontWeight: "600",
  },
  reason: {
    marginTop: 4,
    color: "#93c5fd",
    fontSize: 13,
  },
});
