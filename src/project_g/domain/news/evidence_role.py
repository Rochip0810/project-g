from enum import StrEnum


class EvidenceRole(StrEnum):
    TARGET = "target"
    COMPARISON = "comparison"
    TEAM_CONTEXT = "team_context"
