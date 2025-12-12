import asyncio
import json
import logging
import os
import re
from typing import Dict, List

import aiohttp
from playwright.async_api import async_playwright


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class IkeaDataMiner:
    """
    Tool to gather product data from IKEA using Playwright.
    Targeting IKEA Portugal (English).
    Downloads images locally.
    """

    BASE_URL = "https://www.ikea.com/pt/en/"

    # Use absolute paths based on this script's location
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
    IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.data: List[Dict] = []

        # Ensure output directories exist
        logger.info(f"Ensuring output directory exists at: {self.OUTPUT_DIR}")
        os.makedirs(self.IMAGES_DIR, exist_ok=True)

    async def download_image(self, url: str, product_name: str, product_index: int, img_index: int) -> str:
        """
        Downloads an image from a URL and saves it locally.
        Returns the absolute local file path.
        """
        if not url:
            return ""

        try:
            # Create a safe filename
            safe_name = re.sub(r"[^a-zA-Z0-9]", "_", product_name).lower()
            safe_name = safe_name[:50]

            filename = f"{product_index}_{safe_name}_{img_index}.jpg"
            filepath = os.path.join(self.IMAGES_DIR, filename)

            # Avoid re-downloading if exists
            if os.path.exists(filepath):
                logger.info(f"Image already exists: {filename}")
                return filepath

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        with open(filepath, "wb") as f:
                            f.write(await response.read())
                        logger.info(f"Downloaded: {filename}")
                        return filepath
                    else:
                        logger.warning(f"Failed to download {url}: status {response.status}")
                        return ""
        except Exception as e:
            logger.error(f"Error downloading image {url}: {e}")
            return ""

    async def gather_categories(self, queries: List[str], max_items_per_category: int = 10):
        """
        Launches browser once, then loops through a list of search queries.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context()
            page = await context.new_page()

            logger.info(f"Navigating to {self.BASE_URL}")
            await page.goto(self.BASE_URL)

            # --- Cookie Consent (Once) ---
            try:
                cookie_button = page.locator("#onetrust-accept-btn-handler")
                if await cookie_button.is_visible(timeout=5000):
                    await cookie_button.click()
                    logger.info("Accepted cookies.")
            except Exception:
                logger.warning("Cookie banner skipped or not found.")

            total_items_collected = 0

            for category in queries:
                logger.info(f"=== Processing Category: {category} ===")

                if "search" in page.url:
                    await page.goto(self.BASE_URL)
                    await page.wait_for_load_state("domcontentloaded")

                # --- Search ---
                search_input = page.locator('input[name="q"]')
                await search_input.wait_for(state="visible")
                await search_input.fill(category)
                await search_input.press("Enter")

                # --- Wait for Results ---
                try:
                    await page.wait_for_selector(".plp-fragment-wrapper, .pip-product-compact", timeout=10000)
                    await page.wait_for_timeout(2000)
                except Exception:
                    logger.warning(f"No results found for {category}, skipping...")
                    continue

                # --- Step 1: Extract Basic Info & Fallback Image ---
                logger.info(f"Extracting product list for '{category}'...")

                product_cards = await page.locator(".plp-fragment-wrapper").all()
                if not product_cards:
                    product_cards = await page.locator(".pip-product-compact").all()

                category_products = []
                count = 0

                for card in product_cards:
                    if count >= max_items_per_category:
                        break
                    try:
                        p_data = {"category_search_term": category}

                        name_el = card.locator(
                            ".plp-price-module__product-name, .pip-header-section__title--small"
                        ).first
                        if await name_el.is_visible():
                            p_data["name"] = await name_el.inner_text()
                        else:
                            continue

                        price_el = card.locator(".plp-price__integer, .pip-temp-price__integer").first
                        if await price_el.is_visible():
                            p_data["price"] = await price_el.inner_text()
                        else:
                            price_el = card.locator(".plp-price-module__current-price").first
                            p_data["price"] = await price_el.inner_text() if await price_el.is_visible() else "0"

                        desc_el = card.locator(".plp-price-module__description").first
                        p_data["description"] = await desc_el.inner_text() if await desc_el.is_visible() else ""

                        link_el = card.locator("a").first
                        if await link_el.is_visible():
                            href = await link_el.get_attribute("href")
                            if href:
                                p_data["product_url"] = (
                                    href if href.startswith("http") else f"{self.BASE_URL.rstrip('/')}{href}"
                                )

                        # Grab fallback image from search result
                        img_el = card.locator("img").first
                        if await img_el.is_visible():
                            p_data["fallback_image_url"] = await img_el.get_attribute("src")

                        if "product_url" in p_data:
                            category_products.append(p_data)
                            count += 1
                            logger.info(f"Listed: {p_data['name']}")

                    except Exception as e:
                        logger.error(f"Error listing card: {e}")

                # --- Step 2: Visit PDPs for Images ---
                logger.info(f"Visiting {len(category_products)} product pages for '{category}'...")

                for idx, prod in enumerate(category_products):
                    global_idx = total_items_collected + idx
                    logger.info(f"Processing {prod['name']}...")

                    image_urls = []

                    try:
                        await page.goto(prod["product_url"])
                        await page.wait_for_load_state("domcontentloaded")

                        # Broader selector strategy
                        # 1. Grid images
                        # 2. Jumbo image
                        # 3. ANY image in main content
                        try:
                            await page.wait_for_selector("img", timeout=5000)
                        except Exception:
                            pass

                        # Strategy A: Specific Classes
                        image_elements = await page.locator(
                            ".pip-media-grid__media-image, .pip-product-gallery__image"
                        ).all()
                        for img in image_elements:
                            src = await img.get_attribute("src")
                            if src and "http" in src and src not in image_urls:
                                image_urls.append(src)

                        # Strategy B: Fallback to any large image in product container
                        if not image_urls:
                            # Look for images inside typical product containers
                            potential_images = await page.locator(
                                ".pip-product-main-image img, .pip-jumbo-media__image"
                            ).all()
                            for img in potential_images:
                                src = await img.get_attribute("src")
                                if src and "http" in src and src not in image_urls:
                                    image_urls.append(src)

                        logger.info(f"Found {len(image_urls)} images on PDP for {prod['name']}")

                    except Exception as e:
                        logger.error(f"Failed processing PDP for {prod['name']}: {e}")

                    # If no images found on PDP, use fallback
                    if not image_urls and "fallback_image_url" in prod:
                        logger.info(f"Using fallback image from search results for {prod['name']}")
                        image_urls.append(prod["fallback_image_url"])

                    # Limit images
                    image_urls = image_urls[:5]

                    local_paths = []
                    for img_i, url in enumerate(image_urls):
                        path = await self.download_image(url, prod["name"], global_idx, img_i)
                        if path:
                            local_paths.append(path)

                    prod["image"] = local_paths[0] if local_paths else None
                    prod["images"] = local_paths

                    # Clean up temp key
                    if "fallback_image_url" in prod:
                        del prod["fallback_image_url"]

                    self.data.append(prod)
                    await page.wait_for_timeout(500)

                total_items_collected += len(category_products)

            await browser.close()

    def save_data(self, filename: str = "ikea_data.json"):
        filepath = os.path.join(self.OUTPUT_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            logger.info(f"Successfully saved {len(self.data)} items to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save data: {str(e)}")


async def main():
    miner = IkeaDataMiner(headless=True)

    categories = ["sofa", "bed", "dining table", "desk", "floor lamp", "rug", "armchair", "bookshelf"]

    await miner.gather_categories(categories, max_items_per_category=10)
    miner.save_data()


if __name__ == "__main__":
    asyncio.run(main())
