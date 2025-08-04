# Marketplace Test Data Setup

This guide will help you populate your marketplace with test data for development and testing.

## Quick Setup (Recommended)

Run the setup script to get started quickly:

```bash
cd /path/to/Designia-backend
python setup_test_data.py
```

This will:
- Run Django migrations
- Create 6 categories (Sofas, Tables, Chairs, Beds, Storage, Lighting)
- Create 20 sample products with realistic data
- Use existing users or create a test user

## Manual Commands

### Option 1: Quick Test Data (No Image Downloads)
```bash
python manage.py create_test_data --clear
```

### Option 2: Rich Sample Data (With Image Downloads)
```bash
python manage.py populate_sample_data --clear --products 20
```

## Command Options

### create_test_data
- `--clear` - Clear existing data before creating new data

### populate_sample_data
- `--clear` - Clear existing data before creating new data
- `--users N` - Number of sample users to create (default: 5)
- `--products N` - Number of products to create (default: 20)

## What Gets Created

### Categories
- Sofas & Couches
- Tables
- Chairs
- Beds & Mattresses
- Storage & Organization
- Lighting
- Decor & Accessories

### Sample Products
- Modern L-Shaped Sectional Sofa
- Vintage Leather Chesterfield Sofa
- Scandinavian Oak Dining Table
- Industrial Metal Coffee Table
- Ergonomic Office Chair
- Mid-Century Accent Chair
- Memory Foam Queen Mattress
- Industrial Bookshelf Unit
- Modern Floor Lamp
- And more variations...

### Sample Users (if using populate_sample_data)
- furniture_expert
- home_decor_pro
- modern_living
- vintage_finds
- luxury_interiors

## After Setup

1. **Start Django server:**
   ```bash
   python manage.py runserver 192.168.3.2:8001
   ```

2. **Test the marketplace:**
   - Visit your React app
   - Browse products on the homepage
   - Test product creation and editing
   - Try the search functionality

3. **Admin Access:**
   ```bash
   python manage.py createsuperuser
   ```
   Then visit: http://192.168.3.2:8001/admin/

## Troubleshooting

### No Products Showing
- Check Django server is running on port 8001
- Verify React app is configured for port 8001 in `.env`
- Check browser network tab for API errors
- Toggle "Use API Data" button in development mode

### Permission Errors
- Ensure your user has seller permissions
- Check Django admin for user roles

### Migration Issues
```bash
python manage.py makemigrations marketplace
python manage.py migrate
```

## Development Tips

- Use the debug toggle in React components to switch between API and mock data
- Check Django admin to verify data was created
- Monitor Django logs for API errors
- Use browser dev tools to inspect API responses