# test_converters_and_validation.py
import pytest
import json
from pydantic import ValidationError
from product_schema import Product, RawData
from models import StandardizedProduct
from converters import product_to_standardized, standardized_to_product


def rawdata_to_dict(raw):
    """
    Преобразует raw_data в словарь.
    Если raw_data - экземпляр RawData, возвращает его root,
    если это словарь - возвращает его как есть.
    """
    if raw is None:
        return {}
    if isinstance(raw, RawData):
        return dict(raw.root)
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "root"):
        return dict(raw.root)
    return dict(raw)


def dict_to_rawdata(d):
    """Обратное преобразование словаря в RawData."""
    if d is None:
        return RawData(root={})
    if isinstance(d, RawData):
        return d
    if isinstance(d, dict):
        return RawData(root=d)
    raise ValueError(f"Cannot convert to RawData from type {type(d)}")


def normalize_url(url):
    return str(url).rstrip("/") if url else None

def deep_equal_json(a, b):
    try:
        ja = json.dumps(a, sort_keys=True)
        jb = json.dumps(b, sort_keys=True)
        return ja == jb
    except Exception as e:
        print(f"JSON сравнение: ошибка {e}")
        return False

def products_equivalent(prod1, prod2):
    """
    Сравнивает два объекта Product по всем полям.
    При сравнении raw_data использует rawdata_to_dict для нормализации.
    """
    for field in Product.model_fields:
        v1 = getattr(prod1, field)
        v2 = getattr(prod2, field)
        if field == "raw_data":
            d1 = rawdata_to_dict(v1)
            d2 = rawdata_to_dict(v2)
            if not deep_equal_json(d1, d2):
                print("Исходный raw_data:", d1)
                print("Восстановленный raw_data:", d2)
                assert False, f"raw_data mismatch in field '{field}'"
        elif field == "source_url":
            def norm(url): return str(url).rstrip("/") if url else None
            assert norm(v1) == norm(v2), f"source_url mismatch in field '{field}'"
        else:
            assert v1 == v2, f"Field '{field}' mismatch: {v1} != {v2}"


@pytest.mark.parametrize("field,value,should_fail", [
    ("price_kwh", "not_a_number", True),
    ("monthly_cost", "12.34abc", True),
    ("download_speed", "fast", True),
    ("available", "yes", False),
    ("contract_duration_months", "twelve", True),
])
def test_type_errors_in_product(field, value, should_fail):
    data = {
        "category": "mobile_plan",
        "source_url": "https://example.com/p",
        "provider_name": "Provider",
        "product_id": "p1",
        "name": "Test",
        "available": True,
        "raw_data": RawData(root={})
    }
    data[field] = value
    if should_fail:
        with pytest.raises(ValidationError):
            Product(**data)
    else:
        p = Product(**data)
        assert p.available is True


@pytest.mark.parametrize("field,value,should_fail", [
    ("price_kwh", "not_a_number", True),
    ("monthly_cost", "12.34abc", True),
    ("download_speed", "fast", True),
    ("available", "yes", False),
    ("contract_duration_months", "twelve", True),
])
def test_type_errors_in_internal_standardizedproduct(field, value, should_fail):
    data = {
        "category": "mobile_plan",
        "source_url": "https://example.com/p",
        "provider_name": "Provider",
        "product_id": "p1",
        "name": "Test",
        "available": True,
        "raw_data": {"a": 1}
    }
    data[field] = value
    if should_fail:
        with pytest.raises(ValidationError):
            StandardizedProduct(**data)
    else:
        p = StandardizedProduct(**data)
        assert p.available is True

def test_round_trip_conversion():
    """Тестирование кругового преобразования Product -> StandardizedProduct -> Product"""
    original_product = Product(
        category="electricity_plan",
        source_url="https://example.com/plan/",
        provider_name="ProviderLabs",
        product_id="prod-789",
        name="Test Plan",
        description="Cool plan",
        contract_duration_months=24,
        available=True,
        price_kwh=0.20,
        standing_charge=5.5,
        contract_type="variable",
        monthly_cost=40,
        data_gb=200,
        calls=1000,
        texts=2000,
        network_type="5G",
        download_speed=300,
        upload_speed=150,
        connection_type="fiber",
        data_cap_gb=1000,
        internet_monthly_cost=50,
        raw_data=RawData(root={"custom": "value", "nested": {"a": 1}})
    )
    
    # Product -> StandardizedProduct
    std_product = product_to_standardized(original_product)
    
    # Приведение raw_data к dict для корректного восстановления
    raw_dict = rawdata_to_dict(std_product.raw_data)
    
    # Подготовка словаря данных для создания StandardizedProduct
    data = std_product.model_dump()
    data["raw_data"] = raw_dict
    
    # Восстановление StandardizedProduct
    std_product_reconstructed = StandardizedProduct(**data)
    
    # Обратное преобразование StandardizedProduct -> Product
    product_restored = standardized_to_product(std_product)
    
    # Сравнение исходного и восстановленного продукта
    products_equivalent(original_product, product_restored)
