#!/usr/bin/env python3
"""取官方「アトラクション一覧」JSON → data/areas.json（設施 → 官方分區）

為何需要：官方數位地圖只有 12 個 spot、OSM 亦冇齊 29 項設施，但有幾項（例：メンキョセンター、
GPレーサーズ）官方分區係公開嘅。有咗分區就可以把搵唔到精確座標嘅設施，
標成「官方分區中心（非精確）」而唔係完全唔顯示。

來源：
  1. https://www.suzukacircuit.jp/park/attraction/json/attraction.json（設施 → area 1..8）
  2. https://www.suzukacircuit.jp/park/licence/（官方原文：「発行場所 コチラのプッチタウン内
     メンキョセンター」→ メンキョセンター 屬 area 1）

用法：python3 fetch_areas.py   （慢變，唔喺 5 分鐘路徑）
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "https://www.suzukacircuit.jp/park/attraction/json/attraction.json"
RAW = os.path.join(HERE, "data", "attractions-official.json")
OUT = os.path.join(HERE, "data", "areas.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

AREAS = {
    "1": "コチラのプッチタウン",
    "2": "チララのハローガーデン",
    "3": "プートのモビパーク",
    "4": "ピピラのモトフィールド",
    "5": "バットのアドベンチャーヴィレッジ",
    "6": "GPフィールド",
    "7": "サーキットチャレンジャー",
    "8": "アクア・アドベンチャー",
}

# 官方設施一覽冇列、但官方另一頁有寫明分區嘅項目
MANUAL = {
    "メンキョセンター": {"area": "1", "src": "官方 licence 頁：「発行場所 コチラのプッチタウン内メンキョセンター」"},
    "ライセンスセンター": {"area": "4", "src": "官方 licence 頁：「ピピラのモトフィールド内ライセンスセンター」"},
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"[（(].*?[）)]", "", s)          # 去括號補充：ene-1（エネワン）→ ene-1
    return re.sub(r"[\s　]+", "", s).lower()


def main() -> int:
    req = urllib.request.Request(SRC, headers={"User-Agent": UA})
    data = json.load(urllib.request.urlopen(req, timeout=60))
    items = data["list"] if isinstance(data, dict) else data
    json.dump(data, open(RAW, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    by_name = {}
    for it in items:
        a = str(it.get("area") or "").strip()
        if not a:
            continue
        by_name[norm(it["name"])] = {"name": it["name"], "area": a,
                                     "areaName": AREAS.get(a, ""), "link": it.get("link", "")}
    for name, info in MANUAL.items():
        by_name.setdefault(norm(name), {"name": name, **info,
                                        "areaName": AREAS.get(info["area"], "")})

    payload = {"source": SRC, "areas": AREAS, "byName": by_name, "count": len(by_name)}
    json.dump(payload, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"官方設施 {len(items)} 項 → 分區對照 {len(by_name)} 項 → {OUT}")
    for k, v in sorted(by_name.items(), key=lambda kv: (kv[1]["area"], kv[0])):
        print(f"  area{v['area']} {v['areaName']:<16} {v['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
