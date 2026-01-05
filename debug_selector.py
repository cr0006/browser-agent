from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print("Navigating...")
        page.goto("https://health-quote-explorer.lovable.app/chubb")
        page.wait_for_load_state("networkidle")
        
        print("Filling Page 1...")
        # Fill known fields
        page.wait_for_selector("#firstName")
        page.fill("#firstName", "John")
        page.fill("#lastName", "Doe")
        page.fill("#dob", "1990-01-01")
        
        # Click labels
        page.click("label[for='gender-male']")
        page.click("label[for='non-smoker']")
        
        print("Clicking Continue on Page 1...")
        page.click("//button[contains(text(), 'Continue')]")
        
        # Helper to wait and identify page
        def analyze_page(name):
            print(f"\n--- ANALYZING {name} ---")
            try:
                page.wait_for_load_state("networkidle")
                time.sleep(2)
                
                # Print Header Text
                header = page.query_selector("h1, h2, h3, .text-xl, .text-2xl")
                if header:
                    print(f"Header: {header.inner_text()}")

                # Print Form Fields
                print("INPUTS:")
                for inp in page.query_selector_all("input"):
                    if inp.is_visible():
                         attrs = inp.evaluate("el => { let a={}; Array.from(el.attributes).forEach(attr => a[attr.name] = attr.value); return a; }")
                         print(f"  {attrs}")
                
                print("BUTTONS:")
                for btn in page.query_selector_all("button"):
                    if btn.is_visible():
                        print(f"  {btn.inner_text()} (Class: {btn.get_attribute('class')})")
                        
                print("LABELS:")
                for lbl in page.query_selector_all("label"):
                    if lbl.is_visible():
                        print(f"  {lbl.inner_text()} (For: {lbl.get_attribute('for')})")
                        
            except Exception as e:
                print(f"Error analyzing {name}: {e}")

        # Page 2 (Intermediate)
        analyze_page("PAGE 2")
        
        print("\n--- DETAILED SLIDER ANALYSIS ---")
        # Dump the entire container that likely holds sliders
        slider_container = page.query_selector("div.space-y-6") # Hypothesizing container class based on typical tailwind
        if slider_container:
            print(slider_container.evaluate("el => el.innerHTML"))
        else:
            # Plan B: Print structure of ALL role=slider elements
            sliders = page.query_selector_all("[role='slider']")
            for i, s in enumerate(sliders):
                print(f"Slider {i} Path:")
                print(s.evaluate("""el => {
                     let path = [];
                     let curr = el;
                     while(curr && curr !== document.body) {
                        let tag = curr.tagName.toLowerCase();
                        if(curr.id) tag += "#" + curr.id;
                        if(curr.className) tag += "." + curr.className.split(" ").join(".");
                        path.push(tag);
                        curr = curr.parentElement;
                     }
                     return path.reverse().join(" > ");
                }"""))

        browser.close()

if __name__ == "__main__":
    run()
