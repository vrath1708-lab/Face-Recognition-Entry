import "dart:async";
import "dart:convert";
import "dart:io";

import "package:camera/camera.dart";
import "package:flutter/material.dart";
import "package:web_socket_channel/web_socket_channel.dart";

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final cameras = await availableCameras();
  runApp(GateMobileApp(cameras: cameras));
}

class GateMobileApp extends StatelessWidget {
  const GateMobileApp({super.key, required this.cameras});

  final List<CameraDescription> cameras;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Airport Gate Verification",
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2563EB)),
        useMaterial3: true,
      ),
      home: GateScreen(cameras: cameras),
    );
  }
}

class GateScreen extends StatefulWidget {
  const GateScreen({super.key, required this.cameras});

  final List<CameraDescription> cameras;

  @override
  State<GateScreen> createState() => _GateScreenState();
}

class _GateScreenState extends State<GateScreen> {
  static const Duration frameInterval = Duration(milliseconds: 320);
  static const Duration inFlightTimeout = Duration(milliseconds: 1300);
  static const Duration waitingLabelDelay = Duration(milliseconds: 700);

  CameraController? _cameraController;
  WebSocketChannel? _channel;
  Timer? _sendTimer;

  final TextEditingController _wsController =
      TextEditingController(text: "ws://192.168.29.111:8000/ws/gate-live");

  bool _isConnecting = false;
  bool _isStreaming = false;
  bool _isSocketConnected = false;
  bool _inFlight = false;
  DateTime _lastInFlightAt = DateTime.fromMillisecondsSinceEpoch(0);

  String _decision = "WAITING";
  String _name = "-";
  int _confidencePct = 0;
  int _orbGoodMatches = 0;
  int _orbRatioPct = 0;
  String _reason = "Tap Start to begin";

  @override
  void dispose() {
    _stopStreaming();
    _wsController.dispose();
    super.dispose();
  }

  CameraDescription? _selectCamera() {
    if (widget.cameras.isEmpty) return null;

    final back = widget.cameras.where((camera) => camera.lensDirection == CameraLensDirection.back);
    if (back.isNotEmpty) return back.first;

    final front = widget.cameras.where((camera) => camera.lensDirection == CameraLensDirection.front);
    if (front.isNotEmpty) return front.first;
    return widget.cameras.first;
  }

  Future<void> _ensureCameraReady() async {
    if (_cameraController != null && _cameraController!.value.isInitialized) {
      return;
    }

    final selected = _selectCamera();
    if (selected == null) {
      throw Exception("No camera found on this device.");
    }

    final controller = CameraController(
      selected,
      ResolutionPreset.low,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );

    await controller.initialize();
    if (!mounted) {
      await controller.dispose();
      return;
    }

    setState(() {
      _cameraController = controller;
    });
  }

  void _connectSocket() {
    final uri = Uri.parse(_wsController.text.trim());
    final channel = WebSocketChannel.connect(uri);
    _channel = channel;

    channel.stream.listen(
      _onSocketMessage,
      onError: (_) {
        if (!mounted) return;
        setState(() {
          _isSocketConnected = false;
          _reason = "WebSocket error. Check backend URL and network.";
        });
      },
      onDone: () {
        if (!mounted) return;
        setState(() {
          _isSocketConnected = false;
          _inFlight = false;
          if (_isStreaming) {
            _reason = "Connection closed. Tap Stop then Start.";
          }
        });
      },
      cancelOnError: true,
    );

    if (!mounted) return;
    setState(() {
      _isSocketConnected = true;
      _reason = "Connected. Streaming frames...";
    });
  }

  Future<void> _startStreaming() async {
    if (_isStreaming || _isConnecting) return;

    setState(() {
      _isConnecting = true;
      _reason = "Preparing camera...";
    });

    try {
      await _ensureCameraReady();
      _connectSocket();

      _sendTimer?.cancel();
      _sendTimer = Timer.periodic(frameInterval, (_) => _sendFrame());

      if (!mounted) return;
      setState(() {
        _isStreaming = true;
        _isConnecting = false;
        _decision = "WAITING";
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _isConnecting = false;
        _isStreaming = false;
        _reason = "Failed to start: $error";
      });
    }
  }

  void _stopStreaming() {
    _sendTimer?.cancel();
    _sendTimer = null;

    _channel?.sink.close();
    _channel = null;

    _cameraController?.dispose();
    _cameraController = null;

    if (!mounted) return;
    setState(() {
      _isStreaming = false;
      _isConnecting = false;
      _isSocketConnected = false;
      _inFlight = false;
      _decision = "WAITING";
      _name = "-";
      _confidencePct = 0;
      _orbGoodMatches = 0;
      _orbRatioPct = 0;
      _reason = "Stopped";
    });
  }

