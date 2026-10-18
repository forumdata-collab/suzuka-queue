#!/usr/bin/env python3
"""鈴鹿サーキット（モートピア）即時營業狀況 → site/data/suzuka.json

數據來源（都係官方、免 key、GET only）：
  1. https://apps.mobilityland.co.jp/suzuka/norimono/   本日のアトラクション営業案内
     —— 每項設施嘅「待ち時間 N 分以内」、日文(英文)名、乗車時間、運休名單、官方注意事項
  2. https://www.suzukacircuit.jp/park/fee/              月曆（每日營業時間＋入園券／パスポート價格）
     —— 慢變，cache 6 小時

冇官方公告嘅更新間隔：官方頁冇時間戳，所以要靠本站自己連續採樣去測（history 就係做呢件事）。
本頁只作參考，非官方。
"""
from __future__ import annotations

import datetime as dt
import html as htmllib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "site", "data")
HIST = os.path.join(HERE, "cache", "history.json")
CACHE_DIR = os.path.join(HERE, "cache")
NORIMONO = "https://apps.mobilityland.co.jp/suzuka/norimono/"
FEE_URL = "https://www.suzukacircuit.jp/park/fee/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
JST = ZoneInfo("Asia/Tokyo")
HKT = ZoneInfo("Asia/Hong_Kong")
MAX_HISTORY = 6000
TREND_SAMPLES = 24

# 行程表（nagoya.we1co.me 十二、LEGOLAND 攻略之後嘅鈴鹿日 10/21）指定玩嘅設施，用關鍵字比對
ROUTE_KEYWORDS = ["チクタクトレイン", "コチラドライビングスクール", "プッチグランプリ",
                  "スモッグ ラッシュ アドベンチャー", "スモッグ・ラッシュ・アドベンチャー",
                  "アドベンボート フロンティア", "アドベンボート・フロンティア",
                  "サーキットホイール", "ピンキーバイク"]

GEO_FILE = os.path.join(HERE, "data", "geo.json")

REQS = 0


def load_geo() -> dict:
    """園區座標表（build_geo.py 生成）；冇檔案／壞檔就當冇座標，地圖自動唔顯示。"""
    try:
        with open(GEO_FILE, encoding="utf-8") as fh:
            g = json.load(fh)
        return g.get("located") or {}
    except Exception:
        return {}


GEO = load_geo()


def get(url, timeout=30, retries=2):
    global REQS
    last = None
    for attempt in range(retries):
        REQS += 1
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            last = e
            if attempt == 0 and e.code in (403, 429, 500, 502, 503, 504):
                wait = min(int(e.headers.get("Retry-After") or 0) or 5, 60)
                sys.stderr.write(f"⏳ HTTP {e.code}，等 {wait}s 再試：{url}\n")
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(3)
    raise RuntimeError(f"fetch failed: {last}")


def cached(key, url, ttl_h=6.0):
    """慢變資料（月曆）快取：cache/<key>.html，唔會部署出去。"""
    path = os.path.join(CACHE_DIR, f"{key}.html")
    try:
        if (time.time() - os.path.getmtime(path)) / 3600 < ttl_h:
            return open(path, encoding="utf-8").read()
    except Exception:
        pass
    try:
        body = get(url)
    except Exception as e:
        sys.stderr.write(f"WARN {url}: {e} — 用舊快取\n")
        return open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return body


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_norimono(h: str):
    """→ (date, suspend, attractions, notes)"""
    date = ""
    m = re.search(r"アトラクション営業案内\s*<p>([^<]+)</p>", h)
    if m:
        date = htmllib.unescape(m.group(1)).strip()

    suspend = {"all": False, "text": "", "items": []}
    s = re.search(r'<div id="suspend">(.*?)</div><!-- /#suspend -->', h, re.S)
    if s:
        block = s.group(1)
        body = text_of(block.split("</h2>", 1)[-1])
        suspend["text"] = body
        suspend["all"] = "通常通り" in body and "運休" not in body.replace("運休アトラクション", "")
        if not suspend["all"]:
            suspend["items"] = [t for t in re.findall(r'<li[^>]*>(.*?)</li>', block, re.S) and
                                [text_of(x) for x in re.findall(r'<li[^>]*>(.*?)</li>', block, re.S)] if t]

    attractions = []
    for tr in re.findall(r'<tr class="attraction\d+">(.*?)</tr>', h, re.S):
        num = re.search(r"&#x([0-9A-Fa-f]{4});", tr)
        link = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', tr, re.S)
        wait = re.search(r'class="time waitingtime\d+">\s*(\d+)\s*</span>', tr)
        if not link:
            continue
        label = text_of(link.group(2))
        ride = ""
        rm = re.search(r"乗車時間[:：]\s*([^　<\s]+)", label)
        if rm:
            ride = rm.group(1)
            label = label[:rm.start()].strip()
        name_ja, name_en = label, ""
        em = re.search(r"[（(]([^）)]+)[）)]", label)
        if em:
            name_en = em.group(1).strip()
            name_ja = label[:em.start()].strip()
        attractions.append({
            "no": chr(int(num.group(1), 16)) if num else "",
            "name": name_ja,
            "nameEn": name_en,
            "rideMin": ride,
            "wait": int(wait.group(1)) if wait else None,
            "url": link.group(1).strip(),
        })

    notes = []
    c = re.search(r'<div class="comment">(.*?)</div>', h, re.S)
    if c:
        for line in re.split(r"<br\s*/?>", c.group(1)):
            t = text_of(line)
            if t and len(t) > 6:
                notes.append(t)
    return date, suspend, attractions, notes


