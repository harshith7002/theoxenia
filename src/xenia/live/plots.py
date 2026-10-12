"""Small, deterministic SVG plots for the static Mission Control page."""

from __future__ import annotations

import html
import math
from collections.abc import Sequence

from xenia.live.models import DetectionFloor, Pointing

_VIEW_WIDTH = 640
_VIEW_HEIGHT = 330
_MAP_CX = 320.0
_MAP_CY = 165.0
_MAP_RX = 286.0
_MAP_RY = 143.0
_NGP_RA_DEG = 192.8594812065348
_NGP_DEC_DEG = 27.12825118085622


def render_sky_svg(pointings: Sequence[Pointing], *, demo: bool) -> str:
    """Render a Mollweide equatorial sky map with manifest-linked points.

    The faint Galactic-plane band uses the J2000 north-Galactic-pole
    coordinates from Astropy's Galactic frame implementation, itself following
    the IAU Galactic-coordinate definition. The input demo pointings remain
    synthetic and are explicitly identified as such.
    """
    paths = [path for dec_deg in (-60, -30, 0, 30, 60) for path in _render_parallel(dec_deg)]
    paths.extend(_render_meridian(ra_deg) for ra_deg in range(0, 360, 30))
    band_paths = _galactic_plane_paths()
    band_markup = "".join(f'<path d="{path}" class="galactic-band" />' for path in band_paths)
    point_markup = "".join(_render_pointing(pointing) for pointing in pointings)
    points_description = "synthetic demo coordinates" if demo else "recorded pointings"
    aria_label = html.escape(
        f"Mollweide equatorial sky map of {points_description}. "
        "The shaded band marks the Galactic plane; each point links to its run manifest.",
        quote=True,
    )
    grid_markup = "".join(f'<path d="{path}" class="graticule" />' for path in paths)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_VIEW_WIDTH} {_VIEW_HEIGHT}"
     role="img" aria-label="{aria_label}" focusable="false">
  <defs>
    <clipPath id="sky-boundary">
      <ellipse cx="{_MAP_CX:g}" cy="{_MAP_CY:g}" rx="{_MAP_RX:g}"
        ry="{_MAP_RY:g}" />
    </clipPath>
  </defs>
  <ellipse cx="{_MAP_CX:g}" cy="{_MAP_CY:g}" rx="{_MAP_RX:g}"
    ry="{_MAP_RY:g}" class="map-outline" />
  <g clip-path="url(#sky-boundary)">
    {band_markup}
    {grid_markup}
    {point_markup}
  </g>
