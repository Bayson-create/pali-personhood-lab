"""Evidence IDs shared with the static lab; no locator is invented when V4 resolution is absent."""
EVIDENCE_IDS = {
    "sn12.23", "mn18", "sn22.59", "sn35.23", "mn10", "dn22",
    "abhidhamma.citta-vithi", "research.five-aggregates",
}


def has_evidence(evidence_id: str) -> bool:
    return evidence_id in EVIDENCE_IDS
