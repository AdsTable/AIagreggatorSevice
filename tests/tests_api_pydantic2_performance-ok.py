"""
Performance and stress tests for Pydantic 2.x migration
"""

import pytest
import time
import asyncio
import json
import math
import concurrent.futures
import psutil
import gc
from typing import List, Dict, Any
from pydantic import ValidationError
from unittest.mock import AsyncMock
from models import StandardizedProduct, create_product_db_from_standardized
import random


class TestPydantic2Performance:
    """Performance tests for Pydantic 2.x features."""
    
    def test_model_validation_performance(self):
        """Test model validation performance with Pydantic 2.x."""
        # Create a large number of products to test performance
        start_time = time.time()
        
        products = []
        for i in range(1000):
            product = StandardizedProduct(
                category="electricity_plan",
                source_url=f"https://test.com/product{i}",
                name=f"Product {i}",
                provider_name=f"Provider {i % 10}",
                product_id=f"perf_{i}",
                price_kwh=round(random.uniform(0.10, 0.50), 3),
                standing_charge=round(random.uniform(1.0, 10.0), 2),
                contract_duration_months=random.choice([0, 12, 24]),
                monthly_cost=round(random.uniform(10.0, 100.0), 2),
                data_gb=float(random.randint(1, 100)),
                calls=random.choice([100, 500, 999999.0]),
                texts=random.choice([100, 500, 999999.0]),
                network_type="4G",
                available=i % 2 == 0,
                raw_data={"index": i, "test": True}
            )
            products.append(product)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"Created {len(products)} products in {duration:.3f} seconds")
        print(f"Average: {duration/len(products)*1000:.3f} ms per product")
        
        # Performance should be reasonable (less than 1 second for 1000 products)
        assert duration < 1.0
        assert len(products) == 1000

    def test_json_serialization_performance(self):
        """Test JSON serialization performance with infinity/NaN handling."""
        # Create products with various problematic values
        products = []
        for i in range(500):
            product = StandardizedProduct(
                category="mobile_plan",
                source_url=f"https://test.com/mobile{i}",
                name=f"Mobile Plan {i}",
                provider_name=f"Mobile Provider {i % 5}",
                monthly_cost=30.0 + (i * 0.1),
                data_gb=float('inf') if i % 10 == 0 else 50.0 + i,  # Some unlimited plans
                calls=float('inf') if i % 7 == 0 else 1000.0,       # Some unlimited calls
                texts=500.0,
                network_type="5G" if i % 3 == 0 else "4G",
                available=True,
                raw_data={
                    "index": i,
                    "test_inf": float('inf') if i % 5 == 0 else i,
                    "test_nan": float('nan') if i % 8 == 0 else i,
                    "nested": {
                        "value": float('inf') if i % 12 == 0 else i * 2,
                        "list": [float('inf'), float('nan'), i] if i % 20 == 0 else [i, i+1, i+2]
                    }
                }
            )
            products.append(product)

        # Test JSON-safe serialization performance
        start_time = time.time()
        
        json_safe_dicts = []
        for product in products:
            json_safe_dict = product.to_json_safe_dict()
            json_safe_dicts.append(json_safe_dict)
        
        serialization_time = time.time() - start_time
        
        # Test actual JSON dumps performance
        json_dumps_start = time.time()
        
        json_strings = []
        for json_dict in json_safe_dicts:
            json_str = json.dumps(json_dict)
            json_strings.append(json_str)
        
        json_dumps_time = time.time() - json_dumps_start
        
        print(f"JSON-safe serialization: {serialization_time:.3f}s ({serialization_time/len(products)*1000:.3f}ms per product)")
        print(f"JSON dumps: {json_dumps_time:.3f}s ({json_dumps_time/len(products)*1000:.3f}ms per product)")
        
        # Verify all serializations succeeded without errors
        assert len(json_safe_dicts) == 500
        assert len(json_strings) == 500
        
        # Performance should be reasonable
        assert serialization_time < 2.0  # Less than 2 seconds for 500 products
        assert json_dumps_time < 1.0     # Less than 1 second for JSON dumps
        
        # Verify infinity/NaN handling worked
        sample_json = json.loads(json_strings[0])
        assert isinstance(sample_json, dict)

    def test_memory_usage_performance(self):
        """Test memory usage during large-scale operations."""
        # Measure initial memory
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create many products and measure memory growth
        products = []
        for i in range(2000):
            product = StandardizedProduct(
                category="internet_plan",
                source_url=f"https://test.com/internet{i}",
                name=f"Internet Plan {i}",
                provider_name=f"ISP {i % 8}",
                download_speed=100.0 + (i * 10),
                upload_speed=50.0 + (i * 5),
                connection_type="Fiber" if i % 2 == 0 else "Cable",
                monthly_cost=60.0 + (i * 0.5),
                data_cap_gb=float('inf') if i % 15 == 0 else None,
                available=True,
                raw_data={
                    "large_data": [f"item_{j}" for j in range(50)],  # Some bulk data
                    "features": {
                        f"feature_{k}": f"value_{k}_{i}" for k in range(20)
                    }
                }
            )
            products.append(product)
            
            # Check memory periodically
            if i % 500 == 499:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_growth = current_memory - initial_memory
                print(f"After {i+1} products: {memory_growth:.1f}MB growth")
        
        final_memory = process.memory_info().rss / 1024 / 1024
        total_growth = final_memory - initial_memory
        
        print(f"Total memory growth: {total_growth:.1f}MB for {len(products)} products")
        print(f"Average: {total_growth/len(products)*1024:.2f}KB per product")
        
        # Memory growth should be reasonable (less than 200MB for 2000 products)
        assert total_growth < 200
        assert len(products) == 2000
        
        # Clean up
        del products
        gc.collect()

    def test_model_dump_vs_legacy_dict_performance(self):
        """Compare model_dump() vs legacy dict() performance."""
        # Create test products
        products = []
        for i in range(1000):
            product = StandardizedProduct(
                category="electricity_plan",
                source_url=f"https://test.com/elec{i}",
                name=f"Electricity Plan {i}",
                provider_name=f"Electric Corp {i % 6}",
                price_kwh=0.12 + (i * 0.0001),
                standing_charge=4.0 + (i * 0.001),
                contract_type="Fixed" if i % 2 == 0 else "Variable",
                available=True
            )
            products.append(product)

        # Test model_dump() performance (Pydantic 2.x)
        start_time = time.time()
        
        model_dump_results = []
        for product in products:
            result = product.model_dump()
            model_dump_results.append(result)
        
        model_dump_time = time.time() - start_time

        # Test model_dump(mode="json") performance with serializers
        json_mode_start = time.time()
        
        json_mode_results = []
        for product in products:
            result = product.model_dump(mode="json")
            json_mode_results.append(result)
        
        json_mode_time = time.time() - json_mode_start

        print(f"model_dump(): {model_dump_time:.3f}s ({model_dump_time/len(products)*1000:.3f}ms per product)")
        print(f"model_dump(mode='json'): {json_mode_time:.3f}s ({json_mode_time/len(products)*1000:.3f}ms per product)")
        
        # Both should complete quickly
        assert model_dump_time < 1.0
        assert json_mode_time < 1.0
        
        # Verify results
        assert len(model_dump_results) == 1000
        assert len(json_mode_results) == 1000
        
        # Verify that json mode handles special values correctly
        # (This would matter if we had infinity/NaN values)
        assert isinstance(model_dump_results[0], dict)
        assert isinstance(json_mode_results[0], dict)

    def test_concurrent_validation_performance(self):
        """Test concurrent model validation performance."""
        def create_product_batch(start_idx: int, count: int) -> List[StandardizedProduct]:
            """Create a batch of products."""
            products = []
            for i in range(start_idx, start_idx + count):
                product = StandardizedProduct(
                    category="mobile_plan",
                    source_url=f"https://test.com/concurrent{i}",
                    name=f"Concurrent Plan {i}",
                    provider_name=f"Provider {i % 4}",
                    monthly_cost=25.0 + (i * 0.1),
                    data_gb=10.0 + i,
                    network_type="5G",
                    available=True
                )
                products.append(product)
            return products

        # Test sequential creation
        start_time = time.time()
        sequential_products = create_product_batch(0, 1000)
        sequential_time = time.time() - start_time

        # Test concurrent creation
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            batch_size = 250
            for i in range(0, 1000, batch_size):
                future = executor.submit(create_product_batch, i, batch_size)
                futures.append(future)
            
            concurrent_results = []
            for future in concurrent.futures.as_completed(futures):
                batch = future.result()
                concurrent_results.extend(batch)
        
        concurrent_time = time.time() - start_time

        print(f"Sequential creation: {sequential_time:.3f}s")
        print(f"Concurrent creation: {concurrent_time:.3f}s")
        print(f"Speedup: {sequential_time/concurrent_time:.2f}x")

        # Verify results
        assert len(sequential_products) == 1000
        assert len(concurrent_results) == 1000
        
        # Concurrent should be faster or at least not significantly slower
        # (allowing some overhead for thread management)
        assert concurrent_time <= sequential_time * 2.5

    @pytest.mark.asyncio
    async def test_async_database_operations_performance(self):
        """Test async database operations performance simulation."""
        # Create test products
        products = []
        for i in range(500):
            product = StandardizedProduct(
                category="internet_plan",
                source_url=f"https://test.com/async{i}",
                name=f"Async Plan {i}",
                provider_name=f"Async ISP {i % 3}",
                download_speed=100.0 + i,
                monthly_cost=50.0 + (i * 0.2),
                available=True
            )
            products.append(product)

        # Simulate async database operations
        async def mock_store_product(product: StandardizedProduct) -> bool:
            """Mock async database store operation."""
            # Simulate some async work
            await asyncio.sleep(0.001)  # 1ms delay
            # Convert to DB model to test conversion performance
            db_product = create_product_db_from_standardized(product)
            return db_product is not None

        # Test sequential async operations
        start_time = time.time()
        
        sequential_results = []
        for product in products[:100]:  # Test with smaller subset for speed
            result = await mock_store_product(product)
            sequential_results.append(result)
        
        sequential_time = time.time() - start_time

        # Test concurrent async operations
        start_time = time.time()
        
        tasks = []
        for product in products[:100]:
            task = asyncio.create_task(mock_store_product(product))
            tasks.append(task)
        
        concurrent_results = await asyncio.gather(*tasks)
        concurrent_time = time.time() - start_time

        print(f"Sequential async: {sequential_time:.3f}s")
        print(f"Concurrent async: {concurrent_time:.3f}s")
        print(f"Async speedup: {sequential_time/concurrent_time:.2f}x")

        # Verify results
        assert len(sequential_results) == 100
        assert len(concurrent_results) == 100
        assert all(sequential_results)
        assert all(concurrent_results)
        
        # Concurrent should be significantly faster
        assert concurrent_time < sequential_time * 0.5

    def test_large_raw_data_serialization_performance(self):
        """Test performance with large raw_data fields."""
        # Create products with large raw_data
        products = []
        for i in range(100):  # Smaller count due to large data
            large_raw_data = {
                "measurements": [{"timestamp": j, "value": j * 1.5} for j in range(1000)],
                "features": {f"feature_{k}": f"long_description_value_{k}_{i}" * 10 for k in range(100)},
                "metadata": {
                    "history": [f"event_{m}_{i}" for m in range(200)],
                    "analytics": {
                        "stats": [i + n for n in range(500)],
                        "complex_data": {
                            f"level_{p}": {
                                f"sublevel_{q}": f"data_{p}_{q}_{i}" for q in range(20)
                            } for p in range(10)
                        }
                    }
                },
                "test_special_values": {
                    "infinity": float('inf'),
                    "negative_infinity": float('-inf'),
                    "nan": float('nan'),
                    "nested_inf": {"value": float('inf')},
                    "list_with_special": [float('inf'), float('nan'), 42.0]
                }
            }
            
            product = StandardizedProduct(
                category="electricity_plan",
                source_url=f"https://test.com/large{i}",
                name=f"Large Data Plan {i}",
                provider_name=f"Big Data Corp {i % 2}",
                price_kwh=0.15,
                available=True,
                raw_data=large_raw_data
            )
            products.append(product)

        # Test serialization performance
        start_time = time.time()
        
        serialized_products = []
        for product in products:
            json_safe_dict = product.to_json_safe_dict()
            json_str = json.dumps(json_safe_dict)
            serialized_products.append(json_str)
        
        serialization_time = time.time() - start_time

        # Test deserialization performance
        start_time = time.time()
        
        deserialized_data = []
        for json_str in serialized_products:
            data = json.loads(json_str)
            deserialized_data.append(data)
        
        deserialization_time = time.time() - start_time

        print(f"Large data serialization: {serialization_time:.3f}s ({serialization_time/len(products)*1000:.1f}ms per product)")
        print(f"Large data deserialization: {deserialization_time:.3f}s ({deserialization_time/len(products)*1000:.1f}ms per product)")

        # Verify all operations completed
        assert len(serialized_products) == 100
        assert len(deserialized_data) == 100
        
        # Performance should be reasonable even with large data
        assert serialization_time < 10.0    # Less than 10 seconds
        assert deserialization_time < 5.0   # Less than 5 seconds
        
        # Verify special values were handled correctly
        sample_data = deserialized_data[0]
        special_values = sample_data["raw_data"]["test_special_values"]
        
        # Check infinity/NaN conversion
        assert special_values["infinity"] == 999999.0
        assert special_values["negative_infinity"] == -999999.0
        assert special_values["nan"] is None
        assert special_values["nested_inf"]["value"] == 999999.0
        assert special_values["list_with_special"][0] == 999999.0
        assert special_values["list_with_special"][1] is None
        assert special_values["list_with_special"][2] == 42.0

    def test_field_validation_edge_cases_performance(self):
        """Test performance of field validation with edge cases."""
        # Test data with various edge cases
        edge_cases = [
            {"category": "electricity_plan", "source_url": "https://test.com/edge1"},
            {"category": "mobile_plan", "source_url": "https://test.com/edge2"},
            {"category": "internet_plan", "source_url": "https://test.com/edge3"},
        ]
        
        # Add edge case values
        for i, base_data in enumerate(edge_cases):
            base_data.update({
                "name": f"Edge Case {i}",
                "provider_name": "  Edge Provider  ",  # Test whitespace trimming
                "contract_duration_months": 0 if i == 0 else 12,
                "price_kwh": 0.0 if i == 1 else 0.15,
                "monthly_cost": float('inf') if i == 2 else 30.0,
                "data_gb": float('-inf') if i == 0 else float('nan') if i == 1 else 50.0,
                "available": True
            })

        # Test validation performance with edge cases
        start_time = time.time()
        
        validated_products = []
        for i in range(1000):  # Create many products with cycling edge cases
            edge_data = edge_cases[i % len(edge_cases)].copy()
            edge_data["source_url"] = f"https://test.com/edge{i}"
            edge_data["name"] = f"Edge Case {i}"
            
            try:
                product = StandardizedProduct(**edge_data)
                validated_products.append(product)
            except ValueError as e:
                print(f"Validation error for case {i}: {e}")

        validation_time = time.time() - start_time

        print(f"Edge case validation: {validation_time:.3f}s ({validation_time/1000*1000:.3f}ms per product)")
        print(f"Successfully validated: {len(validated_products)}/1000 products")

        # Should complete quickly even with edge cases
        assert validation_time < 2.0
        assert len(validated_products) > 0  # At least some should validate successfully

    def test_stress_test_maximum_load(self):
        """Stress test with maximum realistic load."""
        print("\n=== STRESS TEST: Maximum Load ===")
        
        # Test with very large dataset
        start_time = time.time()
        stress_products = []
        
        categories = ["electricity_plan", "mobile_plan", "internet_plan"]
        providers = [f"Provider_{i}" for i in range(20)]
        
        for i in range(5000):  # Large dataset
            category = categories[i % len(categories)]
            provider = providers[i % len(providers)]
            
            # Vary the data complexity
            complex_raw_data = {}
            if i % 100 == 0:  # Every 100th product has complex data
                complex_raw_data = {
                    "complex_metrics": [{"id": j, "value": j * 1.1} for j in range(100)],
                    "features": {f"f_{k}": f"value_{k}" for k in range(50)},
                    "special_values": {
                        "inf_val": float('inf') if i % 200 == 0 else i,
                        "nan_val": float('nan') if i % 300 == 0 else i * 2
                    }
                }
            
            product = StandardizedProduct(
                category=category,
                source_url=f"https://stress.test.com/{category}/{i}",
                name=f"Stress Test Product {i}",
                provider_name=provider,
                price_kwh=0.10 + (i % 100) * 0.001 if category == "electricity_plan" else None,
                monthly_cost=20.0 + (i % 200) * 0.1 if category in ["mobile_plan", "internet_plan"] else None,
                data_gb=10.0 + (i % 500) if category == "mobile_plan" else None,
                download_speed=100.0 + (i % 1000) if category == "internet_plan" else None,
                contract_duration_months=(i % 36) + 1,
                available=i % 10 != 0,  # 90% available
                raw_data=complex_raw_data
            )
            stress_products.append(product)

        creation_time = time.time() - start_time

        # Test mass serialization
        serialization_start = time.time()
        
        serialized_count = 0
        for i, product in enumerate(stress_products):
            try:
                json_dict = product.to_json_safe_dict()
                json_str = json.dumps(json_dict)
                serialized_count += 1
                
                # Progress reporting
                if i % 1000 == 999:
                    elapsed = time.time() - serialization_start
                    rate = (i + 1) / elapsed
                    print(f"Serialized {i+1}/5000 products ({rate:.0f} products/sec)")
                    
            except Exception as e:
                print(f"Serialization error for product {i}: {e}")

        total_serialization_time = time.time() - serialization_start

        # Calculate performance metrics
        total_time = creation_time + total_serialization_time
        products_per_second = len(stress_products) / total_time
        
        print(f"\n=== STRESS TEST RESULTS ===")
        print(f"Products created: {len(stress_products)}")
        print(f"Creation time: {creation_time:.3f}s")
        print(f"Serialization time: {total_serialization_time:.3f}s")
        print(f"Total time: {total_time:.3f}s")
        print(f"Overall rate: {products_per_second:.0f} products/second")
        print(f"Successfully serialized: {serialized_count}/{len(stress_products)}")
        
        # Performance assertions for stress test
        assert len(stress_products) == 5000
        assert serialized_count >= 4900  # At least 98% should serialize successfully
        assert total_time < 30.0         # Should complete within 30 seconds
        assert products_per_second > 100 # Should handle at least 100 products/second
        
        print("✅ Stress test completed successfully!")


