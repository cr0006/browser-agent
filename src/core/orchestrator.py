"""Orchestrator - Main workflow coordinator."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import structlog

from src.config import Config
from src.core.browser_agent import BrowserAgent, PageState
from src.core.session import ActionRecord, Session
from src.intelligence.llm_client import Action, LLMClient
from src.intelligence.prompts import EXPLORATION_PROMPT, SYSTEM_PROMPT
from src.learning.confidence_scorer import ConfidenceMetrics, ConfidenceScorer
from src.learning.memory_store import MemoryStore
from src.notifications.email_service import EmailService

logger = structlog.get_logger()


@dataclass
class LearningResult:
    """Result of a learning session."""

    session: Session
    metrics: ConfidenceMetrics
    success: bool
    message: str
    report: str = ""


class Orchestrator:
    """Coordinates all components for the learning workflow."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.config.ensure_directories()

        self.browser = BrowserAgent(self.config)
        self.llm = LLMClient(self.config)
        self.memory = MemoryStore(self.config.patterns_dir)
        self.scorer = ConfidenceScorer(self.config.confidence_threshold)
        self.email = EmailService(self.config)

    async def learn(self, url: str) -> LearningResult:
        """Run a learning session on a URL."""
        session = Session.create(url)
        domain = urlparse(url).netloc

        logger.info("Starting learning session", session_id=session.session_id, url=url)

        try:
            # Launch browser and navigate
            await self.browser.launch()
            page_state = await self.browser.navigate(url)

            # Update session with initial page info
            session.total_elements_found = len(page_state.interactive_elements)
            session.metadata["initial_title"] = page_state.title

            # Main learning loop
            metrics = await self._learning_loop(session, page_state, domain)

            # Mark session complete
            session.status = "completed"
            session.confidence_score = metrics.weighted_score
            session.save(self.config.sessions_dir)

            # Generate report if learning was successful
            report = ""
            if self.scorer.is_learning_complete(metrics):
                # Generate LLM report could be added here
                report = self._generate_summary_report(session, metrics)

            # Send completion email
            await self.email.send_learning_complete(session, metrics, report)

            return LearningResult(
                session=session,
                metrics=metrics,
                success=True,
                message="Learning completed successfully",
                report=report,
            )

        except Exception as e:
            logger.error("Learning failed", error=str(e), session_id=session.session_id)
            session.status = "failed"
            session.save(self.config.sessions_dir)

            # Send error notification
            await self.email.send_error_alert(session, str(e))

            return LearningResult(
                session=session,
                metrics=ConfidenceMetrics(0, 0, 0, 0),
                success=False,
                message=f"Learning failed: {str(e)}",
            )

        finally:
            await self.browser.close()

    async def _learning_loop(
        self,
        session: Session,
        initial_state: PageState,
        domain: str,
    ) -> ConfidenceMetrics:
        """Execute the main learning loop."""
        page_state = initial_state
        explored_selectors: set[str] = set()
        metrics = ConfidenceMetrics(0, 0, 0, 0)

        for iteration in range(self.config.max_iterations):
            logger.info(
                "Learning iteration",
                iteration=iteration + 1,
                max=self.config.max_iterations,
                confidence=metrics.weighted_score,
            )

            # Build context for LLM
            user_prompt = self._build_exploration_prompt(session, page_state, explored_selectors)

            # Get LLM decision
            action = await self.llm.decide_action(
                SYSTEM_PROMPT,
                user_prompt,
                page_state.screenshot_base64,
            )

            # Check for completion signal from LLM
            if action.type == "complete":
                logger.info("LLM signaled completion", reasoning=action.reasoning)
                break

            # Execute action
            result = await self.browser.execute_action(
                action.type,
                action.selector,
                action.value,
            )

            # Record action
            action_record = ActionRecord(
                timestamp=datetime.now().isoformat(),
                action_type=action.type,
                selector=action.selector,
                value=action.value,
                reasoning=action.reasoning,
                success=result.success,
                page_url=page_state.url,
                screenshot_path=page_state.screenshot_path,
            )
            session.add_action(action_record)

            # Update explored selectors
            if action.selector:
                explored_selectors.add(action.selector)
                session.elements_explored = len(explored_selectors)

            # Update memory with pattern
            if action.selector:
                self.memory.add_pattern_from_action(
                    domain=domain,
                    element_type=action.type,
                    selector=action.selector,
                    action_type=action.type,
                    success=result.success,
                )

            # Update confidence
            metrics = self.scorer.update(session)
            session.confidence_score = metrics.weighted_score

            # Check if learning is complete (require minimum pages visited)
            unique_urls = set(a.page_url for a in session.actions)
            if self.scorer.is_learning_complete(metrics, len(unique_urls)):
                logger.info("Confidence threshold reached, completing learning")
                break

            # Get new page state
            try:
                page_state = await self.browser.get_page_state()
                # Update total elements if we found more
                new_count = len(page_state.interactive_elements)
                if new_count > session.total_elements_found:
                    session.total_elements_found = new_count
            except Exception as e:
                logger.warning("Failed to get page state", error=str(e))

            # Small delay to be respectful
            await asyncio.sleep(self.config.action_delay_ms / 1000)

        return metrics

    def _build_exploration_prompt(
        self,
        session: Session,
        page_state: PageState,
        explored_selectors: set[str],
    ) -> str:
        """Build the exploration prompt for the LLM."""
        # Format elements list
        elements_list = []
        for elem in page_state.interactive_elements[:30]:  # Limit to 30
            explored_marker = "✓ " if elem.selector in explored_selectors else "  "
            elements_list.append(f"{explored_marker}{elem}")

        # Format action history
        action_history = []
        for action in session.actions[-5:]:  # Last 5 actions
            status = "✓" if action.success else "✗"
            action_history.append(f"{status} {action.action_type}: {action.selector or 'N/A'}")

        return EXPLORATION_PROMPT.format(
            url=page_state.url,
            title=page_state.title,
            element_count=len(page_state.interactive_elements),
            elements_list="\n".join(elements_list) or "No interactive elements found",
            dom_tree=page_state.dom_tree[:8000],  # Truncate DOM
            action_count=len(session.actions),
            elements_explored=session.elements_explored,
            total_elements=session.total_elements_found,
            confidence=session.confidence_score,
            action_history="\n".join(action_history) or "No actions taken yet",
        )

    def _generate_summary_report(self, session: Session, metrics: ConfidenceMetrics) -> str:
        """Generate a text summary of the learning session."""
        unique_urls = set(a.page_url for a in session.actions)
        action_types = {}
        for a in session.actions:
            action_types[a.action_type] = action_types.get(a.action_type, 0) + 1

        report = f"""
Learning Session Summary
========================
Target: {session.target_url}
Session ID: {session.session_id}
Duration: {session.duration_seconds:.0f} seconds

Metrics:
- Total Actions: {len(session.actions)}
- Success Rate: {metrics.success_rate:.0%}
- Coverage: {metrics.coverage_score:.0%}
- Confidence: {metrics.weighted_score:.0%}

Exploration:
- Unique Pages Visited: {len(unique_urls)}
- Elements Explored: {session.elements_explored}/{session.total_elements_found}

Action Breakdown:
{chr(10).join(f'- {k}: {v}' for k, v in action_types.items())}
        """
        return report.strip()

    async def resume(self, session_id: str) -> LearningResult:
        """Resume a previously saved session."""
        session = Session.load(session_id, self.config.sessions_dir)
        return await self.learn(session.target_url)
