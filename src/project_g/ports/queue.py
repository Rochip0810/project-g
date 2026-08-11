from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

type JobScalar = str | int | float | bool | None
type JobArgument = JobScalar | list[JobScalar] | dict[str, JobScalar]


class QueueName(StrEnum):
    DEFAULT = "default"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: str
    queue: QueueName
    status: str


class QueueProvider(Protocol):
    def enqueue(
        self,
        queue_name: QueueName,
        function_path: str,
        *,
        args: Sequence[JobArgument] = (),
        kwargs: Mapping[str, JobArgument] | None = None,
        job_id: str | None = None,
        description: str | None = None,
    ) -> JobSnapshot:
        """Enqueue one background job."""
        ...
