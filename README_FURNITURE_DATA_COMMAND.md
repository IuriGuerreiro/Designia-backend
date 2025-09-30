# Comprehensive Furniture Data Management Command

This document describes the `create_comprehensive_furniture_data` Django management command that generates realistic, extensive furniture marketplace data for testing and development.

## Overview

The command creates a complete furniture marketplace ecosystem including:
- **Hierarchical Categories**: Main categories with subcategories (Living Room, Bedroom, Office, etc.)
- **Diverse Users**: Individual sellers, businesses, and creators with realistic profiles
- **Realistic Products**: 100s-1000s of furniture items with proper specifications
- **Engagement Data**: Reviews, ratings, favorites, and cart items
- **Product Analytics**: Metrics and performance data

## Quick Start

```bash
# Basic usage - creates 500 products with default settings
python manage.py create_comprehensive_furniture_data

# Create a smaller test dataset
python manage.py create_comprehensive_furniture_data --products 100 --users 10 --reviews 200

# Clear existing data and create fresh dataset
python manage.py create_comprehensive_furniture_data --clear --products 200

# Create only specific categories
python manage.py create_comprehensive_furniture_data --categories living_room,bedroom --products 150
```

## Command Arguments

### Core Data Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--products` | 500 | Number of furniture products to create |
| `--users` | 20 | Number of test users (sellers) to create |
| `--reviews` | 1000 | Number of product reviews to generate |
| `--favorites` | 500 | Number of favorite/wishlist relationships |
| `--cart-items` | 100 | Number of shopping cart items |

### Control Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--clear` | False | Clear existing marketplace data before creation |
| `--no-images` | False | Skip product image generation (faster) |
| `--seed SEED` | Random | Random seed for reproducible data |
| `--batch-size` | 50 | Batch size for bulk database operations |

### Category Filtering

| Argument | Default | Description |
|----------|---------|-------------|
| `--categories` | All | Comma-separated category filters |

Available categories:
- `living_room` - Sofas, coffee tables, accent chairs, etc.
- `bedroom` - Beds, dressers, nightstands, mattresses
- `dining_room` - Dining tables, chairs, bar stools, buffets
- `office` - Desks, office chairs, filing cabinets, bookcases
- `outdoor` - Patio sets, outdoor sofas, garden furniture
- `storage` - Shelving, cabinets, closet systems
- `lighting` - Table lamps, floor lamps, chandeliers
- `decor` - Wall art, mirrors, rugs, curtains

## Generated Data Structure

### Categories (8 Main + 48 Subcategories)

```
📂 Living Room
   ├── Sofas & Sectionals
   ├── Coffee Tables
   ├── TV Stands & Media
   ├── Accent Chairs
   ├── Ottomans & Benches
   └── Bookcases & Shelving

📂 Bedroom
   ├── Beds & Frames
   ├── Mattresses
   ├── Dressers & Chests
   ├── Nightstands
   ├── Wardrobes & Armoires
   └── Vanities & Mirrors

📂 Dining Room
   ├── Dining Tables
   ├── Dining Chairs
   ├── Bar Stools
   ├── Buffets & Sideboards
   ├── China Cabinets
   └── Kitchen Islands

📂 Office & Study
   ├── Desks
   ├── Office Chairs
   ├── Filing Cabinets
   ├── Bookcases
   ├── Conference Tables
   └── Reception Furniture

📂 Outdoor & Patio
   ├── Patio Sets
   ├── Outdoor Sofas
   ├── Garden Furniture
   ├── Umbrellas & Shade
   ├── Outdoor Storage
   └── Fire Pits & Heaters

📂 Storage & Organization
   ├── Shelving Units
   ├── Storage Cabinets
   ├── Closet Systems
   ├── Garage Storage
   ├── Pantry Storage
   └── Bathroom Storage

📂 Lighting
   ├── Table Lamps
   ├── Floor Lamps
   ├── Chandeliers
   ├── Pendant Lights
   ├── Wall Sconces
   └── Smart Lighting

📂 Decor & Accessories
   ├── Wall Art
   ├── Mirrors
   ├── Rugs & Carpets
   ├── Curtains & Blinds
   ├── Vases & Planters
   └── Sculptures & Figurines
```

### User Types

1. **Personal Sellers** (individual users)
   - Furniture enthusiasts and collectors
   - Home decorators and design lovers
   - Realistic personal profiles

2. **Business Sellers** (commercial accounts)
   - Furniture stores and retailers
   - Established businesses with company profiles
   - Professional seller features

3. **Creator Sellers** (artisan accounts)
   - Custom furniture designers
   - Woodworkers and craftspeople
   - Unique, handmade items

### Product Specifications

Each product includes:
- **Basic Info**: Name, description, category, seller
- **Pricing**: Current price, original price (for sales), stock quantity
- **Physical Properties**: Dimensions (L×W×H), weight, materials
- **Attributes**: Colors, condition, brand, tags
- **Images**: Placeholder URLs (if not using `--no-images`)
- **Metadata**: View count, click count, favorite count

### Realistic Data Features

- **Price Distribution**: Skewed toward realistic market prices
- **Condition Variations**: New (60%), Like New (25%), Good (12%), Fair (3%)
- **Material Combinations**: Realistic materials by furniture type
- **Color Palettes**: Style-based color combinations (Modern, Traditional, Scandinavian, etc.)
- **Brand Diversity**: 40+ realistic furniture brands
- **Review Distribution**: Positively skewed (realistic marketplace pattern)

## Example Usage Scenarios

### Development Setup
```bash
# Small dataset for quick development testing
python manage.py create_comprehensive_furniture_data \
    --products 50 \
    --users 5 \
    --reviews 50 \
    --no-images
```

