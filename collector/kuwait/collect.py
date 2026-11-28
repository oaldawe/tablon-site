#!/usr/bin/env python3
"""Kuwait's vehicle recalls, from the Ministry of Commerce and Industry's page, into the app's list.

    collect.py fetch --ocr <reader> [--summary <file>]
        Reads the page, reads each picture not seen before with <reader> (ocr.swift, built),
        keeps what it found in seen.json and writes recalls.json again.
    collect.py feed
        Writes recalls.json again from seen.json, after a person has changed seen.json.

Only announcements whose status is "ready" reach recalls.json. An id that has been published
must never change: the app keeps what the user said about a recall under its id.
"""

import argparse
import datetime
import html.parser
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

from parse import Catalog, announcement, read_lines, repeats

HERE = pathlib.Path(__file__).resolve().parent
SITE = HERE.parent.parent
SEEN = HERE / "seen.json"
MAKES = HERE / "makes.json"
FEED = SITE / "recalls.json"
PAGE = "https://www.moci.gov.kw/MociSite/summoning-vehicles-tires/index.html"
PICTURE_HOST = "files.moci.gov.kw"
AGENT = "TablonRecalls/1.0 (+https://oaldawe.github.io/tablon-site/)"


class AlbumReader(html.parser.HTMLParser):
    """The page's albums: each a link holding one picture whose description is its date."""

    def __init__(self):
        super().__init__()
        self.albums, self._inside = [], False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and "al" in (attributes.get("class") or "").split():
            self._inside = True
        elif tag == "img" and self._inside:
            self.albums.append({"src": attributes.get("src") or "", "alt": attributes.get("alt") or ""})
            self._inside = False

    def handle_endtag(self, tag):
        if tag == "a":
            self._inside = False


def albums(page):
    reader = AlbumReader()
    reader.feed(page)
    found = []
    for album in reader.albums:
        url = urllib.parse.urlparse(album["src"])
        name = pathlib.PurePosixPath(url.path).name
        if url.scheme != "https" or url.hostname != PICTURE_HOST or not re.fullmatch(r"[0-9a-f-]{36}\.jpe?g", name):
            continue
        day = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", album["alt"])
        found.append({
            "picture": name.rsplit(".", 1)[0],
            "pictureURL": album["src"],
            "date": f"{day[1]}-{int(day[2]):02d}-{int(day[3]):02d}" if day else None,
        })
    return found


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as answer:
        return answer.read()


def load(path, empty):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else empty


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def catalog():
    makes = load(MAKES, None)
    return Catalog(makes["makes"], makes["aliases"])


def read_picture(ocr, data):
    with tempfile.TemporaryDirectory() as folder:
        picture = pathlib.Path(folder) / "picture.jpg"
        picture.write_bytes(data)
        result = subprocess.run([ocr, str(picture)], capture_output=True, text=True, timeout=180, check=True)
    return read_lines(result.stdout)


def with_ids(record, found):
    """Each vehicle group becomes one entry of the list, with an id that will not change."""
    vehicles = found.pop("vehicles")
    base = "kw-" + record["picture"]
    found["entries"] = [
        {"id": base if len(vehicles) == 1 else f"{base}-{index}", **vehicle}
        for index, vehicle in enumerate(vehicles, start=1)
    ]
    return {**record, **found}


def fetch(ocr, summary):
    seen = load(SEEN, {"source": PAGE, "announcements": []})
    known = {a["picture"] for a in seen["announcements"]}
    page = download(PAGE).decode("utf-8")
    listed = albums(page)
    if not listed:
        sys.exit("No recall was found on the page: its layout may have changed.")
    names = catalog()
    today = datetime.date.today().isoformat()
    added = []
    # Oldest first, so that a picture that repeats an earlier one is the one held back.
    for album in reversed([a for a in listed if a["picture"] not in known]):
        found = announcement(read_picture(ocr, download(album["pictureURL"])), names)
        record = with_ids({**album, "readAt": today}, found)
        if record["date"] is None:
            record["notes"].append("The page gave no date for it.")
        earlier = next((a for a in seen["announcements"] if a.get("status") != "skipped" and repeats(
            {"vehicles": record["entries"], "fault": record.get("fault", "")},
            {"vehicles": a.get("entries", []), "fault": a.get("fault", "")},
        )), None)
        if earlier:
            record["notes"].append(f"Looks like a repeat of {earlier['picture']}: publish only one of them.")
        if record["notes"] and record["status"] == "ready":
            record["status"] = "needs-review"
        seen["announcements"].append(record)
        added.append(record)
    save(SEEN, seen)
    feed()
    if summary:
        pathlib.Path(summary).write_text(describe(added), encoding="utf-8")
    print(f"{len(added)} new, {sum(a['status'] == 'ready' for a in added)} ready")


def entries(record):
    for entry in record["entries"]:
        if not entry.get("make") or not entry.get("models") or len(entry.get("years", [])) != 2:
            sys.exit(f"{entry.get('id')}: a make, models and two years are needed before it is ready.")
        yield {
            "id": entry["id"],
            "region": "KW",
            "date": record["date"],
            "category": record["category"],
            "make": entry["make"],
            "models": entry["models"],
            "years": entry["years"],
            "fault": {"ar": record["fault"]},
            "remedy": {"ar": record["remedy"]},
            "url": record["pictureURL"],
        }


def feed():
    """recalls.json: what was written by hand stays, and Kuwait's ready entries are put beside it."""
    current = load(FEED, {"version": 1, "recalls": []})
    kept = [r for r in current["recalls"] if not r["id"].startswith("kw-")]
    kuwait = [e for a in load(SEEN, {"announcements": []})["announcements"] if a["status"] == "ready" for e in entries(a)]
    recalls = kept + kuwait
    ids = [r["id"] for r in recalls]
    if len(ids) != len(set(ids)):
        sys.exit("Two recalls share an id.")
    recalls.sort(key=lambda r: (r.get("date") or "", r["id"]), reverse=True)
    save(FEED, {"version": current.get("version", 1), "recalls": recalls})


def describe(added):
    lines = [
        f"The reader found {len(added)} new announcement(s) on the ministry's page.",
        "",
        "Only those marked ready are in `recalls.json`. For each one that needs review: open its "
        "picture, correct its record in `collector/kuwait/seen.json` (make and models as the app's "
        "list writes them in English, first and last model year, the fault and the remedy), set "
        "`status` to `ready` or `skipped`, run `python3 collector/kuwait/collect.py feed`, and push "
        "to this branch. Merging publishes it to the app.",
    ]
    for a in added:
        lines += ["", f"### {a['date']} · {a['status']}", f"[Picture]({a['pictureURL']})", ""]
        lines += [f"- {e['id']}: {e['make']} {', '.join(e['models'])} {'–'.join(map(str, e['years']))}" for e in a["entries"]]
        if a.get("category"):
            lines.append(f"- Category: {a['category']}")
        lines += [f"- **{note}**" for note in a["notes"]]
    return "\n".join(lines) + "\n"


def main():
    arguments = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = arguments.add_subparsers(dest="command", required=True)
    fetching = commands.add_parser("fetch")
    fetching.add_argument("--ocr", required=True)
    fetching.add_argument("--summary")
    commands.add_parser("feed")
    chosen = arguments.parse_args()
    if chosen.command == "fetch":
        fetch(chosen.ocr, chosen.summary)
    else:
        feed()


if __name__ == "__main__":
    main()
