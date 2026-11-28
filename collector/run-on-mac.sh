#!/bin/bash
# Reads Kuwait's recalls on a Mac, as the workflow in .github would on GitHub: run once a day by
# launchd. While a pull request of the reader's is open it waits, so that a person's
# corrections in it are never written over. It opens a pull request with what is new, and
# nothing reaches the app until that is merged. A notification on the Mac says when there is
# something to review, and when the run failed.
set -euo pipefail
cd "$(dirname "$0")/.."

BRANCH=kuwait-recalls
CACHE="$HOME/Library/Caches/tablon-kuwait-recalls"
OCR="$CACHE/ocr"

notify() {
    osascript -e "display notification \"$1\" with title \"طبلون: استدعاءات الكويت\"" || true
}
trap 'notify "تعذّرت قراءة صفحة وزارة التجارة. التفاصيل في السجل."' ERR

echo "== $(date '+%F %T')"
if [ "$(gh pr list --head "$BRANCH" --state open --json number --jq length)" != "0" ]; then
    echo "A pull request is waiting for review."
    exit 0
fi
git switch -q main
git pull -q --ff-only
git branch -D "$BRANCH" >/dev/null 2>&1 || true

mkdir -p "$CACHE"
if [ ! -x "$OCR" ] || [ collector/kuwait/ocr.swift -nt "$OCR" ]; then
    swiftc -O collector/kuwait/ocr.swift -o "$OCR"
fi
python3 -m unittest discover -s collector/tests
SUMMARY="$(mktemp)"
python3 collector/kuwait/collect.py fetch --ocr "$OCR" --summary "$SUMMARY"

if [ -z "$(git status --porcelain -- collector/kuwait/seen.json recalls.json)" ]; then
    echo "Nothing new."
    exit 0
fi
DAY="$(date +%F)"
git switch -q -c "$BRANCH"
git add collector/kuwait/seen.json recalls.json
git commit -q -m "Kuwait recalls read on $DAY"
git push -q --force origin "$BRANCH"
gh pr create --base main --head "$BRANCH" --title "Kuwait recalls read on $DAY" --body-file "$SUMMARY"
git switch -q main
notify "استدعاءات جديدة تنتظر المراجعة قبل نشرها."
