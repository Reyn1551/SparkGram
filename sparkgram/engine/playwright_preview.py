"""
Playwright Visual Web Preview Engine for SparkGram.
Renders localhost web apps or staging URLs and captures high-DPI screenshots.
Features SSRF protection, console error triage, responsive viewport switching, and lazy auto-kill.
"""
import io
import time
import asyncio
import logging
from urllib.parse import urlparse
from typing import Optional, Tuple, Dict, Any, List

log = logging.getLogger(__name__)

VIEWPORT_PRESETS = {
    "desktop": {"width": 1440, "height": 900, "device_scale_factor": 2, "is_mobile": False, "name": "💻 Desktop (1440p)"},
    "mobile": {"width": 390, "height": 844, "device_scale_factor": 2, "is_mobile": True, "name": "📱 Mobile (390px)"},
    "tablet": {"width": 768, "height": 1024, "device_scale_factor": 2, "is_mobile": True, "name": "📱 Tablet (768px)"},
}

COMMON_DEV_PORTS = [3000, 5173, 8000, 8080, 8501, 4200, 5000, 8888, 80]


class PlaywrightPreviewService:
    """Manages lazy headless Chromium browser pool with SSRF defense and auto-idle shutdown."""

    def __init__(self, idle_timeout_sec: float = 120.0):
        self._playwright = None
        self._browser = None
        self._last_used: float = 0.0
        self._idle_timeout_sec: float = idle_timeout_sec
        self._idle_watcher_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._last_console_logs: Dict[str, List[str]] = {}

    async def _ensure_browser(self):
        """Lazily starts headless Chromium instance."""
        async with self._lock:
            self._last_used = time.monotonic()
            if self._browser is None or not self._browser.is_connected():
                try:
                    from playwright.async_api import async_playwright
                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                            "--disable-extensions",
                        ]
                    )
                    log.info("Playwright Chromium browser pool initialized successfully.")
                except Exception as e:
                    log.error(f"Failed to launch Playwright Chromium: {e}")
                    raise RuntimeError(f"Playwright Chromium browser tidak dapat dijalankan: {e}")

            if self._idle_watcher_task is None or self._idle_watcher_task.done():
                self._idle_watcher_task = asyncio.create_task(self._idle_auto_kill_loop())

    async def _idle_auto_kill_loop(self):
        """Terminates browser instance when inactive for >120s to conserve host RAM."""
        while True:
            await asyncio.sleep(30.0)
            async with self._lock:
                if self._browser and self._browser.is_connected():
                    idle_duration = time.monotonic() - self._last_used
                    if idle_duration >= self._idle_timeout_sec:
                        log.info(f"Playwright idle for {idle_duration:.1f}s — closing browser to free host RAM.")
                        try:
                            await self._browser.close()
                            if self._playwright:
                                await self._playwright.stop()
                        except Exception as e:
                            log.debug(f"Error stopping idle browser: {e}")
                        finally:
                            self._browser = None
                            self._playwright = None
                        break

    @staticmethod
    def detect_active_dev_port() -> Optional[int]:
        """Detects active listening local dev port using psutil."""
        try:
            import psutil
            connections = psutil.net_connections(kind="inet")
            listening_ports = set()
            for conn in connections:
                if conn.status == "LISTEN" and conn.laddr:
                    listening_ports.add(conn.laddr.port)

            for port in COMMON_DEV_PORTS:
                if port in listening_ports:
                    return port
            return None
        except Exception as e:
            log.debug(f"detect_active_dev_port error: {e}")
            return None

    @staticmethod
    def sanitize_and_validate_url(target: str) -> Tuple[bool, str, str]:
        """
        Validates target URL with strict SSRF defense.
        Allows loopback localhost/127.0.0.1 or standard URLs.
        Blocks AWS/GCP cloud metadata (169.254.x.x) and dangerous schemes.
        """
        raw = target.strip()
        if "://" in raw:
            scheme = raw.split("://", 1)[0].lower()
            if scheme not in ("http", "https"):
                return False, "", f"Skema URL tidak didukung ({scheme}). Gunakan http atau https."
        elif raw.isdigit():
            raw = f"http://localhost:{raw}"
        else:
            raw = f"http://{raw}"

        try:
            parsed = urlparse(raw)
        except Exception as e:
            return False, "", f"URL tidak valid: {e}"

        if parsed.scheme not in ("http", "https"):
            return False, "", f"Skema URL tidak didukung ({parsed.scheme}). Gunakan http atau https."

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False, "", "Hostname tidak ditemukan dalam URL."

        is_loopback = hostname in ("localhost", "127.0.0.1", "::1")
        if not is_loopback:
            # Block internal private ranges (cloud metadata service / private subnets)
            if hostname.startswith("169.254.") or hostname.startswith("10.") or hostname.startswith("192.168."):
                return False, "", "Akses ditolak: Alamat IP intranet/metadata tidak diizinkan."

        return True, raw, ""

    async def capture_url(
        self,
        url_or_port: str,
        viewport_type: str = "desktop",
        full_page: bool = False,
        timeout_ms: int = 8000,
    ) -> Tuple[bool, Optional[bytes], Dict[str, Any]]:
        """
        Captures high-DPI screenshot of the target URL or local dev port.
        Returns (success, image_bytes_or_none, metadata_dict).
        """
        # 1. SSRF & URL Validation
        ok, valid_url, err = self.sanitize_and_validate_url(url_or_port)
        if not ok:
            return False, None, {"error": err}

        # 2. Ensure browser is running
        try:
            await self._ensure_browser()
        except Exception as e:
            return False, None, {"error": str(e)}

        preset = VIEWPORT_PRESETS.get(viewport_type, VIEWPORT_PRESETS["desktop"])
        console_logs: List[str] = []
        start_time = time.monotonic()
        meta: Dict[str, Any] = {
            "url": valid_url,
            "viewport": viewport_type,
            "viewport_name": preset["name"],
            "status": 200,
            "console_logs": console_logs,
            "render_time_ms": 0,
        }

        context = None
        try:
            context = await self._browser.new_context(
                viewport={"width": preset["width"], "height": preset["height"]},
                device_scale_factor=preset["device_scale_factor"],
                is_mobile=preset["is_mobile"],
            )
            page = await context.new_page()

            # Listen for browser console output
            def on_console(msg):
                txt = f"[{msg.type.upper()}] {msg.text}"
                console_logs.append(txt)
                if len(console_logs) > 50:
                    console_logs.pop(0)

            page.on("console", on_console)

            # Navigate to target
            response = await page.goto(valid_url, wait_until="networkidle", timeout=timeout_ms)
            if response:
                meta["status"] = response.status
            
            # Short settling delay for CSS animations / hydration
            await page.wait_for_timeout(300)

            screenshot_bytes = await page.screenshot(
                type="jpeg",
                quality=85,
                full_page=full_page,
            )
            meta["render_time_ms"] = int((time.monotonic() - start_time) * 1000)
            self._last_console_logs[valid_url] = console_logs
            return True, screenshot_bytes, meta

        except Exception as primary_err:
            log.warning(f"Playwright networkidle failed ({primary_err}), falling back to domcontentloaded...")
            try:
                if context:
                    page = await context.new_page()
                    await page.goto(valid_url, wait_until="domcontentloaded", timeout=4000)
                    await page.wait_for_timeout(400)
                    screenshot_bytes = await page.screenshot(type="jpeg", quality=80)
                    meta["render_time_ms"] = int((time.monotonic() - start_time) * 1000)
                    self._last_console_logs[valid_url] = console_logs
                    return True, screenshot_bytes, meta
            except Exception as fallback_err:
                return False, None, {"error": f"Gagal memuat URL: {fallback_err}"}

        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

    def get_console_logs(self, url: str) -> List[str]:
        """Returns cached console logs for a URL."""
        return self._last_console_logs.get(url, [])


playwright_preview = PlaywrightPreviewService()
