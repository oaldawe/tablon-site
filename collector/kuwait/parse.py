"""Pure rules: the lines read from one of the ministry's recall pictures, turned into what the
app's list needs. No network, no files. Whatever the rules cannot settle is named in `notes`,
and an announcement with a note waits for a person before it reaches the app.
"""

import difflib
import re

# Arabic letters written in more than one way are read as one.
_LETTERS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})
_MARKS = re.compile(r"[ـً-ٰٟ]")

HEADERS = {"fault": "الخلل", "action": "الاجراء", "contact": "الاتصال"}

MONTHS = [
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
    "oct", "nov", "dec", "يناير", "فبراير", "مارس", "ابريل", "مايو", "يونيو", "يوليو", "اغسطس",
    "سبتمبر", "اكتوبر", "نوفمبر", "ديسمبر",
]

# Earlier wins: a fault that names the suspension and the brakes is about the suspension, and
# a screen is electrical even when it hides a warning light.
CATEGORIES = [
    ("airBags", ["وساده هوائيه", "الوساده الهوائيه", "وسائد"]),
    ("seatBelts", ["حزام", "احزمه"]),
    ("suspension", ["تعليق"]),
    ("brakes", ["فرامل", "مكابح", "الكبح"]),
    ("steering", ["توجيه", "المقود"]),
    ("fuelSystem", ["وقود"]),
    ("powerTrain", ["ناقل الحركه", "ناقل حركه"]),
    ("seats", ["مقعد", "مقاعد", "كرسي", "مسند ظهر", "مساند الظهر"]),
    ("engine", ["محرك", "عمود المرفق"]),
    ("structure", ["باب", "ابواب", "قفل", "هيكل"]),
    ("tires", ["اطار", "عجلات", "العجله"]),
    ("lighting", ["مصابيح", "المصباح", "اضاءه"]),
    ("electrical", ["بطاريه", "كهرب", "شاشه", "برمج"]),
    ("visibility", ["رؤيه", "كاميرا", "مرايا", "مراه", "المساحات"]),
]


def normalized(text):
    """Small letters and digits with single spaces, Arabic spelling variants read as one."""
    text = _MARKS.sub("", text.lower().translate(_LETTERS))
    return " ".join(re.sub(r"[^\w]+", " ", text).replace("_", " ").split())


def _has_arabic(text):
    return re.search(r"[؀-ۿ]", text) is not None


def read_lines(output):
    """The reader's output, one `confidence text` per line, as (confidence, text) pairs."""
    lines = []
    for raw in output.splitlines():
        confidence, _, text = raw.strip().partition(" ")
        try:
            lines.append((float(confidence), text.strip()))
        except ValueError:
            continue
    return [line for line in lines if line[1]]


def _header(text):
    """Which section a line opens, if it is one of the three titles, even when misread."""
    letters = normalized(text).replace(" ", "")
    if not letters or len(letters) > 9:
        return None
    for key, title in HEADERS.items():
        if difflib.SequenceMatcher(None, letters, title).ratio() >= 0.7:
            return key
    return None


def _is_footer(text):
    words = normalized(text)
    return words.startswith("تم تنظيم هذا الاستدعاء") or words.startswith("رقم 2015 27") or "mocikw" in words


def split(lines):
    """The picture's parts: its kind, the lines about the vehicles, and the three sections."""
    start = next((i for i, (_, text) in enumerate(lines) if normalized(text).startswith("استدعاء")), None)
    if start is None:
        return None
    kind = "tires" if "اطار" in normalized(lines[start][1]) else "vehicles"
    block, sections, order, current = [], {"fault": [], "action": [], "contact": []}, [], None
    for confidence, text in lines[start + 1:]:
        if _is_footer(text):
            continue
        key = _header(text)
        if key:
            current = key
            order.append(key)
            continue
        if current is None:
            block.append(text)
        elif _has_arabic(text) or confidence >= 0.5:
            sections[current].append(text)
    return {"kind": kind, "block": block, "sections": sections, "order": order}


