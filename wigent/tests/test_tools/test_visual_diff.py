"""Tests for wigent.tools.visual_diff — pixel & layout regression testing."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wigent.tools.browser_mcp import BrowserMCP, BrowserSnapshot
from wigent.tools.visual_diff import (
    DiffSeverity,
    LayoutChange,
    LayoutDiff,
    PixelDiff,
    PixelDiffRegion,
    VisualDiff,
    VisualDiffReport,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_browser() -> MagicMock:
    browser = MagicMock(spec=BrowserMCP)
    browser.capture_snapshot = AsyncMock()
    browser.viewport = (1920, 1080)
    return browser


def _fake_screenshot_b64(size: tuple[int, int] = (100, 100), colour: tuple[int, int, int] = (255, 255, 255)) -> str:
    """Generate a solid-colour PNG as base64."""
    from PIL import Image
    img = Image.new("RGB", size, colour)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _minimal_dom_tree(node_name: str = "html", children: list | None = None) -> dict:
    return {
        "nodeName": node_name,
        "nodeType": 1,
        "childIndex": 0,
        "attributes": {},
        "children": children or [],
    }


@pytest.fixture
def baseline_snapshot() -> BrowserSnapshot:
    return BrowserSnapshot(
        url="http://localhost:3000/",
        title="Test Page",
        timestamp=1000.0,
        screenshot_b64=_fake_screenshot_b64(),
        dom_tree=_minimal_dom_tree(),
        viewport_width=1920,
        viewport_height=1080,
    )


@pytest.fixture
def current_snapshot() -> BrowserSnapshot:
    return BrowserSnapshot(
        url="http://localhost:3000/",
        title="Test Page",
        timestamp=2000.0,
        screenshot_b64=_fake_screenshot_b64(),
        dom_tree=_minimal_dom_tree(),
        viewport_width=1920,
        viewport_height=1080,
    )


# ─────────────────────────────────────────────────────────────────────────
# Dataclass tests
# ─────────────────────────────────────────────────────────────────────────

class TestPixelDiffRegion:
    def test_bounds(self) -> None:
        r = PixelDiffRegion(x=10, y=20, width=30, height=40, area=50)
        assert r.bounds == (10, 20, 40, 60)


class TestPixelDiff:
    def test_identical(self) -> None:
        d = PixelDiff(changed_pixels=0, total_pixels=10000, change_ratio=0.0)
        assert d.severity == DiffSeverity.EQUAL
        assert d.passed is True

    def test_cosmetic(self) -> None:
        d = PixelDiff(changed_pixels=10, total_pixels=10000, change_ratio=0.001)
        assert d.severity == DiffSeverity.COSMETIC
        assert d.passed is True

    def test_moderate(self) -> None:
        d = PixelDiff(changed_pixels=100, total_pixels=10000, change_ratio=0.01)
        assert d.severity == DiffSeverity.MODERATE
        assert d.passed is False

    def test_severe(self) -> None:
        d = PixelDiff(changed_pixels=5000, total_pixels=10000, change_ratio=0.5)
        assert d.severity == DiffSeverity.SEVERE
        assert d.passed is False


class TestLayoutDiff:
    def test_empty(self) -> None:
        d = LayoutDiff()
        assert d.total_changes == 0
        assert d.severity == DiffSeverity.EQUAL
        assert d.passed is True

    def test_cosmetic(self) -> None:
        d = LayoutDiff(
            added_elements=[LayoutChange(change_type="added")],
            removed_elements=[LayoutChange(change_type="removed")],
        )
        assert d.total_changes == 2
        assert d.severity == DiffSeverity.COSMETIC
        assert d.passed is True

    def test_moderate(self) -> None:
        d = LayoutDiff(
            added_elements=[LayoutChange(change_type="added") for _ in range(6)],
        )
        assert d.severity == DiffSeverity.MODERATE
        assert d.passed is False

    def test_severe(self) -> None:
        d = LayoutDiff(
            added_elements=[LayoutChange(change_type="added") for _ in range(12)],
        )
        assert d.severity == DiffSeverity.SEVERE
        assert d.passed is False


class TestVisualDiffReport:
    def test_passed_when_no_diffs(self) -> None:
        r = VisualDiffReport(url="http://test", label="test")
        assert r.passed is True

    def test_passed_when_cosmetic_pixel_diff(self) -> None:
        r = VisualDiffReport(
            url="http://test", label="test",
            pixel_diff=PixelDiff(changed_pixels=1, total_pixels=10000, change_ratio=0.0001),
        )
        assert r.passed is True

    def test_fails_on_moderate_pixel_diff(self) -> None:
        r = VisualDiffReport(
            url="http://test", label="test",
            pixel_diff=PixelDiff(changed_pixels=100, total_pixels=10000, change_ratio=0.01),
        )
        assert r.passed is False

    def test_summary_structure(self) -> None:
        r = VisualDiffReport(
            url="http://test", label="test",
            pixel_diff=PixelDiff(changed_pixels=50, total_pixels=1000, change_ratio=0.05, regions=[
                PixelDiffRegion(x=0, y=0, width=10, height=10, area=100),
            ]),
            layout_diff=LayoutDiff(
                added_elements=[LayoutChange(change_type="added", tag="DIV")],
            ),
        )
        s = r.summary
        assert s["url"] == "http://test"
        assert s["passed"] is False
        assert s["pixel"]["change_ratio"] == 0.05
        assert s["pixel"]["regions"] == 1
        assert s["pixel"]["severity"] == "severe"
        assert s["layout"]["total_changes"] == 1
        assert s["layout"]["added"] == 1
        assert s["layout"]["severity"] == "cosmetic"


# ─────────────────────────────────────────────────────────────────────────
# VisualDiff logic tests
# ─────────────────────────────────────────────────────────────────────────

class TestVisualDiffPixelComparison:
    def test_identical_screenshots(self) -> None:
        b64 = _fake_screenshot_b64((50, 50), (100, 150, 200))
        diff = VisualDiff.__new__(VisualDiff)
        result = diff._compare_pixel(b64, b64)
        assert result.changed_pixels == 0
        assert result.change_ratio == 0.0
        assert result.severity == DiffSeverity.EQUAL
        assert result.passed is True

    def test_different_screenshots(self) -> None:
        white = _fake_screenshot_b64((50, 50), (255, 255, 255))
        black = _fake_screenshot_b64((50, 50), (0, 0, 0))
        diff = VisualDiff.__new__(VisualDiff)
        result = diff._compare_pixel(white, black)
        assert result.changed_pixels > 0
        assert result.change_ratio > 0.0
        assert result.severity == DiffSeverity.SEVERE
        assert result.passed is False

    def test_diff_image_generated(self) -> None:
        white = _fake_screenshot_b64((50, 50), (255, 255, 255))
        black = _fake_screenshot_b64((50, 50), (0, 0, 0))
        diff = VisualDiff.__new__(VisualDiff)
        result = diff._compare_pixel(white, black, generate_diff_image=True)
        assert result.diff_image_b64 is not None
        # Verify it's valid base64
        decoded = base64.b64decode(result.diff_image_b64)
        assert len(decoded) > 0


class TestVisualDiffLayoutComparison:
    def test_identical_trees(self) -> None:
        tree = _minimal_dom_tree("BODY", children=[
            {"nodeName": "DIV", "nodeType": 1, "childIndex": 0, "attributes": {"class": "container"}, "children": []},
        ])
        diff = VisualDiff.__new__(VisualDiff)
        result = diff._compare_layout(tree, tree)
        assert result.total_changes == 0
        assert result.severity == DiffSeverity.EQUAL

    def test_added_element(self) -> None:
        before = _minimal_dom_tree("BODY")
        after = _minimal_dom_tree("BODY", children=[
            {"nodeName": "DIV", "nodeType": 1, "childIndex": 0, "attributes": {}, "children": []},
        ])
        diff = VisualDiff.__new__(VisualDiff)
        result = diff._compare_layout(before, after)
        assert len(result.added_elements) == 1
        assert result.added_elements[0].tag == "DIV"
        assert len(result.removed_elements) == 0

    def test_removed_element(self) -> None:
        before = _minimal_dom_tree("BODY", children=[
            {"nodeName": "SPAN", "nodeType": 1, "childIndex": 0, "attributes": {}, "children": []},
        ])
        after = _minimal_dom_tree("BODY")
        diff = VisualDiff.__new__(VisualDiff)
        result = diff._compare_layout(before, after)
        assert len(result.removed_elements) == 1
        assert result.removed_elements[0].tag == "SPAN"
        assert len(result.added_elements) == 0

    def test_attribute_changed(self) -> None:
        before = _minimal_dom_tree("BODY", children=[
            {"nodeName": "DIV", "nodeType": 1, "childIndex": 0, "attributes": {"class": "old"}, "children": []},
        ])
        after = _minimal_dom_tree("BODY", children=[
            {"nodeName": "DIV", "nodeType": 1, "childIndex": 0, "attributes": {"class": "new"}, "children": []},
        ])
        diff = VisualDiff.__new__(VisualDiff)
        result = diff._compare_layout(before, after)
        assert len(result.attribute_changes) == 1
        assert result.attribute_changes[0].attribute_diffs == {"class": ("old", "new")}


class TestVisualDiffBaselineManagement:
    @pytest.mark.asyncio
    async def test_capture_and_compare(self, mock_browser: MagicMock, baseline_snapshot: BrowserSnapshot) -> None:
        mock_browser.capture_snapshot.return_value = baseline_snapshot
        vd = VisualDiff(mock_browser)
        await vd.capture_baseline("http://test", label="default")
        key = "http://test::default"
        assert key in vd._baselines

    def test_get_baseline(self, mock_browser: MagicMock, baseline_snapshot: BrowserSnapshot) -> None:
        vd = VisualDiff(mock_browser)
        vd._baselines["http://test::default"] = baseline_snapshot
        result = vd.get_baseline("http://test", "default")
        assert result is baseline_snapshot

    def test_get_baseline_missing(self, mock_browser: MagicMock) -> None:
        vd = VisualDiff(mock_browser)
        result = vd.get_baseline("http://test", "default")
        assert result is None

    def test_clear_baselines(self, mock_browser: MagicMock, baseline_snapshot: BrowserSnapshot) -> None:
        vd = VisualDiff(mock_browser)
        vd._baselines["http://test::default"] = baseline_snapshot
        vd.clear_baselines()
        assert len(vd._baselines) == 0

    @pytest.mark.asyncio
    async def test_compare_to_baseline_missing(self, mock_browser: MagicMock) -> None:
        vd = VisualDiff(mock_browser)
        with pytest.raises(ValueError, match="No baseline found"):
            await vd.compare_to_baseline("http://test")


class TestVisualDiffSnapshots:
    @pytest.mark.asyncio
    async def test_compare_identical_snapshots(self, baseline_snapshot: BrowserSnapshot, current_snapshot: BrowserSnapshot) -> None:
        current_snapshot.screenshot_b64 = baseline_snapshot.screenshot_b64
        current_snapshot.dom_tree = baseline_snapshot.dom_tree
        vd = VisualDiff.__new__(VisualDiff)
        report = await vd.compare_snapshots(
            baseline_snapshot, current_snapshot,
            url="http://test", label="test",
        )
        assert report.passed is True
        assert report.pixel_diff is not None
        assert report.pixel_diff.changed_pixels == 0
        assert report.layout_diff is not None
        assert report.layout_diff.total_changes == 0

    @pytest.mark.asyncio
    async def test_compare_different_snapshots(self, baseline_snapshot: BrowserSnapshot, current_snapshot: BrowserSnapshot) -> None:
        current_snapshot.screenshot_b64 = _fake_screenshot_b64((100, 100), (0, 0, 0))
        vd = VisualDiff.__new__(VisualDiff)
        report = await vd.compare_snapshots(
            baseline_snapshot, current_snapshot,
            url="http://test", label="test",
        )
        assert report.passed is False
        assert report.pixel_diff is not None
        assert report.pixel_diff.changed_pixels > 0

    @pytest.mark.asyncio
    async def test_compare_no_screenshots(self, baseline_snapshot: BrowserSnapshot, current_snapshot: BrowserSnapshot) -> None:
        baseline_snapshot.screenshot_b64 = None
        current_snapshot.screenshot_b64 = None
        vd = VisualDiff.__new__(VisualDiff)
        report = await vd.compare_snapshots(
            baseline_snapshot, current_snapshot,
            url="http://test", label="test",
        )
        assert report.pixel_diff is None


class TestVisualDiffSerialization:
    def test_save_and_load_report(self, tmp_path: Path) -> None:
        vd = VisualDiff.__new__(VisualDiff)
        report = VisualDiffReport(
            url="http://test", label="test",
            pixel_diff=PixelDiff(changed_pixels=10, total_pixels=1000, change_ratio=0.01, regions=[
                PixelDiffRegion(x=5, y=5, width=10, height=10, area=100),
            ]),
            layout_diff=LayoutDiff(
                added_elements=[LayoutChange(change_type="added", selector="DIV[0]", tag="DIV")],
            ),
        )
        p = tmp_path / "report.json"
        vd.save_report(report, p)
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["url"] == "http://test"
        assert data["pixel"]["change_ratio"] == 0.01

        loaded = VisualDiff.load_report(p)
        assert loaded["url"] == "http://test"

    def test_save_diff_image(self, tmp_path: Path) -> None:
        b64 = _fake_screenshot_b64((50, 50), (0, 0, 0))
        black2 = _fake_screenshot_b64((50, 50), (255, 255, 255))
        diff = VisualDiff.__new__(VisualDiff)
        pixel_diff = diff._compare_pixel(b64, black2)

        report = VisualDiffReport(url="http://test", label="test", pixel_diff=pixel_diff)
        p = tmp_path / "diff.png"
        diff.save_diff_image(report, p)
        assert p.exists()
        assert p.stat().st_size > 0


class TestVisualDiffCompareElement:
    @pytest.mark.asyncio
    async def test_compare_element_with_b64(self, mock_browser: MagicMock) -> None:
        b64_a = _fake_screenshot_b64()
        b64_b = _fake_screenshot_b64((100, 100), (0, 0, 0))
        vd = VisualDiff(mock_browser)
        report = await vd.compare_element("button", before_b64=b64_a, after_b64=b64_b)
        assert report.pixel_diff is not None
        assert report.pixel_diff.changed_pixels > 0

    @pytest.mark.asyncio
    async def test_compare_element_identical(self, mock_browser: MagicMock) -> None:
        b64 = _fake_screenshot_b64()
        vd = VisualDiff(mock_browser)
        report = await vd.compare_element("button", before_b64=b64, after_b64=b64)
        assert report.pixel_diff is not None
        assert report.pixel_diff.changed_pixels == 0


class TestVisualDiffFlattenDom:
    def test_flatten_simple_tree(self) -> None:
        tree = _minimal_dom_tree("HTML", children=[
            {"nodeName": "BODY", "nodeType": 1, "childIndex": 0, "attributes": {}, "children": [
                {"nodeName": "DIV", "nodeType": 1, "childIndex": 0, "attributes": {"id": "root"}, "children": []},
            ]},
        ])
        vd = VisualDiff.__new__(VisualDiff)
        result = vd._flatten_dom(tree)
        # Should have HTML, BODY, DIV
        assert len(result) == 3
        paths = [el["path"] for el in result]
        assert "HTML[0]" in paths
        assert "HTML[0]/BODY[0]" in paths
        assert "HTML[0]/BODY[0]/DIV[0]" in paths

    def test_skips_text_nodes(self) -> None:
        tree = _minimal_dom_tree("DIV", children=[
            {"nodeName": "#text", "nodeType": 3, "childIndex": 0, "nodeValue": "hello"},
        ])
        vd = VisualDiff.__new__(VisualDiff)
        result = vd._flatten_dom(tree)
        assert len(result) == 1
        assert result[0]["nodeName"] == "DIV"


class TestDiffSeverity:
    def test_values(self) -> None:
        assert DiffSeverity.EQUAL.value == "equal"
        assert DiffSeverity.COSMETIC.value == "cosmetic"
        assert DiffSeverity.MODERATE.value == "moderate"
        assert DiffSeverity.SEVERE.value == "severe"