</svg>
"""


def render_floor_svg(floor: DetectionFloor | None, *, demo: bool) -> str:
    """Render the injection recovery grid, or an honest pre-EXP-002 frame."""
    if floor is None:
        label = "Detection floor placeholder. Waiting for EXP-002."
        demo_note = "Synthetic demo state; no injection results are available yet." if demo else ""
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 330"
     role="img" aria-label="{html.escape(label, quote=True)}" focusable="false">
  <rect x="1" y="1" width="458" height="328" rx="10" class="plot-frame" />
  <text x="230" y="152" text-anchor="middle" class="plot-empty-title">Waiting for EXP-002</text>
  <text x="230" y="180" text-anchor="middle" class="plot-empty-copy">No recovery results yet</text>
  <text x="230" y="207" text-anchor="middle" class="plot-empty-copy">{html.escape(demo_note)}</text>
</svg>
"""

    rows = len(floor.snr_grid)
    columns = len(floor.drift_grid)
    cell_width = 36.0
    cell_height = 24.0
    gap = 5.0
    left = 58.0
    top = 26.0
    cells: list[str] = []
    for row_index, (snr, fractions) in enumerate(
        zip(floor.snr_grid, floor.recovered_fraction, strict=True)
    ):
        y = top + row_index * (cell_height + gap)
        cells.append(
            f'<text x="{left - 10:g}" y="{y + cell_height * 0.7:g}" '
            f'text-anchor="end" class="axis-label">{snr:g}</text>'
        )
        for column_index, (drift, fraction) in enumerate(
            zip(floor.drift_grid, fractions, strict=True)
        ):
            x = left + column_index * (cell_width + gap)
            fill = "#6FE3FF" if fraction > 0 else "#1A2435"
            opacity = "1" if fraction == 1 else "0.5" if fraction > 0 else "1"
            recovered = round(fraction * floor.trials_per_cell)
            title = html.escape(
                f"SNR {snr:g}, drift {drift:g} Hz/s: {recovered} of "
                f"{floor.trials_per_cell} trials recovered",
                quote=True,
            )
            cells.append(
                f'<rect x="{x:g}" y="{y:g}" width="{cell_width:g}" '
                f'height="{cell_height:g}" rx="2" fill="{fill}" '
                f'fill-opacity="{opacity}" class="floor-cell"><title>{title}</title></rect>'
            )
    chart_width = columns * cell_width + max(columns - 1, 0) * gap
    bottom = top + rows * (cell_height + gap)
    for column_index, drift in enumerate(floor.drift_grid):
        x = left + column_index * (cell_width + gap) + cell_width / 2
        cells.append(
            f'<text x="{x:g}" y="{bottom + 18:g}" text-anchor="middle" '
            f'class="axis-label">{drift:g}</text>'
        )
    label = html.escape(
        f"Injection recovery floor, {rows} SNR values by {columns} drift values. {floor.summary}",
        quote=True,
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 330"
     role="img" aria-label="{label}" focusable="false">
  <rect x="1" y="1" width="458" height="328" rx="10" class="plot-frame" />
  <text x="{left + chart_width / 2:g}" y="18" text-anchor="middle"
    class="axis-title">Drift (Hz/s)</text>
  {"".join(cells)}
  <text x="18" y="{bottom:g}" text-anchor="middle" class="axis-title"
    transform="rotate(-90 18 {top + (bottom - top) / 2:g})">SNR</text>
</svg>
"""


def _project(ra_deg: float, dec_deg: float) -> tuple[float, float]:
    """Project equatorial RA/Dec to a Mollweide viewBox, with RA increasing left."""
    longitude = math.radians(180.0 - ra_deg)
    latitude = math.radians(dec_deg)
    theta = _mollweide_theta(latitude)
    x = (2 * math.sqrt(2) / math.pi) * longitude * math.cos(theta)
    y = math.sqrt(2) * math.sin(theta)
    px = _MAP_CX + x * (_MAP_RX / (2 * math.sqrt(2)))
    py = _MAP_CY - y * (_MAP_RY / math.sqrt(2))
    return px, py


def _mollweide_theta(latitude: float) -> float:
    """Solve 2θ + sin(2θ) = π sin(φ) with bounded Newton iterations."""
    if math.isclose(abs(latitude), math.pi / 2, abs_tol=1e-12):
        return math.copysign(math.pi / 2, latitude)
    theta = latitude
    for _ in range(20):
        numerator = 2 * theta + math.sin(2 * theta) - math.pi * math.sin(latitude)
        denominator = 2 + 2 * math.cos(2 * theta)
        if math.isclose(denominator, 0, abs_tol=1e-15):
            break
        delta = numerator / denominator
        theta -= delta
        if abs(delta) < 1e-12:
            break
    return theta


def _path_from_sky_points(points: Sequence[tuple[float, float]]) -> tuple[str, ...]:
    """Convert projected points to path data, splitting at map-seam jumps."""
    segments: list[list[tuple[float, float]]] = [[]]
    for point in points:
        if segments[-1] and abs(point[0] - segments[-1][-1][0]) > _MAP_RX:
            segments.append([])
        segments[-1].append(point)
    paths: list[str] = []
    for segment in segments:
        if len(segment) < 2:
            continue
        commands = [f"M {segment[0][0]:.2f} {segment[0][1]:.2f}"]
        commands.extend(f"L {x:.2f} {y:.2f}" for x, y in segment[1:])
        paths.append(" ".join(commands))
    return tuple(paths)


def _render_parallel(dec_deg: float) -> tuple[str, ...]:
    """Render one declination graticule."""
    points = [_project(ra, dec_deg) for ra in range(0, 361, 3)]
    return _path_from_sky_points(points)


def _render_meridian(ra_deg: float) -> str:
    """Render one right-ascension graticule."""
    points = [_project(ra_deg, dec) for dec in range(-90, 91, 3)]
    return _path_from_sky_points(points)[0]


def _galactic_plane_paths() -> tuple[str, ...]:
    """Return the J2000 Galactic equator as a sequence of clipped sky paths."""
    alpha = math.radians(_NGP_RA_DEG)
    delta = math.radians(_NGP_DEC_DEG)
    pole = (
        math.cos(delta) * math.cos(alpha),
        math.cos(delta) * math.sin(alpha),
        math.sin(delta),
    )
    celestial_north = (0.0, 0.0, 1.0)
    first = _cross(pole, celestial_north)
    first_norm = math.sqrt(sum(component * component for component in first))
    basis_u = tuple(component / first_norm for component in first)
    basis_v = _cross(pole, basis_u)
    projected: list[tuple[float, float]] = []
    for step in range(361):
        angle = math.radians(step)
        vector = tuple(
            basis_u[index] * math.cos(angle) + basis_v[index] * math.sin(angle)
            for index in range(3)
        )
        ra = math.degrees(math.atan2(vector[1], vector[0])) % 360
        dec = math.degrees(math.asin(max(-1.0, min(1.0, vector[2]))))
        projected.append(_project(ra, dec))
    return _path_from_sky_points(projected)


def _cross(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Return the cross product of two three-dimensional vectors."""
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _render_pointing(pointing: Pointing) -> str:
    """Render one accessible, manifest-linked cadence dot."""
    x, y = _project(pointing.ra_deg, pointing.dec_deg)
    title = html.escape(
        f"{pointing.target}, {pointing.status.value}, {pointing.hits} hits, "
        f"{pointing.survivors} survivors",
        quote=True,
    )
    link = html.escape(pointing.manifest_url, quote=True)
    if pointing.status.value == "running":
        marker = (
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5.5" class="search-ring" />'
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" class="search-dot" />'
        )
    elif pointing.survivors:
        marker = (
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="7" class="survivor-ring" />'
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" class="searched-dot" />'
        )
    elif pointing.status.value == "failed":
        marker = f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" class="failed-dot" />'
    else:
        marker = f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" class="searched-dot" />'
    return f'<a href="{link}" aria-label="{title}">{marker}<title>{title}</title></a>'
