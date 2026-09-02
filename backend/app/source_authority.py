from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlsplit


SCHEMA_VERSION = "parallm-source-authority/v1"


def _host_matches(host: str, *domains: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _grade(
    host: str,
    source_class: str,
    authority_score: int,
    evidence_role: str,
    *,
    evidence_eligible: bool,
    standalone_eligible: bool,
    memory_eligible: bool,
    requires_corroboration: bool,
    reason: str,
    caveat: str,
) -> Dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "host": host,
        "sourceClass": source_class,
        "authorityScore": max(0, min(100, int(authority_score))),
        "evidenceRole": evidence_role,
        "evidenceEligible": bool(evidence_eligible),
        "standaloneEligible": bool(standalone_eligible),
        "memoryEligible": bool(memory_eligible),
        "requiresCorroboration": bool(requires_corroboration),
        "reason": reason,
        "caveat": caveat,
    }


def grade_source(url: Any) -> Dict[str, Any]:
    candidate = str(url or "").strip()
    parsed = urlsplit(candidate)
    host = str(parsed.hostname or "").lower().strip(".")
    path = str(parsed.path or "/").lower()
    if not host:
        return _grade(
            "",
            "invalid_source",
            0,
            "excluded",
            evidence_eligible=False,
            standalone_eligible=False,
            memory_eligible=False,
            requires_corroboration=True,
            reason="The source does not have a valid network host.",
            caveat="Do not use or retain this source.",
        )

    if _host_matches(host, "4chan.org", "4channel.org"):
        return _grade(
            host,
            "anonymous_imageboard",
            2,
            "excluded",
            evidence_eligible=False,
            standalone_eligible=False,
            memory_eligible=False,
            requires_corroboration=True,
            reason="Anonymous, mutable, and unaccountable user content is not admissible evidence.",
            caveat="It may suggest a search lead, but must not support a claim or enter durable memory.",
        )

    if _host_matches(host, "arxiv.org"):
        return _grade(
            host,
            "research_preprint",
            84,
            "primary",
            evidence_eligible=True,
            standalone_eligible=False,
            memory_eligible=True,
            requires_corroboration=True,
            reason="arXiv provides stable, attributable research manuscripts and version history.",
            caveat="A preprint is not proof of peer review; verify version, methods, and later publication status.",
        )

    if _host_matches(
        host,
        "nist.gov",
        "cisa.gov",
        "rfc-editor.org",
        "ietf.org",
        "w3.org",
        "who.int",
        "nih.gov",
        "ncbi.nlm.nih.gov",
        "europa.eu",
    ) or host.endswith(".gov") or ".gov." in host:
        return _grade(
            host,
            "official_or_standards_source",
            94,
            "primary",
            evidence_eligible=True,
            standalone_eligible=True,
            memory_eligible=True,
            requires_corroboration=False,
            reason="The source is an official authority, standards body, or public institution.",
            caveat="Confirm jurisdiction, revision, effective date, and whether the document is normative.",
        )

    if host.endswith(".edu") or ".edu." in host or ".ac." in host:
        return _grade(
            host,
            "academic_institution",
            82,
            "supporting",
            evidence_eligible=True,
            standalone_eligible=False,
            memory_eligible=True,
            requires_corroboration=True,
            reason="The source is attributable to an academic institution.",
            caveat="Institutional hosting does not establish that every page is peer reviewed or current.",
        )

    if _host_matches(host, "github.com", "gitlab.com"):
        return _grade(
            host,
            "code_repository",
            72,
            "supporting",
            evidence_eligible=True,
            standalone_eligible=False,
            memory_eligible=True,
            requires_corroboration=True,
            reason="A versioned repository can be primary evidence for its own code, releases, and maintainers.",
            caveat="Repository popularity is not validation; bind claims to a revision and inspect provenance.",
        )

    if host.startswith("docs.") or any(marker in path for marker in ("/docs", "/documentation", "/manual", "/reference", "/spec")):
        return _grade(
            host,
            "technical_documentation_candidate",
            76,
            "supporting",
            evidence_eligible=True,
            standalone_eligible=False,
            memory_eligible=True,
            requires_corroboration=True,
            reason="The URL presents as attributable product or technical documentation.",
            caveat="Confirm publisher ownership, product version, and whether the page is normative or community-authored.",
        )

    if _host_matches(host, "wikipedia.org"):
        return _grade(
            host,
            "secondary_reference",
            58,
            "supporting",
            evidence_eligible=True,
            standalone_eligible=False,
            memory_eligible=False,
            requires_corroboration=True,
            reason="The source is useful for orientation and discovery of attributable references.",
            caveat="Follow citations to primary sources before relying on the claim or retaining it as memory.",
        )

    if _host_matches(
        host,
        "reddit.com",
        "x.com",
        "twitter.com",
        "facebook.com",
        "quora.com",
        "tiktok.com",
        "discord.com",
        "discord.gg",
    ):
        return _grade(
            host,
            "community_or_social_report",
            28,
            "lead_only",
            evidence_eligible=False,
            standalone_eligible=False,
            memory_eligible=False,
            requires_corroboration=True,
            reason="User-generated social content is weakly attributable, mutable, and not independently verified.",
            caveat="Use only to discover a claim that can be checked against admissible primary or authoritative sources.",
        )

    return _grade(
        host,
        "general_web_source",
        50,
        "supporting",
        evidence_eligible=True,
        standalone_eligible=False,
        memory_eligible=False,
        requires_corroboration=True,
        reason="The source is attributable enough to inspect but has no recognized authority classification.",
        caveat="Corroborate material claims and identify the publisher, author, date, and primary evidence before retention.",
    )


def source_selection_key(item: Dict[str, Any]) -> tuple[int, int, int]:
    grade = item.get("sourceAuthority") if isinstance(item.get("sourceAuthority"), dict) else {}
    return (
        -int(bool(grade.get("standaloneEligible"))),
        -int(grade.get("authorityScore") or 0),
        int(item.get("rank") or 9999),
    )
