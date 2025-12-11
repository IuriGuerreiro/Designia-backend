#!/usr/bin/env python
"""
Script to fix Order model creation in test files
"""

import os
import re


def fix_order_creation(content):
    """Fix Order.objects.create calls to include required fields"""
    # Pattern to match Order.objects.create calls
    pattern = r"Order\.objects\.create\(\s*\n(\s+)([^)]+)\)"

    def replacement(match):
        indent = match.group(1)
        params = match.group(2)

        # Parse existing parameters
        lines = [line.strip().rstrip(",") for line in params.strip().split("\n") if line.strip()]

        has_subtotal = any("subtotal=" in line for line in lines)
        has_shipping_address = any("shipping_address=" in line for line in lines)

        # Add missing fields
        if not has_subtotal:
            # Find total_amount line and add subtotal before it
            for i, line in enumerate(lines):
                if "total_amount=" in line:
                    # Extract the amount
                    amount = line.split("=")[1].strip()
                    subtotal_line = f"subtotal={amount}"
                    lines.insert(i, subtotal_line)
                    break

        if not has_shipping_address:
            shipping_address = "shipping_address={'street': '123 Test St', 'city': 'Test City', 'state': 'TC', 'postal_code': '12345', 'country': 'US'}"
            lines.append(shipping_address)

        # Reconstruct the call
        formatted_params = ",\n".join(f"{indent}{line}" for line in lines)
        return f"Order.objects.create(\n{formatted_params}\n{indent.rstrip()})"

    return re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)


def fix_order_item_creation(content):
    """Fix OrderItem.objects.create calls to include required fields"""
    pattern = r"OrderItem\.objects\.create\(\s*\n(\s+)([^)]+)\)"

    def replacement(match):
        indent = match.group(1)
        params = match.group(2)

        lines = [line.strip().rstrip(",") for line in params.strip().split("\n") if line.strip()]

        # Fix field names and add missing fields
        fixed_lines = []
        has_seller = False
        has_product_description = False

        for line in lines:
            if "price=" in line and "unit_price=" not in line and "total_price=" not in line:
                # Change price to unit_price
                fixed_lines.append(line.replace("price=", "unit_price="))
                # Also add total_price with same value
                price_value = line.split("=")[1].strip()
                fixed_lines.append(f"total_price={price_value}")
                # unit_price and total_price accounted for
            else:
                fixed_lines.append(line)
                if "seller=" in line:
                    has_seller = True
                # presence of unit_price/total_price does not impact logic beyond existence
                elif "product_description=" in line:
                    has_product_description = True

        # Add missing fields
        if not has_seller and any("product=" in line for line in fixed_lines):
            fixed_lines.append("seller=self.seller")

        if not has_product_description and any("product_name=" in line for line in fixed_lines):
            fixed_lines.append("product_description=self.product.description")

        formatted_params = ",\n".join(f"{indent}{line}" for line in fixed_lines)
        return f"OrderItem.objects.create(\n{formatted_params}\n{indent.rstrip()})"

    return re.sub(pattern, replacement, content, flags=re.MULTILINE | re.DOTALL)


def fix_file(filepath):
    """Fix a single test file"""
    try:
        with open(filepath, "r") as f:
            content = f.read()

        original_content = content
        content = fix_order_creation(content)
        content = fix_order_item_creation(content)

        if content != original_content:
            with open(filepath, "w") as f:
                f.write(content)
            print(f"  Fixed {filepath}")
        else:
            print(f"ℹ️ No changes needed for {filepath}")

    except Exception as e:
        print(f" Error fixing {filepath}: {e}")


def main():
    """Fix all test files"""
    test_dir = os.path.dirname(__file__)
    test_files = [
        os.path.join(test_dir, "test_views.py"),
        os.path.join(test_dir, "test_end_to_end.py"),
        os.path.join(test_dir, "test_webhooks.py"),
    ]

    print("🔧 Fixing Order model creation in test files...")

    for filepath in test_files:
        if os.path.exists(filepath):
            fix_file(filepath)
        else:
            print(f"⚠️ File not found: {filepath}")

    print("  Test file fixes completed!")


if __name__ == "__main__":
    main()
