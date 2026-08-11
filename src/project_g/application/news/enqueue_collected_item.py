from project_g.application.news.enqueue_metadata_processing import (
    EnqueueNewsMetadataProcessing,
)
from project_g.application.news.register_collected_item import (
    CollectedNewsRegistrationStatus,
    RegisterCollectedNewsItemResult,
)
from project_g.ports.queue import (
    JobSnapshot,
    QueueProvider,
)


class InvalidCollectedNewsRegistrationError(RuntimeError):
    """Raised when a registration result is inconsistent."""


class EnqueueRegisteredCollectedNewsItem:
    def __init__(
        self,
        *,
        queue_provider: QueueProvider,
    ) -> None:
        self._enqueue_metadata = EnqueueNewsMetadataProcessing(
            queue_provider=queue_provider,
        )

    def execute(
        self,
        registration: RegisterCollectedNewsItemResult,
    ) -> JobSnapshot | None:
        if registration.status is CollectedNewsRegistrationStatus.DUPLICATE:
            return None

        processing_job = registration.processing_job

        if processing_job is None:
            raise InvalidCollectedNewsRegistrationError(
                "Registered news item must include a processing job"
            )

        return self._enqueue_metadata.execute(processing_job)
