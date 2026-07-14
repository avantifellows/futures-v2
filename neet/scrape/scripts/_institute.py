"""
Shared institute-name cleaning for the NEET cutoff parsers.

Some counselling PDFs (notably the MCC All India Quota file, and partly
Karnataka) pack the full postal address into the institute cell:

    "AIIMS, New Delhi,AIIMS ANSARI NAGAR EAST AUROBINDO MARG NEW DELHI 110029,
     Delhi (NCT), 110029"

That is an extraction artifact, so we resolve it here at the parser layer (not
downstream): split into a clean display NAME (+ city) and a preserved ADDRESS.
The address is never discarded — it moves to its own column.

Parsers whose PDFs already give clean names (Gujarat, WB, MP, Punjab, Andhra)
can call split_institute too; it is a no-op for a plain name.
"""
from __future__ import annotations
import re


def split_institute(raw: str):
    """Return (name, address, state) from a raw institute string.

    Format seen in MCC/AIQ: 'Name, City,ADDRESS BLOB, State, pincode'.
    - name    = college name (+ city when the 2nd segment is clearly a city)
    - address = everything else, joined back with ", " (preserved, not dropped)
    - state   = best-effort from the trailing ', State, pincode'
    """
    raw = (raw or "").strip()
    # 'Name,,ADDRESS' — empty city slot means the address starts immediately.
    had_empty_city = ",," in raw.replace(", ,", ",,")
    parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
    if len(parts) <= 1:
        return raw, "", ""

    name = parts[0]
    city = parts[1] if len(parts) >= 2 else ""
    looks_like_city = (
        city
        and not had_empty_city
        and len(city) <= 18
        and not re.search(r"\d{3,}", city)
        and len(city.split()) <= 2  # a city, not an ALL-CAPS street phrase
    )
    if looks_like_city:
        name = f"{parts[0]}, {city}"
        rest = parts[2:]
    else:
        rest = parts[1:]

    state = ""
    if rest:
        tail = rest[-1]
        if re.fullmatch(r"\d{5,6}", tail) and len(rest) >= 2:
            state = rest[-2]
        elif not re.fullmatch(r"\d{5,6}", tail):
            state = tail
    address = ", ".join(rest)
    return name, address, state


# --- program (MBBS vs BDS) from the college name -------------------------------
# Several state files don't label the degree per row, but the college name does
# (Amogh's heuristic): a Medical college -> MBBS, a Dental college -> BDS. Indian
# college names fuse the M/D into acronyms (GMC/GSMC/BJMC/GDC = medical/dental),
# so match those acronym suffixes plus the spelled-out words. A name matching
# both (or neither) returns "REVIEW" for manual check rather than a guess.
_MED_RE = re.compile(r"MEDICAL|\bMED\b|[A-Z]MC\b|\bMC\b|IMS|\bMH\b")
_DEN_RE = re.compile(r"DENTAL|[A-Z]DC\b|\bDC\b")


def program_from_name(name: str) -> str:
    u = (name or "").upper()
    med = bool(_MED_RE.search(u))
    den = bool(_DEN_RE.search(u))
    if med and den:
        return "REVIEW"
    if med:
        return "MBBS"
    if den:
        return "BDS"
    return "REVIEW"
