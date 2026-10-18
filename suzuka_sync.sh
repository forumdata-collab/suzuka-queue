#!/bin/bash
# 鈴鹿サーキット（モートピア）即時狀況：時間窗把關 → 抓 → 內容 digest 把關 → 只部署網站檔案 → CF Pages
# Silent on success。失敗才輸出（cron no_agent 會推送）。
set -u
cd /home/ubuntu/suzuka-map || exit 1
PY=python3
LOG=/home/ubuntu/suzuka-map/deploy.log

# 營業時間外（開園前 30 分 / 閉園後 30 分以外）→ 0 request
$PY should_run.py; gate=$?
if [ "$gate" -eq 10 ]; then exit 0; fi

OUT=$($PY fetch_suzuka.py 2>&1)
RC=$?
printf '%s fetch rc=%s %s\n' "$(date '+%F %T')" "$RC" "$OUT" >> "$LOG"
if [ $RC -ne 0 ]; then
  echo "SUZUKA FETCH FAIL: $OUT"
  exit 1
fi

$PY deploy_gate.py check; dg=$?
if [ "$dg" -eq 10 ]; then
  printf '%s skip-deploy（內容無變）\n' "$(date '+%F %T')" >> "$LOG"
  exit 0
fi

set -a; . /home/ubuntu/.hermes/.env; set +a
export CLOUDFLARE_API_TOKEN="${CF_WORKERS_TOKEN:-}"
export CLOUDFLARE_ACCOUNT_ID="${CF_ACCOUNT_ID:-}"

# 只部署 index.html + data/suzuka.json（唔會公開 fetch 腳本／README／history）
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/data" "$STAGE/vendor"
cp site/index.html "$STAGE/"
cp site/data/suzuka.json "$STAGE/data/"
cp site/vendor/leaflet.js site/vendor/leaflet.css site/vendor/leaflet.markercluster.js site/vendor/MarkerCluster.css "$STAGE/vendor/"

for attempt in 1 2 3; do
  OUT2=$(env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    npx --yes wrangler@4 pages deploy "$STAGE" --project-name=suzuka-queue --branch=main \
    --commit-dirty=true 2>&1)
  if [ $? -eq 0 ]; then
    printf '%s deploy ok (attempt %s)\n' "$(date '+%F %T')" "$attempt" >> "$LOG"
    $PY deploy_gate.py commit
    exit 0
  fi
  printf '%s deploy attempt %s FAIL\n' "$(date '+%F %T')" "$attempt" >> "$LOG"
  sleep $((attempt * 10))
done
echo "SUZUKA DEPLOY FAIL: $(printf '%s' "$OUT2" | tail -3)"
exit 1