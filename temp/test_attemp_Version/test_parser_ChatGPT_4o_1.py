# ✅ test_parser.py  https://chatgpt.com/share/6830d70a-0870-800d-bc5d-5728de21fa76

import pytest
import math
from data_parser import (
    extract_float_with_units,
    extract_float_or_handle_unlimited,
    extract_duration_in_months,
    parse_availability,
    standardize_extracted_product,
    parse_and_standardize
)
from models import StandardizedProduct


def test_extract_float_with_units():
    assert extract_float_with_units("0.15 $/kWh", ["$/kwh"], {}) == 0.15
    assert extract_float_with_units("50", [], {}) == 50.0
    assert extract_float_with_units("invalid", [], {}) is None

def test_extract_float_or_handle_unlimited():
    assert math.isinf(extract_float_or_handle_unlimited("Unlimited", ["unlimited"], ["gb"]))
    assert extract_float_or_handle_unlimited("100 GB", [], ["gb"]) == 100.0
    assert extract_float_or_handle_unlimited("N/A", [], []) is None

def test_extract_duration_in_months():
    assert extract_duration_in_months("1 year", ["month"], ["year"]) == 12
    assert extract_duration_in_months("24 months", ["month"], []) == 24
    assert extract_duration_in_months("cancel anytime", [], []) == 0

def test_parse_availability():
    assert parse_availability("Available") is True
    assert parse_availability("unavailable") is False
    assert parse_availability(None) is True

def test_standardize_extracted_product_electricity():
    raw = {
        "product_type": "electricity",
        "provider_name": "PowerCo",
        "product_name": "Basic Power",
        "price": "0.20 €/kWh",
        "contract_duration": "12 months"
    }
    product = standardize_extracted_product(raw)
    assert isinstance(product, StandardizedProduct)
    assert product.type == "electricity_plan"
    assert product.price_kwh == 0.20
    assert product.contract_duration_months == 12

def test_parse_and_standardize_batch():
    batch = [
        {"product_type": "electricity", "provider_name": "E1", "product_name": "A", "price": "0.1", "contract_duration": "6 months"},
        {"product_type": "mobile", "provider_name": "M1", "product_name": "B", "price": "$30", "data_gb": "50 GB", "contract_duration": "1 year"}
    ]
    results = parse_and_standardize(batch)
    assert len(results) == 2
    assert results[0].type == "electricity_plan"
    assert results[1].type == "mobile_plan"