def parse_fee(h: str, want_dates: set):
    """月曆 → {date: {hours, entry, passport, band}}"""
    out = {}
    for m in re.finditer(r'<a[^>]*data-month="(\d+)"[^>]*data-day="(\d+)"[^>]*data-week="([^"]*)"[^>]*class="([^"]*)"(.*?)</a>', h, re.S):
        month, day, dow, cls, body = m.groups()
        try:
            d = dt.date(dt.datetime.now(JST).year, int(month), int(day))
        except Exception:
            continue
        iso = d.isoformat()
        if iso not in want_dates:
            continue
        times = re.search(r'class="fcal_time">([^<]+)<', body)
        prices = re.findall(r'<span>([^<]+)</span>', body)
        band = re.search(r"fcal_type-([a-z])", cls or "")
        out[iso] = {
            "date": iso, "dow": dow,
            "hours": htmllib.unescape(times.group(1)).strip() if times else "",
            "prices": [htmllib.unescape(p).strip() for p in prices],
            "band": band.group(1) if band else "",
        }
    return out


def load_history():
    try:
        with open(HIST, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_history(hist):
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = HIST + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(hist, fh, ensure_ascii=False)
    os.replace(tmp, HIST)


def geo_meta(attractions) -> dict:
    """地圖 metadata：園區中心、輪廓、實用設施、已定位數量。"""
    try:
        with open(GEO_FILE, encoding="utf-8") as fh:
            g = json.load(fh)
    except Exception:
        return {}
    located = sum(1 for a in attractions if a.get("lat"))
    return {
        "center": g.get("center"),
        "source": g.get("source"),
        "sourceBreakdown": g.get("sourceBreakdown"),
        "outline": g.get("outline") or [],
        "facilities": g.get("facilities") or [],
        "located": located,
        "total": len(attractions),
    }


def fmt_hhmm(iso):
    return iso


def main() -> int:
    now = dt.datetime.now(JST)
    norimono = get(NORIMONO)
    date_text, suspend, attractions, notes = parse_norimono(norimono)

    # 今日＋未來 20 日營業時間（月曆；慢變、cache 6 小時）
    want = {(now.date() + dt.timedelta(days=i)).isoformat() for i in range(0, 21)}
    fee_html = cached("fee_calendar", FEE_URL, ttl_h=6)
    days = parse_fee(fee_html, want)
    today = days.get(now.date().isoformat(), {})
    hours = today.get("hours", "")
    ho = hc = ""
    if "〜" in hours:
        ho, hc = [x.strip() for x in hours.split("〜", 1)]

    def hm2min(v):
        try:
            hh, mm = v.split(":")[:2]
            return int(hh) * 60 + int(mm)
        except Exception:
            return None

    o_m, c_m = hm2min(ho), hm2min(hc)
    now_m = now.hour * 60 + now.minute
    park_open = bool(o_m is not None and c_m is not None and o_m <= now_m <= c_m)

    # 歷史（趨勢用）
    hist = load_history()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    hist[stamp] = {a["no"] or a["name"]: a["wait"] for a in attractions}
    keys = sorted(hist.keys())
    if len(keys) > MAX_HISTORY:
        hist = {k: hist[k] for k in keys[-MAX_HISTORY:]}
        keys = sorted(hist.keys())
    save_history(hist)
    day = keys[-1][:10]
    shown = [k for k in keys if k[:10] == day][-TREND_SAMPLES:]

    for a in attractions:
        a["isRoute"] = any(k.replace(" ", "").replace("・", "") in (a["name"] or "").replace(" ", "").replace("・", "")
                           for k in ROUTE_KEYWORDS)
        g = GEO.get((a.get("no") or "").strip())
        if g:
            a["lat"], a["lon"] = g["lat"], g["lon"]
            a["geoLabel"] = g.get("label") or ("OpenStreetMap（近似對照）" if g.get("approx") else "OpenStreetMap")
            if g.get("approx"):
                a["geoApprox"] = True

    payload = {
        "updatedJst": now.strftime("%Y-%m-%d %H:%M"),
        "updatedHkt": now.astimezone(HKT).strftime("%Y-%m-%d %H:%M"),
        "park": {
            "name": "Suzuka Circuit MOTOPIA",
            "nameZh": "鈴鹿賽車場・モートピア",
            "date": now.date().isoformat(),
            "dateText": date_text,
            "open": park_open,
            "hoursOpen": ho, "hoursClose": hc,
            "entryPrice": (today.get("prices") or [""])[0],
            "passportPrice": (today.get("prices") or ["", ""])[1] if len(today.get("prices") or []) > 1 else "",
        },
        "suspend": suspend,
        "attractions": attractions,
        "notes": notes,
        "days": [days[k] for k in sorted(days)],
        "history": [{"t": k, "data": hist[k]} for k in shown],
        "historyStats": {"samples": len(keys), "shown": len(shown), "since": keys[0] if keys else ""},
        "geo": geo_meta(attractions),
        "sources": ["apps.mobilityland.co.jp（アトラクション営業・待ち時間案内）",
                    "suzukacircuit.jp/park/fee（營業時間・價格）"],
    }
    os.makedirs(DATA, exist_ok=True)
    tmp = os.path.join(DATA, "suzuka.json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(DATA, "suzuka.json"))
    waits = [a["wait"] for a in attractions if a["wait"] is not None]
    print(f"OK: {len(attractions)} attractions, {len(waits)} with wait, "
          f"avg={round(sum(waits)/len(waits)) if waits else 0} max={max(waits) if waits else 0}, "
          f"hours={ho}-{hc}, suspend={'all-ok' if suspend['all'] else len(suspend['items'])}, "
          f"days={len(days)} hist={len(keys)} reqs={REQS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
