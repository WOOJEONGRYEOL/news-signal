"""data/kr_admin1.geojson (Natural Earth 10m admin-1, 퍼블릭 도메인) → site/kr-map.js
시·도 경계를 Douglas-Peucker로 단순화하고, 작은 섬은 버린 뒤, 520×640 화면 좌표로 투영한다.
실행: python3 scripts/build_krmap.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "kr_admin1.geojson"
OUT = ROOT / "site" / "kr-map.js"
TOL = 0.012          # 단순화 허용 오차(도) ≈ 1.2 km
MIN_AREA = 0.006     # 이보다 작은 고리(섬)는 버림 (도²) — 단, 시·도의 가장 큰 고리는 항상 유지
W, H, PAD = 520, 640, 14
NAMES = {"KR-11": "서울", "KR-26": "부산", "KR-27": "대구", "KR-28": "인천", "KR-29": "광주", "KR-30": "대전", "KR-31": "울산",
         "KR-50": "세종", "KR-41": "경기", "KR-42": "강원", "KR-43": "충북", "KR-44": "충남", "KR-45": "전북", "KR-46": "전남",
         "KR-47": "경북", "KR-48": "경남", "KR-49": "제주"}
# 라벨 위치 보정(화면 좌표 오프셋): 중심이 다른 시·도 안에 떨어지는 경우
LABEL_SHIFT = {"KR-41": (-28, -34), "KR-28": (-22, 6), "KR-44": (-10, 10), "KR-48": (0, 8), "KR-47": (10, 0)}


def dp(points: list, tol: float) -> list:
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-12
    best, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        d = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
        if d > best:
            best, idx = d, i
    if best > tol:
        return dp(points[: idx + 1], tol)[:-1] + dp(points[idx:], tol)
    return [points[0], points[-1]]


def simplify_ring(r: list, tol: float) -> list:
    """닫힌 고리는 시작점과 끝점이 같아 DP가 통째로 지워 버리므로, 가장 먼 점에서 둘로 나눠 처리한다."""
    if len(r) > 1 and r[0] == r[-1]:
        r = r[:-1]
    if len(r) < 4:
        return r
    x0, y0 = r[0]
    far = max(range(len(r)), key=lambda i: (r[i][0] - x0) ** 2 + (r[i][1] - y0) ** 2)
    a = dp(r[: far + 1], tol)
    b = dp(r[far:] + [r[0]], tol)
    return a[:-1] + b[:-1]


def ring_area(r: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]))) / 2


def centroid(r: list) -> tuple:
    a = 0.0
    cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
        c = x1 * y2 - x2 * y1
        a += c
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a)) if a else r[0]


def main() -> None:
    feats = json.loads(SRC.read_text(encoding="utf-8"))["features"]
    regions = {}
    for f in feats:
        code = f["properties"]["iso_3166_2"]
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = [[tuple(p) for p in poly[0]] for poly in polys]           # 외곽 고리만
        rings.sort(key=ring_area, reverse=True)
        keep = [rings[0]] + [r for r in rings[1:] if ring_area(r) >= MIN_AREA]
        regions[code] = [simplify_ring(r, TOL) for r in keep]
    # 투영 범위
    lons = [x for rs in regions.values() for r in rs for x, _ in r]
    lats = [y for rs in regions.values() for r in rs for _, y in r]
    lon0, lon1, lat0, lat1 = min(lons), max(lons), min(lats), max(lats)
    k = math.cos(math.radians((lat0 + lat1) / 2))
    sx = (W - 2 * PAD) / ((lon1 - lon0) * k)
    sy = (H - 2 * PAD) / (lat1 - lat0)
    s = min(sx, sy)
    ox = PAD + ((W - 2 * PAD) - (lon1 - lon0) * k * s) / 2
    oy = PAD + ((H - 2 * PAD) - (lat1 - lat0) * s) / 2
    proj = lambda lon, lat: (ox + (lon - lon0) * k * s, oy + (lat1 - lat) * s)
    out = {}
    total = 0
    for code, rings in regions.items():
        parts = []
        for r in rings:
            pts = [proj(*p) for p in r]
            parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
            total += len(pts)
        cx, cy = centroid([proj(*p) for p in rings[0]])
        dx, dy = LABEL_SHIFT.get(code, (0, 0))
        out[code] = {"n": NAMES.get(code, code), "d": "".join(parts), "cx": round(cx + dx, 1), "cy": round(cy + dy, 1)}
    js = ("// 대한민국 시·도 경계 — Natural Earth 10m admin-1 (public domain) 를 scripts/build_krmap.py 로 단순화·투영한 것\n"
          f"window.KR_MAP = {{W:{W}, H:{H}, regions:{json.dumps(out, ensure_ascii=False, separators=(',', ':'))}}};\n")
    OUT.write_text(js, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(out)} regions, {total} points, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
