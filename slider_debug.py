"""
Deep Slider DOM Analysis Script
Purpose: Understand Radix UI slider structure to fix programmatic manipulation
"""
from playwright.sync_api import sync_playwright
import time

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # Navigate
        page.goto("https://health-quote-explorer.lovable.app/chubb")
        time.sleep(2)
        
        # Fill Page 1 quickly
        page.fill("#firstName", "Test")
        page.fill("#lastName", "User")
        page.fill("#dob", "1990-01-01")
        page.click("label[for='gender-male']")
        page.click("label[for='non-smoker']")
        page.click("//button[contains(text(), 'Continue')]")
        time.sleep(2)
        
        print("\n" + "="*60)
        print("SLIDER DEEP ANALYSIS")
        print("="*60)
        
        # Get ALL sliders
        sliders = page.query_selector_all("[role='slider']")
        print(f"\nFound {len(sliders)} sliders")
        
        for i, slider in enumerate(sliders):
            print(f"\n--- SLIDER {i} ---")
            
            # Get full attributes
            attrs = slider.evaluate("""el => {
                const attrs = {};
                for (const attr of el.attributes) {
                    attrs[attr.name] = attr.value;
                }
                return attrs;
            }""")
            print(f"Attributes: {attrs}")
            
            # Get parent structure
            parent_info = slider.evaluate("""el => {
                const parent = el.parentElement;
                const grandparent = parent?.parentElement;
                return {
                    parent_tag: parent?.tagName,
                    parent_role: parent?.getAttribute('role'),
                    parent_class: parent?.className,
                    grandparent_tag: grandparent?.tagName,
                    grandparent_class: grandparent?.className
                };
            }""")
            print(f"Parent Info: {parent_info}")
            
            # Get sibling track element
            track_info = slider.evaluate("""el => {
                const parent = el.closest('[class*="relative"]');
                const track = parent?.querySelector('[class*="Range"]');
                return {
                    has_track: !!track,
                    track_style: track?.getAttribute('style')
                };
            }""")
            print(f"Track Info: {track_info}")
        
        # Now test manipulation
        print("\n" + "="*60)
        print("MANIPULATION TEST")
        print("="*60)
        
        first_slider = sliders[0]
        
        # Get initial value
        initial = first_slider.get_attribute("aria-valuenow")
        print(f"Initial aria-valuenow: {initial}")
        
        # Try setting via aria-valuenow
        first_slider.evaluate("""el => {
            el.setAttribute('aria-valuenow', '400000');
        }""")
        after_attr = first_slider.get_attribute("aria-valuenow")
        print(f"After setAttribute: {after_attr}")
        
        # Try triggering events
        first_slider.evaluate("""el => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new CustomEvent('pointerdown', { bubbles: true }));
            el.dispatchEvent(new CustomEvent('pointerup', { bubbles: true }));
        }""")
        
        # Check if visual changed (look at style transform)
        style_after = first_slider.evaluate("el => el.style.cssText")
        print(f"Style after events: {style_after}")
        
        # Check the range track
        range_track = page.query_selector('[class*="SliderRange"]')
        if range_track:
            range_style = range_track.get_attribute("style")
            print(f"Range track style: {range_style}")
        
        # Try using keyboard simulation
        print("\n--- KEYBOARD TEST ---")
        first_slider.focus()
        for _ in range(10):
            first_slider.press("ArrowRight")
        new_val = first_slider.get_attribute("aria-valuenow")
        print(f"After 10x ArrowRight: {new_val}")
        
        time.sleep(3)
        browser.close()

if __name__ == "__main__":
    main()
