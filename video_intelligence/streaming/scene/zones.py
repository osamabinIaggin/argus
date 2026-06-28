"""
Zones — named regions of the frame that entities can occupy or breach.

Design notes:
  * Polygons are stored in **normalized** coordinates (each x, y in 0..1), NOT
    pixels. A zone is therefore independent of frame resolution: the same config
    works whether the source decodes at 640x480 or 4K, and survives a source
    reconnecting at a different size. Conversion to pixels happens only if a
    caller needs to draw the zone.
  * Containment is a self-contained ray-casting test — no shapely/matplotlib
    dependency, keeping the live path light and import-cheap.
  * A zone has a `kind`: an AREA zone is purely informational (we track who is
    inside), while a RESTRICTED zone turns an entry into a `zone_breach` event.
    That is the only behavioural difference; geometry is identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Sequence, Tuple

Point = Tuple[float, float]


class ZoneKind(str, Enum):
    AREA = "area"              # informational: track occupancy only
    RESTRICTED = "restricted"  # entry emits a zone_breach event


@dataclass(slots=True)
class Zone:
    """A named polygonal region, in normalized (0..1) frame coordinates."""

    name: str
    polygon: List[Point]
    kind: ZoneKind = ZoneKind.AREA

    def __post_init__(self) -> None:
        if len(self.polygon) < 3:
            raise ValueError(
                f"zone {self.name!r} needs at least 3 vertices, got {len(self.polygon)}"
            )
        # Clamp defensively: a config typo (e.g. a pixel coord slipping in) would
        # otherwise silently produce a zone nothing can ever be inside.
        for x, y in self.polygon:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(
                    f"zone {self.name!r} vertex ({x}, {y}) is outside 0..1 — "
                    "polygons must be in normalized coordinates"
                )

    @classmethod
    def rect(
        cls,
        name: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        kind: ZoneKind = ZoneKind.AREA,
    ) -> "Zone":
        """Convenience constructor for an axis-aligned rectangle zone."""
        lo_x, hi_x = sorted((x1, x2))
        lo_y, hi_y = sorted((y1, y2))
        return cls(
            name,
            [(lo_x, lo_y), (hi_x, lo_y), (hi_x, hi_y), (lo_x, hi_y)],
            kind,
        )

    def contains(self, x: float, y: float) -> bool:
        """True if normalized point (x, y) lies inside the polygon.

        Standard even-odd ray-casting: count edges a ray cast to +x crosses.
        Points exactly on an edge are treated as inside often enough for our
        purposes; sub-pixel boundary behaviour does not matter for occupancy.
        """
        poly = self.polygon
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            # Does the horizontal ray at height y cross edge (i, j)?
            if (yi > y) != (yj > y):
                x_cross = xi + (y - yi) * (xj - xi) / (yj - yi)
                if x < x_cross:
                    inside = not inside
            j = i
        return inside

    def to_pixels(self, width: int, height: int) -> List[Point]:
        """Polygon in pixel coordinates, for drawing/overlay."""
        return [(x * width, y * height) for x, y in self.polygon]


def zones_containing(zones: Sequence[Zone], x: float, y: float) -> set[str]:
    """Names of every zone whose polygon contains normalized point (x, y)."""
    return {z.name for z in zones if z.contains(x, y)}