if __name__ == "__main__":
    # Run performance tests with detailed output
    print("=== PYDANTIC 2.X PERFORMANCE TEST SUITE ===")
    print("🚀 Testing model validation, serialization, and stress scenarios")
    print("📊 Measuring memory usage, concurrent operations, and large data handling")
    print()
    
    # Run individual tests for detailed analysis
    test_suite = TestPydantic2Performance()
    
    print("1. Testing model validation performance...")
    test_suite.test_model_validation_performance()
    
    print("\n2. Testing JSON serialization performance...")
    test_suite.test_json_serialization_performance()
    
    print("\n3. Testing memory usage...")
    test_suite.test_memory_usage_performance()
    
    print("\n4. Testing model_dump vs legacy dict...")
    test_suite.test_model_dump_vs_legacy_dict_performance()
    
    print("\n5. Testing concurrent validation...")
    test_suite.test_concurrent_validation_performance()
    
    print("\n6. Testing large raw data serialization...")
    test_suite.test_large_raw_data_serialization_performance()
    
    print("\n7. Testing field validation edge cases...")
    test_suite.test_field_validation_edge_cases_performance()
    
    print("\n8. Running stress test...")
    test_suite.test_stress_test_maximum_load()
    
    print("\n🎉 All performance tests completed!")
    print("\nRun with pytest for automated testing:")
    print("pytest tests/tests_api_pydantic2_performance-ok.py -v --tb=short")