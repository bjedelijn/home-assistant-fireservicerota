"""Presentation only; never use display names as identity keys."""

def format_turnout_person(row: dict, mode: str = "role", *, assigned_role: str | None = None) -> str:
    roles = {
        "chauffeur": "Chauffeur/pompbediende",
        "pompbediende": "Chauffeur/pompbediende",
        "chauffeur/pompbediende": "Chauffeur/pompbediende",
        "bevelvoerder": "Bevelvoerder",
        "manschap": "Manschap",
        "officier van dienst": "Officier van Dienst",
    }
    role = roles.get((assigned_role or "").strip().casefold(), "Functie onbekend")
    if mode not in {"full", "first", "initial"}:
        return role
    name = row.get("user_name")
    if not isinstance(name, str) or not name.strip():
        return role
    if mode == "full":
        return name
    # Do not guess surname boundaries from a provider display name.
    first = row.get("first_name")
    last = row.get("last_name")
    if not isinstance(first, str) or not first.strip():
        return role
    if mode == "first":
        return first.strip()
    if isinstance(last, str) and last.strip():
        return f"{first.strip()} {last.strip()[0]}."
    return role
