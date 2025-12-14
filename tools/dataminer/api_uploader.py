import argparse
import json
import logging
import mimetypes
import os
from typing import Dict, List, Optional

import requests


# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DesigniaAPIUploader:
    """
    Uploads scraped product data to Designia Backend via API.
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = "admin@admin.com"
        self.password = "admin"
        self.token = None
        self.headers = {}
        self.category_map = {}  # Store {lower_case_name_or_slug: id}
        self.category_names_to_id = {}  # Store {lower_case_name: id} for fuzzy matching
        self.category_slugs_to_id = {}  # Store {lower_case_slug: id} for fuzzy matching

        # Hardcoded mapping for known IKEA search terms to Designia category slugs
        self.term_mapping = {
            "armchair": "armchair",
            "armchairs": "armchair",
            "bed": "bed",
            "beds": "bed",
            "double bed": "bed",
            "bookshelf": "bookshelf",
            "bookcase": "bookshelf",
            "shelving unit": "bookshelf",
            "desk": "desk",
            "desks": "desk",
            "computer desk": "desk",
            "dining table": "dining-table",
            "dining tables": "dining-table",
            "floor lamp": "floor-lamp",
            "floor lamps": "floor-lamp",
            "rug": "rug",
            "rugs": "rug",
            "sofa": "sofa",
            "sofas": "sofa",
            "couch": "sofa",
        }

    def login(self) -> bool:
        """Authenticates and retrieves JWT token."""
        url = f"{self.base_url}/api/auth/login/"
        logger.info(f"Logging in to {url} as {self.username}...")
        try:
            response = requests.post(url, json={"email": self.username, "password": self.password})

            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access")
                self.headers = {"Authorization": f"Bearer {self.token}"}
                logger.info("Login successful.")
                return True
            elif response.status_code == 202:
                logger.error(
                    f"Login failed: 2FA required (Status 202). Please disable 2FA for user '{self.username}' or use a different user."
                )
                logger.error(f"Response: {response.text}")
                return False
            else:
                logger.error(f"Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Connection error during login: {e}")
            return False

    def fetch_categories(self):
        """Fetches existing categories to map names to IDs."""
        url = f"{self.base_url}/api/marketplace/products/categories/"
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                results = response.json()
                # Handle pagination if necessary, but assuming list for now or first page
                # If paginated, results might be {'results': [...]}
                if isinstance(results, dict) and "results" in results:
                    categories = results["results"]
                else:
                    categories = results

                for cat in categories:
                    # Store exact matches
                    self.category_map[cat["name"].lower()] = cat["id"]
                    self.category_map[cat["slug"].lower()] = cat["id"]
                    # Store for fuzzy matching
                    self.category_names_to_id[cat["name"].lower()] = cat["id"]
                    self.category_slugs_to_id[cat["slug"].lower()] = cat["id"]

                logger.info(f"Fetched {len(self.category_names_to_id)} categories.")
            else:
                logger.warning(f"Failed to fetch categories: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")

    def upload_product(self, item: Dict, images_paths: List[str]) -> Optional[str]:
        """
        Creates a product and returns its slug. Uploads images as base64 encoded JSON.
        """
        import base64

        logger.info(f"Uploading product '{item.get('name')}' with {len(images_paths)} image paths provided.")

        url = f"{self.base_url}/api/marketplace/products/"

        name = item.get("name")
        if not name:
            return None

        # Clean Price
        raw_price = item.get("price", "0")
        clean_price = "".join(c for c in raw_price if c.isdigit() or c in ".,")
        if "," in clean_price and "." in clean_price:
            clean_price = clean_price.replace(".", "").replace(",", ".")
        elif "," in clean_price:
            clean_price = clean_price.replace(",", ".")
        price = float(clean_price) if clean_price else 0.0

        # Map Category
        # Prioritize matched_category_slug from the miner if available
        category_term_raw = item.get("matched_category_slug")
        if not category_term_raw:
            # Fallback to category_search_term if matched_category_slug is not provided
            category_term_raw = item.get("category_search_term", "")

        category_term = category_term_raw.lower().strip()  # Clean input

        category_id = None

        # 0. Check Hardcoded Mapping
        mapped_slug = self.term_mapping.get(category_term)
        if mapped_slug:
            category_id = self.category_map.get(mapped_slug)
            if category_id:
                logger.info(f"Mapped term '{category_term}' to hardcoded slug '{mapped_slug}' (ID: {category_id})")

        # 1. Try exact match on name or slug
        if not category_id:
            category_id = self.category_map.get(category_term)

        # 2. If no exact match, try fuzzy matching (contains)
        if not category_id:
            for name_lower, cat_id in self.category_names_to_id.items():
                if category_term in name_lower or name_lower in category_term:
                    category_id = cat_id
                    logger.info(f"Fuzzy matched '{category_term_raw}' to category name '{name_lower}' (ID: {cat_id})")
                    break

        if not category_id:
            for slug_lower, cat_id in self.category_slugs_to_id.items():
                if category_term in slug_lower or slug_lower in category_term:
                    category_id = cat_id
                    logger.info(f"Fuzzy matched '{category_term_raw}' to category slug '{slug_lower}' (ID: {cat_id})")
                    break

        if not category_id:
            logger.error(
                f"Category '{category_term_raw}' not found for product '{name}'. "
                f"Please ensure categories like 'Sofa, Bed, Dining Table, Desk, Floor Lamp, Rug, Armchair, Bookshelf' "
                f"exist in your backend. Skipping product."
            )
            return None

        # Build image_data array with base64-encoded images
        image_data = []
        for idx, img_path in enumerate(images_paths):
            exists = os.path.exists(img_path)
            logger.info(f"Checking image path: {img_path} (Exists: {exists})")
            if exists:
                try:
                    # Read and encode image as base64
                    with open(img_path, "rb") as img_file:
                        image_bytes = img_file.read()
                        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                        # Determine MIME type
                        mime_type, _ = mimetypes.guess_type(img_path)
                        if not mime_type:
                            mime_type = "image/jpeg"

                        # Create data URI
                        image_content = f"data:{mime_type};base64,{image_base64}"

                        filename = os.path.basename(img_path)
                        image_data.append(
                            {
                                "image_content": image_content,
                                "filename": filename,
                                "alt_text": f"{name} - Image {idx + 1}",
                                "is_primary": idx == 0,  # First image is primary
                                "order": idx,
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to encode image {img_path}: {e}")
                    continue
            else:
                logger.warning(f"Image file not found: {img_path}")

        # Prepare payload as JSON
        payload = {
            "name": name,
            "description": item.get("description", "") + "\n\nSource: IKEA Demo Data",
            "short_description": item.get("description", "")[:150],
            "price": str(price),
            "stock_quantity": 10,
            "category": category_id,
            "condition": "new",
            "is_digital": False,
            "image_data": image_data,
        }

        # Send JSON request
        try:
            headers = self.headers.copy()
            headers["Content-Type"] = "application/json"

            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 201:
                product_data = response.json()
                logger.info(f"Created product: {name} with {len(image_data)} images")
                return product_data.get("slug")
            elif response.status_code == 202:
                logger.warning(f"Product creation accepted (202): {name}. Unexpected.")
                logger.info(f"Response: {response.text}")
                return None
            else:
                logger.error(f"Failed to create product '{name}': {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error creating product '{name}': {e}")
            return None

    def upload_image(self, product_slug: str, image_path: str, is_primary: bool = False):
        """
        Uploads an image to a product.
        """
        if not os.path.exists(image_path):
            logger.warning(f"Image file not found: {image_path}")
            return

        url = f"{self.base_url}/api/marketplace/products/{product_slug}/images/"

        # Prepare file
        filename = os.path.basename(image_path)
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            with open(image_path, "rb") as f:
                files = {"image": (filename, f, mime_type)}
                data = {"is_primary": str(is_primary).lower(), "alt_text": f"Product image for {product_slug}"}

                # Note: Do not use 'json=' here, requests handles multipart boundary automatically with 'files='
                # Also remove Content-Type header so requests can set boundary
                headers = self.headers.copy()
                if "Content-Type" in headers:
                    del headers["Content-Type"]  # Allow multipart/form-data

                response = requests.post(url, headers=headers, files=files, data=data)

                # Print response for debugging
                logger.info(f"Image Upload Response: {response.status_code}")
                if response.status_code not in [200, 201, 204]:
                    logger.info(f"Response Body: {response.text}")

                if response.status_code == 201:
                    logger.info(f"Uploaded image: {filename}")
                elif response.status_code == 202:
                    logger.warning(
                        f"Image upload accepted (202): {filename}. Check backend logs for processing status."
                    )
                else:
                    logger.error(f"Failed to upload image {filename}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Error uploading image {image_path}: {e}")

    def run(self, file_path: str):
        if not self.login():
            return

        self.fetch_categories()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON file: {e}")
            return

        logger.info(f"Found {len(data)} items to process.")

        for i, item in enumerate(data):
            logger.info(f"[{i+1}/{len(data)}] Processing {item.get('name')}")

            # Gather image paths
            images = item.get("images", [])
            if not images and item.get("image"):
                images = [item.get("image")]

            # Pass images to upload_product directly
            product_slug = self.upload_product(item, images)

            # Separate image upload loop removed since it's handled in upload_product
            if product_slug:
                logger.info(f"Product {product_slug} created successfully with images.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload IKEA data via API")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--username", default="admin", help="Username")
    parser.add_argument("--password", default="admin", help="Password")
    parser.add_argument(
        "--file", default="Designia-backend/tools/dataminer/output/ikea_data.json", help="Path to data JSON"
    )

    args = parser.parse_args()

    # Resolve relative path if running from root
    if not os.path.isabs(args.file) and not os.path.exists(args.file):
        # Try finding it relative to script if default
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.join(script_dir, "output", "ikea_data.json")
        if os.path.exists(alt_path):
            args.file = alt_path

    uploader = DesigniaAPIUploader(args.url, args.username, args.password)
    uploader.run(args.file)
