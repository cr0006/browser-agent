"""Confidence Scorer - Evaluates learning progress."""

from dataclasses import dataclass

import structlog

from src.core.session import Session

logger = structlog.get_logger()


@dataclass
class ConfidenceMetrics:
    """Detailed breakdown of confidence scoring."""

    coverage_score: float  # % of elements explored
    success_rate: float  # % of successful actions
    pattern_stability: float  # Consistency of behavior
    exploration_depth: float  # How deep into the site

    @property
    def weighted_score(self) -> float:
        """Calculate weighted confidence score."""
        weights = {
            "coverage": 0.30,
            "success_rate": 0.25,
            "pattern_stability": 0.25,
            "exploration_depth": 0.20,
        }
        return (
            self.coverage_score * weights["coverage"]
            + self.success_rate * weights["success_rate"]
            + self.pattern_stability * weights["pattern_stability"]
            + self.exploration_depth * weights["exploration_depth"]
        )


class ConfidenceScorer:
    """Evaluates how well the agent has learned a website."""

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._visited_selectors: set[str] = set()
        self._successful_patterns: list[tuple[str, str]] = []  # (action_type, outcome)

    def update(self, session: Session) -> ConfidenceMetrics:
        """Update confidence based on session progress."""
        # Calculate coverage
        if session.total_elements_found > 0:
            coverage = session.elements_explored / session.total_elements_found
        else:
            coverage = 0.0

        # Calculate success rate
        success_rate = session.success_rate

        # Calculate pattern stability (based on action variety)
        pattern_stability = self._calculate_pattern_stability(session)

        # Calculate exploration depth (based on unique URLs/pages visited)
        exploration_depth = self._calculate_exploration_depth(session)

        metrics = ConfidenceMetrics(
            coverage_score=min(coverage, 1.0),
            success_rate=success_rate,
            pattern_stability=pattern_stability,
            exploration_depth=exploration_depth,
        )

        logger.info(
            "Confidence updated",
            weighted_score=metrics.weighted_score,
            coverage=metrics.coverage_score,
            success_rate=metrics.success_rate,
        )

        return metrics

    def _calculate_pattern_stability(self, session: Session) -> float:
        """Measure how stable patterns are (fewer errors = more stable)."""
        if len(session.actions) < 5:
            return 0.3  # Not enough data

        # Look at last N actions for stability
        recent_actions = session.actions[-10:]
        recent_success_rate = sum(1 for a in recent_actions if a.success) / len(recent_actions)

        # Also consider action type variety (good exploration = varied actions)
        action_types = set(a.action_type for a in session.actions)
        variety_bonus = min(len(action_types) / 4, 0.3)  # Up to 0.3 bonus for variety

        return min(recent_success_rate + variety_bonus, 1.0)

    def _calculate_exploration_depth(self, session: Session) -> float:
        """Measure how deeply the site has been explored."""
        if not session.actions:
            return 0.0

        # Count unique URLs visited
        unique_urls = set(a.page_url for a in session.actions)
        url_score = min(len(unique_urls) / 5, 0.5)  # Up to 0.5 for URL diversity

        # Count unique selectors interacted with
        unique_selectors = set(a.selector for a in session.actions if a.selector)
        selector_score = min(len(unique_selectors) / 20, 0.5)  # Up to 0.5 for element diversity

        return url_score + selector_score

    def is_learning_complete(self, metrics: ConfidenceMetrics, unique_pages: int = 1) -> bool:
        """Check if learning threshold has been reached.
        
        Args:
            metrics: The confidence metrics
            unique_pages: Number of unique pages visited (from session)
        """
        # Require minimum 4 pages visited (Personal, Sliders, Existing, Quote)
        MIN_PAGES_REQUIRED = 4
        
        if unique_pages < MIN_PAGES_REQUIRED:
            return False
        
        is_complete = metrics.weighted_score >= self.threshold

        if is_complete:
            logger.info(
                "Learning complete!",
                final_score=metrics.weighted_score,
                threshold=self.threshold,
            )

        return is_complete

    def record_interaction(self, selector: str, success: bool) -> None:
        """Record an interaction for pattern tracking."""
        self._visited_selectors.add(selector)
        if success:
            self._successful_patterns.append((selector, "success"))
