from project_g.domain.news.relevance_analysis import (
    NewsRelevanceAnalysis,
    NewsRelevanceStatus,
)
from project_g.ports.queue import (
    JobSnapshot,
    QueueName,
    QueueProvider,
)

NEWS_RELEVANCE_WORKER_FUNCTION = "project_g.interfaces.workers.jobs.process_news_relevance"


class NewsRelevanceAnalysisNotPendingError(RuntimeError):
    def __init__(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> None:
        super().__init__("Only pending news relevance analyses can be enqueued")
        self.analysis = analysis


class EnqueueNewsRelevanceAnalysis:
    def __init__(
        self,
        *,
        queue_provider: QueueProvider,
    ) -> None:
        self._queue_provider = queue_provider

    def execute(
        self,
        analysis: NewsRelevanceAnalysis,
    ) -> JobSnapshot:
        if analysis.status is not NewsRelevanceStatus.PENDING:
            raise NewsRelevanceAnalysisNotPendingError(analysis)

        return self._queue_provider.enqueue(
            QueueName.DEFAULT,
            NEWS_RELEVANCE_WORKER_FUNCTION,
            args=[
                str(analysis.intake_id),
            ],
            job_id=(f"news-relevance-{analysis.analysis_id}"),
            description=(f"Analyze news relevance for intake {analysis.intake_id}"),
        )
