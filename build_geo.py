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
OUT = os.path.join(HERE, "data", "geo.json")

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


def main() -> int:
    src = fetch_osm()
    osm, outline = src["osm"], src.get("outline") or []
    by_norm = {norm(k): k for k in osm}
    live = json.load(open(os.path.join(HERE, "site", "data", "suzuka.json"), encoding="utf-8"))["attractions"]

    located, missed = {}, []
    for a in live:
        key = (a.get("no") or "").strip()
        name = (a.get("name") or "").strip()
        cand = ALIAS.get(name, {}).get("osm") or osm.get(name) and name or by_norm.get(norm(name))
        approx = bool(ALIAS.get(name, {}).get("approx"))
        if not cand:
            hit = [k for k in osm if norm(name) and (norm(name) in norm(k) or norm(k) in norm(name))]
            cand = hit[0] if len(hit) == 1 and len(norm(hit[0])) >= 4 else None
        if cand and cand in osm:
            located[key] = {"lat": osm[cand]["lat"], "lon": osm[cand]["lon"], "osm": cand, **({"approx": True} if approx else {})}
        else:
            missed.append(f"{key} {name}")

    facs = [{"name": zh, "osm": o, "lat": osm[o]["lat"], "lon": osm[o]["lon"]}
            for zh, o in FACILITIES.items() if o in osm]
    payload = {
        "center": list(CENTER),
        "source": "OpenStreetMap（ODbL）via Overpass API",
        "locatedCount": len(located),
        "total": len(live),
        "located": located,
        "facilities": facs,
        "outline": outline,
    }
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"已定位 {len(located)}/{len(live)}、實用設施 {len(facs)}、輪廓 {len(outline)} 點 → {OUT}")
    for k, v in located.items():
        print(f"   ✓ {k} {v['osm']}{'（近似）' if v.get('approx') else ''}")
    print("   未定位：" + ("；".join(missed) if missed else "無"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
