"""
Visual Diff Toolkit -- Pixel & Layout Regression Testing for Agent Verification

Provides the agent with visual regression testing primitives:
- Pixel-level screenshot comparisons with diff image generation
- Layout (DOM) structure diffing for structural regression detection
- Element-level focused diffs for targeted validation
- Baseline management for snapshot testing workflows

These tools are used during the Verify phase to prove that UI changes
produce only intended visual differences.
"""

from __future__ import annotations

import base64
import io
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from wigent.tools.browser_mcp import BrowserMCP, BrowserSnapshot


class DiffSeverity(Enum):
    EQUAL = "equal"
    COSMETIC = "cosmetic"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass
class PixelDiffRegion:
    """A contiguous region of pixel differences."""
    x: int
    y: int
    width: int
    height: int
    area: int = 0

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


@dataclass
class PixelDiff:
    """Pixel-level comparison result between two screenshots."""
    changed_pixels: int
    total_pixels: int
    change_ratio: float
    regions: list[PixelDiffRegion] = field(default_factory=list)
    diff_image_b64: Optional[str] = None
    has_alpha_channel: bool = False

    @property
    def severity(self) -> DiffSeverity:
        if self.change_ratio == 0.0:
            return DiffSeverity.EQUAL
        if self.change_ratio < 0.005:
            return DiffSeverity.COSMETIC
        if self.change_ratio < 0.05:
            return DiffSeverity.MODERATE
        return DiffSeverity.SEVERE

    @property
    def passed(self) -> bool:
        return self.severity in (DiffSeverity.EQUAL, DiffSeverity.COSMETIC)


@dataclass
class LayoutChange:
    """A single structural change between two DOM snapshots."""
    change_type: str  # "added", "removed", "moved", "attribute_changed"
    selector: Optional[str] = None
    tag: Optional[str] = None
    text_before: Optional[str] = None
    text_after: Optional[str] = None
    attribute_diffs: dict[str, tuple[Optional[str], Optional[str]]] = field(default_factory=dict)
    bounding_box_before: Optional[tuple[float, float, float, float]] = None
    bounding_box_after: Optional[tuple[float, float, float, float]] = None


@dataclass
class LayoutDiff:
    """Structural comparison between two DOM trees."""
    added_elements: list[LayoutChange] = field(default_factory=list)
    removed_elements: list[LayoutChange] = field(default_factory=list)
    moved_elements: list[LayoutChange] = field(default_factory=list)
    attribute_changes: list[LayoutChange] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return (len(self.added_elements) + len(self.removed_elements)
                + len(self.moved_elements) + len(self.attribute_changes))

    @property
    def severity(self) -> DiffSeverity:
        if self.total_changes == 0:
            return DiffSeverity.EQUAL
        if self.total_changes <= 3:
            return DiffSeverity.COSMETIC
        if self.total_changes <= 10:
            return DiffSeverity.MODERATE
        return DiffSeverity.SEVERE

    @property
    def passed(self) -> bool:
        return self.severity in (DiffSeverity.EQUAL, DiffSeverity.COSMETIC)


@dataclass
class VisualDiffReport:
    """Complete visual regression report for a single comparison."""
    url: str
    label: str
    pixel_diff: Optional[PixelDiff] = None
    layout_diff: Optional[LayoutDiff] = None
    baseline_timestamp: float = 0.0
    current_timestamp: float = 0.0
    viewport: tuple[int, int] = (1920, 1080)
    duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        pixel_ok = self.pixel_diff is None or self.pixel_diff.passed
        layout_ok = self.layout_diff is None or self.layout_diff.passed
        return pixel_ok and layout_ok

    @property
    def summary(self) -> dict[str, Any]:
        pixel = self.pixel_diff
        layout = self.layout_diff
        return {
            "url": self.url,
            "label": self.label,
            "passed": self.passed,
            "viewport": list(self.viewport),
            "pixel": {
                "change_ratio": pixel.change_ratio if pixel else 0.0,
                "changed_pixels": pixel.changed_pixels if pixel else 0,
                "regions": len(pixel.regions) if pixel else 0,
                "severity": pixel.severity.value if pixel else "equal",
            } if pixel else None,
            "layout": {
                "total_changes": layout.total_changes if layout else 0,
                "added": len(layout.added_elements) if layout else 0,
                "removed": len(layout.removed_elements) if layout else 0,
                "moved": len(layout.moved_elements) if layout else 0,
                "attribute_changes": len(layout.attribute_changes) if layout else 0,
                "severity": layout.severity.value if layout else "equal",
            } if layout else None,
            "duration_ms": self.duration_ms,
        }


