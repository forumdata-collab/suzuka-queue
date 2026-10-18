#!/usr/bin/env python3
"""由 OpenStreetMap（Overpass API）抽鈴鹿サーキット園區內命名設施座標 → data/geo.json

同 legoland-map 一樣：座標只作參考（圖示位置），前端對唔上嘅設施就只喺清單顯示。
人手維護：data/geo-map.json 內 live 設施名 → OSM 名 嘅對照（OGSM 命名同官方名稱唔一定一致）。
"""
from __future__ import annotations
import json, os, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CENTER = (34.8469872, 136.5410968)   # モートピア（OSM way「鈴鹿サーキット　遊園地　モートピア」）
Q = f"""
[out:json][timeout:90];
(
  nwr(around:650, {CENTER[0]}, {CENTER[1]})["name"];
  nwr(around:650, {CENTER[0]}, {CENTER[1]})["attraction"];
);
out center tags;
"""
UA = "suzuka-map/1.0 (+https://we1co.me)"

def main():
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": Q}).encode(), headers={"User-Agent": UA})
    d = json.load(urllib.request.urlopen(req, timeout=120))
    out = {}
    for e in d.get("elements", []):
        t = e.get("tags") or {}
        name = (t.get("name") or "").strip()
        if not name:
            continue
        c = e.get("center") or {"lat": e.get("lat"), "lon": e.get("lon")}
        if not c.get("lat"):
            continue
        kind = t.get("attraction") or t.get("tourism") or t.get("leisure") or t.get("amenity") or t.get("shop") or ""
        prev = out.get(name)
        if prev is None or (kind and not prev.get("kind")):
            out[name] = {"lat": round(c["lat"], 6), "lon": round(c["lon"], 6), "kind": kind}
    payload = {"center": list(CENTER), "count": len(out), "source": "OpenStreetMap (ODbL) via Overpass API", "osm": out}
    with open(os.path.join(HERE, "data", "geo.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"OSM 命名設施 {len(out)} 項 → data/geo.json")
    for k, v in sorted(out.items()):
        print(f"   {v['kind']:14s} {v['lat']},{v['lon']}  {k}")

if __name__ == "__main__":
    main()
