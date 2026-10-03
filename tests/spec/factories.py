"""Shared golden spec for tests."""

from homelab_creator.spec.models import (
    CompromisePath,
    Difficulty,
    Host,
    LabSpec,
    Network,
    VulnMode,
)


STUB_NOTE = "public writeup: default credentials on edge services"
STUB_CITATION = "https://example.invalid/bounty"


def beginner_company_spec(*, extra_path: bool = False) -> LabSpec:
    """Golden plan-ready catalog company (3 hosts, 2 hops) without compose files."""
    hosts = [
        Host(id="web", role="foothold", networks=["dmz"], stack=["nginx"], vulns=["default creds"]),
        Host(id="app", role="internal", networks=["int"], stack=["app"], vulns=["sqli class"]),
        Host(id="dc", role="crown_jewel", networks=["int"], stack=["samba"], vulns=["unconstrained delegation class"]),
    ]
    paths = [CompromisePath(hops=["web", "app", "dc"])]
    if extra_path:
        paths.append(CompromisePath(hops=["web", "dc"]))
    return LabSpec(
        idea="small company",
        idea_locked=True,
        form_completed=True,
        vuln_mode=VulnMode.agent,
        difficulty=Difficulty.beginner,
        hosts=hosts,
        networks=[Network(id="dmz", zone="dmz"), Network(id="int", zone="internal")],
        paths=paths,
        extra_paths_accepted=extra_path,
        catalog_ids=["web", "app", "dc"],
    )