### Demo/Presentation Setup
```bash
# Medium dataset with comprehensive features
python manage.py create_comprehensive_furniture_data \
    --products 200 \
    --users 15 \
    --reviews 400 \
    --favorites 150 \
    --cart-items 50
```

### Performance Testing
```bash
# Large dataset for stress testing
python manage.py create_comprehensive_furniture_data \
    --products 1000 \
    --users 50 \
    --reviews 2000 \
    --favorites 800 \
    --cart-items 200 \
    --batch-size 100
```

### Category-Specific Testing
```bash
# Test only living room and bedroom furniture
python manage.py create_comprehensive_furniture_data \
    --categories living_room,bedroom \
    --products 300 \
    --users 10
```

### Reproducible Test Data
```bash
# Create the same dataset every time using a seed
python manage.py create_comprehensive_furniture_data \
    --seed 12345 \
    --products 100 \
    --users 8
```

## Performance Considerations

### Memory Usage
- **Small** (≤100 products): ~50MB RAM
- **Medium** (≤500 products): ~200MB RAM
- **Large** (≤1000 products): ~400MB RAM
- **Very Large** (>1000 products): >500MB RAM

### Execution Time
- **Small** (≤100 products): 30-60 seconds
- **Medium** (≤500 products): 2-5 minutes
- **Large** (≤1000 products): 5-10 minutes
- **Very Large** (>1000 products): 10+ minutes

### Optimization Tips

1. **Use `--no-images`** for faster generation during development
2. **Increase `--batch-size`** for better performance with large datasets
3. **Use category filtering** to reduce data volume
4. **Set a `--seed`** for reproducible test environments

## Data Cleanup

To remove all generated data:

```bash
python manage.py create_comprehensive_furniture_data --clear
```

**⚠️ Warning**: This will delete ALL marketplace data including:
- Products, categories, reviews, favorites, cart items
- Product images and metrics
- **Does NOT delete user accounts** (for safety)

## Integration with Existing Data

The command is designed to work alongside existing data:

- **Existing Users**: Will reuse existing users as sellers
- **Existing Categories**: Will avoid duplicating categories
- **Existing Products**: Will not interfere with existing products
- **Safe Operation**: Uses Django transactions for data integrity

## Troubleshooting

### Common Issues

1. **"No module named 'marketplace'"**
   - Ensure you're running from the Django project root
   - Check that Django apps are properly installed

2. **Memory errors with large datasets**
   - Reduce `--products` count
   - Increase `--batch-size` for better memory management
   - Use `--no-images` to reduce memory usage

3. **Slow generation**
   - Use `--no-images` for faster creation
   - Increase `--batch-size` for bulk operations
   - Consider using category filtering

4. **Database errors**
   - Ensure database is accessible and has sufficient space
   - Check database permissions
   - Try running with smaller batch sizes

### Debug Mode

For development debugging, you can run the command with Django's debug output:

```bash
python manage.py create_comprehensive_furniture_data --verbosity 2 --products 10
```

## Technical Architecture

### Command Structure
- **FurnitureDataGenerator**: Core data generation engine
- **Command Class**: Django management command interface
- **Template System**: Furniture specification templates
- **Validation Layer**: Data integrity and error handling

### Data Generation Process
1. **Category Creation**: Hierarchical category structure
2. **User Generation**: Diverse seller profiles
3. **Product Creation**: Realistic furniture items with specifications
4. **Image Assignment**: Placeholder image URLs
5. **Review Generation**: Realistic review distribution
6. **Engagement Data**: Favorites and cart items
7. **Metrics Update**: Product analytics and performance data

### Quality Assurance
- **Transaction Safety**: All operations in database transactions
- **Data Validation**: Comprehensive input validation
- **Error Handling**: Graceful error recovery
- **Progress Tracking**: Real-time progress reporting
- **Memory Management**: Efficient batch processing

## Development Notes

### Extending the Command

To add new furniture categories:
1. Update `categories_structure` in `_create_comprehensive_categories()`
2. Add templates in `_get_furniture_templates()`
3. Update material combinations in `_generate_material_combinations()`

To add new furniture templates:
1. Add entries to the appropriate category in `_get_furniture_templates()`
2. Include realistic price ranges, dimensions, and specifications
3. Add appropriate tags and image URLs

### Code Organization
- **Main Command**: `/marketplace/management/commands/create_comprehensive_furniture_data.py`
- **Test Script**: `/test_furniture_command.py`
- **Documentation**: This README file

## License and Usage

This command is part of the Desginia marketplace project and is intended for development and testing purposes. The generated data includes realistic specifications but uses placeholder images from Unsplash.

---

**Generated Data Summary Example:**
```
🎉 COMPREHENSIVE FURNITURE DATA CREATION COMPLETE!

📊 DATA SUMMARY:
┌─────────────────────────────────────────┐
│ CATEGORIES                              │
├─────────────────────────────────────────┤
│ Main Categories:          8            │
│ Subcategories:           48            │
│ Total Categories:        56            │
├─────────────────────────────────────────┤
│ USERS                                   │
├─────────────────────────────────────────┤
│ Total Users:             20            │
│ - Personal:               7            │
│ - Business:               8            │
│ - Creator:                5            │
├─────────────────────────────────────────┤
│ PRODUCTS                                │
├─────────────────────────────────────────┤
│ Total Products:         500            │
│ With Images:            500            │
│ Featured Products:       50            │
│ Price Range:       $49.99 - $3,499.99  │
│ Average Price:          $687.45         │
├─────────────────────────────────────────┤
│ ENGAGEMENT DATA                         │
├─────────────────────────────────────────┤
│ Product Reviews:       1000            │
│ Favorite Items:         500            │
│ Shopping Carts:          67            │
│ Cart Items:             100            │
└─────────────────────────────────────────┘

🚀 READY FOR TESTING!
```