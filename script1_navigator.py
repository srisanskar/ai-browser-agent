"""
Script 1 — Navigator
Opens Hacker News, extracts the top 5 article titles, saves to articles.json
Error handling: element not found, timeout
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


async def extract_hn_titles() -> list[dict]:
    """Navigate to Hacker News and extract top 5 article titles."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # Navigate with a 15-second timeout
            print("🌐 Navigating to Hacker News...")
            await page.goto("https://news.ycombinator.com", timeout=15000)

            # Wait for the story list to appear
            try:
                await page.wait_for_selector(".athing", timeout=10000)
            except PlaywrightTimeout:
                raise RuntimeError("Timed out waiting for article list to load.")

            # Grab all story title links
            title_elements = await page.locator(".athing .titleline > a").all()

            if not title_elements:
                raise RuntimeError("No article titles found — selector may have changed.")

            articles = []
            for i, el in enumerate(title_elements[:5]):
                try:
                    title = await el.inner_text()
                    url = await el.get_attribute("href")
                    articles.append({
                        "rank": i + 1,
                        "title": title.strip(),
                        "url": url
                    })
                    print(f"  {i+1}. {title.strip()}")
                except Exception as e:
                    print(f"  ⚠️  Could not read article #{i+1}: {e}")
                    continue

            return articles

        except PlaywrightTimeout:
            raise RuntimeError("Page navigation timed out. Check your internet connection.")

        finally:
            await browser.close()


async def save_to_json(articles: list[dict], filename: str = "articles.json"):
    """Save articles list to a JSON file."""
    output = {
        "scraped_at": datetime.now().isoformat(),
        "source": "https://news.ycombinator.com",
        "articles": articles
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Saved {len(articles)} articles to {filename}")


async def main():
    print("=" * 50)
    print("  Script 1 — HN Navigator")
    print("=" * 50)

    try:
        articles = await extract_hn_titles()
        await save_to_json(articles)
    except RuntimeError as e:
        print(f"\n❌ Error: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
