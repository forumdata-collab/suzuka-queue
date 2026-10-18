#!/usr/bin/env python3
"""建立鈴鹿園區座標表（一次性／需要更新時跑）：Overpass → data/geo-osm.json → data/geo.json

為何要分開：5 分鐘抓取嗰條路不應打 Overpass（慢、易被限流）。所以座標只喺呢度抓一次，
之後 fetch_suzuka.py 只讀 data/geo.json 附上 lat/lon。

座標用途：只作地圖定位參考。官方頁冇座標，源頭係 OpenStreetMap（ODbL）；
OSM 命名同官方設施名唔一定一致 → ALIAS 人手對照；對唔上嘅設施就只喺清單顯示，唔會亂放點。

用法：python3 build_geo.py
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CENTER = (34.8469872, 136.5410968)   # OSM way「鈴鹿サーキット　遊園地　モートピア」
UA = "suzuka-map/1.0 (+https://we1co.me)"
OSM_DUMP = os.path.join(HERE, "data", "geo-osm.json")
PA_SPOTS = os.path.join(HERE, "data", "pa-spots.json")     # 官方數位地圖（fetch_pa_spots.py）
EXTRA = os.path.join(HERE, "data", "geo-extra.json")       # Google 地圖 POI（已用官方座標對照）
AREAS_FILE = os.path.join(HERE, "data", "areas.json")      # 官方分區（fetch_areas.py）
OUT = os.path.join(HERE, "data", "geo.json")

LABELS = {"official": "官方數位地圖", "gmaps": "Google 地圖（第三方）", "osm": "OpenStreetMap"}

# live 設施名 → OSM 名（唔一致／英文名／同一地點嘅近似對照）。approx=True 代表係「同一場地但唔完全同名」。
ALIAS = {
    "ドリームR": {"osm": "DREAM R"},
    "キッズバイクトレーニング": {"osm": "キッズバイク コース", "approx": True},
    "ピンキーバイクプラス": {"osm": "ピンキーバイク コース", "approx": True},
    "テストフライト": {"osm": "フライングシップ", "approx": True},
}

# 園區實用設施（唔係機動遊戲，但當日會用得到）→ OSM 名
FACILITIES = {
    "入口（メインゲート）": "メインゲート",
    "售票處": "チケット売場",
    "醫務室": "医務室",
    "餐飲（ぐるめぷらざ）": "ぐるめぷらざ",
    "鈴鹿サーキットホテル": "鈴鹿サーキットホテル",
    "天然温泉クア・ガーデン": "鈴鹿サーキット;クア・ガーデン",
}

QUERY = f"""[out:json][timeout:90];
(
  nwr(around:700, {CENTER[0]}, {CENTER[1]})["name"];
  nwr(around:700, {CENTER[0]}, {CENTER[1]})["attraction"];
);
out center tags;
"""
OUTLINE_QUERY = f"""[out:json][timeout:90];
way(around:300, {CENTER[0]}, {CENTER[1]})["tourism"="theme_park"];
out geom tags;
"""


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[\s　]+", "", s)
    return s.replace("（", "(").replace("）", ")").lower()


def overpass(query: str):
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                data=urllib.parse.urlencode({"data": query}).encode(),
                                headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=150))


def fetch_osm() -> dict:
    if os.path.exists(OSM_DUMP) and "--refresh" not in os.environ.get("GEO_ARGS", ""):
        print(f"用快取 {OSM_DUMP}（要更新：GEO_ARGS=--refresh python3 build_geo.py）")
        return json.load(open(OSM_DUMP, encoding="utf-8"))
    d = overpass(QUERY)
    osm, outline = {}, []
    for e in d.get("elements", []):
        t = e.get("tags") or {}
        name = (t.get("name") or "").strip()
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        if name and c.get("lat"):
            osm.setdefault(name, {"lat": round(c["lat"], 6), "lon": round(c["lon"], 6),
                                  "kind": t.get("attraction") or t.get("tourism") or t.get("leisure") or ""})
    for e in overpass(OUTLINE_QUERY).get("elements", []):
        if (e.get("tags") or {}).get("tourism") == "theme_park":
            outline = [[round(p["lat"], 6), round(p["lon"], 6)] for p in (e.get("geometry") or [])]
    payload = {"osm": osm, "outline": outline}
    os.makedirs(os.path.dirname(OSM_DUMP), exist_ok=True)
    json.dump(payload, open(OSM_DUMP, "w", encoding="utf-8"), ensure_ascii=False, sort_keys=True)
    print(f"Overpass：命名設施 {len(osm)}、輪廓 {len(outline)} 點 → {OSM_DUMP}")
    return payload


def load_pa() -> dict:
    """官方數位地圖 spots（名稱 → {lat,lon}）。官方標示位置，優先於 OSM。"""
    try:
        with open(PA_SPOTS, encoding="utf-8") as fh:
            return {s["title"].strip(): s for s in json.load(fh).get("spots") or []}
    except Exception:
        return {}


def load_extra() -> dict:
    """Google 地圖 POI 座標（人手核對過；工程說明寫喺 geo-extra.json 嘅 _provenance）。"""
    try:
        with open(EXTRA, encoding="utf-8") as fh:
            return {norm(k): v for k, v in (json.load(fh).get("spots") or {}).items()}
    except Exception:
        return {}


def load_areas() -> dict:
    """官方分區對照（設施名 → {area, areaName}）。"""
    try:
        with open(AREAS_FILE, encoding="utf-8") as fh:
            return json.load(fh).get("byName") or {}
    except Exception:
        return {}


def main() -> int:
    src = fetch_osm()
    osm, outline = src["osm"], src.get("outline") or []
    pa = load_pa()
    extra = load_extra()
    areas = load_areas()
    by_norm = {norm(k): k for k in osm}
    live = json.load(open(os.path.join(HERE, "site", "data", "suzuka.json"), encoding="utf-8"))["attractions"]

    located, missed, area_of = {}, [], {}
    for a in live:
        key = (a.get("no") or "").strip()
        name = (a.get("name") or "").strip()
        cand = ALIAS.get(name, {}).get("osm") or osm.get(name) and name or by_norm.get(norm(name))
        approx = bool(ALIAS.get(name, {}).get("approx"))
        if not cand:
            hit = [k for k in osm if norm(name) and (norm(name) in norm(k) or norm(k) in norm(name))]
            cand = hit[0] if len(hit) == 1 and len(norm(hit[0])) >= 4 else None
        official = pa.get(name)
        gm = extra.get(norm(name))
        ai = areas.get(norm(name))
        if ai:
            area_of[key] = ai
        if official:
            located[key] = {"lat": official["lat"], "lon": official["lng"], "src": "official",
                            "label": LABELS["official"]}
        elif gm:
            located[key] = {"lat": gm["lat"], "lon": gm["lon"], "src": "gmaps", "label": LABELS["gmaps"]}
        elif cand and cand in osm:
            located[key] = {"lat": osm[cand]["lat"], "lon": osm[cand]["lon"], "src": "osm", "osm": cand,
                            **({"approx": True} if approx else {})}
        else:
            missed.append((key, name))

    # 第二輪：官方分區中心（非精確）——取同區「已定位」設施嘅平均位置，唔會亂放點到園區外
    still = []
    for key, name in missed:
        ai = area_of.get(key) or {}
        same = [v for k, v in located.items() if area_of.get(k, {}).get("area") == ai.get("area")] if ai else []
        if ai and len(same) >= 2:
            located[key] = {"lat": round(sum(v["lat"] for v in same) / len(same), 6),
                            "lon": round(sum(v["lon"] for v in same) / len(same), 6),
                            "src": "area", "approx": True, "areaName": ai["areaName"], "areaCount": len(same),
                            "label": "官方分區中心（" + ai["areaName"] + "，非精確）"}
        else:
            still.append(f"{key} {name}")

    facs = [{"name": zh, "osm": o, "lat": osm[o]["lat"], "lon": osm[o]["lon"]}
            for zh, o in FACILITIES.items() if o in osm]
    n_off = sum(1 for v in located.values() if v.get("src") == "official")
    n_gm = sum(1 for v in located.values() if v.get("src") == "gmaps")
    n_area = sum(1 for v in located.values() if v.get("src") == "area")
    payload = {
        "center": list(CENTER),
        "source": "OpenStreetMap（ODbL）+ 鈴鹿官方數位地圖 + Google 地圖 POI",
        "sourceBreakdown": {"official": n_off, "gmaps": n_gm, "area": n_area,
                            "osm": len(located) - n_off - n_gm - n_area},
        "locatedCount": len(located),
        "total": len(live),
        "located": located,
        "facilities": facs,
        "outline": outline,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"已定位 {len(located)}/{len(live)}、實用設施 {len(facs)}、輪廓 {len(outline)} 點 → {OUT}")
    for k, v in sorted(located.items()):
        if v.get("src") in ("official", "gmaps"):
            tag = LABELS[v["src"]]
        elif v.get("src") == "area":
            tag = v.get("label", "官方分區中心")
        else:
            tag = f"OSM {v.get('osm','')}" + ("（近似對照）" if v.get("approx") else "")
        print(f"   ✓ {k} {v['lat']:.6f},{v['lon']:.6f} ← {tag}")
    print("   未定位：" + ("；".join(still) if still else "無"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
