#!/usr/bin/env python3
"""決定今次 cron 要唔要抓鈴鹿數據（同 legoland/op/disney 同一套邏輯）。

規則（以 site/data/suzuka.json 嘅 park.date / hoursOpen / hoursClose 為準，JST）：
  1. 現在時間喺 [開園-30 分, 閉園+30 分] 內 → 抓。
  2. 其餘時間 → 跳過，一個 request 都唔發。
  3. 冇資料／讀唔到／唔係今日 → 抓（fail-open）。
夜場／延長營業會反映喺當日月曆 hours，自動跟隨。

Exit 0 = 抓；10 = 跳過。測試：SZ_NOW="2026-10-21T18:10:00+09:00" python3 should_run.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "site", "data", "suzuka.json")
GRACE_MIN = 30


def now_jst() -> dt.datetime:
    override = os.environ.get("SZ_NOW")
    if override:
        return dt.datetime.fromisoformat(override).astimezone(JST)
    return dt.datetime.now(JST)


def hm(value: str):
    """'9:30' 或 ISO 都可以 → (hour, minute)；解析失敗就拋（caller 會 fail-open）。"""
    value = (value or "").strip()
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d.hour, d.minute
    except Exception:
        pass
    hh, mm = value.split(":")[:2]
    return int(hh), int(mm)


def main() -> int:
    now = now_jst()
    try:
        with open(DATA, encoding="utf-8") as fh:
            park = (json.load(fh) or {}).get("park") or {}
        stamp = park.get("date") or ""
        opens, closes = park.get("hoursOpen") or "", park.get("hoursClose") or ""
    except Exception:
        return 0
    if stamp != now.date().isoformat() or not (opens and closes):
        return 0
    try:
        oh, om = hm(opens)
        ch, cm = hm(closes)
    except Exception:
        return 0
    start = now.replace(hour=oh, minute=om, second=0, microsecond=0) - dt.timedelta(minutes=GRACE_MIN)
    end = now.replace(hour=ch, minute=cm, second=0, microsecond=0) + dt.timedelta(minutes=GRACE_MIN)
    return 0 if start <= now <= end else 10


if __name__ == "__main__":
    sys.exit(main())