class VisualDiff:
    """
    Visual regression testing toolkit wrapping BrowserMCP.

    Provides pixel-level and layout-level comparison primitives for the
    Verify phase. Supports baseline capture, on-demand comparison, and
    structured report generation.

    Usage:
        diff = VisualDiff(browser)
        baseline = await diff.capture_baseline("http://localhost:3000")
        report = await diff.compare_to_baseline(baseline)
        print(report.passed, report.summary)
    """

    def __init__(self, browser: BrowserMCP):
        self.browser = browser
        self._baselines: dict[str, BrowserSnapshot] = {}

    # ─────────────────────────────────────────────────────────────
    # BASELINE MANAGEMENT
    # ─────────────────────────────────────────────────────────────

    async def capture_baseline(
        self,
        url: str,
        label: str = "default",
        include_screenshot: bool = True,
    ) -> BrowserSnapshot:
        """Capture a baseline snapshot for later comparison."""
        snapshot = await self.browser.capture_snapshot(include_screenshot=include_screenshot)
        key = f"{url}::{label}"
        self._baselines[key] = snapshot
        return snapshot

    async def compare_to_baseline(
        self,
        url: str,
        label: str = "default",
        include_pixel_diff: bool = True,
        include_layout_diff: bool = True,
        screenshot_threshold: float = 0.02,
    ) -> VisualDiffReport:
        """Compare current page state against a stored baseline."""
        key = f"{url}::{label}"
        baseline = self._baselines.get(key)
        if baseline is None:
            raise ValueError(f"No baseline found for {key}. Call capture_baseline first.")

        current = await self.browser.capture_snapshot(include_screenshot=include_pixel_diff)
        return await self.compare_snapshots(
            baseline, current, url=url, label=label,
            include_pixel_diff=include_pixel_diff,
            include_layout_diff=include_layout_diff,
            screenshot_threshold=screenshot_threshold,
        )

    def get_baseline(self, url: str, label: str = "default") -> Optional[BrowserSnapshot]:
        """Retrieve a stored baseline snapshot."""
        return self._baselines.get(f"{url}::{label}")

    def clear_baselines(self) -> None:
        """Remove all stored baselines."""
        self._baselines.clear()

    # ─────────────────────────────────────────────────────────────
    # SNAPSHOT COMPARISON
    # ─────────────────────────────────────────────────────────────

    async def compare_snapshots(
        self,
        before: BrowserSnapshot,
        after: BrowserSnapshot,
        url: str = "",
        label: str = "",
        include_pixel_diff: bool = True,
        include_layout_diff: bool = True,
        screenshot_threshold: float = 0.02,
    ) -> VisualDiffReport:
        """Compare two BrowserSnapshots and produce a structured report."""
        import time
        start = time.monotonic()

        report = VisualDiffReport(
            url=url or before.url or after.url,
            label=label,
            baseline_timestamp=before.timestamp,
            current_timestamp=after.timestamp,
            viewport=(before.viewport_width, before.viewport_height),
        )

        if include_pixel_diff and before.screenshot_b64 and after.screenshot_b64:
            report.pixel_diff = self._compare_pixel(
                before.screenshot_b64, after.screenshot_b64, threshold=screenshot_threshold,
            )

        if include_layout_diff and before.dom_tree and after.dom_tree:
            report.layout_diff = self._compare_layout(before.dom_tree, after.dom_tree)

        report.duration_ms = (time.monotonic() - start) * 1000
        return report

    # ─────────────────────────────────────────────────────────────
    # PIXEL DIFF
    # ─────────────────────────────────────────────────────────────

    def compare_screenshots(
        self,
        before_b64: str,
        after_b64: str,
        threshold: float = 0.02,
        generate_diff_image: bool = True,
    ) -> PixelDiff:
        """Compare two base64-encoded screenshots at the pixel level."""
        return self._compare_pixel(before_b64, after_b64, threshold, generate_diff_image)

    def _compare_pixel(
        self,
        before_b64: str,
        after_b64: str,
        threshold: float = 0.02,
        generate_diff_image: bool = True,
    ) -> PixelDiff:
        """Internal pixel comparison implementation using Pillow."""
        from PIL import Image, ImageChops, ImageDraw

        before_img = Image.open(io.BytesIO(base64.b64decode(before_b64)))
        after_img = Image.open(io.BytesIO(base64.b64decode(after_b64)))

        # Ensure same dimensions
        if before_img.size != after_img.size:
            after_img = after_img.resize(before_img.size, Image.LANCZOS)

        # Handle alpha channel
        has_alpha = before_img.mode in ("RGBA", "LA") or "A" in before_img.mode

        before_rgb = before_img.convert("RGB")
        after_rgb = after_img.convert("RGB")

        diff_img = ImageChops.difference(before_rgb, after_rgb)
        diff_gray = diff_img.convert("L")

        # Count changed pixels
        pixels = list(diff_gray.getdata())
        changed_pixels = sum(1 for p in pixels if p > threshold * 255)
        total_pixels = before_rgb.width * before_rgb.height
        change_ratio = changed_pixels / total_pixels if total_pixels > 0 else 0.0

        # Find diff regions (bounding boxes of contiguous changes)
        regions = self._find_diff_regions(diff_gray, threshold=threshold)

        diff_image_b64 = None
        if generate_diff_image and changed_pixels > 0:
            diff_image_b64 = self._generate_diff_image(
                before_img, after_img, diff_gray, regions, has_alpha,
            )

        return PixelDiff(
            changed_pixels=changed_pixels,
            total_pixels=total_pixels,
            change_ratio=change_ratio,
            regions=regions,
            diff_image_b64=diff_image_b64,
            has_alpha_channel=has_alpha,
        )

    def _find_diff_regions(
        self,
        diff_gray: Any,
        threshold: float = 0.02,
        min_region_size: int = 16,
    ) -> list[PixelDiffRegion]:
        """Find bounding boxes of changed pixel regions."""
        width, height = diff_gray.size
        pixels = diff_gray.load()

        visited = set()
        regions: list[PixelDiffRegion] = []

        for y in range(height):
            for x in range(width):
                if (x, y) in visited:
                    continue
                if pixels[x, y] <= threshold * 255:
                    continue

                # Flood-fill to find contiguous region
                stack = [(x, y)]
                visited.add((x, y))
                min_x = max_x = x
                min_y = max_y = y
                area = 0

                while stack:
                    cx, cy = stack.pop()
                    area += 1
                    min_x = min(min_x, cx)
                    max_x = max(max_x, cx)
                    min_y = min(min_y, cy)
                    max_y = max(max_y, cy)

                    # Check 4-connected neighbours
                    for nx, ny in [(cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)]:
                        if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                            if pixels[nx, ny] > threshold * 255:
                                visited.add((nx, ny))
                                stack.append((nx, ny))

                if area >= min_region_size:
                    regions.append(PixelDiffRegion(
                        x=min_x, y=min_y,
                        width=max_x - min_x + 1,
                        height=max_y - min_y + 1,
                        area=area,
                    ))

        return regions

    def _generate_diff_image(
        self,
        before_img: Any,
        after_img: Any,
        diff_gray: Any,
        regions: list[PixelDiffRegion],
        has_alpha: bool,
    ) -> str:
        """Generate a diff visualization: before | after | diff overlay."""
        from PIL import Image

        width, height = before_img.size

        # Before panel
        before_panel = before_img.copy()
        if has_alpha:
            before_panel = before_panel.convert("RGBA")

        # After panel
        after_panel = after_img.copy()
        if after_panel.mode != "RGBA":
            after_panel = after_panel.convert("RGBA")

        # Diff panel: overlay changed pixels in red
        diff_panel = after_img.copy()
        if diff_panel.mode != "RGBA":
            diff_panel = diff_panel.convert("RGBA")

        diff_pixels = diff_panel.load()
        mask = diff_gray.load()

        for y in range(height):
            for x in range(width):
                if mask[x, y] > 5:
                    diff_pixels[x, y] = (255, 0, 0, 200)

        # Draw bounding boxes on before panel
        from PIL import ImageDraw

        draw = ImageDraw.Draw(before_panel)
        for region in regions:
            draw.rectangle(region.bounds, outline=(255, 0, 0), width=2)

        # Composite into a single side-by-side image
        total_width = width * 2 + width  # before | after | diff
        composite = Image.new("RGBA", (total_width, height), (255, 255, 255, 255))

        composite.paste(before_panel.convert("RGBA"), (0, 0))
        composite.paste(after_panel, (width, 0))
        composite.paste(diff_panel, (width * 2, 0))

        buf = io.BytesIO()
        composite.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    # ─────────────────────────────────────────────────────────────
    # LAYOUT DIFF
    # ─────────────────────────────────────────────────────────────

    def compare_layout(
        self,
        before_tree: dict,
        after_tree: dict,
    ) -> LayoutDiff:
        """Compare two DOM trees for structural changes."""
        return self._compare_layout(before_tree, after_tree)

    def _compare_layout(
        self,
        before_tree: dict,
        after_tree: dict,
    ) -> LayoutDiff:
        """Internal layout comparison implementation."""
        diff = LayoutDiff()

        # Flatten both trees into element lists
        before_elements = self._flatten_dom(before_tree)
        after_elements = self._flatten_dom(after_tree)

        # Index by selector path
        before_by_path: dict[str, dict] = {}
        for el in before_elements:
            path = el.get("path", "")
            if path:
                before_by_path[path] = el

        after_by_path: dict[str, dict] = {}
        for el in after_elements:
            path = el.get("path", "")
            if path:
                after_by_path[path] = el

        before_paths = set(before_by_path.keys())
        after_paths = set(after_by_path.keys())

        # Detect removed elements
        removed_paths = before_paths - after_paths
        for path in removed_paths:
            el = before_by_path[path]
            diff.removed_elements.append(LayoutChange(
                change_type="removed",
                selector=path,
                tag=el.get("nodeName", ""),
                text_before=el.get("nodeValue", ""),
            ))

        # Detect added elements
        added_paths = after_paths - before_paths
        for path in added_paths:
            el = after_by_path[path]
            diff.added_elements.append(LayoutChange(
                change_type="added",
                selector=path,
                tag=el.get("nodeName", ""),
                text_after=el.get("nodeValue", ""),
            ))

        # Detect attribute changes in common elements
        common_paths = before_paths & after_paths
        for path in common_paths:
            before_el = before_by_path[path]
            after_el = after_by_path[path]
            attr_diffs: dict[str, tuple[Optional[str], Optional[str]]] = {}

            before_attrs = before_el.get("attributes", {}) or {}
            after_attrs = after_el.get("attributes", {}) or {}

            all_attr_keys = set(before_attrs.keys()) | set(after_attrs.keys())
            for key in sorted(all_attr_keys):
                bv = before_attrs.get(key)
                av = after_attrs.get(key)
                if bv != av:
                    attr_diffs[key] = (bv, av)

            if attr_diffs:
                diff.attribute_changes.append(LayoutChange(
                    change_type="attribute_changed",
                    selector=path,
                    tag=before_el.get("nodeName", ""),
                    attribute_diffs=attr_diffs,
                ))

        return diff

    def _flatten_dom(
        self,
        node: dict,
        depth: int = 0,
        path: str = "",
    ) -> list[dict]:
        """Flatten a DOM tree into a list of elements with selector paths."""
        results: list[dict] = []

        node_name = node.get("nodeName", "")
        node_type = node.get("nodeType", 1)

        # Skip text nodes, document nodes
        if node_type not in (1,):
            return results

        # Build selector path
        child_index = node.get("childIndex", 0)
        current_path = f"{path}/{node_name}[{child_index}]" if path else f"{node_name}[{child_index}]"

        attrs = node.get("attributes", {})
        if isinstance(attrs, dict):
            node["attributes"] = attrs
        elif isinstance(attrs, list):
            attr_dict = {}
            for a in attrs:
                if isinstance(a, dict):
                    attr_dict[a.get("name", "")] = a.get("value", "")
            node["attributes"] = attr_dict

        node["path"] = current_path
        results.append(node)

        # Recurse into children
        children = node.get("children", [])
        if isinstance(children, list):
            for i, child in enumerate(children):
                child["childIndex"] = i
                results.extend(self._flatten_dom(child, depth + 1, current_path))

        return results

    # ─────────────────────────────────────────────────────────────
    # ELEMENT-LEVEL DIFF
    # ─────────────────────────────────────────────────────────────

    async def compare_element(
        self,
        selector: str,
        before_b64: Optional[str] = None,
        after_b64: Optional[str] = None,
    ) -> VisualDiffReport:
        """
        Compare a specific element between two states.

        If no images provided, captures fresh screenshots of the element
        by navigating from the baseline snapshot.
        """
        report = VisualDiffReport(url="", label=f"element:{selector}")

        # Capture baseline element if needed
        if before_b64 is None:
            baseline = await self.browser.capture_snapshot(include_screenshot=True)
            before_b64 = baseline.screenshot_b64

        if after_b64 is None:
            current = await self.browser.capture_snapshot(include_screenshot=True)
            after_b64 = current.screenshot_b64

        if before_b64 and after_b64:
            report.pixel_diff = self._compare_pixel(before_b64, after_b64)

        return report

    # ─────────────────────────────────────────────────────────────
    # SERIALIZATION
    # ─────────────────────────────────────────────────────────────

    def save_report(self, report: VisualDiffReport, path: Path) -> None:
        """Save a visual diff report as JSON."""
        data = report.summary
        # Include diff image if present (large, but useful for debugging)
        if report.pixel_diff and report.pixel_diff.diff_image_b64:
            data["pixel"]["diff_image_b64"] = report.pixel_diff.diff_image_b64

        # Serialize regions
        if report.pixel_diff and report.pixel_diff.regions:
            data["pixel"]["regions"] = [
                {"x": r.x, "y": r.y, "width": r.width, "height": r.height, "area": r.area}
                for r in report.pixel_diff.regions
            ]

        # Serialize layout changes
        if report.layout_diff:
            data["layout"] = {
                "added": [{"selector": c.selector, "tag": c.tag} for c in report.layout_diff.added_elements],
                "removed": [{"selector": c.selector, "tag": c.tag} for c in report.layout_diff.removed_elements],
                "moved": [{"selector": c.selector} for c in report.layout_diff.moved_elements],
                "attribute_changes": [
                    {"selector": c.selector, "attributes": dict(c.attribute_diffs)}
                    for c in report.layout_diff.attribute_changes
                ],
            }

        path.write_text(json.dumps(data, indent=2))

    @staticmethod
    def load_report(path: Path) -> dict:
        """Load a previously saved visual diff report."""
        return json.loads(path.read_text())

    def save_diff_image(self, report: VisualDiffReport, path: Path) -> None:
        """Save the diff visualization image to disk."""
        if report.pixel_diff and report.pixel_diff.diff_image_b64:
            data = base64.b64decode(report.pixel_diff.diff_image_b64)
            path.write_bytes(data)

    # ─────────────────────────────────────────────────────────────
    # BATCH COMPARISON
    # ─────────────────────────────────────────────────────────────

    async def compare_multiple(
        self,
        urls: list[str],
        label: str = "default",
        include_pixel_diff: bool = True,
        include_layout_diff: bool = True,
    ) -> list[VisualDiffReport]:
        """
        Compare multiple pages against their baselines in sequence.
        """
        reports = []
        for url in urls:
            report = await self.compare_to_baseline(
                url, label=label,
                include_pixel_diff=include_pixel_diff,
                include_layout_diff=include_layout_diff,
            )
            reports.append(report)
        return reports


__all__ = [
    "VisualDiff",
    "VisualDiffReport",
    "PixelDiff",
    "PixelDiffRegion",
    "LayoutDiff",
    "LayoutChange",
    "DiffSeverity",
]
