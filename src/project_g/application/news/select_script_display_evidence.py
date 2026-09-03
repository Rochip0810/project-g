from project_g.domain.news.evidence_role import EvidenceRole
from project_g.ports.news_script import NewsScriptBackgroundFact


def select_script_display_evidence(
    facts: tuple[NewsScriptBackgroundFact, ...],
    *,
    limit: int = 4,
) -> tuple[NewsScriptBackgroundFact, ...]:
    if not 1 <= limit <= 4:
        raise ValueError("limit must be between 1 and 4")

    if not facts:
        return ()

    targets = [fact for fact in facts if fact.role is EvidenceRole.TARGET]
    comparisons = [fact for fact in facts if fact.role is EvidenceRole.COMPARISON]
    team_context = [fact for fact in facts if fact.role is EvidenceRole.TEAM_CONTEXT]

    selected: list[NewsScriptBackgroundFact] = []

    def add(
        fact: NewsScriptBackgroundFact,
    ) -> None:
        if fact not in selected and len(selected) < limit:
            selected.append(fact)

    # A comparison must show evidence from both sides.
    if targets and comparisons:
        add(targets[0])
        add(comparisons[0])

        for index in range(
            1,
            max(
                len(targets),
                len(comparisons),
            ),
        ):
            if index < len(targets):
                add(targets[index])

            if index < len(comparisons):
                add(comparisons[index])

        for fact in team_context:
            add(fact)

    else:
        for fact in targets:
            add(fact)

        for fact in comparisons:
            add(fact)

        for fact in team_context:
            add(fact)

    return tuple(selected)
