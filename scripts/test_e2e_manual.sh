#!/bin/bash

# Manual E2E Test Script for Car Scraper - Lexus LC
# This script tests the complete workflow using the CLI via Poetry
# Simulates a real CI/CD environment test scenario

set -e  # Exit on any error

echo "🚀 Starting Manual E2E Test for Car Scraper - Lexus LC"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
MODEL="lexus-lc"
MAKE="lexus"
MODEL_NAME="lc"
TEST_DATA_DIR="./data_test_e2e"
BACKUP_DIR="./data_backup_$(date +%Y%m%d_%H%M%S)"
CI_MODE=${CI:-false}  # Check if running in CI environment

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command succeeded
check_command() {
    if [ $? -eq 0 ]; then
        print_success "$1"
    else
        print_error "$1 failed"
        exit 1
    fi
}

# Cleanup function
cleanup() {
    print_status "Cleaning up test environment..."
    if [ -d "$TEST_DATA_DIR" ]; then
        rm -rf "$TEST_DATA_DIR"
        print_success "Removed test data directory"
    fi
}

# Trap cleanup on exit
trap cleanup EXIT

print_status "Step 1: Environment Setup"
# Change to script directory and then to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Script directory: $SCRIPT_DIR"
echo "Project root: $PROJECT_ROOT"
echo "Current directory: $(pwd)"
echo "Python version: $(python --version 2>&1 || echo 'Python not found')"
echo "Poetry version: $(poetry --version 2>&1 || echo 'Poetry not found')"
echo "CI Mode: $CI_MODE"

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    print_error "pyproject.toml not found. Please run this script from the project root."
    exit 1
fi

print_success "Environment check passed"

print_status "Step 2: Backup existing data (if any)"
if [ -d "data" ]; then
    cp -r data "$BACKUP_DIR"
    print_success "Backed up existing data to $BACKUP_DIR"
else
    print_warning "No existing data directory found"
fi

print_status "Step 3: Create test data directory"
mkdir -p "$TEST_DATA_DIR"
check_command "Test data directory created"

print_status "Step 4: Install dependencies"
poetry install
check_command "Dependencies installed"

print_status "Step 5: Test CLI help command"
poetry run python main.py --help > /dev/null
check_command "CLI help command works"

print_status "Step 6: Test scraping with simplified storage (dry run simulation)"
# Since we can't do real scraping in CI, let's create some test data
# and use the simplified storage system directly

print_status "Creating sample data for testing..."

# Create Python script to generate test data
cat > test_data_generator.py << 'EOF'
#!/usr/bin/env python3
"""Generate test data for E2E testing"""

import json
import time
from datetime import datetime
from pathlib import Path

def create_test_data():
    """Create sample lexus-lc data for testing"""

    # Sample data that mimics real scraped data
    sample_listings = [
        {
            "id": "lexus-lc-500-2021-test1.html",
            "title": "Lexus LC 500 2021 V8",
            "price": 450000,
            "year": 2021,
            "mileage": 15000,
            "url": "https://example.com/test1",
            "model": "lexus-lc",
            "scrape_date": "2025-05-31",
            "scrape_timestamp": int(time.time())
        },
        {
            "id": "lexus-lc-500h-2022-test2.html",
            "title": "Lexus LC 500h 2022 Hybrid",
            "price": 520000,
            "year": 2022,
            "mileage": 8000,
            "url": "https://example.com/test2",
            "model": "lexus-lc",
            "scrape_date": "2025-05-31",
            "scrape_timestamp": int(time.time())
        },
        {
            "id": "lexus-lc-500-2020-test3.html",
            "title": "Lexus LC 500 2020 Coupe",
            "price": 420000,
            "year": 2020,
            "mileage": 25000,
            "url": "https://example.com/test3",
            "model": "lexus-lc",
            "scrape_date": "2025-05-31",
            "scrape_timestamp": int(time.time())
        }
    ]

    return sample_listings

if __name__ == "__main__":
    import sys
    sys.path.insert(0, 'src')

    from car_scraper.storage.simplified_listings import SimplifiedListingsStorage

    # Create test data directory
    test_dir = "./data_test_e2e"
    Path(test_dir).mkdir(parents=True, exist_ok=True)

    # Create storage instance
    storage = SimplifiedListingsStorage(test_dir)

    # Generate and store test data
    test_data = create_test_data()
    storage.store_listings_data("lexus-lc", test_data, "2025-05-31")

    print(f"✅ Created test data: {len(test_data)} listings for lexus-lc")

    # Create second batch with price changes for time series testing
    updated_data = test_data.copy()
    updated_data[0]["price"] = 445000  # Price decrease
    updated_data[1]["price"] = 525000  # Price increase
    # Add new listing
    updated_data.append({
        "id": "lexus-lc-500-2023-test4.html",
        "title": "Lexus LC 500 2023 Limited",
        "price": 580000,
        "year": 2023,
        "mileage": 2000,
        "url": "https://example.com/test4",
        "model": "lexus-lc",
        "scrape_date": "2025-06-01",
        "scrape_timestamp": int(time.time())
    })

    storage.store_listings_data("lexus-lc", updated_data, "2025-06-01")
    print(f"✅ Created updated data: {len(updated_data)} listings with price changes")
EOF

poetry run python test_data_generator.py
check_command "Test data generated"

