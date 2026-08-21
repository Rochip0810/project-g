from project_g.domain.news.priority_analysis import (
    NewsPriorityAnalysis,
    NewsPriorityStatus,
)
from project_g.ports.queue import (
    JobSnapshot,
    QueueName,
    QueueProvider,
)

NEWS_PRIORITY_WORKER_FUNCTION = "project_g.interfaces.workers.jobs.process_news_priority"


class NewsPriorityAnalysisNotPendingError(RuntimeError):
    def __init__(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> None:
        super().__init__("Only pending news priority analyses can be enqueued")
        self.analysis = analysis


class EnqueueNewsPriorityAnalysis:
    def __init__(
        self,
        *,
        queue_provider: QueueProvider,
    ) -> None:
        self._queue_provider = queue_provider

    def execute(
        self,
        analysis: NewsPriorityAnalysis,
    ) -> JobSnapshot:
        if analysis.status is not NewsPriorityStatus.PENDING:
            raise NewsPriorityAnalysisNotPendingError(analysis)

        return self._queue_provider.enqueue(
            QueueName.DEFAULT,
            NEWS_PRIORITY_WORKER_FUNCTION,
            args=[
                str(analysis.intake_id),
            ],
            job_id=(f"news-priority-{analysis.analysis_id}"),
            description=(f"Analyze news priority for intake {analysis.intake_id}"),
        )
