"""Lab specification models."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

REQUIRED_ROLES = ("foothold", "internal", "crown_jewel")
EXTRA_ROLES = ("workstation", "mail", "jump")
CATALOG_ROLES = REQUIRED_ROLES + EXTRA_ROLES
CatalogRole = Literal["foothold", "internal", "crown_jewel", "workstation", "mail", "jump"]

# (min hosts, min hop *edges* on the primary path). hops = len(host_ids) - 1.
DIFFICULTY_MINIMA: dict[str, tuple[int, int]] = {
    "beginner": (3, 2),
    "intermediate": (4, 3),
    "advanced": (5, 4),
    "senior_expert": (6, 5),
}

OBJECTIVE = "full_network_compromise"
COMPOSE_FILENAMES = (
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
)


class VulnMode(str, Enum):
    """Who authors issues: the operator, the planner, or both."""

    user = "user"
    agent = "agent"
    both = "both"


class Difficulty(str, Enum):
    """Planner size bar. ``user_defined`` means the operator supplied the chain."""

    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    senior_expert = "senior_expert"
    user_defined = "user_defined"


class LabUpStatus(str, Enum):
    """Compose lifecycle stored on the spec. Product success is ``running`` or ``skipped``."""

    not_run = "not_run"
    running = "running"
    skipped = "skipped"
    failed = "failed"


class ResearchNotes(BaseModel):
    """Whether research ran, plus assessment notes and citation URLs."""

    opted_in: bool = False
    notes: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


class Host(BaseModel):
    """One catalog host: role, networks, stack, issues, and accounts."""

    id: str
    role: CatalogRole
    networks: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)
    vulns: list[str] = Field(default_factory=list)
    accounts: list[str] = Field(default_factory=list)


class Network(BaseModel):
    """Named lab network. Isolation is enforced when Compose is rendered, not by ``zone``."""

    id: str
    zone: str = "internal"


class CompromisePath(BaseModel):
    """Ordered host ids on one path toward company control."""

    hops: list[str]


class Artifacts(BaseModel):
    """Filesystem paths of the generated compose directory, topology, and writeup."""

    compose_dir: str | None = None
    topology_path: str | None = None
    writeup_path: str | None = None


class LabSpec(BaseModel):
    """Interview and lab contract shared by the graph, workers, and validators.

    Artifact flags (``artifacts``, ``artifacts_stale``, ``lab_up_status``) live here,
    not as sibling graph keys. ``objective`` is always full network compromise.
    """

    idea: str = ""
    idea_locked: bool = False
    form_completed: bool = False
    objective: Literal["full_network_compromise"] = OBJECTIVE
    vuln_mode: VulnMode | None = None
    difficulty: Difficulty = Difficulty.user_defined
    research: ResearchNotes = Field(default_factory=ResearchNotes)
    hosts: list[Host] = Field(default_factory=list)
    networks: list[Network] = Field(default_factory=list)
    paths: list[CompromisePath] = Field(default_factory=list)
    extra_paths_accepted: bool = False
    catalog_ids: list[str] = Field(default_factory=list)
    artifacts: Artifacts = Field(default_factory=Artifacts)
    artifacts_stale: bool = False
    lab_up_status: LabUpStatus = LabUpStatus.not_run
    user_vulns: list[str] = Field(default_factory=list)