  Future<void> _sendFrame() async {
    final controller = _cameraController;
    final channel = _channel;

    if (!_isStreaming || !_isSocketConnected || controller == null || channel == null) {
      return;
    }

    if (!controller.value.isInitialized || controller.value.isTakingPicture) {
      return;
    }

    if (_inFlight) {
      final elapsed = DateTime.now().difference(_lastInFlightAt);
      if (elapsed < inFlightTimeout) return;

      if (!mounted) return;
      setState(() {
        _inFlight = false;
        _reason = "Recovered from delayed frame response.";
      });
    }

    try {
      final file = await controller.takePicture();
      final bytes = await File(file.path).readAsBytes();
      final base64Frame = base64Encode(bytes);
      channel.sink.add(base64Frame);

      if (!mounted) return;
      setState(() {
        _inFlight = true;
        _lastInFlightAt = DateTime.now();
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _reason = "Frame capture failed. Hold device steady.";
      });
    }
  }

  void _onSocketMessage(dynamic message) {
    if (!mounted) return;

    try {
      final payload = jsonDecode(message as String) as Map<String, dynamic>;
      _inFlight = false;

      if (payload["ok"] != true) {
        setState(() {
          _decision = "ERROR";
          _reason = payload["error"]?.toString() ?? "Unknown backend error";
        });
        return;
      }

      if (payload["face_detected"] != true) {
        setState(() {
          _decision = "NO FACE";
          _name = "-";
          _confidencePct = 0;
          _orbGoodMatches = 0;
          _orbRatioPct = 0;
          _reason = "No face detected";
        });
        return;
      }

      setState(() {
        _decision = (payload["decision"] ?? "WAITING").toString();
        _name = (payload["name"] ?? "Unknown").toString();
        _confidencePct = (payload["confidence_pct"] is int)
            ? payload["confidence_pct"] as int
            : ((payload["score"] as num?)?.toDouble() ?? 0.0 * 100).round();
        _orbGoodMatches = (payload["orb_good_matches"] as num?)?.toInt() ?? 0;
        final ratio = (payload["orb_evidence_ratio"] as num?)?.toDouble() ?? 0.0;
        _orbRatioPct = (ratio * 100).round();
        _reason = (payload["reason"] ?? "-").toString();
      });
    } catch (_) {
      setState(() {
        _reason = "Invalid response payload";
      });
    }
  }

  Color _decisionColor() {
    if (_decision == "ALLOW") return const Color(0xFF166534);
    if (_decision == "DENY") return const Color(0xFF991B1B);
    return const Color(0xFF334155);
  }

  String _frameStatusLabel() {
    if (!_isStreaming || !_isSocketConnected) {
      return "Idle";
    }

    if (_inFlight && DateTime.now().difference(_lastInFlightAt) >= waitingLabelDelay) {
      return "Waiting for backend";
    }

    return "Streaming";
  }

  @override
  Widget build(BuildContext context) {
    final controller = _cameraController;

    return Scaffold(
      backgroundColor: const Color(0xFF0B1220),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0B1220),
        title: const Text("Airport Gate Verification"),
        foregroundColor: Colors.white,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                height: 320,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: const Color(0xFF334155)),
                  color: Colors.black,
                ),
                child: (controller != null && controller.value.isInitialized)
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: CameraPreview(controller),
                      )
                    : const Center(
                        child: Text(
                          "Camera preview will appear here",
                          style: TextStyle(color: Colors.white70),
                        ),
                      ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _wsController,
                style: const TextStyle(color: Colors.white),
                decoration: InputDecoration(
                  labelText: "WebSocket URL",
                  labelStyle: const TextStyle(color: Colors.white70),
                  hintText: "ws://192.168.x.x:8000/ws/gate-live",
                  hintStyle: const TextStyle(color: Colors.white38),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: Color(0xFF475569)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(10),
                    borderSide: const BorderSide(color: Color(0xFF3B82F6)),
                  ),
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton(
                      onPressed: (_isStreaming || _isConnecting) ? null : _startStreaming,
                      child: Text(_isConnecting ? "Connecting..." : "Start"),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: _stopStreaming,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF475569),
                        foregroundColor: Colors.white,
                      ),
                      child: const Text("Stop"),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF111827),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFF334155)),
                ),
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: _decisionColor(),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: Text(
                        _decision,
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
                      ),
                    ),
                    const SizedBox(height: 8),
                    _kv("Name", _name),
                    _kv("Confidence", "$_confidencePct%"),
                    _kv("ORB", "$_orbGoodMatches matches ($_orbRatioPct%)"),
                    _kv("Socket", _isSocketConnected ? "Connected" : "Disconnected"),
                    _kv("Frame", _frameStatusLabel()),
                    const SizedBox(height: 6),
                    Text(
                      _reason,
                      style: const TextStyle(color: Color(0xFF93C5FD)),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _kv(String key, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: RichText(
        text: TextSpan(
          style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 14),
          children: [
            TextSpan(text: "$key: "),
            TextSpan(
              text: value,
              style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }
}
