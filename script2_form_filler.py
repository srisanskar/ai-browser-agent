"""
Script 2 — Form Filler
Reads user data from users.json, fills demoqa.com/automation-practice-form,
takes a screenshot before submitting.
Error handling: element not found, timeout, missing JSON fields
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


def load_user(filename: str = "users.json") -> dict:
    """Load first user from users.json."""
    if not os.path.exists(filename):
        raise FileNotFoundError(f"'{filename}' not found. Run from your project root.")

    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    users = data.get("users")
    if not users:
        raise ValueError("'users' key missing or empty in users.json.")

    return users[0]  # Use the first user


def parse_user(user: dict) -> dict:
    """Parse and validate user fields, map to form fields."""
    required = ["name", "email", "phone", "address"]
    for field in required:
        if field not in user:
            raise ValueError(f"Missing required field '{field}' in user data.")

    name_parts = user["name"].split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    # Strip the country code from phone for the form (expects 10-digit mobile)
    phone = user["phone"].replace("+91-", "").replace("-", "").replace(" ", "")

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": user["email"],
        "phone": phone,
        "address": user["address"],
    }


async def fill_form(user: dict):
    """Open demoqa form, fill all fields, take screenshot."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False so you can watch
        page = await browser.new_page()

        try:
            print("🌐 Navigating to demoqa form...")
            await page.goto("https://demoqa.com/automation-practice-form", timeout=20000)

            # Wait for the form to be visible
            try:
                await page.wait_for_selector("#firstName", timeout=10000)
            except PlaywrightTimeout:
                raise RuntimeError("Form did not load in time — possible timeout or site down.")

            # --- Remove ads/banners that block clicks (common on demoqa) ---
            await page.evaluate("""
                const ads = document.querySelectorAll('#fixedban, .introjs-overlay, iframe');
                ads.forEach(el => el.remove());
            """)

            print("📝 Filling form fields...")

            # First Name
            await page.locator("#firstName").fill(user["first_name"])
            print(f"   First Name: {user['first_name']}")

            # Last Name
            await page.locator("#lastName").fill(user["last_name"])
            print(f"   Last Name:  {user['last_name']}")

            # Email
            await page.locator("#userEmail").fill(user["email"])
            print(f"   Email:      {user['email']}")

            # Gender — click Male radio
            try:
                await page.locator("label[for='gender-radio-1']").click()
                print("   Gender:     Male ✓")
            except Exception as e:
                print(f"   ⚠️  Could not select gender: {e}")

            # Phone
            await page.locator("#userNumber").fill(user["phone"])
            print(f"   Phone:      {user['phone']}")

            # Date of Birth — type into the date picker input
            try:
                dob_input = page.locator("#dateOfBirthInput")
                await dob_input.click(click_count=3)
                await dob_input.type("01 Jan 2000")
                await page.keyboard.press("Enter")
                print("   DOB:        01 Jan 2000 ✓")
            except Exception as e:
                print(f"   ⚠️  Could not fill DOB: {e}")

            # Subject — type and select from dropdown
            try:
                subjects_input = page.locator("#subjectsInput")
                await subjects_input.fill("Math")
                await page.wait_for_selector(".subjects-auto-complete__option", timeout=5000)
                await page.locator(".subjects-auto-complete__option").first.click()
                print("   Subject:    Maths ✓")
            except PlaywrightTimeout:
                print("   ⚠️  Subject autocomplete did not appear.")
            except Exception as e:
                print(f"   ⚠️  Could not fill subject: {e}")

            # Hobby — check Sports
            try:
                await page.locator("label[for='hobbies-checkbox-1']").click()
                print("   Hobby:      Sports ✓")
            except Exception as e:
                print(f"   ⚠️  Could not select hobby: {e}")

            # Current Address
            await page.locator("#currentAddress").fill(user["address"])
            print(f"   Address:    {user['address']}")

            # State dropdown
            try:
                await page.locator("#state").click()
                await page.wait_for_selector("#react-select-3-option-0", timeout=5000)
                await page.locator("#react-select-3-option-0").click()
                print("   State:      NCR ✓")
            except Exception as e:
                print(f"   ⚠️  Could not select state: {e}")

            # City dropdown
            try:
                await page.locator("#city").click()
                await page.wait_for_selector("#react-select-4-option-0", timeout=5000)
                await page.locator("#react-select-4-option-0").click()
                print("   City:       Delhi ✓")
            except Exception as e:
                print(f"   ⚠️  Could not select city: {e}")

            # Screenshot BEFORE submitting
            screenshot_path = "form_filled.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n📸 Screenshot saved → {screenshot_path}")
            print("✅ Form filled successfully! (Not submitted — screenshot taken.)")

        except PlaywrightTimeout:
            raise RuntimeError("Navigation timed out. Is demoqa.com reachable?")

        finally:
            await browser.close()


async def main():
    print("=" * 50)
    print("  Script 2 — Form Filler")
    print("=" * 50)

    try:
        raw_user = load_user("users.json")
        user = parse_user(raw_user)
        print(f"\n👤 Using user: {raw_user['name']}\n")
        await fill_form(user)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n❌ Data error: {e}")
    except RuntimeError as e:
        print(f"\n❌ Browser error: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
