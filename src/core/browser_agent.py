"""Browser Agent - Playwright wrapper for browser control."""

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import structlog
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.config import Config

logger = structlog.get_logger()


@dataclass
class Element:
    """Represents an interactive element on the page."""

    tag: str
    selector: str
    text: str
    element_type: str  # button, link, input, etc.
    attributes: dict[str, str]
    bounds: dict[str, float] | None = None

    def __str__(self) -> str:
        """Human-readable representation."""
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"[{self.element_type}] {self.tag}: {text_preview}"


@dataclass
class PageState:
    """Current state of a browser page."""

    url: str
    title: str
    dom_tree: str
    interactive_elements: list[Element]
    screenshot_base64: str
    screenshot_path: str | None
    viewport_width: int
    viewport_height: int
    timestamp: str


@dataclass
class ActionResult:
    """Result of executing an action."""

    success: bool
    message: str
    new_url: str | None = None
    error: str | None = None


class BrowserAgent:
    """Manages browser interactions via Playwright."""

    def __init__(self, config: Config):
        self.config = config
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def launch(self) -> None:
        """Launch the browser."""
        logger.info("Launching browser", headless=self.config.headless)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
        )
        self._context = await self._browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            }
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.config.timeout_ms)

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    async def navigate(self, url: str) -> PageState:
        """Navigate to a URL and return page state."""
        if not self._page:
            raise RuntimeError("Browser not launched. Call launch() first.")

        logger.info("Navigating to URL", url=url)
        await self._page.goto(url, wait_until="domcontentloaded")
        await self._page.wait_for_load_state("networkidle")

        return await self.get_page_state()

    async def get_page_state(self, save_screenshot: bool = True) -> PageState:
        """Capture current page state including DOM and screenshot."""
        if not self._page:
            raise RuntimeError("Browser not launched.")

        # Capture screenshot
        screenshot_bytes = await self._page.screenshot(full_page=False)
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Save screenshot to file if requested
        screenshot_path = None
        if save_screenshot:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = str(
                self.config.screenshots_dir / f"screenshot_{timestamp}.png"
            )
            self.config.screenshots_dir.mkdir(parents=True, exist_ok=True)
            with open(screenshot_path, "wb") as f:
                f.write(screenshot_bytes)

        # Extract interactive elements
        elements = await self._extract_interactive_elements()

        # Get simplified DOM
        dom_tree = await self._get_simplified_dom()

        return PageState(
            url=self._page.url,
            title=await self._page.title(),
            dom_tree=dom_tree,
            interactive_elements=elements,
            screenshot_base64=screenshot_base64,
            screenshot_path=screenshot_path,
            viewport_width=self.config.viewport_width,
            viewport_height=self.config.viewport_height,
            timestamp=datetime.now().isoformat(),
        )

    async def _extract_interactive_elements(self) -> list[Element]:
        """Extract all interactive elements from the page."""
        if not self._page:
            return []

        elements = []

        # Define selectors for interactive elements
        selectors = {
            "button": "button, [role='button'], input[type='submit'], input[type='button']",
            "link": "a[href]",
            "input": "input:not([type='hidden']):not([type='submit']):not([type='button'])",
            "select": "select",
            "textarea": "textarea",
            "clickable": "[onclick], [data-action]",
        }

        for element_type, selector in selectors.items():
            try:
                handles = await self._page.query_selector_all(selector)
                for i, handle in enumerate(handles[:50]):  # Limit to 50 per type
                    try:
                        tag = await handle.evaluate("el => el.tagName.toLowerCase()")
                        text = (await handle.inner_text())[:200] if await handle.is_visible() else ""
                        
                        # Get key attributes
                        attrs = await handle.evaluate("""el => {
                            const attrs = {};
                            ['id', 'name', 'class', 'type', 'aria-label', 'href'].forEach(attr => {
                                if (el.hasAttribute(attr)) attrs[attr] = el.getAttribute(attr);
                            });
                            return attrs;
                        }""")

                        # Build a unique selector
                        unique_selector = await self._build_selector(handle, attrs, i)

                        # Get bounding box
                        bounds = await handle.bounding_box()

                        elements.append(Element(
                            tag=tag,
                            selector=unique_selector,
                            text=text.strip(),
                            element_type=element_type,
                            attributes=attrs,
                            bounds=bounds,
                        ))
                    except Exception:
                        continue
            except Exception as e:
                logger.warning("Error extracting elements", selector=selector, error=str(e))

        return elements

    async def _build_selector(self, handle, attrs: dict, index: int) -> str:
        """Build a reliable CSS selector for an element."""
        if attrs.get("id"):
            return f"#{attrs['id']}"
        if attrs.get("name"):
            tag = await handle.evaluate("el => el.tagName.toLowerCase()")
            return f"{tag}[name='{attrs['name']}']"
        if attrs.get("data-testid"):
            return f"[data-testid='{attrs['data-testid']}']"
        if attrs.get("aria-label"):
            return f"[aria-label='{attrs['aria-label']}']"

        # Fallback to nth-of-type approach
        tag = await handle.evaluate("el => el.tagName.toLowerCase()")
        return f"{tag}:nth-of-type({index + 1})"

    async def _get_simplified_dom(self) -> str:
        """Get a simplified DOM structure for LLM consumption."""
        if not self._page:
            return ""

        # Extract a clean, simplified DOM representation
        dom = await self._page.evaluate("""() => {
            function simplifyNode(node, depth = 0) {
                if (depth > 5) return '';  // Limit depth
                if (node.nodeType === Node.TEXT_NODE) {
                    const text = node.textContent.trim();
                    return text.length > 0 && text.length < 200 ? text : '';
                }
                if (node.nodeType !== Node.ELEMENT_NODE) return '';
                
                const tag = node.tagName.toLowerCase();
                const skipTags = ['script', 'style', 'noscript', 'svg', 'path'];
                if (skipTags.includes(tag)) return '';
                
                const interactiveTags = ['a', 'button', 'input', 'select', 'textarea', 'form'];
                const structuralTags = ['div', 'section', 'main', 'nav', 'header', 'footer', 'article'];
                
                let attrs = '';
                if (node.id) attrs += ` id="${node.id}"`;
                if (node.className && typeof node.className === 'string') {
                    attrs += ` class="${node.className.split(' ').slice(0, 3).join(' ')}"`;
                }
                if (tag === 'a' && node.href) attrs += ` href="${node.href}"`;
                if (tag === 'input') {
                    attrs += ` type="${node.type || 'text'}"`;
                    if (node.placeholder) attrs += ` placeholder="${node.placeholder}"`;
                    if (node.name) attrs += ` name="${node.name}"`;
                    if (node.hasAttribute('aria-label')) attrs += ` aria-label="${node.getAttribute('aria-label')}"`;
                }
                if (tag === 'label' && node.htmlFor) attrs += ` for="${node.htmlFor}"`;
                
                const children = Array.from(node.childNodes)
                    .map(child => simplifyNode(child, depth + 1))
                    .filter(s => s.length > 0)
                    .join('');
                
                if (!children && !interactiveTags.includes(tag)) return '';
                
                const indent = '  '.repeat(depth);
                return `${indent}<${tag}${attrs}>${children}</${tag}>\\n`;
            }
            
            return simplifyNode(document.body);
        }""")

        # Truncate if too long
        if len(dom) > 15000:
            dom = dom[:15000] + "\n<!-- truncated -->"

        return dom

    async def execute_action(self, action_type: str, selector: str | None = None, value: str | None = None) -> ActionResult:
        """Execute an action on the page."""
        if not self._page:
            raise RuntimeError("Browser not launched.")

        logger.info("Executing action", action_type=action_type, selector=selector, value=value)

        # Helper: Auto-fix common LLM selector mistakes
        if selector and ":contains(" in selector:
            # Replace invalid :contains with Playwright's :has-text
            selector = selector.replace(":contains(", ":has-text(")

        try:
            if action_type == "click":
                if not selector:
                    return ActionResult(success=False, error="Selector is required for click")
                
                # Wait for element to be attached and visible
                await self._page.wait_for_selector(selector, state="visible", timeout=5000)
                await self._page.click(selector)
                await asyncio.sleep(self.config.action_delay_ms / 1000)
                return ActionResult(success=True, message=f"Clicked {selector}", new_url=self._page.url)

            elif action_type == "type":
                if not selector or value is None:
                    return ActionResult(success=False, error="Selector and value are required for type")
                
                # Resolve element first - supports CSS, XPath, etc.
                element = await self._page.wait_for_selector(selector, state="attached", timeout=5000)
                if not element:
                     return ActionResult(success=False, error=f"Element not found: {selector}")

                # Check if it's a slider (Radix UI or Range Input)
                is_slider = await element.evaluate("""el => {
                    return el.getAttribute('role') === 'slider' || el.type === 'range';
                }""")

                if is_slider:
                    # SLIDER MANIPULATION: Use keyboard for Radix UI sliders
                    logger.info("Detected slider, using keyboard manipulation", selector=selector, value=value)
                    
                    # Get current value and min/max
                    slider_info = await element.evaluate("""el => ({
                        current: parseInt(el.getAttribute('aria-valuenow')) || 0,
                        min: parseInt(el.getAttribute('aria-valuemin')) || 0,
                        max: parseInt(el.getAttribute('aria-valuemax')) || 100,
                        isRange: el.type === 'range'
                    })""")
                    
                    target_value = int(value)
                    current_value = slider_info['current']
                    min_val = slider_info['min']
                    max_val = slider_info['max']
                    
                    if slider_info['isRange']:
                        # Standard range input - set directly
                        await element.evaluate("""(el, val) => {
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }""", str(target_value))
                    else:
                        # Radix UI slider - use keyboard with ADAPTIVE step detection
                        # Focus the slider first
                        await element.focus()
                        await asyncio.sleep(0.1)
                        
                        # Get current value
                        current = int(await element.get_attribute("aria-valuenow") or 0)
                        target = target_value
                        
                        if current == target:
                            logger.info("Slider already at target", current=current, target=target)
                            final = str(current)
                        else:
                            # Determine direction
                            direction = "ArrowRight" if target > current else "ArrowLeft"
                            
                            # Detect actual step size by pressing once
                            await element.press(direction)
                            await asyncio.sleep(0.05)
                            new_val = int(await element.get_attribute("aria-valuenow") or current)
                            step_size = abs(new_val - current)
                            
                            if step_size == 0:
                                step_size = 1  # Fallback
                            
                            logger.info("Slider step detected", step_size=step_size, current=current, after_one=new_val)
                            
                            # Calculate remaining steps (we already moved once)
                            remaining_diff = abs(target - new_val)
                            remaining_steps = remaining_diff // step_size
                            
                            # Cap for safety
                            remaining_steps = min(remaining_steps, 300)
                            
                            logger.info("Slider navigating", remaining_steps=remaining_steps, direction=direction)
                            
                            for _ in range(remaining_steps):
                                await element.press(direction)
                                await asyncio.sleep(0.015)  # Fast but stable
                            
                            # Verify final value
                            final = await element.get_attribute("aria-valuenow")
                            logger.info("Slider final value", final=final, target=target_value)
                    
                    return ActionResult(success=True, message=f"Set slider to {final} (target: {value})")
                else:
                    # Standard behavior
                    await self._page.fill(selector, str(value), timeout=5000)
                    return ActionResult(success=True, message=f"Typed '{value}' into {selector}")
            
            elif action_type == "scroll":
                direction = value or "down"
                amount = 300 if direction == "down" else -300
                await self._page.evaluate(f"window.scrollBy(0, {amount})")
                return ActionResult(success=True, message=f"Scrolled {direction}")

            elif action_type == "hover":
                if not selector:
                    return ActionResult(success=False, message="Hover requires a selector")
                await self._page.hover(selector, timeout=5000)
                return ActionResult(success=True, message=f"Hovered over {selector}")

            elif action_type == "wait":
                wait_time = float(value) if value else 1.0
                await asyncio.sleep(wait_time)
                return ActionResult(success=True, message=f"Waited {wait_time}s")

            elif action_type == "navigate":
                if not value:
                    return ActionResult(success=False, message="Navigate requires a URL")
                await self._page.goto(value, wait_until="domcontentloaded")
                return ActionResult(success=True, message=f"Navigated to {value}", new_url=self._page.url)

            else:
                return ActionResult(success=False, message=f"Unknown action type: {action_type}")

        except Exception as e:
            logger.error("Action failed", action_type=action_type, error=str(e))
            return ActionResult(success=False, message=f"Action failed: {action_type}", error=str(e))
