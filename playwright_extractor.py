import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import nest_asyncio

nest_asyncio.apply()

async def extract_form_fields(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        await page.goto(url, wait_until="load", timeout=60000)

        fields = []

        # Part 1: Handle standard inputs and textareas,
        # but EXCLUDE inputs that are part of custom dropdowns.
        standard_elements = await page.query_selector_all("input:not([type='hidden']):not([type='submit']):not([class*='select__']), textarea, select")
        for el in standard_elements:
            try:
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                field_type = await el.get_attribute("type") if tag == "input" else tag
                name = await el.get_attribute("name")
                fid = await el.get_attribute("id")
                placeholder = await el.get_attribute("placeholder")

                label = await el.evaluate("""
                    el => {
                        let text = null;
                        const labelEl = document.querySelector(`label[for="${el.id}"]`);
                        if (labelEl) {
                            text = labelEl.innerText;
                        } else if (el.labels && el.labels.length > 0) {
                            text = Array.from(el.labels).map(l => l.innerText).join(", ");
                        } else {
                            const parentLabel = el.closest("label");
                            if (parentLabel) {
                                text = parentLabel.innerText;
                            }
                        }
                        return text;
                    }
                """)

                options = None
                current_value = None

                if tag == "select":
                    options = [await opt.inner_text() for opt in await el.query_selector_all("option")]
                    current_value = await el.evaluate("el => el.options[el.selectedIndex]?.text")
                elif field_type in ["checkbox", "radio"]:
                    current_value = await el.is_checked()
                else:
                    try:
                        current_value = await el.input_value()
                    except Exception:
                        current_value = None

                fields.append({
                    "tag": tag,
                    "type": field_type,
                    "name": name,
                    "id": fid,
                    "placeholder": placeholder,
                    "label": label,
                    "options": options,
                    "current_value": current_value
                })
            except Exception as e:
                print(f"Skipping standard element due to error: {e}")
                continue

        # Part 2: Handle custom dropdowns separately
        custom_select_controls = await page.query_selector_all("div.select__control")
        for el in custom_select_controls:
            try:
                label = await el.evaluate("""
                    el => {
                        const container = el.closest("div.select__container");
                        if (container) {
                            const labelEl = container.querySelector("label");
                            return labelEl ? labelEl.innerText : null;
                        }
                        return null;
                    }
                """)
                
                # Check for an internal input to get name/id if available
                input_el = await el.query_selector("input")
                input_name = await input_el.get_attribute("name") if input_el else None
                input_id = await input_el.get_attribute("id") if input_el else None
                
                current_value_el = await el.query_selector("div.select__single-value")
                current_value = await current_value_el.inner_text() if current_value_el else None
                
                await el.click()
                await page.wait_for_selector("div.select__option", state="visible")
                option_elements = await page.query_selector_all("div.select__option")
                options = [await opt.inner_text() for opt in option_elements]
                await page.keyboard.press("Escape")

                fields.append({
                    "tag": "div",
                    "type": "custom-select",
                    "name": input_name,
                    "id": input_id,
                    "placeholder": None,
                    "label": label,
                    "options": options,
                    "current_value": current_value
                })

            except Exception as e:
                print(f"Skipping custom select element due to error: {e}")
                continue

        await browser.close()
        return fields

# -------------------------------
# Run and save to DataFrame
# -------------------------------
url = "https://job-boards.greenhouse.io/valon/jobs/4008455006"

print("Starting extraction...")
df_fields = pd.DataFrame(asyncio.run(extract_form_fields(url)))

if not df_fields.empty:
    print("\nExtraction complete! Here are the results:")
    print(df_fields.to_string())
else:
    print("\nNo form fields were extracted. Please check the URL and selectors.")