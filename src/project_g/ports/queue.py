from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

JobScalar: TypeAlias = str | int | float | bool | None
JobArgument: TypeAlias = JobScalar | list[JobScalar] | dict[str, JobScalar]


class QueueName(StrEnum):
    DEFAULT = "default"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: str
    queue: QueueName
    status: str
