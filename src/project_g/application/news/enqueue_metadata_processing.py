from project_g.domain.news.processing_job import (
    NewsProcessingJob,
    NewsProcessingStatus,
)
from project_g.ports.queue import (
    JobSnapshot,
    QueueName,
    QueueProvider,
)

NEWS_METADATA_WORKER_FUNCTION = "project_g.interfaces.workers.jobs.process_news_metadata"


class NewsProcessingJobNotPendingError(RuntimeError):
    def __init__(
        self,
        job: NewsProcessingJob,
    ) -> None:
        super().__init__("Only pending news processing jobs can be enqueued")
        self.job = job


class EnqueueNewsMetadataProcessing:
    def __init__(
        self,
        *,
        queue_provider: QueueProvider,
    ) -> None:
        self._queue_provider = queue_provider

    def execute(
        self,
        job: NewsProcessingJob,
    ) -> JobSnapshot:
        if job.status is not NewsProcessingStatus.PENDING:
            raise NewsProcessingJobNotPendingError(job)

        return self._queue_provider.enqueue(
            QueueName.DEFAULT,
            NEWS_METADATA_WORKER_FUNCTION,
            args=[
                str(job.intake_id),
            ],
            job_id=(f"news-metadata-{job.job_id}"),
            description=(f"Process news metadata for intake {job.intake_id}"),
        )
