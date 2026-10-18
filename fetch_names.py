#!/usr/bin/env python3
"""由鈴鹿サーキット官方繁中網站抽設施中文名 → data/names-zh.json

來源：官方 zh-tw 版設施頁 <title>（例：チクタクトレイン → 滴答電車）。
清單來自 /park/attraction/json/attraction.json（每項有 link = slug），再逐頁抓 zh-tw 標題。
（官網嘅 JSON 本身只有日文名；中文係前端用 Cistate 翻譯服務套上去，所以一定要逐頁抓 title。）

用法：python3 fetch_names.py   （要更新：直接再跑）
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "names-zh.json")
BASE = "https://www.suzukacircuit.jp"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
SUFFIX = "| 鈴鹿賽車場樂園"

# 官方 zh-tw 網站偶爾漏簡體字／標題夾其他頁名 → 人手修正（只改字面，唔改官方叫法）
FIXUP = {"机": "機"}
MANUAL = {   # 官方設施清單冇嘅兩項（プッチタウン／GP 區嘅發證櫃檯）→ 本站譯
    "メンキョセンター": {"zh": "駕照中心", "src": "本站譯"},
    "ライセンスセンター": {"zh": "牌照中心", "src": "本站譯"},
}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def main() -> int:
    data = json.loads(get(f"{BASE}/park/attraction/json/attraction.json"))
    rides = data["list"] if isinstance(data, dict) else data
    out = {}
    for r in rides:
        slug = (r.get("link") or "").strip("/")
        ja = r.get("name") or ""
        if not slug or not ja:
            continue
        url = f"{BASE}/zh-tw/park/attraction/{slug}/"
        try:
            h = get(url)
            m = re.search(r"<title>(.*?)</title>", h, re.S)
            title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
            zh = re.split(r"[|｜]", re.sub(re.escape(SUFFIX), "", title))[0].strip()
            for a, b in FIXUP.items():
                zh = zh.replace(a, b)
        except Exception as e:
            zh, title = "", f"err {e}"
        out[ja] = {"zh": zh, "slug": slug, "url": url, "src": "官方繁中網站"}
        print(f"  {ja[:26]:28s} → {zh or '（抓唔到）'}")
        time.sleep(0.3)
    for ja, v in MANUAL.items():
        out[ja] = {"zh": v["zh"], "slug": "", "url": "", "src": v["src"]}
    json.dump({"source": "鈴鹿賽車場官方繁中網站（suzukacircuit.jp/zh-tw）＋本站補譯", "count": len(out), "names": out},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"官方中文名 {len(out)} 項 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
