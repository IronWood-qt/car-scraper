"""
End-to-end test suite for the simplified storage system.

This test covers the complete workflow:
1. Mock scraping data
2. Storing data with SimplifiedListingsStorage
3. Reading data back
4. Data processing operations
5. Price change tracking over multiple scrape sessions
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.car_scraper.storage import SimplifiedListingsStorage
from src.car_scraper.utils import DataProcessor


class TestE2ESimplifiedStorage(unittest.TestCase):
    """End-to-end test for the complete simplified storage workflow."""

    def setUp(self):
        """Set up test environment with temporary directory."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.test_data_dir = self.test_dir / "data"
        self.test_data_dir.mkdir()

        # Test model name
        self.test_model = "test-car-model"

        # Create storage instance
        self.storage = SimplifiedListingsStorage(str(self.test_data_dir))

        # Sample listings data for testing
        self.sample_listings_1 = [
            {
                "id": "car-1-abc123.html",
                "title": "BMW 320i 2020",
                "price": 150000,
                "year": 2020,
                "mileage": 45000,
                "url": "https://example.com/car-1-abc123.html",
                "model": self.test_model,
                "scrape_date": "2025-05-31",
                "scrape_timestamp": 1748640000,
            },
            {
                "id": "car-2-def456.html",
                "title": "BMW 320i 2021",
                "price": 180000,
                "year": 2021,
                "mileage": 25000,
                "url": "https://example.com/car-2-def456.html",
                "model": self.test_model,
                "scrape_date": "2025-05-31",
                "scrape_timestamp": 1748640001,
            },
            {
                "id": "car-3-ghi789.html",
                "title": "BMW 320i 2022",
                "price": 200000,
                "year": 2022,
                "mileage": 15000,
                "url": "https://example.com/car-3-ghi789.html",
                "model": self.test_model,
                "scrape_date": "2025-05-31",
                "scrape_timestamp": 1748640002,
            },
        ]

        # Second set with price changes
        self.sample_listings_2 = [
            {
                "id": "car-1-abc123.html",
                "title": "BMW 320i 2020",
                "price": 145000,  # Price decreased
                "year": 2020,
                "mileage": 45000,
                "url": "https://example.com/car-1-abc123.html",
                "model": self.test_model,
                "scrape_date": "2025-06-01",
                "scrape_timestamp": 1748726400,
            },
            {
                "id": "car-2-def456.html",
                "title": "BMW 320i 2021",
                "price": 185000,  # Price increased
                "year": 2021,
                "mileage": 25000,
                "url": "https://example.com/car-2-def456.html",
                "model": self.test_model,
                "scrape_date": "2025-06-01",
                "scrape_timestamp": 1748726401,
            },
            {
                "id": "car-4-jkl012.html",  # New listing
                "title": "BMW 320i 2023",
                "price": 220000,
                "year": 2023,
                "mileage": 5000,
                "url": "https://example.com/car-4-jkl012.html",
                "model": self.test_model,
                "scrape_date": "2025-06-01",
                "scrape_timestamp": 1748726402,
            },
        ]

    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)

    def test_01_initial_data_storage(self):
        """Test initial data storage with new simplified system."""
        print("\n=== Testing Initial Data Storage ===")

        # Store initial data
        self.storage.store_listings_data(
            self.test_model, self.sample_listings_1, "2025-05-31"
        )

        # Verify file was created
        data_file = self.test_data_dir / self.test_model / f"{self.test_model}.json"
        self.assertTrue(data_file.exists(), "Data file should be created")

        # Verify file structure
        with open(data_file) as f:
            data = json.load(f)

        self.assertIn("metadata", data, "Should have metadata section")
        self.assertIn("listings", data, "Should have listings section")
        self.assertEqual(len(data["listings"]), 3, "Should have 3 listings")
        self.assertEqual(data["metadata"]["total_listings"], 3)
        self.assertEqual(data["metadata"]["model"], self.test_model)

        # Verify individual listing structure
        for listing_id, listing in data["listings"].items():
            self.assertIn("internal_id", listing)
            self.assertIn("initial_price", listing)
            self.assertIn("current_price", listing)
            self.assertIn("price_readings", listing)
            self.assertEqual(
                len(listing["price_readings"]),
                1,
                "Should have one initial price reading",
            )
            self.assertEqual(
                listing["price_change"], 0, "Initial price change should be 0"
            )

        print("✅ Initial data storage test passed")

    def test_02_data_retrieval(self):
        """Test data retrieval through get_historical_data."""
        print("\n=== Testing Data Retrieval ===")

        # Store data first
        self.storage.store_listings_data(
            self.test_model, self.sample_listings_1, "2025-05-31"
        )

        # Retrieve data
        df = self.storage.get_historical_data(self.test_model)

        # Verify DataFrame structure
        self.assertEqual(len(df), 3, "Should have 3 rows")
        expected_columns = [
            "id",
            "internal_id",
            "title",
            "price",
            "year",
            "mileage",
            "url",
            "model",
            "date",
            "scrape_timestamp",
        ]
        for col in expected_columns:
            self.assertIn(col, df.columns, f"Should have {col} column")

        # Verify data content
        self.assertEqual(df["model"].iloc[0], self.test_model)
        self.assertTrue(all(df["price"] > 0), "All prices should be positive")
        self.assertTrue(all(df["year"] >= 2020), "All years should be >= 2020")

        print("✅ Data retrieval test passed")

    def test_03_price_change_tracking(self):
        """Test price change tracking over multiple scrape sessions."""
        print("\n=== Testing Price Change Tracking ===")

        # Store initial data
        self.storage.store_listings_data(
            self.test_model, self.sample_listings_1, "2025-05-31"
        )

        # Store updated data with price changes
        self.storage.store_listings_data(
            self.test_model, self.sample_listings_2, "2025-06-01"
        )

        # Verify price changes were tracked
        data_file = self.test_data_dir / self.test_model / f"{self.test_model}.json"
        with open(data_file) as f:
            data = json.load(f)

        # Check car-1 price decrease
        car1 = data["listings"]["car-1-abc123.html"]
        self.assertEqual(car1["initial_price"], 150000)
        self.assertEqual(car1["current_price"], 145000)
        self.assertEqual(car1["price_change"], -5000)
        self.assertEqual(len(car1["price_readings"]), 2, "Should have 2 price readings")

        # Check car-2 price increase
        car2 = data["listings"]["car-2-def456.html"]
        self.assertEqual(car2["initial_price"], 180000)
        self.assertEqual(car2["current_price"], 185000)
        self.assertEqual(car2["price_change"], 5000)
        self.assertEqual(len(car2["price_readings"]), 2, "Should have 2 price readings")

        # Check new listing
        car4 = data["listings"]["car-4-jkl012.html"]
        self.assertEqual(car4["price_change"], 0)
        self.assertEqual(
            len(car4["price_readings"]), 1, "New listing should have 1 price reading"
        )

        print("✅ Price change tracking test passed")

    def test_06_data_processor_integration(self):
        """Test DataProcessor integration with simplified storage."""
        print("\n=== Testing DataProcessor Integration ===")

        # Store data
        self.storage.store_listings_data(
            self.test_model, self.sample_listings_1, "2025-05-31"
        )

        # Create data processor
        processor = DataProcessor(str(self.test_data_dir))

        # Test status functionality
        status = processor.get_data_status()
        self.assertIn("simplified_listings", status)
        self.assertIn(self.test_model, status["simplified_listings"])

        model_status = status["simplified_listings"][self.test_model]
        self.assertEqual(model_status["total_listings"], 3)
        self.assertEqual(model_status["total_price_readings"], 3)

        print("✅ DataProcessor integration test passed")

    def test_07_export_functionality(self):
        """Test data export functionality."""
        print("\n=== Testing Export Functionality ===")

        # Store data
        self.storage.store_listings_data(
            self.test_model, self.sample_listings_1, "2025-05-31"
        )

        # Create processor and test export
        processor = DataProcessor(str(self.test_data_dir))
        exports_dir = self.test_dir / "exports"
        exports_dir.mkdir()

        try:
            # Test CSV export
            processor._export_individual_listings(exports_dir, "csv", self.test_model)
            csv_file = (
                exports_dir
                / f"individual_listings_{self.test_model.replace('/', '_')}.csv"
            )
            self.assertTrue(csv_file.exists(), "CSV export should create file")

            # Verify CSV content
            df = pd.read_csv(csv_file)
            self.assertEqual(len(df), 3, "CSV should have 3 rows")

            print("✅ Export functionality test passed")
        except Exception as e:
            self.fail(f"Export functionality failed: {e}")

    def test_08_backward_compatibility(self):
        """Test backward compatibility with old data format."""
        print("\n=== Testing Backward Compatibility ===")

        # Create old format data file
        old_format_data = [
            {
                "id": "old-car-1.html",
                "title": "Old Format Car",
                "price": 100000,
                "year": 2019,
                "mileage": 50000,
                "url": "https://example.com/old-car-1.html",
                "model": "old-format-model",
                "scrape_date": "2025-05-30T10:00:00",
                "scrape_timestamp": 1748550000,
            }
        ]

        # Save in old format
        old_model_dir = self.test_data_dir / "old-format-model"
        old_model_dir.mkdir()
        old_data_file = old_model_dir / "old-format-model.json"

        with open(old_data_file, "w") as f:
            json.dump(old_format_data, f, indent=2)

        # Test reading old format
        try:
            df = self.storage.get_historical_data("old-format-model")
            self.assertEqual(len(df), 1, "Should read 1 row from old format")
            self.assertEqual(df["price"].iloc[0], 100000)
            print("✅ Backward compatibility test passed")
        except Exception as e:
            self.fail(f"Backward compatibility failed: {e}")

    def test_10_full_workflow_simulation(self):
        """Test complete workflow simulation over multiple days."""
        print("\n=== Testing Full Workflow Simulation ===")

        try:
            # Day 1: Initial scrape
            self.storage.store_listings_data(
                self.test_model, self.sample_listings_1, "2025-05-31"
            )

            # Day 2: Updated scrape with price changes
            self.storage.store_listings_data(
                self.test_model, self.sample_listings_2, "2025-06-01"
            )

            # Test data processing
            processor = DataProcessor(str(self.test_data_dir))
            status = processor.get_data_status()

            # Verify complete workflow
            self.assertIn(self.test_model, status["simplified_listings"])
            model_info = status["simplified_listings"][self.test_model]
            self.assertEqual(model_info["total_listings"], 4)  # 3 original + 1 new
            self.assertGreater(
                model_info["total_price_readings"], 4
            )  # Should have price history

            # Verify historical data includes price changes
            df = self.storage.get_historical_data(self.test_model)
            self.assertGreater(len(df), 4, "Should have historical price readings")

            print("✅ Full workflow simulation test passed")

        except Exception as e:
            self.fail(f"Full workflow simulation failed: {e}")


if __name__ == "__main__":
    # Configure test runner
    unittest.main(verbosity=2, buffer=True)
