#!/usr/bin/env python3
"""由鈴鹿サーキット「官方數位地圖」抽設施座標 → data/pa-spots.json

官方數位地圖（platinumaps.jp/d/suzukacircuit_park，由 suzukacircuit.jp 官方頁 iframe 引用）
本身有 CF 反爬（curl／無頭瀏覽器都被 challenge），但佢個 viewer API 冇擋：
  POST https://platinumaps.jp/map/api/search/spot-markers?culture=ja
  body: {"mapId":267,"zoom":18,"minLimit":4000,"latitude":..,"longitude":..,"bounds":{north,east,south,west}}
回傳 **每個 spot 嘅 lat/lng**（同 categoryIds）。注意：
  1. 回應係「視窗範圍」— 同一個大 bounds 只回一次，所以要用格仔掃（sweep）全圖。
  2. mapId／地圖 bbox／center 喺 viewer HTML 嘅內嵌 config JSON 揾到（267 / 見 BOUNDS）。
  3. 實測呢張官方地圖只有 12 個 spot（8 個遊樂設施 + 4 個餐飲），所以佢補唔齊所有設施。

用法：python3 fetch_pa_spots.py  （要重跑更新：直接再跑）
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "pa-spots.json")
MAP_ID = 267
BOUNDS = {"west": 136.503201, "east": 136.56974, "south": 34.82128, "north": 34.875096}
API = f"https://platinumaps.jp/map/api/search/spot-markers?culture=ja"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
GRID = 12


def post(bounds: dict, zoom: int = 20) -> list:
    payload = {
        "mapId": MAP_ID, "zoom": zoom, "minLimit": 4000,
        "latitude": (bounds["north"] + bounds["south"]) / 2,
        "longitude": (bounds["east"] + bounds["west"]) / 2,
        "bounds": bounds,
    }
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), headers={
        "User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json",
        "Referer": "https://platinumaps.jp/maps/suzukacircuit_park?culture=ja",
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r).get("spots") or []


def main() -> int:
    found: dict[int, dict] = {}
    W, E, S, N = BOUNDS["west"], BOUNDS["east"], BOUNDS["south"], BOUNDS["north"]
    for i in range(GRID):
        for j in range(GRID):
            box = {"south": S + (N - S) * i / GRID, "north": S + (N - S) * (i + 1) / GRID,
                   "west": W + (E - W) * j / GRID, "east": W + (E - W) * (j + 1) / GRID}
            try:
                for s in post(box):
                    found[s["id"]] = s
            except Exception as e:
                print(f"  ⚠️ cell {i},{j}: {e}")
            time.sleep(0.2)
    spots = sorted(found.values(), key=lambda x: x["id"])
    out = {
        "source": "鈴鹿サーキット官方數位地圖（platinumaps.jp/d/suzukacircuit_park）",
        "note": "官方地圖只有 12 個 spot（8 設施 + 4 餐飲）；座標為官方標示位置",
        "mapId": MAP_ID, "count": len(spots),
        "spots": [{k: s[k] for k in ("id", "title", "lat", "lng", "categoryIds")} for s in spots],
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"官方數位地圖：{len(spots)} 個 spot → {OUT}")
    for s in spots:
        print(f"   {s['id']:7d} {s['lat']:.6f},{s['lng']:.6f}  {s['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
