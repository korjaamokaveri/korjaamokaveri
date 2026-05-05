import re


RISK_KEYWORDS = {
    "high": ["airbag", "turvatyyny", "jarru", "brake", "polttoaine", "bensa", "diesel", "korkeajännite", "hybrid", "srs", "abs"],
    "medium": ["akku", "sähkö", "momentti", "kiristä", "nosta", "tunkki", "jäähdytysneste", "öljy", "paine"],
}

DIFFICULTY_KEYWORDS = {
    "hard": ["irrota apurunko", "jakohihna", "kytkin", "vaihdelaatikko", "moottori", "turbo", "purista", "erikoistyökalu", "kalibroi"],
    "medium": ["pultit", "momentti", "nosta", "tunkki", "suojamuovi", "liitin", "tiiviste", "ilmaa", "neste"],
}

IMPORTANT_KEYWORDS = [
    "airbag", "turvatyyny", "akku", "momentti", "kalibroi", "abs", "srs",
    "jarru", "polttoaine", "korkeajännite", "varo", "odota"
]


def _clean(value):
    return (value or "").strip()


def _normalize_step_text(text):
    text = _clean(text)
    text = re.sub(r"^\d+[\.\)]\s*", "", text)
    text = text.strip(" -•\t")
    return text


def _split_sentences(text: str):
    text = _clean(text)
    if not text:
        return []

    raw = re.split(r"[\n.;]+", text)
    cleaned = []

    for item in raw:
        value = _normalize_step_text(item)
        if value and len(value) > 2:
            cleaned.append(value)

    return cleaned


def parse_steps(text: str):
    steps = []

    for index, step in enumerate(_split_sentences(text), start=1):
        lower = step.lower()
        is_important = any(keyword in lower for keyword in IMPORTANT_KEYWORDS)

        steps.append({
            "order": index,
            "text": step,
            "important": is_important,
        })

    return steps


def parse_tools(text: str):
    text = _clean(text)
    if not text:
        return []

    raw = re.split(r"[,;\n]+", text)
    tools = []

    for tool in raw:
        value = _clean(tool)
        value = re.sub(r"\s+", " ", value)
        if value and value.lower() not in [t.lower() for t in tools]:
            tools.append(value)

    return tools


def parse_notes(text: str):
    notes = []

    for note in _split_sentences(text):
        lower = note.lower()
        notes.append({
            "text": note,
            "important": any(keyword in lower for keyword in IMPORTANT_KEYWORDS),
        })

    return notes


def estimate_difficulty(steps, tools, notes):
    note_texts = [n["text"] for n in notes]
    combined = " ".join([s["text"] for s in steps] + tools + note_texts).lower()

    if len(steps) >= 10 or any(word in combined for word in DIFFICULTY_KEYWORDS["hard"]):
        return {
            "label": "Vaativa",
            "level": "hard",
            "description": "Vaatii kokemusta, tarkkuutta tai erikoistyökaluja.",
        }

    if len(steps) >= 5 or any(word in combined for word in DIFFICULTY_KEYWORDS["medium"]):
        return {
            "label": "Keskitaso",
            "level": "medium",
            "description": "Sopii harrastajalle, jos perustyökalut ja turvallinen työskentely onnistuvat.",
        }

    return {
        "label": "Helppo",
        "level": "easy",
        "description": "Yksinkertainen työ, jos perustaidot ja oikeat työkalut ovat kunnossa.",
    }


def estimate_time(steps, difficulty):
    count = len(steps)

    if difficulty["level"] == "hard":
        return "2–5 h"
    if difficulty["level"] == "medium":
        return "1,5–3 h" if count >= 8 else "45–90 min"
    return "45–90 min" if count >= 5 else "15–45 min"


def estimate_risk_level(steps, tools, notes):
    note_texts = [n["text"] for n in notes]
    combined = " ".join([s["text"] for s in steps] + tools + note_texts).lower()

    if any(word in combined for word in RISK_KEYWORDS["high"]):
        return {
            "label": "Korkea huomio",
            "level": "high",
            "description": "Tarkista turvallisuus, oikeat momentit ja valmistajan ohjeet ennen työn aloittamista.",
        }

    if any(word in combined for word in RISK_KEYWORDS["medium"]):
        return {
            "label": "Normaali varovaisuus",
            "level": "medium",
            "description": "Huomioi nostaminen, sähköliitännät, nesteet ja kiristykset.",
        }

    return {
        "label": "Matala",
        "level": "low",
        "description": "Ei tunnistettu erityisiä riskisanoja, mutta työ tehdään aina omalla vastuulla.",
    }


def format_repair_guide(guide_row):
    if not guide_row:
        return None

    guide = dict(guide_row)

    steps = parse_steps(guide.get("steps"))
    tools = parse_tools(guide.get("tools"))
    notes = parse_notes(guide.get("notes"))

    difficulty = estimate_difficulty(steps, tools, notes)
    risk = estimate_risk_level(steps, tools, notes)

    guide["steps_parsed"] = steps
    guide["tools_parsed"] = tools
    guide["notes_parsed"] = notes
    guide["difficulty"] = difficulty
    guide["estimated_time"] = estimate_time(steps, difficulty)
    guide["risk"] = risk

    return guide