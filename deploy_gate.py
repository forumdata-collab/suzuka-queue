#!/usr/bin/env python3
"""內容冇變就唔部署（省 CF Pages deployment）—— 同其他園區站同一套邏輯。

  python3 deploy_gate.py check   → exit 0 = 部署；10 = 跳過
  python3 deploy_gate.py commit  → 部署成功後記住 digest

Digest 只計用戶睇得到嘅嘢：每個設施嘅名／等候／乗車時間、運休名單、營業時間同價格、
官方注意事項，加前端檔案內容；唔計每次都會變嘅 updatedJst/Hkt 同 history；另含 10 分鐘時間格。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "site", "data", "suzuka.json")
STATE = os.path.join(HERE, "cache", "deploy_digest.txt")
FRONTEND = ("index.html", "vendor/leaflet.js", "vendor/leaflet.css")
BUCKET_MIN = 10


def bucket() -> str:
    override = os.environ.get("SZ_NOW")
    now = dt.datetime.fromisoformat(override).astimezone(JST) if override else dt.datetime.now(JST)
    return now.strftime(f"%Y-%m-%dT%H:{now.minute // BUCKET_MIN * BUCKET_MIN:02d}")


def digest() -> str:
    h = hashlib.sha256()
    with open(DATA, encoding="utf-8") as fh:
        d = json.load(fh)
    park = d.get("park") or {}
    visible = {
        "park": {k: park.get(k) for k in ("date", "open", "hoursOpen", "hoursClose", "entryPrice", "passportPrice")},
        "suspend": d.get("suspend"),
        "attractions": [[a.get("no"), a.get("name"), a.get("nameEn"), a.get("wait"), a.get("rideMin"), a.get("isRoute")]
                        for a in d.get("attractions", [])],
        "notes": d.get("notes"),
        "days": d.get("days"),
    }
    h.update(json.dumps(visible, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for name in FRONTEND:
        p = os.path.join(HERE, "site", name)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                h.update(fh.read())
    h.update(bucket().encode("utf-8"))
    return h.hexdigest()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    try:
        cur = digest()
    except Exception:
        return 0
    if mode == "commit":
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w", encoding="utf-8") as fh:
            fh.write(cur)
        return 0
    try:
        with open(STATE, encoding="utf-8") as fh:
            prev = fh.read().strip()
    except Exception:
        prev = ""
    return 10 if (prev and cur == prev) else 0


if __name__ == "__main__":
    sys.exit(main())
