from project_g.ports.news_relevance import (
    NewsRelevanceAnalyzer,
    NewsRelevanceAnalyzerInput,
    NewsRelevanceAnalyzerResult,
)


class FakeNewsRelevanceAnalyzer:
    def analyze(
        self,
        input_data: NewsRelevanceAnalyzerInput,
    ) -> NewsRelevanceAnalyzerResult:
        return NewsRelevanceAnalyzerResult(
            relevance_score=95,
            reason=(f"{input_data.title} directly concerns the Yomiuri Giants."),
        )


def _analyze(
    analyzer: NewsRelevanceAnalyzer,
) -> NewsRelevanceAnalyzerResult:
    return analyzer.analyze(
        NewsRelevanceAnalyzerInput(
            source_id="hochi_giants_articles",
            title="【巨人】ダルベックが20号",
            description=None,
        )
    )


def test_analyzer_port_accepts_fake_implementation() -> None:
    result = _analyze(FakeNewsRelevanceAnalyzer())

    assert result.relevance_score == 95
    assert "Yomiuri Giants" in result.reason
