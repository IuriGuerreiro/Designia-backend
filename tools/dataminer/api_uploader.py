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
        self.category_map = {}  # Name -> ID

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
                    self.category_map[cat["name"].lower()] = cat["id"]
                    self.category_map[cat["slug"].lower()] = cat["id"]

                logger.info(f"Fetched {len(self.category_map)} categories.")
            else:
                logger.warning(f"Failed to fetch categories: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")

    def upload_product(self, item: Dict, images_paths: List[str]) -> Optional[str]:
        """
        Creates a product and returns its slug. Uploads images in the same request.
        """
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
        category_term = item.get("category_search_term", "").lower()
        category_id = self.category_map.get(category_term)

        if not category_id:
            if self.category_map:
                category_id = list(self.category_map.values())[0]
                logger.warning(f"Category '{category_term}' not found. Using fallback ID: {category_id}")
            else:
                logger.error(f"No categories available to map '{category_term}'. skipping.")
                return None

        # Build image metadata for each image
        image_metadata = {}
        for idx, img_path in enumerate(images_paths):
            filename = os.path.basename(img_path)
            image_metadata[filename] = {
                "alt_text": f"{name} - Image {idx + 1}",
                "is_primary": idx == 0,  # First image is primary
                "order": idx,
            }

        # Prepare payload as data (form fields)
        data = {
            "name": name,
            "description": item.get("description", "") + "\n\nSource: IKEA Demo Data",
            "short_description": item.get("description", "")[:150],
            "price": str(price),
            "stock_quantity": str(10),
            "category": str(category_id),
            "condition": "new",
            "is_featured": "false",
            "image_metadata": json.dumps(image_metadata),  # Send as JSON string
        }

        # Prepare files
        files = []
        open_files = []
        try:
            for img_path in images_paths:
                if os.path.exists(img_path):
                    f = open(img_path, "rb")
                    open_files.append(f)
                    filename = os.path.basename(img_path)
                    mime_type, _ = mimetypes.guess_type(img_path)
                    if not mime_type:
                        mime_type = "application/octet-stream"
                    # 'uploaded_images' matches the new serializer field
                    files.append(("uploaded_images", (filename, f, mime_type)))
                else:
                    logger.warning(f"Image not found: {img_path}")

            # Also support standard 'images' key if backend supports multiple keys or standard DRF behavior
            # The backend loops over request.FILES, so key name actually doesn't matter much for the loop,
            # but for serializer validation it matters. We added 'uploaded_images'.
            # Just in case, let's duplicate or stick to one. The view iterates all request.FILES.
            # But the serializer validation will check 'uploaded_images'.

            headers = self.headers.copy()
            if "Content-Type" in headers:
                del headers["Content-Type"]  # Allow multipart/form-data boundary

            response = requests.post(url, data=data, files=files, headers=headers)

            if response.status_code == 201:
                product_data = response.json()
                logger.info(f"Created product: {name} with {len(files)} images")
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
        finally:
            for f in open_files:
                f.close()

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