def years_in(text):
    """The model years a line names, as a first and a last."""
    if re.search(r"[A-Z0-9]{17}", text.upper().replace(" ", "")):
        return None
    found = [int(y) for y in re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", text.translate(_LETTERS))]
    return (min(found), max(found)) if found else None


def names_production_dates(text):
    words = normalized(text).split()
    return any(month in words for month in MONTHS) or re.search(r"\d{1,2}/\d{1,2}/\d{4}", text) is not None


class Catalog:
    """The app's list of makes and models, with the other names the ministry writes them by."""

    def __init__(self, makes, aliases):
        self.makes = []
        for make in makes:
            extra = aliases.get(make["id"], {})
            models = []
            for model in make["models"]:
                names = {model["id"], model["en"], model["ar"], *extra.get(model["id"], [])}
                models.append((model["en"], sorted({normalized(n) for n in names if normalized(n)}, key=len, reverse=True)))
            names = {make["id"], make["en"], make["ar"], *extra.get("", [])}
            self.makes.append({
                "en": make["en"],
                "names": sorted({normalized(n) for n in names if normalized(n)}, key=len, reverse=True),
                "models": models,
            })

    @staticmethod
    def _finds(name, words):
        return f" {name} " in f" {words} "

    def makes_in(self, text):
        words = normalized(text)
        return [make for make in self.makes if any(self._finds(n, words) for n in make["names"])]

    def models_in(self, make, text):
        """The models a line names, longest names first so that "Range Rover Sport" is not
        also read as "Range Rover"."""
        words = f" {normalized(text)} "
        candidates = sorted(((n, en) for en, names in make["models"] for n in names), key=lambda c: -len(c[0]))
        found = []
        for name, english in candidates:
            if f" {name} " in words:
                words = words.replace(f" {name} ", " | ", 1)
                if english not in found:
                    found.append(english)
        return found


def vehicles(block, make, catalog):
    """Groups of models with the years each covers, in the order the picture lists them."""
    groups, waiting = [], None
    for text in block:
        models = catalog.models_in(make, text)
        span = years_in(text)
        if models:
            last = groups[-1] if groups else None
            if last and last["years"] is None and set(models) <= set(last["models"]):
                pass
            else:
                groups.append({"models": models, "years": None})
        if span:
            if groups and groups[-1]["years"] is None:
                groups[-1]["years"] = span
            elif not groups:
                waiting = span if waiting is None else (min(waiting[0], span[0]), max(waiting[1], span[1]))
    for group in groups:
        if group["years"] is None:
            group["years"] = waiting
    merged = []
    for group in groups:
        same = next((m for m in merged if m["years"] == group["years"]), None)
        if same:
            same["models"] += [m for m in group["models"] if m not in same["models"]]
        else:
            merged.append({"models": list(group["models"]), "years": group["years"]})
    return merged, waiting


def category(fault):
    words = normalized(fault)
    for key, signs in CATEGORIES:
        if any(normalized(sign) in words for sign in signs):
            return key
    return "other"


def _paragraph(lines):
    return " ".join(line.strip() for line in lines).strip()


def announcement(lines, catalog):
    """What one picture says, in the shape the list keeps, with what a person has to check."""
    parts = split(lines)
    if parts is None:
        return {"status": "needs-review", "notes": ["The recall heading was not found."], "vehicles": []}
    if parts["kind"] == "tires":
        return {"status": "skipped", "notes": ["A tire recall: not matched to a vehicle."], "vehicles": []}
    notes = []
    sections = parts["sections"]
    if parts["order"][:3] != ["fault", "action", "contact"] or not all(sections.values()):
        notes.append("The three sections were not read in order: check the fault and the remedy against the picture.")
    fault = _paragraph(sections["fault"])
    action = _paragraph(sections["action"])
    contact = "\n".join(sections["contact"]).strip()
    remedy = "\n\n".join(part for part in [action, contact] if part)
    if not fault or not remedy:
        notes.append("The fault or the remedy is empty.")

    block_text = " ".join(parts["block"])
    makes = (
        catalog.makes_in(block_text)
        or catalog.makes_in(" ".join([block_text, fault, action, contact]))
        # Some pictures name only the models, such as Discovery and Defender.
        or [make for make in catalog.makes if catalog.models_in(make, block_text)]
    )
    found = []
    if len(makes) != 1:
        notes.append("The make was not found." if not makes else "More than one make: " + ", ".join(m["en"] for m in makes) + ".")
    else:
        groups, waiting = vehicles(parts["block"], makes[0], catalog)
        if not groups:
            notes.append("No model of the app's list was found for " + makes[0]["en"] + ".")
        for group in groups:
            if group["years"] is None:
                notes.append("No model year for " + ", ".join(group["models"]) + ".")
            found.append({"make": makes[0]["en"], "models": group["models"], "years": list(group["years"]) if group["years"] else []})
    if any(names_production_dates(text) for text in parts["block"]):
        notes.append("The picture gives production dates, not model years: the years are a guess.")
    return {
        "status": "needs-review" if notes else "ready",
        "notes": notes,
        "vehicleLines": parts["block"],
        "vehicles": found,
        "category": category(fault),
        "fault": fault,
        "remedy": remedy,
    }


def repeats(candidate, earlier):
    """Whether an announcement seems to say again what an earlier one said."""
    def key(a):
        return sorted((v["make"], tuple(v["models"]), tuple(v["years"])) for v in a.get("vehicles", []))
    if not candidate.get("vehicles") or key(candidate) != key(earlier):
        return False
    return difflib.SequenceMatcher(None, candidate.get("fault", ""), earlier.get("fault", "")).ratio() >= 0.8
