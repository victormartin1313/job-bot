"""Job relevance scoring (0–100), tuned to Victor Martin's resume.

Hard filters (score → 0 regardless):
  - Requires 3+ years experience
  - Explicitly requires current licensure (CPA required, not "CPA eligible")
  - Start date before July 2026 ("immediate", "ASAP", specific early dates)
  - Senior / Manager / Director / VP level

Scoring weights:
  Title match        40 pts
  Entry-level fit    25 pts  (includes accounting firm bonus)
  Dual-major fit     20 pts
  Location match     15 pts
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Accounting firms — company name boosts
# ---------------------------------------------------------------------------
BIG4 = ["deloitte", "ernst & young", "ey", "pwc", "pricewaterhousecoopers", "kpmg"]
REGIONAL_FIRMS = [
    "rsm", "bdo", "grant thornton", "moss adams", "cla", "crowe",
    "forvis", "plante moran", "cliftonlarsonallen", "baker tilly",
    "cbiz", "marcum", "cherry bekaert", "dixon hughes", "dhg",
]
ALL_ACCOUNTING_FIRMS = BIG4 + REGIONAL_FIRMS

# ---------------------------------------------------------------------------
# Hard-disqualify signals
# ---------------------------------------------------------------------------
DISQUALIFY_EXPERIENCE = [
    "3+ years", "3 or more years", "4+ years", "5+ years",
    "minimum 3 years", "minimum 4 years", "minimum 5 years",
    "3-5 years", "4-6 years", "5-7 years",
    "senior", "manager", "director", "vice president", "vp ", "principal",
    "lead ", "head of", "managing ",
]

DISQUALIFY_START = [
    "immediate start", "start immediately", "asap start",
    "january 2026", "february 2026", "march 2026",
    "april 2026", "may 2026", "june 2026",  # must start after July 1
]

DISQUALIFY_LICENSE = [
    "cpa required", "cpa license required", "active cpa",
    "licensed cpa", "must hold cpa",
]

# ---------------------------------------------------------------------------
# Positive keyword sets
# ---------------------------------------------------------------------------
TITLE_KEYWORDS = [
    "it audit",
    "technology risk",
    "erp",
    "accounting information systems",
    "ais",
    "systems auditor",
    "it advisory",
    "cybersecurity assurance",
    "information systems audit",
    "it risk",
    "technology audit",
    "digital trust",
    "soc",
    "sox",
    "sarbanes",
    "advisory",
    "risk advisory",
    "governance",
    "controls",
    "grc",
    "information technology audit",
    "it assurance",
    "data analytics",
    "risk and compliance",
]

ENTRY_LEVEL_SIGNALS = [
    "entry level", "entry-level", "associate", "staff",
    "0-2 years", "0-1 year", "new grad", "new graduate",
    "campus", "junior", "analyst", "2026",
    "class of 2026", "recent graduate", "college hire", "college graduate",
    "summer 2026", "fall 2026",
]

TARGET_SCHOOLS = ["arizona state", "asu", "w.p. carey", "wp carey"]

ACCOUNTING_KEYWORDS = [
    "accounting", "corporate accounting", "cpa", "audit", "assurance",
    "financial reporting", "gaap", "ifrs", "sox", "sarbanes",
    "internal controls", "risk management", "compliance", "governance",
    "advisory", "forensic",
]

TECH_KEYWORDS = [
    "computer information systems", "information systems", "information technology",
    "python", "sql", "excel", "java", "api", "erp", "sap", "oracle",
    "data analytics", "cybersecurity", "it", "technology", "systems",
    "database", "cloud", "automation", "digital", "software", "network",
    "security", "mis", "full-stack", "full stack",
    "process improvement", "systems thinking",
]


def _norm(text: str) -> str:
    return text.lower() if text else ""


def _count_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def _is_disqualified(title: str, description: str, company: str) -> bool:
    t = _norm(title)
    d = _norm(description)
    combined = t + " " + d

    # Senior/manager/etc in title
    senior_title = ["senior", "manager", "director", "vp", "vice president",
                    "principal", "lead ", "head of", "managing "]
    if any(s in t for s in senior_title):
        return True

    # Requires 3+ years experience
    if any(s in combined for s in DISQUALIFY_EXPERIENCE):
        return True

    # Early start date explicitly required
    if any(s in combined for s in DISQUALIFY_START):
        return True

    # Active CPA required (not just preferred/eligible)
    if any(s in combined for s in DISQUALIFY_LICENSE):
        return True

    return False


def score_job(
    title: str,
    description: Optional[str],
    location: Optional[str],
    target_locations: list[str],
    remote_ok: bool,
    company: str = "",
) -> float:
    """Return relevance score 0–100. Returns 0 for hard disqualifications."""
    t = _norm(title)
    d = _norm(description or "")
    c = _norm(company)
    combined = t + " " + d

    # Hard filter — experience/level/start date
    if _is_disqualified(t, d, c):
        return 0.0

    # Hard location filter — must be in target cities (Phoenix/Austin/Nashville/Charlotte) or remote
    loc = _norm(location or "")
    TARGET_CITIES = ["phoenix", "scottsdale", "tempe", "chandler", "mesa", "gilbert",
                     "austin", "round rock", "cedar park",
                     "nashville", "brentwood", "franklin",
                     "charlotte", "concord", "matthews"]
    is_remote = remote_ok and ("remote" in loc or "remote" in d)
    in_target_city = any(city in loc for city in TARGET_CITIES)
    # Accounting firms can bypass city filter ONLY when location is blank or national
    # (e.g. "Multiple Locations", "United States") — not when a specific wrong city is listed
    is_accounting_firm = any(f in c for f in ALL_ACCOUNTING_FIRMS)
    NATIONAL_LOC = ["multiple locations", "united states", "nationwide", "us", "national", "various"]
    is_national_location = not loc or any(n in loc for n in NATIONAL_LOC)
    firm_bypass = is_accounting_firm and is_national_location

    # Hard filter: must be from an accounting firm
    if not is_accounting_firm:
        return 0.0

    if not is_remote and not in_target_city and not firm_bypass:
        return 0.0

    # --- Title match (40 pts) ---
    title_hits = _count_hits(t, TITLE_KEYWORDS)
    title_score = min(40, title_hits * 13)

    strong_title = [
        "it audit", "technology risk", "accounting information systems",
        "systems auditor", "cybersecurity assurance", "it assurance",
        "it risk", "grc", "information systems audit",
    ]
    if any(kw in t for kw in strong_title):
        title_score = max(title_score, 28)

    # --- Entry-level + accounting firm fit (25 pts) ---
    entry_hits = _count_hits(combined, ENTRY_LEVEL_SIGNALS)
    entry_score = min(20, entry_hits * 7)

    # Big 4 / regional accounting firm = strong fit signal
    if any(firm in c for firm in BIG4):
        entry_score = min(25, entry_score + 8)
    elif any(firm in c for firm in REGIONAL_FIRMS):
        entry_score = min(25, entry_score + 5)

    # ASU / W.P. Carey campus recruiting
    if any(school in combined for school in TARGET_SCHOOLS):
        entry_score = min(25, entry_score + 4)

    # Internship titles are deprioritized (he already has one)
    if "intern" in t and not any(s in t for s in ["full time", "full-time", "permanent"]):
        entry_score = max(0, entry_score - 8)

    # --- Dual-major fit: accounting + CIS (20 pts) ---
    acc_hits = _count_hits(d, ACCOUNTING_KEYWORDS)
    tech_hits = _count_hits(d, TECH_KEYWORDS)
    if acc_hits >= 2 and tech_hits >= 2:
        dual_score = 20
    elif acc_hits >= 1 and tech_hits >= 2:
        dual_score = 15
    elif acc_hits >= 1 and tech_hits >= 1:
        dual_score = 10
    elif acc_hits >= 1 or tech_hits >= 2:
        dual_score = 5
    else:
        dual_score = 0

    if "python" in d or "sql" in d:
        dual_score = min(20, dual_score + 3)

    # Boost if job explicitly mentions information systems as a degree requirement
    IS_DEGREE = ["information systems", "computer information systems", "cis", "mis",
                 "management information systems", "information technology"]
    if any(kw in d for kw in IS_DEGREE):
        dual_score = min(20, dual_score + 4)

    # --- Location match (15 pts) — always full points if it passed the hard filter ---
    loc_score = 15

    total = title_score + entry_score + dual_score + loc_score
    return min(100.0, round(total, 1))


def should_store(score: float, min_store: float = 40.0) -> bool:
    return score >= min_store
