# data_parser.py - Совместимая версия с существующими тестами
from typing import List, Dict, Any, Optional, Union
from models import StandardizedProduct
import json
import re
import math
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

# --- Configuration for Mapping Extracted Fields to StandardizedProduct Fields ---
FIELD_MAPPINGS = {
    "electricity_plan": {
        "product_name_on_page": "name",
        "price_info": "price_kwh",
        "standing_charge_info": "standing_charge",
        "contract_details": "contract_duration_months",
        "provider_name_on_page": "provider_name",
        "contract_type_info": "contract_type",
        "validity_info": "available",
        "source_url": "source_url"
    },
    "mobile_plan": {
        "plan_title": "name",
        "monthly_price_text": "monthly_cost",
        "data_allowance_text": "data_gb",
        "calls_info": "calls",
        "texts_info": "texts",
        "contract_term_text": "contract_duration_months",
        "provider_name_on_page": "provider_name",
        "network_type_info": "network_type",
        "source_url": "source_url"
    },
    "internet_plan": {
        "plan_title": "name",
        "provider_name_on_page": "provider_name",
        "download_speed_info": "download_speed",
        "upload_speed_info": "upload_speed",
        "connection_type_info": "connection_type",
        "data_cap_info": "data_cap_gb",
        "monthly_price_text": "monthly_cost",
        "contract_term_text": "contract_duration_months",
        "source_url": "source_url"
    }
}

# --- Configuration for How to Parse Specific Fields ---
PARSING_INSTRUCTIONS = {
    "price_kwh": {
        "method": "extract_float_with_units",
        "units": ["kwh", "usd", "$", "kr", "£", "€"],
        "unit_conversion": {"usd": 1.0, "kr": 0.1}
    },
    "standing_charge": {
        "method": "extract_float_with_units",
        "units": ["usd", "$", "month", "kr", "£", "€"],
        "unit_conversion": {}
    },
    "monthly_cost": {
        "method": "extract_float_with_units",
        "units": ["month", "$", "kr", "£", "€"],
        "unit_conversion": {}
    },
    "data_gb": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "no data cap", "неограниченно"],
        "units": ["gb", "gigabyte", "гб"]
    },
    "calls": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "неограниченно"],
        "units": ["minutes", "мин", "минут"]
    },
    "texts": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "неограниченно"],
        "units": ["texts", "sms", "смс"]
    },
    "contract_duration_months": {
        "method": "extract_duration_in_months",
        "month_terms": ["month", "mo", "месяц", "мес"],
        "year_terms": ["year", "yr", "год", "г"]
    },
    "available": {
        "method": "parse_availability"
    },
    "download_speed": {
        "method": "extract_float_with_units",
        "units": ["mbps", "mbit/s", "мбит/с"],
        "unit_conversion": {}
    },
    "upload_speed": {
        "method": "extract_float_with_units",
        "units": ["mbps", "mbit/s", "мбит/с"],
        "unit_conversion": {}
    },
    "data_cap_gb": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "no data cap", "неограниченно"],
        "units": ["gb", "gigabyte", "гб"]
    }
}

# --- JSON Safety Utilities ---
def json_safe_float(value: Optional[float]) -> Optional[float]:
    """Convert float values to JSON-safe format"""
    if value is None:
        return None
    if value == float('inf'):
        return 999999.0  # Large number to represent unlimited
    if value == float('-inf'):
        return -999999.0
    if value != value:  # NaN check
        return None
    return value

