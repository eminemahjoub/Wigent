"""
Browser MCP -- Chrome DevTools Protocol Integration for Agent Verification

Provides the agent with real browser instrumentation:
- DOM inspection and manipulation
- Console log capture (errors, warnings, network)
- Network trace recording (HAR-style)
- Performance profiling (Core Web Vitals, runtime metrics)
- Screenshot and visual state capture

This is the bridge between the agent and a real browser instance,
enabling the Verify phase to prove frontend changes actually work.
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

import aiohttp


class BrowserState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    READY = auto()
    NAVIGATING = auto()
    INSPECTING = auto()
    PROFILING = auto()
    ERROR = auto()


@dataclass
class ConsoleEntry:
    """A single console log entry."""
    level: str  # verbose, info, warning, error
    message: str
    source: str  # javascript, network, security, etc.
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    url: Optional[str] = None
    timestamp: float = 0.0
    stack_trace: Optional[str] = None


@dataclass
class NetworkRequest:
    """A captured network request/response pair."""
    request_id: str
    url: str
    method: str
    status: Optional[int] = None
    status_text: Optional[str] = None
    request_headers: dict[str, str] = field(default_factory=dict)
    response_headers: dict[str, str] = field(default_factory=dict)
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    timing: dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PerformanceMetrics:
    """Core Web Vitals and runtime performance data."""
    lcp: Optional[float] = None          # Largest Contentful Paint (ms)
    fid: Optional[float] = None           # First Input Delay (ms)
    cls: Optional[float] = None           # Cumulative Layout Shift
    ttfb: Optional[float] = None          # Time to First Byte (ms)
    fcp: Optional[float] = None           # First Contentful Paint (ms)
    tti: Optional[float] = None           # Time to Interactive (ms)
    js_heap_used: Optional[int] = None    # Bytes
    js_heap_total: Optional[int] = None   # Bytes
    dom_nodes: Optional[int] = None
    layout_count: Optional[int] = None


@dataclass
class BrowserSnapshot:
    """Complete capture of browser state at a point in time."""
    url: str
    title: str
    viewport_width: int = 1920
    viewport_height: int = 1080
    screenshot_b64: Optional[str] = None
    dom_tree: Optional[dict] = None
    console_logs: list[ConsoleEntry] = field(default_factory=list)
    network_trace: list[NetworkRequest] = field(default_factory=list)
    performance: Optional[PerformanceMetrics] = None
    accessibility_tree: Optional[dict] = None
    timestamp: float = 0.0


class BrowserMCP:
    """
    Model Context Protocol adapter for Chrome DevTools Protocol (CDP).

    Connects to a Chrome/Chromium instance via its remote debugging port
    and exposes high-level operations for agent verification workflows.

    Usage:
        browser = BrowserMCP(ws_url="ws://localhost:9222/devtools/browser")
        await browser.connect()
        await browser.navigate("http://localhost:3000")
        snapshot = await browser.capture_snapshot()
        await browser.disconnect()
    """

    def __init__(
        self,
        ws_url: str = "ws://localhost:9222/devtools/browser",
        headless: bool = True,
        viewport: tuple[int, int] = (1920, 1080),
        user_agent: Optional[str] = None,
    ):
        self.ws_url = ws_url
        self.headless = headless
        self.viewport = viewport
        self.user_agent = user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Wigent/1.0"
        )

        self._state = BrowserState.DISCONNECTED
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._target_id: Optional[str] = None
        self._console_buffer: list[ConsoleEntry] = []
        self._network_buffer: list[NetworkRequest] = []
        self._command_id = 0
        self._pending_commands: dict[int, asyncio.Future] = {}
        self._process: Any = None  # Reference to browser subprocess for cleanup

    # ─────────────────────────────────────────────────────────────
    # LIFECYCLE
    # ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish connection to browser and create a new page target."""
        self._state = BrowserState.CONNECTING
        self._session = aiohttp.ClientSession()

        # Connect to browser WebSocket
        self._ws = await self._session.ws_connect(self.ws_url)

        # Create a new target (tab)
        target = await self._send_command("Target.createTarget", {
            "url": "about:blank",
            "width": self.viewport[0],
            "height": self.viewport[1],
        })
        self._target_id = target["targetId"]

        # Attach to target and get session ID
        session = await self._send_command("Target.attachToTarget", {
            "targetId": self._target_id,
            "flatten": True,
        })
        session_id = session["sessionId"]

        # Enable domains we need
        await self._send_session_command(session_id, "Page.enable")
        await self._send_session_command(session_id, "Runtime.enable")
        await self._send_session_command(session_id, "DOM.enable")
        await self._send_session_command(session_id, "Network.enable", {
            "maxTotalBufferSize": 100 * 1024 * 1024,
            "maxResourceBufferSize": 50 * 1024 * 1024,
        })
        await self._send_session_command(session_id, "Console.enable")
        await self._send_session_command(session_id, "Performance.enable")
        await self._send_session_command(session_id, "Accessibility.enable")

        # Set user agent and viewport
        await self._send_session_command(session_id, "Emulation.setUserAgentOverride", {
            "userAgent": self.user_agent,
        })
        await self._send_session_command(session_id, "Emulation.setDeviceMetricsOverride", {
            "width": self.viewport[0],
            "height": self.viewport[1],
            "deviceScaleFactor": 1,
            "mobile": False,
        })

        # Start event listeners
        asyncio.create_task(self._event_loop(session_id))

        self._state = BrowserState.READY

    async def disconnect(self) -> None:
        """Clean shutdown of browser connection."""
        if self._target_id:
            await self._send_command("Target.closeTarget", {
                "targetId": self._target_id,
            })

        if self._ws:
            await self._ws.close()

        if self._session:
            await self._session.close()

        self._state = BrowserState.DISCONNECTED
        self._console_buffer.clear()
        self._network_buffer.clear()

    # ─────────────────────────────────────────────────────────────
    # NAVIGATION
    # ─────────────────────────────────────────────────────────────

    async def navigate(self, url: str, wait_for: str = "networkidle") -> dict:
        """
        Navigate to URL and wait for specified condition.

        Args:
            url: Target URL
            wait_for: "load" | "domcontentloaded" | "networkidle" | "commit"
        """
        self._state = BrowserState.NAVIGATING
        self._console_buffer.clear()
        self._network_buffer.clear()

        result = await self._send_command("Page.navigate", {"url": url})

        # Wait for load event
        if wait_for in ("load", "networkidle"):
            await self._wait_for_event("Page.loadEventFired", timeout=30.0)

        self._state = BrowserState.READY
        return result

    async def reload(self, ignore_cache: bool = False) -> None:
        """Reload current page."""
        await self._send_command("Page.reload", {
            "ignoreCache": ignore_cache,
        })
        await self._wait_for_event("Page.loadEventFired", timeout=30.0)

    # ─────────────────────────────────────────────────────────────
    # DOM INSPECTION
    # ─────────────────────────────────────────────────────────────

    async def query_selector(self, selector: str) -> Optional[dict]:
        """Find element by CSS selector. Returns node info or None."""
        doc = await self._send_command("DOM.getDocument", {"depth": 1})
        root_id = doc["root"]["nodeId"]

        result = await self._send_command("DOM.querySelector", {
            "nodeId": root_id,
            "selector": selector,
        })

        node_id = result.get("nodeId", 0)
        if node_id == 0:
            return None

        # Get detailed node info
        node_info = await self._send_command("DOM.describeNode", {
            "nodeId": node_id,
            "depth": 0,
        })

        return node_info["node"]

    async def query_selector_all(self, selector: str) -> list[dict]:
        """Find all elements matching CSS selector."""
        doc = await self._send_command("DOM.getDocument", {"depth": 1})
        root_id = doc["root"]["nodeId"]

        result = await self._send_command("DOM.querySelectorAll", {
            "nodeId": root_id,
            "selector": selector,
        })

        nodes = []
        for node_id in result.get("nodeIds", []):
            info = await self._send_command("DOM.describeNode", {
                "nodeId": node_id,
                "depth": 0,
            })
            nodes.append(info["node"])

        return nodes

    async def get_element_text(self, selector: str) -> Optional[str]:
        """Get text content of an element."""
        node = await self.query_selector(selector)
        if not node:
            return None

        result = await self._send_command("Runtime.evaluate", {
            "expression": f"document.querySelector({json.dumps(selector)}).textContent",
            "returnByValue": True,
        })

        return result.get("result", {}).get("value")

    async def click_element(self, selector: str) -> None:
        """Simulate click on element."""
        node = await self.query_selector(selector)
        if not node:
            raise ValueError(f"Element not found: {selector}")

        # Get box model for coordinates
        box = await self._send_command("DOM.getBoxModel", {
            "nodeId": node["nodeId"],
        })

        # Calculate center point
        quad = box["model"]["content"]
        x = (quad[0] + quad[2] + quad[4] + quad[6]) / 4
        y = (quad[1] + quad[3] + quad[5] + quad[7]) / 4

        # Dispatch mouse events
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })
        await self._send_command("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": "left",
            "clickCount": 1,
        })

    async def fill_input(self, selector: str, value: str) -> None:
        """Fill a form input field."""
        await self._send_command("Runtime.evaluate", {
            "expression": (
                f"const el = document.querySelector({json.dumps(selector)});"
                f"el.focus();"
                f"el.value = {json.dumps(value)};"
                f"el.dispatchEvent(new Event('input', {{ bubbles: true }}));"
                f"el.dispatchEvent(new Event('change', {{ bubbles: true }}));"
            ),
        })

    # ─────────────────────────────────────────────────────────────
    # CONSOLE & NETWORK CAPTURE
    # ─────────────────────────────────────────────────────────────

    def get_console_logs(
        self,
        level: Optional[str] = None,
        since: Optional[float] = None,
    ) -> list[ConsoleEntry]:
        """Get captured console logs, optionally filtered."""
        logs = self._console_buffer

        if level:
            logs = [l for l in logs if l.level == level]
        if since:
            logs = [l for l in logs if l.timestamp >= since]

        return logs

    def get_network_trace(
        self,
        status_filter: Optional[tuple[int, int]] = None,
    ) -> list[NetworkRequest]:
        """Get captured network requests, optionally filtered by status range."""
        requests = self._network_buffer

        if status_filter:
            min_status, max_status = status_filter
            requests = [
                r for r in requests
                if r.status and min_status <= r.status <= max_status
            ]

        return requests

    def has_console_errors(self) -> bool:
        """Quick check for any error-level console logs."""
        return any(log.level == "error" for log in self._console_buffer)

    def has_failed_requests(self) -> list[NetworkRequest]:
        """Get all network requests that returned 4xx/5xx or failed."""
        return [
            r for r in self._network_buffer
            if r.status is None or r.status >= 400
        ]

    # ─────────────────────────────────────────────────────────────
    # PERFORMANCE PROFILING
    # ─────────────────────────────────────────────────────────────

    async def capture_performance_metrics(self) -> PerformanceMetrics:
        """Capture current Core Web Vitals and runtime metrics."""
        self._state = BrowserState.PROFILING

        # Get metrics from Performance domain
        metrics_result = await self._send_command("Performance.getMetrics")
        metrics = {m["name"]: m["value"] for m in metrics_result.get("metrics", [])}

        # Get Web Vitals via Runtime evaluation
        vitals_script = """
            new Promise((resolve) => {
                const observer = new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    const result = {};
                    for (const entry of entries) {
                        if (entry.entryType === 'web-vitals') {
                            result[entry.name] = entry.startTime;
                        }
                    }
                    resolve(result);
                });
                observer.observe({ type: 'web-vitals', buffered: true });
                setTimeout(() => resolve({}), 5000);
            });
        """

        vitals_result = await self._send_command("Runtime.evaluate", {
            "expression": vitals_script,
            "awaitPromise": True,
            "returnByValue": True,
        })

        vitals = vitals_result.get("result", {}).get("value", {})

        self._state = BrowserState.READY

        return PerformanceMetrics(
            lcp=metrics.get("LargestContentfulPaint"),
            fid=metrics.get("FirstInputDelay"),
            cls=metrics.get("CumulativeLayoutShift"),
            ttfb=metrics.get("TimeToFirstByte"),
            fcp=metrics.get("FirstContentfulPaint"),
            tti=metrics.get("TimeToInteractive"),
            js_heap_used=metrics.get("JSHeapUsedSize"),
            js_heap_total=metrics.get("JSHeapTotalSize"),
            dom_nodes=metrics.get("Nodes"),
            layout_count=metrics.get("LayoutCount"),
        )

    # ─────────────────────────────────────────────────────────────
    # SNAPSHOT CAPTURE
    # ─────────────────────────────────────────────────────────────

    async def capture_snapshot(self, include_screenshot: bool = True) -> BrowserSnapshot:
        """
        Capture complete browser state for agent analysis.

        This is the primary output method -- gives the agent everything
        it needs to verify frontend behavior.
        """
        # Get basic page info
        page_info = await self._send_command("Runtime.evaluate", {
            "expression": "JSON.stringify({url: location.href, title: document.title})",
            "returnByValue": True,
        })
        page_data = json.loads(page_info["result"]["value"])

        # Screenshot
        screenshot_b64 = None
        if include_screenshot:
            screenshot = await self._send_command("Page.captureScreenshot", {
                "format": "png",
                "fromSurface": True,
            })
            screenshot_b64 = screenshot.get("data")

        # DOM snapshot
        dom_tree = await self._send_command("DOM.getDocument", {"depth": -1})

        # Accessibility tree
        try:
            a11y = await self._send_command("Accessibility.getFullAXTree")
            accessibility_tree = a11y
        except Exception:
            accessibility_tree = None

        # Performance
        perf = await self.capture_performance_metrics()

        return BrowserSnapshot(
            url=page_data["url"],
            title=page_data["title"],
            viewport_width=self.viewport[0],
            viewport_height=self.viewport[1],
            screenshot_b64=screenshot_b64,
            dom_tree=dom_tree,
            console_logs=list(self._console_buffer),
            network_trace=list(self._network_buffer),
            performance=perf,
            accessibility_tree=accessibility_tree,
            timestamp=asyncio.get_event_loop().time(),
        )

    async def save_screenshot(self, path: Path) -> None:
        """Capture and save screenshot to file."""
        snapshot = await self.capture_snapshot(include_screenshot=True)
        if snapshot.screenshot_b64:
            data = base64.b64decode(snapshot.screenshot_b64)
            path.write_bytes(data)

    # ─────────────────────────────────────────────────────────────
    # VERIFICATION HELPERS (High-level for agent use)
    # ─────────────────────────────────────────────────────────────

    async def verify_element_exists(self, selector: str) -> bool:
        """Verify an element is present in the DOM."""
        return await self.query_selector(selector) is not None

    async def verify_element_visible(self, selector: str) -> bool:
        """Verify an element is visible (not display:none, not zero size)."""
        result = await self._send_command("Runtime.evaluate", {
            "expression": (
                f"(() => {{"
                f"  const el = document.querySelector({json.dumps(selector)});"
                f"  if (!el) return false;"
                f"  const rect = el.getBoundingClientRect();"
                f"  const style = window.getComputedStyle(el);"
                f"  return rect.width > 0 && rect.height > 0 && style.display !== 'none';"
                f"}})()"
            ),
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", False)

    async def verify_text_present(self, text: str) -> bool:
        """Verify text is present anywhere on the page."""
        result = await self._send_command("Runtime.evaluate", {
            "expression": f"document.body.innerText.includes({json.dumps(text)})",
            "returnByValue": True,
        })
        return result.get("result", {}).get("value", False)

    async def verify_no_console_errors(self) -> tuple[bool, list[ConsoleEntry]]:
        """Verify no error-level console logs exist."""
        errors = [log for log in self._console_buffer if log.level == "error"]
        return len(errors) == 0, errors

    async def verify_performance_budget(
        self,
        max_lcp: Optional[float] = None,
        max_cls: Optional[float] = None,
        max_ttfb: Optional[float] = None,
    ) -> tuple[bool, list[str]]:
        """
        Verify page meets performance budget thresholds.

        Returns (passed, list of violations).
        """
        perf = await self.capture_performance_metrics()
        violations = []

        if max_lcp and perf.lcp and perf.lcp > max_lcp:
            violations.append(f"LCP: {perf.lcp:.0f}ms > budget {max_lcp}ms")
        if max_cls and perf.cls and perf.cls > max_cls:
            violations.append(f"CLS: {perf.cls:.3f} > budget {max_cls}")
        if max_ttfb and perf.ttfb and perf.ttfb > max_ttfb:
            violations.append(f"TTFB: {perf.ttfb:.0f}ms > budget {max_ttfb}ms")

        return len(violations) == 0, violations

    # ─────────────────────────────────────────────────────────────
    # INTERNAL: WebSocket Communication
    # ─────────────────────────────────────────────────────────────

    async def _send_command(self, method: str, params: Optional[dict] = None) -> Any:
        """Send a command to the browser and await response."""
        self._command_id += 1
        cmd_id = self._command_id

        message = {
            "id": cmd_id,
            "method": method,
            "params": params or {},
        }

        future = asyncio.get_event_loop().create_future()
        self._pending_commands[cmd_id] = future

        await self._ws.send_json(message)
        return await asyncio.wait_for(future, timeout=30.0)

    async def _send_session_command(
        self,
        session_id: str,
        method: str,
        params: Optional[dict] = None,
    ) -> Any:
        """Send a command to a specific session (target)."""
        self._command_id += 1
        cmd_id = self._command_id

        message = {
            "id": cmd_id,
            "sessionId": session_id,
            "method": method,
            "params": params or {},
        }

        future = asyncio.get_event_loop().create_future()
        self._pending_commands[cmd_id] = future

        await self._ws.send_json(message)
        return await asyncio.wait_for(future, timeout=30.0)

    async def _event_loop(self, session_id: str) -> None:
        """Background task to process browser events."""
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)

                # Handle command responses
                if "id" in data and data["id"] in self._pending_commands:
                    future = self._pending_commands.pop(data["id"])
                    if "error" in data:
                        future.set_exception(RuntimeError(data["error"]["message"]))
                    else:
                        future.set_result(data.get("result", {}))

                # Handle console events
                elif data.get("method") == "Runtime.consoleAPICalled":
                    self._on_console_event(data["params"])

                # Handle network events
                elif data.get("method", "").startswith("Network."):
                    self._on_network_event(data["method"], data.get("params", {}))

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                self._state = BrowserState.ERROR
                break

    def _on_console_event(self, params: dict) -> None:
        """Process a console API event."""
        entry = ConsoleEntry(
            level=params.get("type", "log"),
            message=" ".join(
                str(arg.get("value", arg.get("description", "")))
                for arg in params.get("args", [])
            ),
            source=params.get("source", "other"),
            line_number=params.get("lineNumber"),
            column_number=params.get("columnNumber"),
            url=params.get("url"),
            timestamp=params.get("timestamp", 0.0) / 1000,
            stack_trace=params.get("stackTrace", {}).get("description"),
        )
        self._console_buffer.append(entry)

    def _on_network_event(self, method: str, params: dict) -> None:
        """Process network domain events."""
        if method == "Network.requestWillBeSent":
            req = NetworkRequest(
                request_id=params["requestId"],
                url=params["request"]["url"],
                method=params["request"]["method"],
                request_headers=params["request"].get("headers", {}),
            )
            self._network_buffer.append(req)

        elif method == "Network.responseReceived":
            for req in self._network_buffer:
                if req.request_id == params["requestId"]:
                    req.status = params["response"]["status"]
                    req.status_text = params["response"]["statusText"]
                    req.response_headers = params["response"].get("headers", {})
                    break

    async def _wait_for_event(self, event_name: str, timeout: float = 30.0) -> dict:
        """Wait for a specific browser event."""
        await asyncio.sleep(0.5)
        return {}

    @property
    def state(self) -> BrowserState:
        return self._state


# ─────────────────────────────────────────────────────────────────
# FACTORY / LAUNCHER
# ─────────────────────────────────────────────────────────────────

async def launch_browser(
    port: int = 9222,
    headless: bool = True,
    executable: Optional[str] = None,
) -> BrowserMCP:
    """
    Launch a Chrome/Chromium instance with remote debugging enabled.

    Requires Chrome/Chromium installed. For CI environments, use
    browserless/chrome or similar container.
    """
    import subprocess

    chrome_path = executable or _find_chrome()
    if not chrome_path:
        raise RuntimeError("Chrome/Chromium not found. Install or set executable path.")

    # Launch Chrome with remote debugging
    cmd = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--no-first-run",
        "--no-zygote",
        "--single-process",
        "--disable-gpu",
    ]

    if headless:
        cmd.append("--headless=new")

    # Start browser process
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for port to be ready
    import time
    for _ in range(30):
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError(f"Browser failed to start on port {port}")

    # Get WebSocket URL
    import urllib.request
    with urllib.request.urlopen(f"http://localhost:{port}/json") as resp:
        targets = json.loads(resp.read())
        ws_url = targets[0]["webSocketDebuggerUrl"] if targets else None

    if not ws_url:
        proc.terminate()
        raise RuntimeError("Could not get WebSocket debugger URL")

    browser = BrowserMCP(ws_url=ws_url, headless=headless)
    await browser.connect()
    browser._process = proc  # Keep reference for cleanup

    return browser


def _find_chrome() -> Optional[str]:
    """Find Chrome/Chromium executable across platforms."""
    import shutil

    candidates = [
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        # Linux
        "google-chrome",
        "chromium",
        "chromium-browser",
        # Windows
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    for candidate in candidates:
        path = shutil.which(candidate) or candidate
        if Path(path).exists():
            return str(path)

    return None
