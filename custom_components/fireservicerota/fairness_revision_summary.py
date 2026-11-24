"""Privacy-minimized comparison of an incident's fairness proposal revisions.

An audit proposal is a text snapshot, not a verified crew. No names, user IDs,
membership IDs, addresses, or full audit rows are retained or returned.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any


def _proposal_tokens(proposal: dict[str, Any]) -> tuple[Counter, dict[str, int], bool]:
    rows = proposal.get("members")
    if not isinstance(rows, list) or len(rows) > 100:
        return Counter(), {}, False
    tokens: Counter = Counter()
    roles: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            return Counter(), {}, False
        name = row.get("name")
        role = row.get("role")
        if not isinstance(name, str) or not isinstance(role, str):
            return Counter(), {}, False
        name, role = " ".join(name.split()).casefold(), " ".join(role.split())
        if not name or not role or len(name) > 200 or len(role) > 80:
            return Counter(), {}, False
        # Temporary strings, never returned, logged or persisted.
        tokens[(name, role)] += 1
        roles[role] = roles.get(role, 0) + 1
    return tokens, roles, True


def _safe_timestamp(raw: Any) -> str | None:
    """Accept actual ISO timestamps only, never arbitrary audit strings."""
    if not isinstance(raw, str) or len(raw) > 50:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.isoformat()


# Only these generic role labels may leave the private audit context.
# Never echo arbitrary source labels, even in otherwise anonymous responses.
_SAFE_ROLES = {
    "aspirant manschap": "Aspirant Manschap",
    "bevelvoerder": "Bevelvoerder",
    "chauffeur": "Chauffeur",
    "manschap": "Manschap",
    "bediener redvoertuig": "Bediener Redvoertuig",
    "chauffeur redvoertuig": "Chauffeur Redvoertuig",
}
_OTHER_ROLE = "overig"


def _public_role(role: str) -> str:
    return _SAFE_ROLES.get(role.casefold().strip(), _OTHER_ROLE)


def _public_role_counts(raw: dict[str, int]) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for role, count in raw.items():
        label = _public_role(role)
        totals[label] = totals.get(label, 0) + count
    return [
        {"role": role, "proposed_seats": count}
        for role, count in sorted(totals.items())
    ]


def _role_change_counts(previous: Counter, current: Counter) -> list[dict[str, Any]]:
    """Aggregate anonymous additions/removals by fixed public role vocabulary."""
    removed = previous - current
    added = current - previous
    totals: dict[str, dict[str, int]] = {}
    for delta, field in (
        (added, "added_role_assignments"),
        (removed, "removed_role_assignments"),
    ):
        for (_name, private_role), count in delta.items():
            role = _public_role(private_role)
            row = totals.setdefault(
                role, {"added_role_assignments": 0, "removed_role_assignments": 0}
            )
            row[field] += count
    return [{"role": role, **counts} for role, counts in sorted(totals.items())]

def summarize_proposal_revisions(analysis: dict[str, Any]) -> dict[str, Any]:
    """Report counts only; never infer correctness, availability or actual crew."""
    result = {
        "audit_complete": analysis.get("audit_complete") is True,
        "audit_pagination_warning_present": bool(analysis.get("audit_pagination_warning")),
        "proposal_snapshots_seen": 0,
        "first_proposal_at": None,
        "latest_proposal_at": None,
        "initial_role_counts": [],
        "latest_role_counts": [],
        "added_role_assignments": None,
        "removed_role_assignments": None,
        "distinct_revisions": None,
        "net_role_assignment_changes": [],
        "transition_role_change_totals": [],
        "revision_timeline": [],
        "comparison_status": "unavailable",
        "current_duty_verified": False,
        "historical_eligibility_verified": False,
        "physical_vehicle_crew_verified": False,
        "selection_reason_verified": False,
        "interpretation": (
            "Textual proposed role changes only; no evidence of why a person was "
            "selected, of fairness weighting, or of actual attendance."
        ),
    }
    suggestions = analysis.get("fairness_suggestions")
    if not isinstance(suggestions, list):
        return result
    result["proposal_snapshots_seen"] = len(suggestions)
    if not result["audit_complete"]:
        result["comparison_status"] = "audit_incomplete"
        return result
    if not suggestions or len(suggestions) > 500:
        result["comparison_status"] = "no_proposals_or_limit_exceeded"
        return result
    proposals = sorted(
        suggestions,
        key=lambda row: str(row.get("at") or "") if isinstance(row, dict) else "",
    )
    if any(not isinstance(row, dict) for row in proposals):
        result["comparison_status"] = "invalid_proposals"
        return result
    parsed = [_proposal_tokens(row) for row in proposals]
    if not all(valid for _tokens, _roles, valid in parsed):
        result["comparison_status"] = "invalid_proposal_members"
        return result
    initial, initial_roles, _ = parsed[0]
    latest, latest_roles, _ = parsed[-1]
    safe_times = [_safe_timestamp(item.get("at")) for item in proposals]
    if any(at is None for at in safe_times):
        result["comparison_status"] = "invalid_proposal_timestamp"
        return result
    result["first_proposal_at"] = safe_times[0]
    result["latest_proposal_at"] = safe_times[-1]
    result["initial_role_counts"] = _public_role_counts(initial_roles)
    result["latest_role_counts"] = _public_role_counts(latest_roles)
    result["added_role_assignments"] = sum((latest - initial).values())
    result["removed_role_assignments"] = sum((initial - latest).values())
    result["distinct_revisions"] = sum(
        parsed[i][0] != parsed[i - 1][0] for i in range(1, len(parsed))
    )
    result["net_role_assignment_changes"] = _role_change_counts(initial, latest)
    cumulative: dict[str, dict[str, int]] = {}
    transitions = []
    for index in range(1, len(parsed)):
        before = parsed[index - 1][0]
        after = parsed[index][0]
        if before == after:
            continue
        changes = _role_change_counts(before, after)
        for change in changes:
            role = change["role"]
            counts = cumulative.setdefault(
                role, {"added_role_assignments": 0, "removed_role_assignments": 0}
            )
            counts["added_role_assignments"] += change["added_role_assignments"]
            counts["removed_role_assignments"] += change["removed_role_assignments"]
        transitions.append(
            {
                "proposal_index": index + 1,
                "at": safe_times[index],
                "changes_by_role": changes,
            }
        )
    result["transition_role_change_totals"] = [
        {"role": role, **counts} for role, counts in sorted(cumulative.items())
    ]
    result["revision_timeline"] = transitions
    result["comparison_status"] = "textual_snapshots_compared"
    return result


def summarize_registration_comparison(analysis: dict[str, Any]) -> dict[str, Any]:
    """Compare first/latest textual proposal with current registered membership outcomes."""
    result = {"status": "unavailable", "first_registration_available": False,
              "manual_correction_verified": False, "physical_departure_verified": False}
    if analysis.get("audit_complete") is not True:
        return result
    proposals = analysis.get("fairness_suggestions")
    snapshot = analysis.get("api_snapshot") or {}
    if not isinstance(proposals, list) or not proposals or snapshot.get("available") is not True:
        return result
    if any(not isinstance(p, dict) or _safe_timestamp(p.get("at")) is None
           or not _proposal_tokens(p)[2] for p in proposals):
        return result
    def timestamp(p):
        return datetime.fromisoformat(_safe_timestamp(p["at"]))
    proposals = sorted(proposals, key=timestamp)
    if len(proposals) > 1 and (
        timestamp(proposals[0]) == timestamp(proposals[1])
        or timestamp(proposals[-1]) == timestamp(proposals[-2])
    ):
        return result
    def ident(value):
        return str(value) if type(value) in (str, int) and str(value).isascii() and str(value).isdigit() else None
    def name(value):
        return " ".join(value.split()).casefold() if isinstance(value, str) else ""
    responses = snapshot.get("responses")
    if not isinstance(responses, list) or any(not isinstance(r, dict) for r in responses):
        return result
    names = {}
    statuses = {}
    for row in responses:
        key = ident(row.get("membership_id"))
        if key is None:
            continue
        if name(row.get("user_name")):
            names.setdefault(name(row["user_name"]), set()).add(key)
        raw = row.get("reported_status")
        status = raw if isinstance(raw, str) and raw in ("dispatched", "shown_up", "no_show", "unknown") else "other_or_missing"
        statuses.setdefault(key, set()).add(status)
    dispatched = {k for k, v in statuses.items() if v == {"dispatched"}}
    def compare(proposal):
        matched = set()
        unmatched = ambiguous = 0
        for row in proposal["members"]:
            candidates = names.get(name(row["name"]), set())
            if len(candidates) == 1:
                matched.update(candidates)
            elif candidates:
                ambiguous += 1
            else:
                unmatched += 1
        return {"matched_memberships": len(matched), "unmatched_seats": unmatched,
                "ambiguous_seats": ambiguous,
                "matched_registered_dispatched": len(matched & dispatched),
                "matched_registered_shown_up": sum(statuses[k] == {"shown_up"} for k in matched),
                "matched_registered_no_show": sum(statuses[k] == {"no_show"} for k in matched),
                "matched_other_or_ambiguous_outcome": sum(statuses[k] not in ({"dispatched"}, {"shown_up"}, {"no_show"}) for k in matched),
                "registered_dispatched_not_matched_to_proposal": len(dispatched - matched)}
    return {**result, "status": "observed_snapshots_compared",
            "first_proposal": compare(proposals[0]), "latest_proposal": compare(proposals[-1]),
            "current_registered_dispatched_memberships": len(dispatched),
            "interpretation": "Current administrative snapshot only; unmatched names and later corrections may affect comparison."}


def summarize_registration_diagnostics(analysis: dict[str, Any]) -> dict[str, Any]:
    """Inspect private audit text shapes and response multiplicity without echoing text."""
    import re
    from collections import Counter
    result = {"status": "unavailable", "old_new_status_values_verified": False,
              "manual_corrections_verified": False}
    if analysis.get("audit_complete") is not True:
        return result
    snapshot = analysis.get("api_snapshot") or {}
    if snapshot.get("available") is not True:
        return result
    vocabulary = {"dispatched", "shown_up", "no_show", "unknown", "acknowledged",
                  "pending", "expired", "rejected", "accepted", "cancelled",
                  "canceled", "arrived", "at_station", "responding"}
    def bucket(value):
        if value is None:
            return "null"
        if isinstance(value, str):
            normalized = value.strip().casefold()
            return normalized if normalized in vocabulary else ("empty" if not normalized else "other_string")
        return "boolean" if isinstance(value, bool) else "other_type"
    memberships = {}
    outcomes = Counter()
    pairs = Counter()
    for row in snapshot.get("responses") or []:
        if not isinstance(row, dict):
            continue
        status = bucket(row.get("reported_status"))
        outcomes[status] += 1
        pairs[bucket(row.get("status")) + "__" + status] += 1
        key = row.get("membership_id")
        if type(key) in (int, str) and str(key).isascii() and str(key).isdigit():
            memberships.setdefault(str(key), []).append(status)
    shapes = Counter()
    token_counts = Counter()
    transition_counts = Counter()
    timed_transitions = []
    subject_matches = Counter()
    reference_shapes = Counter()
    reference_matches = Counter()
    text_matches = Counter()
    def numeric(value):
        return str(value) if type(value) in (int, str) and str(value).isascii() and str(value).isdigit() else None
    indexes = {field: {} for field in ("user_id", "membership_id", "response_id")}
    for row in snapshot.get("responses") or []:
        if not isinstance(row, dict) or numeric(row.get("membership_id")) is None:
            continue
        for field, index in indexes.items():
            value = numeric(row.get(field))
            if value is not None:
                index.setdefault(value, set()).add(numeric(row["membership_id"]))
    chains = {}
    embedded_chains = {}
    embedded_events = Counter()
    embedded_round_events = []
    names = {}
    for row in snapshot.get("responses") or []:
        if not isinstance(row, dict):
            continue
        name, key = row.get("user_name"), row.get("membership_id")
        if isinstance(name, str) and name.strip() and type(key) in (int, str) and str(key).isascii() and str(key).isdigit():
            names.setdefault(" ".join(name.split()).casefold(), set()).add(str(key))
    labels = {
        "uitgerukt", "opgekomen", "niet opgekomen", "onbekend",
        "niet uitgerukt", "aanwezig", "afwezig", "niet aanwezig",
        "niet ingevuld", "geen", "wel opgekomen", "mee", "niet mee",
        "ingezet", "niet ingezet", "niet verschenen", "verschenen",
        "niet ter plaatse", "ter plaatse", "geen opkomst",
        "niet uitgerukt maar opgekomen", "opgekomen maar niet uitgerukt",
        "wel uitgerukt", "niet mee uitgerukt", "mee uitgerukt",
        "niet bekend", "niet geregistreerd", "niet van toepassing",
        "op de kazerne", "opkomst onbekend", "niet op komen dagen",
        "op komen dagen", "niet op komen dagen", "niet beschikbaar",
    } | vocabulary
    alternatives = "|".join(re.escape(v) for v in sorted(labels, key=len, reverse=True))
    transition_pattern = re.compile(
        r"\b(?:van|from)\s+['‘’“”\"]?(" + alternatives
        + r")['‘’“”\"]?\s+(?:naar|to)\s+['‘’“”\"]?("
        + alternatives + r")['‘’“”\"]?\s*[.!]?\s*$", re.I
    )
    for event in analysis.get("audit_turnout_status_changes") or []:
        if not isinstance(event, dict) or not isinstance(event.get("description"), str):
            shapes["missing_description"] += 1
            continue
        description = event["description"]
        if len(description) > 20000:
            shapes["oversize"] += 1
            continue
        lower = description.casefold()
        for label, pattern in {
            "arrow": r"→|->|⇒",
            "old_new_labels": r"\b(?:old|oud|vorige)\b.*\b(?:new|nieuw|nieuwe)\b",
            "from_to_labels": r"\b(?:from|van)\b.*\b(?:to|naar)\b",
            "html_markup": r"<[a-z][^>]*>",
            "multiline": r"\n",
        }.items():
            if re.search(pattern, lower, re.S):
                shapes[label] += 1
        match = transition_pattern.search(" ".join(lower.split()))
        stamp = _safe_timestamp(event.get("at"))
        pair = "unparsed"
        if match:
            old, new = (v.casefold().replace(" ", "_") for v in match.groups())
            pair = old + "__" + new
            transition_counts[pair] += 1
            shapes["recognized_same_label" if old == new else "recognized_different_label"] += 1
        else:
            shapes["unparsed_transition"] += 1
        subject = event.get("subject")
        for field, value in (event.get("_candidate_references") or {}).items():
            identifier = numeric(value)
            reference_shapes[field + ("__numeric" if identifier is not None else "__other")] += 1
            if identifier is not None:
                for kind, index in indexes.items():
                    matches = index.get(identifier, set())
                    if matches:
                        reference_matches[field + "__" + kind + ("__unique" if len(matches) == 1 else "__ambiguous")] += 1
        embedded_candidates = set()
        for source, value in (("subject", subject), ("description", description)):
            if not isinstance(value, str) or len(value) > 20000:
                continue
            normalized = " ".join(value.split()).casefold()
            matched = set()
            for name, keys in names.items():
                if len(name.split()) >= 2 and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", normalized):
                    matched.update(keys)
            if source == "subject":
                embedded_candidates = matched
            text_matches[source + ("__unique" if len(matched) == 1 else "__ambiguous" if matched else "__none")] += 1
        candidates = names.get(" ".join(subject.split()).casefold(), set()) if isinstance(subject, str) else set()
        if len(candidates) == 1:
            subject_matches["unique_exact_name"] += 1
            chains.setdefault(next(iter(candidates)), []).append((stamp, pair))
        elif candidates:
            subject_matches["ambiguous"] += 1
        else:
            subject_matches["unmatched"] += 1
        if len(embedded_candidates) == 1:
            key = next(iter(embedded_candidates))
            embedded_chains.setdefault(key, []).append((stamp, pair))
            embedded_round_events.append((stamp, key))
            embedded_events["unique"] += 1
        else:
            embedded_events["ambiguous_or_missing"] += 1
        timed_transitions.append((stamp, pair))
        tokens = set(re.findall(r"\b[a-z_]+\b", lower)) & vocabulary
        for token in tokens:
            token_counts[token] += 1
        if not tokens:
            shapes["no_known_status_tokens"] += 1
    chain_counts = Counter()
    final_comparison = Counter()
    mapping = {"uitgerukt": "dispatched", "onbekend": "unknown",
               "niet_opgekomen": "no_show", "opgekomen_maar_niet_uitgerukt": "shown_up"}
    for key, chain in embedded_chains.items():
        if embedded_events["ambiguous_or_missing"] or shapes["missing_description"] or shapes["oversize"] or any(stamp is None or pair == "unparsed" for stamp, pair in chain):
            chain_counts["incomplete"] += 1
            continue
        ordered = sorted((datetime.fromisoformat(stamp), pair) for stamp, pair in chain)
        if len({stamp for stamp, _ in ordered}) != len(ordered):
            chain_counts["ambiguous_order"] += 1
            continue
        transitions = [pair.split("__", 1) for _, pair in ordered]
        if any(a[1] != b[0] for a, b in zip(transitions, transitions[1:])):
            chain_counts["discontinuous"] += 1
            continue
        chain_counts["continuous"] += 1
        expected = mapping.get(transitions[-1][1])
        current = memberships.get(key, [])
        if expected is None or len(current) != 1:
            final_comparison["unresolved"] += 1
        else:
            final_comparison["candidate_match" if current[0] == expected else "candidate_mismatch"] += 1
    from .turnout_audit_summary import summarize_turnout_audit
    audit_summary = summarize_turnout_audit(analysis)
    rounds = []
    round_memberships = []
    proposal_memberships = {}
    proposals = analysis.get("fairness_suggestions") or []
    if proposals and all(isinstance(p, dict) and _safe_timestamp(p.get("at")) and _proposal_tokens(p)[2] for p in proposals):
        ordered_proposals = sorted(proposals, key=lambda p: datetime.fromisoformat(_safe_timestamp(p["at"])))
        for label, proposal in (("first", ordered_proposals[0]), ("latest", ordered_proposals[-1])):
            candidates = [names.get(" ".join(row["name"].split()).casefold(), set()) for row in proposal["members"]]
            if candidates and all(len(keys) == 1 for keys in candidates):
                proposal_memberships[label] = set().union(*candidates)
    if audit_summary.get("comparison_status") == "audit_markers_observed":
        for item in audit_summary["late_registration_rounds"]:
            first = datetime.fromisoformat(item["first_event_at"])
            last = datetime.fromisoformat(item["last_event_at"])
            counts = Counter(pair for stamp, pair in timed_transitions
                             if stamp is not None and first <= datetime.fromisoformat(stamp) <= last)
            round_keys = {key for stamp, key in embedded_round_events if stamp is not None and first <= datetime.fromisoformat(stamp) <= last}
            round_memberships.append(round_keys)
            rounds.append({"first_event_at": item["first_event_at"],
                           "candidate_proposal_overlap": {label: len(round_keys & keys) for label, keys in proposal_memberships.items()},
                           "event_count": item["event_count"],
                           "candidate_transitions": dict(counts),
                           "candidate_unique_memberships": len({key for stamp, key in embedded_round_events if stamp is not None and first <= datetime.fromisoformat(stamp) <= last}),
                           "unclassified_event_count": item["event_count"] - sum(counts.values())})
    return {**result, "status": "private_shapes_observed",
            "reported_status_counts": dict(outcomes), "status_pair_counts": dict(pairs),
            "memberships_with_multiple_response_rows": sum(len(v) > 1 for v in memberships.values()),
            "memberships_with_conflicting_status_buckets": sum(len(set(v)) > 1 for v in memberships.values()),
            "audit_description_shape_counts": dict(shapes),
            "audit_known_status_token_event_counts": dict(token_counts),
            "candidate_label_transitions": dict(transition_counts),
            "label_semantics_verified": False,
            "late_round_candidate_transitions": rounds,
            "candidate_round_overlap": [{"earlier_round": i + 1, "later_round": j + 1, "shared_memberships": len(a & b), "earlier_only": len(a - b), "later_only": len(b - a)} for i, a in enumerate(round_memberships) for j, b in enumerate(round_memberships) if j > i],
            "audit_subject_match_counts": dict(subject_matches),
            "candidate_reference_shapes": dict(reference_shapes),
            "candidate_reference_matches": dict(reference_matches),
            "candidate_embedded_name_matches": dict(text_matches),
            "reference_index_sizes": {k: len(v) for k, v in indexes.items()},
            "candidate_chain_source": "unique_embedded_full_name_in_subject",
            "candidate_chain_event_counts": dict(embedded_events),
            "candidate_membership_chain_counts": dict(chain_counts),
            "candidate_final_status_comparison": dict(final_comparison),
            "membership_identity_verified": False,
            "interpretation": "Token presence is not a parsed old/new transition; no private text returned."}
