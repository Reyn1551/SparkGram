"""
Unit & Integration Tests for:
- Playwright Visual Web Preview (PlaywrightPreviewService)
- Local Port & Process Management (PortManagerService)
"""
import io
import time
import socket
import pytest
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

from sparkgram.engine.playwright_preview import playwright_preview, PlaywrightPreviewService, VIEWPORT_PRESETS
from sparkgram.engine.port_manager import port_manager, PortManagerService


# -------------------------------------------------------------
# 1. Tests for PlaywrightPreviewService
# -------------------------------------------------------------
def test_playwright_url_sanitization():
    # Number port string
    ok, url, _ = PlaywrightPreviewService.sanitize_and_validate_url("3000")
    assert ok is True
    assert url == "http://localhost:3000"

    # Standard localhost
    ok, url, _ = PlaywrightPreviewService.sanitize_and_validate_url("localhost:5173")
    assert ok is True
    assert url == "http://localhost:5173"

    # External public URL
    ok, url, _ = PlaywrightPreviewService.sanitize_and_validate_url("https://github.com")
    assert ok is True
    assert url == "https://github.com"

    # SSRF Attack: Cloud metadata service -> MUST BE BLOCKED
    ok, _, err = PlaywrightPreviewService.sanitize_and_validate_url("http://169.254.169.254/latest/meta-data/")
    assert ok is False
    assert "Akses ditolak" in err

    # Dangerous scheme
    ok, _, err = PlaywrightPreviewService.sanitize_and_validate_url("file:///etc/passwd")
    assert ok is False


@pytest.mark.asyncio
async def test_playwright_capture_local_server():
    # Start a tiny mock local HTTP server
    class SilentHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!DOCTYPE html><html><body><h1>SparkGram Live Preview Test</h1></body></html>")

    # Find a free port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    free_port = sock.getsockname()[1]
    sock.close()

    server = HTTPServer(('127.0.0.1', free_port), SilentHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # Test desktop capture
        ok, img_bytes, meta = await playwright_preview.capture_url(
            url_or_port=str(free_port),
            viewport_type="desktop",
            timeout_ms=5000,
        )
        assert ok is True
        assert img_bytes is not None
        assert len(img_bytes) > 500
        assert meta["status"] == 200
        assert meta["viewport"] == "desktop"
        assert meta["render_time_ms"] > 0

        # Test mobile viewport capture
        ok_mob, img_mob, meta_mob = await playwright_preview.capture_url(
            url_or_port=str(free_port),
            viewport_type="mobile",
            timeout_ms=5000,
        )
        assert ok_mob is True
        assert img_mob is not None
        assert meta_mob["viewport"] == "mobile"
    finally:
        server.shutdown()
        server.server_close()


# -------------------------------------------------------------
# 2. Tests for PortManagerService
# -------------------------------------------------------------
def test_port_manager_get_listening_ports():
    ports = port_manager.get_listening_ports()
    assert isinstance(ports, list)
    if ports:
        first = ports[0]
        assert "port" in first
        assert "ip" in first
        assert "pid" in first
        assert "process_name" in first
        assert "is_web" in first


def test_port_manager_build_ui():
    text, kb = port_manager.build_ports_ui()
    assert "Ports" in text or "Local Port" in text
    assert len(kb.inline_keyboard) > 0


def test_port_manager_kill_non_existent_port():
    # Attempt to kill port 65530 (almost certainly not listening)
    ok, msg, info = port_manager.kill_port(65530)
    assert ok is False or "tidak ada" in msg.lower() or "tidak aktif" in msg.lower()
