"""
Script 3 — Tab Manager
Opens 5 URLs in parallel tabs, captures each page title,
then closes all tabs except the first.
Error handling: navigation timeout per tab, page crash
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

# 5 URLs to open in parallel
URLS = [
    "https://news.ycombinator.com",
    "https://www.bbc.com/news",
    "https://github.com/trending",
    "https://www.python.org",
    "https://playwright.dev/python/docs/intro",
]


async def open_tab_and_get_title(context, url: str, index: int) -> dict:
    """Open a new tab, navigate to URL, capture title."""
    page = await context.new_page()
    result = {"index": index, "url": url, "title": None, "error": None, "page": page}

    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")

        # Wait for title to be non-empty
        try:
            await page.wait_for_function("document.title.length > 0", timeout=5000)
        except PlaywrightTimeout:
            pass  # Title might still be readable even if this times out

        title = await page.title()

        if not title:
            raise RuntimeError("Page loaded but title was empty.")

        result["title"] = title
        print(f"  Tab {index+1} ✓  [{title[:60]}]")

    except PlaywrightTimeout:
        result["error"] = f"Timeout navigating to {url}"
        print(f"  Tab {index+1} ⚠️  Timeout: {url}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  Tab {index+1} ⚠️  Error: {e}")

    return result


async def manage_tabs():
    """Open 5 tabs in parallel, log titles, close all but the first."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        print(f"🚀 Opening {len(URLS)} tabs in parallel...\n")

        # Launch all tabs concurrently
        tasks = [
            open_tab_and_get_title(context, url, i)
            for i, url in enumerate(URLS)
        ]
        results = await asyncio.gather(*tasks)

        # Show summary
        print("\n📋 Tab Summary:")
        print("-" * 60)
        for r in results:
            status = r["title"] if r["title"] else f"ERROR — {r['error']}"
            print(f"  {r['index']+1}. {r['url']}")
            print(f"     → {status}")
        print("-" * 60)

        # Close all tabs except the first (index 0)
        print("\n🗑️  Closing tabs 2–5, keeping Tab 1 open...")
        for r in results[1:]:  # Skip index 0
            try:
                await r["page"].close()
                print(f"  Closed tab {r['index']+1}: {r['url']}")
            except Exception as e:
                print(f"  ⚠️  Could not close tab {r['index']+1}: {e}")

        first_page = results[0]["page"]
        surviving_title = await first_page.title()
        print(f"\n✅ Kept Tab 1 open: [{surviving_title}]")

        # Save results to JSON
        output = {
            "run_at": datetime.now().isoformat(),
            "tabs_opened": len(URLS),
            "tabs_kept": 1,
            "results": [
                {"index": r["index"], "url": r["url"], "title": r["title"], "error": r["error"]}
                for r in results
            ]
        }
        with open("tab_results.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print("💾 Results saved → tab_results.json")

        await browser.close()


async def main():
    print("=" * 50)
    print("  Script 3 — Tab Manager")
    print("=" * 50)
    print()

    try:
        await manage_tabs()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