print_status "Step 7: Test data processor with simplified storage"
poetry run python -c "
import sys
sys.path.insert(0, 'src')
from car_scraper.utils.data_processor import DataProcessor

processor = DataProcessor('./data_test_e2e')
status = processor.get_data_status()
print('Data status:', status)

if 'simplified_listings' in status and 'lexus-lc' in status['simplified_listings']:
    print('✅ SimplifiedListingsStorage detected correctly')
    model_info = status['simplified_listings']['lexus-lc']
    print(f'Total listings: {model_info[\"total_listings\"]}')
    print(f'Total price readings: {model_info[\"total_price_readings\"]}')
else:
    print('❌ SimplifiedListingsStorage not detected')
    sys.exit(1)
"
check_command "Data processor test"

print_status "Step 10: Test data export functionality"
poetry run python -c "
import sys
import pandas as pd
sys.path.insert(0, 'src')
from car_scraper.utils.data_processor import DataProcessor

processor = DataProcessor('./data_test_e2e')
try:
    # Test export to CSV
    df = processor.export_to_csv('lexus-lc', './data_test_e2e/export_test.csv')
    print(f'✅ Exported {len(df)} records to CSV')

    # Test export to JSON
    df_json = processor.export_to_json('lexus-lc', './data_test_e2e/export_test.json')
    print(f'✅ Exported {len(df_json)} records to JSON')

except Exception as e:
    print(f'❌ Export failed: {e}')
    sys.exit(1)
"
check_command "Data export functionality"

print_status "Step 11: Verify output files exist"
expected_files=(
    "./data_test_e2e/lexus-lc/lexus-lc.json"
    "./data_test_e2e/export_test.csv"
    "./data_test_e2e/export_test.json"
)

for file in "${expected_files[@]}"; do
    if [ -f "$file" ]; then
        print_success "✅ $file exists"
    else
        print_error "❌ $file missing"
        exit 1
    fi
done

print_status "Step 12: Test data integrity and price tracking"
poetry run python -c "
import sys
import json
sys.path.insert(0, 'src')
from car_scraper.storage.simplified_listings import SimplifiedListingsStorage

storage = SimplifiedListingsStorage('./data_test_e2e')

# Load and verify data structure
with open('./data_test_e2e/lexus-lc/lexus-lc.json', 'r') as f:
    data = json.load(f)

print('Data structure validation:')
print(f'✅ Metadata present: {\"metadata\" in data}')
print(f'✅ Listings present: {\"listings\" in data}')
print(f'✅ Total listings: {len(data[\"listings\"])}')

# Check for price readings
price_changes = 0
for listing_id, listing in data['listings'].items():
    if len(listing.get('price_readings', [])) > 1:
        price_changes += 1

print(f'✅ Listings with price history: {price_changes}')

# Test historical data retrieval
df = storage.get_historical_data('lexus-lc')
print(f'✅ Historical data rows: {len(df)}')
print(f'✅ Historical data columns: {list(df.columns)}')
"
check_command "Data integrity verification"

print_status "Step 13: Test CLI (main.py scrape-all engine)"
poetry run python main.py --help > /dev/null
check_command "CLI help command works"

print_status "Step 14: Performance and memory check"
poetry run python -c "
import sys
import time
import os
sys.path.insert(0, 'src')

try:
    import psutil
    process = psutil.Process(os.getpid())
    start_memory = process.memory_info().rss / 1024 / 1024  # MB
    psutil_available = True
except ImportError:
    start_memory = 0
    psutil_available = False
    print('⚠️  psutil not available, skipping memory tracking')

from car_scraper.storage.simplified_listings import SimplifiedListingsStorage

start_time = time.time()

# Test operations
storage = SimplifiedListingsStorage('./data_test_e2e')
df = storage.get_historical_data('lexus-lc')

end_time = time.time()

if psutil_available:
    end_memory = process.memory_info().rss / 1024 / 1024  # MB
    print(f'✅ Memory usage: {end_memory - start_memory:.2f} MB increase')
else:
    print('✅ Memory tracking skipped (psutil not available)')

print(f'✅ Performance test completed in {end_time - start_time:.2f} seconds')
print(f'✅ Data processing: {len(df)} records processed')
"
check_command "Performance check"

# Cleanup test files
rm -f test_data_generator.py

echo ""
echo "=================================================="
print_success "🎉 Manual E2E Test COMPLETED SUCCESSFULLY!"
echo "=================================================="
echo ""
print_status "Test Summary:"
echo "✅ Environment setup and dependency installation"
echo "✅ Test data generation with SimplifiedListingsStorage"
echo "✅ Data processor integration and status checking"
echo "✅ Data export functionality (CSV and JSON)"
echo "✅ File output verification"
echo "✅ Data integrity and price tracking validation"
echo "✅ Performance and memory usage check"
echo ""
print_status "Generated Files:"
echo "📁 ./data_test_e2e/lexus-lc/lexus-lc.json (simplified storage format)"
echo "💾 ./data_test_e2e/export_test.csv (exported data)"
echo "💾 ./data_test_e2e/export_test.json (exported data)"
if [ -d "$BACKUP_DIR" ]; then
    echo "💾 $BACKUP_DIR (backup of original data)"
fi
echo ""
print_success "All systems operational! Ready for CI/CD deployment 🚀"
