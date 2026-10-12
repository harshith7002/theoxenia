"""Deterministic SVG plot and coordinate-projection tests."""

from __future__ import annotations

import math

from xenia.live.models import DetectionFloor
from xenia.live.plots import _project, render_floor_svg, render_hit_thumbnail, render_sky_svg
from xenia.live.state import floor_summary


def test_sky_map_has_accessible_projection_band_and_manifest_links(demo_state) -> None:
    """The sky SVG labels its projection and links pointings to run records."""
    svg = render_sky_svg(demo_state.pointings, demo=True)
    assert 'role="img"' in svg
    assert "Galactic plane" in svg
    assert "synthetic demo coordinates" in svg
    assert "galactic-band" in svg
    assert 'href="cadences/demo-cadence-001/index.html"' in svg
    assert "NaN" not in svg
    assert "Infinity" not in svg


def test_mollweide_maps_poles_and_seam_to_finite_coordinates() -> None:
    """Projection math stays finite at poles and both RA seam edges."""
    coordinates = ((0.0, 0.0), (360.0, 0.0), (120.0, 90.0), (240.0, -90.0))
    points = [_project(ra, dec) for ra, dec in coordinates]
    assert all(math.isfinite(value) for point in points for value in point)
    assert points[0][0] > points[1][0]
    assert points[2][1] < points[3][1]


def test_empty_floor_is_an_explicit_exp002_placeholder() -> None:
    """M0 never fabricates detection-floor data."""
    svg = render_floor_svg(None, demo=True)
    assert "Waiting for EXP-002" in svg
    assert "no injection results are available yet" in svg
    assert 'role="img"' in svg


def test_floor_heatmap_uses_values_from_payload() -> None:
    """Recovery-cell titles use the supplied grid and computed summary."""
    floor = DetectionFloor(
        run_id="floor-test",
        snr_grid=(6.0, 12.0),
        drift_grid=(-1.0, 1.0),
        trials_per_cell=5,
        recovered_fraction=((0.4, 0.6), (1.0, 1.0)),
        summary="Recovers SNR ≥ 12 at drift within ±3 Hz/s.",
        manifest_url="runs/floor-test/manifest.json",
    )
    svg = render_floor_svg(floor, demo=False)
    assert "SNR 6, drift -1 Hz/s: 2 of 5 trials recovered" in svg
    assert "SNR 12, drift 1 Hz/s: 5 of 5 trials recovered" in svg
    assert "Recovers SNR" in svg
    assert "Synthetic setigen injection recovery floor" in svg
    assert "Synthetic setigen data · not telescope observations" in svg
    assert 'class="floor-cell"' in svg


def test_floor_summary_has_no_claim_when_recovery_is_incomplete() -> None:
    """Summary text is derived from results and reports incomplete coverage honestly."""
    from xenia.live.models import FloorPayload

    payload = FloorPayload(
        kind="detection_floor",
        experiment="EXP-002",
        snr_grid=(6.0, 12.0),
        drift_grid=(-1.0, 1.0),
        trials_per_cell=5,
        recovered_fraction=((0.8, 0.8), (1.0, 0.8)),
    )
    assert "No tested SNR reached full recovery" in floor_summary(payload)


def test_hit_thumbnail_is_a_small_png(tmp_path) -> None:
    """The night colormap thumbnail is 320 by 140 and stays under the file cap."""
    import struct

    destination = tmp_path / "thumb.png"
    values = [[float((row + column) % 5) for column in range(32)] for row in range(8)]
    render_hit_thumbnail(destination, values=values, line_column=4)
    payload = destination.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", payload[16:24])
    assert (width, height) == (320, 140)
    assert len(payload) < 2 * 1024 * 1024
