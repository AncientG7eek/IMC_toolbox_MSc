from pathlib import Path
from dataclasses import dataclass, field
import logging


@dataclass
class CategoryMatch:
    category: str
    score: int
    evidence: list[str] = field(default_factory=list)


def classify_file(
    path: Path,
    config: dict,
    logger: logging.Logger,
) -> CategoryMatch:
    """Rank possible file categories using configured filename rules."""

    name = path.name.lower()
    suffix = path.suffix.lower()
    matches: list[CategoryMatch] = []

    categories = config.get("categories", {})

    for category, rules in categories.items():
        
        extensions = {
            extension.lower()
            for extension in rules.get("extensions", [])
        }

        # An extension mismatch makes the file ineligible for this category.
        if extensions and suffix not in extensions:
            score = -1 # Small punishment for a not matching extension.
            evidence = [f"extension not matched: {suffix}"]
        else:
            score = 0  # matched extension doesn't mean anything
            evidence = [f"extension matched: {suffix}"]

        strong_keywords = rules.get("strong_positive_keywords", [])
        weak_keywords = rules.get("weak_positive_keywords", [])
        negative_keywords = rules.get("negative_keywords", [])

        for keyword in strong_keywords:
            keyword = keyword.lower()
            if keyword in name:
                score += 2
                evidence.append(f"strong keyword: {keyword}")

        for keyword in weak_keywords:
            keyword = keyword.lower()
            if keyword in name:
                score += 1
                evidence.append(f"weak keyword: {keyword}")

        for keyword in negative_keywords:
            keyword = keyword.lower()
            if keyword in name:
                score -= 2
                evidence.append(f"negative keyword: {keyword}")

        matches.append(
            CategoryMatch(
                category=category,
                score=score,
                evidence=evidence,
            )
        )

    highest_score = max(
        (match.score for match in matches),
        default=0,
    )

    best_category = sorted(
        match.category
        for match in matches
        if match.score == highest_score
    )

    if len(best_category) >= 2:
        matches.append(
                CategoryMatch(
                    category=f"{' or '.join(best_category)}",
                    score=highest_score + 1, 
                    evidence=[f"{' and '.join(best_category)} got the same score"],
                )
            )

    matches.append(
        CategoryMatch(
            category="unclassified",
            score=-highest_score + 1, 
            evidence=["fallback category; all categories scored 0 or lower"],
        )
    )

    # Log every cetegory's score and evidence for diagnostics
    logger.debug(
        "Classification details for %s:\n%s",
        path,
        "\n".join(
            f"  {match.category}: score={match.score}; "
            f"evidence={'; '.join(match.evidence)}"
            for match in matches
        ),
    )

    # Highest score first; alphabetically resolve ties.
    matches.sort(
        key=lambda match: (-match.score, match.category)
    )

    best_match = matches[0]

    logger.debug(
        "Classification result: category=%s, score=%d",
        best_match.category,
        best_match.score,
    )

    return best_match