def json_safe_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively make dictionary JSON-safe"""
    if not isinstance(data, dict):
        return {}
    
    result = {}
    for key, value in data.items():
        if isinstance(value, float):
            result[key] = json_safe_float(value)
        elif isinstance(value, dict):
            result[key] = json_safe_dict(value)
        elif isinstance(value, list):
            result[key] = [json_safe_float(v) if isinstance(v, float) else v for v in value]
        else:
            result[key] = value
    return result

# --- Core Parsing Functions (PUBLIC API для совместимости с тестами) ---

def extract_float_with_units(value: Any, units: List[str], unit_conversion: Dict[str, float]) -> Optional[float]:
    """
    Extracts a float number from a string, considering potential units.
    PUBLIC FUNCTION - используется в тестах для мокинга.
    """
    if not isinstance(value, str):
        if isinstance(value, (int, float)):
            return float(value)
        return None

    lowered_value = value.lower().strip()
    
    # Улучшенный regex для извлечения чисел
    match = re.search(r'(\d+(?:[,\.]\d+)?)', lowered_value)
    if not match:
        return None

    try:
        number_str = match.group(1).replace(',', '.')
        number = float(number_str)
    except ValueError:
        logger.warning(f"Failed to parse number from: {value}")
        return None

    if not units:
        return number

    # Проверка единиц измерения и конвертация
    for unit in units:
        if unit.lower() in lowered_value:
            conversion_factor = unit_conversion.get(unit.lower(), 1.0)
            return number * conversion_factor

    return number


def extract_float_or_handle_unlimited(value: Any, unlimited_terms: List[str], units: List[str]) -> Optional[float]:
    """
    Extracts a float number or handles 'unlimited' terms.
    PUBLIC FUNCTION - используется в тестах для мокинга.
    """
    if not isinstance(value, str):
        if isinstance(value, (int, float)):
            return float(value)
        return None

    lowered_value = value.lower().strip()

    # Проверка на безлимитные термины
    for term in unlimited_terms:
        if term.lower() in lowered_value:
            return float('inf')

    # Если не безлимитный, извлекаем число с единицами
    return extract_float_with_units(value, units, {})


def extract_duration_in_months(value: Any, month_terms: List[str], year_terms: List[str]) -> Optional[int]:
    """
    Extracts duration from a string and converts to months.
    PUBLIC FUNCTION - используется в тестах для мокинга.
    """
    if not isinstance(value, str):
        if isinstance(value, int):
            return value
        return None

    lowered_value = value.lower().strip()

    # Обработка "без контракта"
    no_contract_terms = ["no contract", "без контракта", "cancel anytime", "prepaid"]
    if any(term in lowered_value for term in no_contract_terms):
        return 0

    # Извлечение числа
    match = re.search(r'(\d+)', lowered_value)
    if not match:
        return None

    try:
        number = int(match.group(1))
    except ValueError:
        return None

    # Проверка единиц времени
    if any(term in lowered_value for term in month_terms):
        return number
    
    if any(term in lowered_value for term in year_terms):
        return number * 12

    return None


def parse_availability(value: Any) -> bool:
    """
    Parses a value to determine product availability.
    PUBLIC FUNCTION - используется в тестах для мокинга.
    """
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        unavailable_keywords = [
            "expired", "sold out", "inactive", "недоступен", 
            "нет в наличии", "unavailable", "discontinued", 
            "out of stock", "not available", "temporarily unavailable"
        ]
        return not any(keyword in normalized_value for keyword in unavailable_keywords)
    
    return True


# --- Main Standardization Function ---

def standardize_extracted_product(extracted_data: Dict[str, Any], category: str) -> Optional[StandardizedProduct]:
    """
    Standardizes data extracted by the AI into the StandardizedProduct format
    using configurable mappings and parsing instructions.
    """
    logger.debug(f"Attempting to standardize data for category: {category}")
    
    mapping = FIELD_MAPPINGS.get(category)
    if not mapping:
        logger.error(f"No field mapping defined for category: {category}")
        return None

    standardized_fields: Dict[str, Any] = {
        "category": category,
        "raw_data": extracted_data.copy()
    }

    for extracted_key, standardized_key in mapping.items():
        raw_value = extracted_data.get(extracted_key)
        
        if raw_value is None:
            continue

        # Получение инструкций парсинга
        parsing_instruction = PARSING_INSTRUCTIONS.get(standardized_key)
        parsed_value = raw_value  # По умолчанию

        if parsing_instruction:
            method = parsing_instruction.get("method")
            
            try:
                if method == "extract_float_with_units":
                    parsed_value = extract_float_with_units(
                        raw_value,
                        parsing_instruction.get("units", []),
                        parsing_instruction.get("unit_conversion", {})
                    )
                elif method == "extract_float_or_handle_unlimited":
                    parsed_value = extract_float_or_handle_unlimited(
                        raw_value,
                        parsing_instruction.get("unlimited_terms", []),
                        parsing_instruction.get("units", [])
                    )
                elif method == "extract_duration_in_months":
                    parsed_value = extract_duration_in_months(
                        raw_value,
                        parsing_instruction.get("month_terms", []),
                        parsing_instruction.get("year_terms", [])
                    )
                elif method == "parse_availability":
                    parsed_value = parse_availability(raw_value)
                else:
                    logger.warning(f"Unknown parsing method '{method}' for field '{standardized_key}'")
                    
            except Exception as e:
                logger.error(f"Error parsing {standardized_key} with value {raw_value}: {e}")
                parsed_value = raw_value  # Fallback to raw value

        standardized_fields[standardized_key] = parsed_value

    # Отладочная информация
    logger.debug(f"Attempting to validate with data: {standardized_fields}")

    try:
        return StandardizedProduct.model_validate(standardized_fields)
    except Exception as e:
        logger.error(f"Error validating StandardizedProduct for category {category}: {e}")
        logger.error(f"Data being validated: {standardized_fields}")
        return None


def parse_and_standardize(raw_data: List[Dict[str, Any]], category: str) -> List[StandardizedProduct]:
    """
    Parses raw data and standardizes it into a list of StandardizedProduct models.
    """
    standardized_products: List[StandardizedProduct] = []

    if not isinstance(raw_data, list):
        logger.error(f"Invalid raw data format: Expected list, got {type(raw_data)}")
        return standardized_products

    if not raw_data:
        logger.info("No raw product data provided for parsing")
        return standardized_products

    logger.info(f"Attempting to standardize {len(raw_data)} items for category: {category}")

    successful_count = 0
    for i, item in enumerate(raw_data):
        if not isinstance(item, dict):
            logger.warning(f"Skipping item {i}: Expected dict, got {type(item)}")
            continue

        standardized_product = standardize_extracted_product(item, category)
        if standardized_product:
            standardized_products.append(standardized_product)
            successful_count += 1

    logger.info(f"Parsing complete: {successful_count}/{len(raw_data)} items successfully standardized")
    return standardized_products


# --- Compatibility Functions for Tests ---

def get_parsing_stats() -> Dict[str, Any]:
    """Получение статистики парсинга для совместимости с тестами"""
    return {
        "field_mappings_count": len(FIELD_MAPPINGS),
        "parsing_instructions_count": len(PARSING_INSTRUCTIONS),
        "supported_categories": list(FIELD_MAPPINGS.keys())
    }


# --- JSON-Safe Export Functions для API ---

def to_json_safe_product(product: StandardizedProduct) -> Dict[str, Any]:
    """Конвертация продукта в JSON-safe формат"""
    if hasattr(product, 'model_dump'):  # Pydantic V2
        data = product.model_dump()
    else:  # Pydantic V1
        data = product.dict()
    
    return json_safe_dict(data)


def to_json_safe_products(products: List[StandardizedProduct]) -> List[Dict[str, Any]]:
    """Конвертация списка продуктов в JSON-safe формат"""
    return [to_json_safe_product(product) for product in products]


# --- Example Usage (for testing the parser independently) ---
if __name__ == "__main__":
    # Sample data for testing
    sample_data = [
        {
            "source_url": "https://example.com/elec/plan_a",
            "product_name_on_page": "Green Energy Plan",
            "price_info": "0.15 USD/kWh",
            "standing_charge_info": "5.00 USD/month",
            "contract_details": "12-month contract",
            "contract_type_info": "Fixed",
            "provider_name_on_page": "EcoPower",
            "validity_info": "Available"
        }
    ]
    
    print("=== Testing Enhanced Data Parser ===")
    results = parse_and_standardize(sample_data, "electricity_plan")
    
    if results:
        print(f"✅ Successfully parsed {len(results)} products")
        for product in results:
            safe_product = to_json_safe_product(product)
            print(f"Product: {safe_product['name']} - Price: {safe_product['price_kwh']} USD/kWh")
    else:
        print("❌ No products were successfully parsed")
    
    print(f"\nParsing Stats: {get_parsing_stats()}")