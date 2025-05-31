# data_parser.py
from typing import List, Dict, Any, Optional
from models import StandardizedProduct
from pydantic import BaseModel, ConfigDict, field_validator
import json
import re
import math


class ParsingConfig(BaseModel):
    """Configuration for parsing operations using Pydantic 2.x."""
    category: str
    field_mappings: Dict[str, str]
    parsing_instructions: Dict[str, Dict[str, Any]]
    
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid"
    )
    
    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        allowed = ["electricity_plan", "mobile_plan", "internet_plan"]
        if v not in allowed:
            raise ValueError(f"Category must be one of: {allowed}")
        return v


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
        "units": ["kwh", "usd", "$", "kr"],
        "unit_conversion": {"usd": 1.0}
    },
    "standing_charge": {
        "method": "extract_float_with_units",
        "units": ["usd", "$", "month", "kr"],
        "unit_conversion": {}
    },
    "monthly_cost": {
        "method": "extract_float_with_units",
        "units": ["month", "$", "kr"],
        "unit_conversion": {}
    },
    "data_gb": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "no data cap"],
        "units": ["gb", "gigabyte"]
    },
    "calls": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит"],
        "units": ["minutes", "мин"]
    },
    "texts": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит"],
        "units": ["texts", "sms"]
    },
    "contract_duration_months": {
        "method": "extract_duration_in_months",
        "month_terms": ["month", "mo", "месяц"],
        "year_terms": ["year", "yr", "год"]
    },
    "available": {
        "method": "parse_availability"
    },
    "download_speed": {
        "method": "extract_float_with_units",
        "units": ["mbps", "mbit/s"],
        "unit_conversion": {}
    },
    "upload_speed": {
        "method": "extract_float_with_units",
        "units": ["mbps", "mbit/s"],
        "unit_conversion": {}
    },
    "data_cap_gb": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "no data cap"],
        "units": ["gb", "gigabyte"]
    }
}


class OptimizedParsers:
    """Singleton parser class with cached regex patterns for Pydantic 2.x compatibility."""
    
    _instance = None
    _number_pattern = None
    _duration_pattern = None
    _unavailable_terms = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize compiled regex patterns for performance."""
        self._number_pattern = re.compile(r'(\d+([\.,]\d+)?)')
        self._duration_pattern = re.compile(r'(\d+)')
        self._unavailable_terms = [
            "expired", "sold out", "inactive", "недоступен", 
            "нет в наличии", "unavailable"
        ]

    def extract_float_with_units(self, value: Any, units: List[str], unit_conversion: Dict[str, float]) -> Optional[float]:
        """Extract float with units, optimized for Pydantic 2.x."""
        if not isinstance(value, str):
            if isinstance(value, (int, float)):
                return float(value)
            return None

        lowered_value = value.lower()
        match = self._number_pattern.search(lowered_value)
        if not match:
            return None

        try:
            number_str = match.group(1).replace(',', '.')
            number = float(number_str)
        except ValueError:
            return None

        if not units:
            return number

        for unit in units:
            if unit in lowered_value:
                return number

        return number

    def extract_float_or_handle_unlimited(self, value: Any, unlimited_terms: List[str], units: List[str]) -> Optional[float]:
        """Extract float or handle unlimited terms."""
        if not isinstance(value, str):
            if isinstance(value, (int, float)):
                return float(value)
            return None

        lowered_value = value.lower()

        for term in unlimited_terms:
            if term in lowered_value:
                return float('inf')

        return self.extract_float_with_units(value, units, {})

    def extract_duration_in_months(self, value: Any, month_terms: Optional[List[str]] = None, year_terms: Optional[List[str]] = None) -> Optional[int]:
        """Extract duration and convert to months."""
        if month_terms is None:
            month_terms = ["month", "mo", "месяц"]
        if year_terms is None:
            year_terms = ["year", "yr", "год"]
            
        if not isinstance(value, str):
            if isinstance(value, int):
                return value
            return None

        lowered_value = value.lower()

        no_contract_terms = ["no contract", "без контракта", "cancel anytime"]
        if any(term in lowered_value for term in no_contract_terms):
            return 0

        match = self._duration_pattern.search(lowered_value)
        if not match:
            return None

        try:
            number = int(match.group(1))
        except ValueError:
            return None

        if any(term in lowered_value for term in month_terms):
            return number

        if any(term in lowered_value for term in year_terms):
            return number * 12

        return None

    def parse_availability(self, value: Any) -> bool:
        """Parse availability with enhanced logic."""
        if isinstance(value, str):
            normalized_value = value.strip().lower()
            for keyword in self._unavailable_terms:
                if keyword in normalized_value:
                    return False
        return True


# Global parser instance
parsers = OptimizedParsers()


def standardize_extracted_product(extracted_data: Dict[str, Any], category: str) -> Optional[StandardizedProduct]:
    """
    Standardizes data using Pydantic 2.x validation and serialization.
    """
    print(f"Attempting to standardize data for category: {category}")
    mapping = FIELD_MAPPINGS.get(category)
    if not mapping:
        print(f"Warning: No field mapping defined for category: {category}. Skipping standardization.")
        return None

    standardized_fields: Dict[str, Any] = {}
    raw_data_storage: Dict[str, Any] = extracted_data.copy()

    for extracted_key, standardized_key in mapping.items():
        raw_value = extracted_data.get(extracted_key)
        parsing_instruction = PARSING_INSTRUCTIONS.get(standardized_key)
        parsed_value = raw_value

        if parsing_instruction:
            method = parsing_instruction.get("method")
            if method == "extract_float_with_units":
                parsed_value = parsers.extract_float_with_units(
                    raw_value,
                    parsing_instruction.get("units", []),
                    parsing_instruction.get("unit_conversion", {})
                )
            elif method == "extract_float_or_handle_unlimited":
                parsed_value = parsers.extract_float_or_handle_unlimited(
                    raw_value,
                    parsing_instruction.get("unlimited_terms", []),
                    parsing_instruction.get("units", [])
                )
            elif method == "extract_duration_in_months":
                parsed_value = parsers.extract_duration_in_months(
                    raw_value,
                    parsing_instruction.get("month_terms", []),
                    parsing_instruction.get("year_terms", [])
                )
            elif method == "parse_availability":
                parsed_value = parsers.parse_availability(raw_value)
            else:
                print(f"Warning: Unknown parsing method '{method}' for field '{standardized_key}'. Storing raw value.")

        standardized_fields[standardized_key] = parsed_value

    standardized_fields['category'] = category
    standardized_fields['raw_data'] = raw_data_storage

    print(f"Attempting to validate with data: {standardized_fields}")

    try:
        # Use Pydantic 2.x model_validate method
        return StandardizedProduct.model_validate(standardized_fields)
    except Exception as e:
        print(f"Error validating StandardizedProduct model for category {category}:")
        print(f"Error details: {e}")
        print(f"Data being validated: {standardized_fields}")
        print("-" * 20)
        return None


def parse_and_standardize(raw_data: List[Dict[str, Any]], category: str) -> List[StandardizedProduct]:
    """
    Parse raw data and standardize using Pydantic 2.x models.
    """
    standardized_products: List[StandardizedProduct] = []

    if not isinstance(raw_data, list):
        print(f"Invalid raw data format: Expected a list of dictionaries, but got {type(raw_data)}. Cannot parse.")
        return standardized_products

    if not raw_data:
        print("No raw product data provided for parsing.")
        return standardized_products

    print(f"Attempting to standardize {len(raw_data)} items for category: {category}.")

    for item in raw_data:
        if not isinstance(item, dict):
            print(f"Skipping invalid item format: Expected a dictionary, but got {type(item)} - Data: {item}")
            continue

        standardized_product = standardize_extracted_product(item, category)
        if standardized_product:
            standardized_products.append(standardized_product)

    print(f"Parsing and standardization complete. Successfully generated {len(standardized_products)} standardized products.")
    return standardized_products


# Example Usage (for testing the parser independently with AI extraction output):
# if __name__ == "__main__":
#      # Sample data that mimics the expected output of the AI extraction function
#      sample_extracted_data = [
#          {
#              "source_url": "https://dummy-provider-a.com/plans/elec1",
#              "product_name_on_page": "Basic Home Plan",
#              "price_info": "Starts at 0.18 USD per kWh. Plus a $10 monthly fee.",
#              "standing_charge_info": "10 USD/month",
#              "contract_details": "24-month contract.",
#              "contract_type_info": "Fixed",
#              "provider_name_on_page": "Dummy Provider A",
#              "validity_info": "Available now"
#          },
#          {
#              "source_url": "https://dummy-provider-a.com/plans/elec2",
#              "product_name_on_page": "Premium Green Plan",
#              "price_info": "0.22 USD/kWh, no monthly fee.",
#              "standing_charge_info": "0",
#              "contract_details": "No contract.",
#              "contract_type_info": "Variable",
#              "provider_name_on_page": "Dummy Provider A",
#              "validity_info": "Expired promotion"
#          },
#           {
#              "source_url": "https://dummy-provider-b.com/pricing/mobile1",
#              "plan_title": "Mobile Pro 50GB",
#              "monthly_price_text": "$50/month",
#              "data_allowance_text": "50 GB high-speed data",
#              "calls_info": "Unlimited calls",
#              "texts_info": "500 texts",
#              "contract_term_text": "12 mo agreement",
#              "provider_name_on_page": "Dummy Provider B",
#              "network_type_info": "5G"
#           },
#           {
#              "source_url": "https://dummy-provider-c.com/deals/internet1",
#              "plan_title": "Super Data Plan",
#              "provider_name_on_page": "Dummy Provider C",
#              "monthly_price_text": "75 USD",
#              "download_speed_info": "1000 Mbps",
#              "upload_speed_info": "100 Mbps",
#              "connection_type_info": "Fiber",
#              "data_cap_info": "Unlimited Data!",
#              "contract_term_text": "2 Year Term"
#           }
#      ]
#
#      # Test with electricity plans
#      print("\n--- Testing Parsing for Electricity Plans ---")
#      # Filter data for electricity based on some criteria if needed, or pass all
#      standardized_products_electricity = parse_and_standardize(
#          [item for item in sample_extracted_data if "kwh" in json.dumps(item).lower() or "electricity" in json.dumps(item).lower()],
#          "electricity_plan"
#      )
#      if standardized_products_electricity:
#          for product in standardized_products_electricity:
#             print(product.model_dump_json(indent=2))
#      else:
#         print("No standardized electricity products were generated.")
#
#      # Test with mobile plans
#      print("\n--- Testing Parsing for Mobile Plans ---")
#      standardized_products_mobile = parse_and_standardize(
#           [item for item in sample_extracted_data if "gb" in json.dumps(item).lower() or "mobile" in json.dumps(item).lower()],
#          "mobile_plan"
#      )
#      if standardized_products_mobile:
#          for product in standardized_products_mobile:
#             print(product.model_dump_json(indent=2))
#      else:
#         print("No standardized mobile products were generated.")
#
#      # Test with internet plans
#      print("\n--- Testing Parsing for Internet Plans ---")
#      standardized_products_internet = parse_and_standardize(
#           [item for item in sample_extracted_data if "mbps" in json.dumps(item).lower() or "internet" in json.dumps(item).lower()],
#          "internet_plan" # Corrected category name
#      )
#      if standardized_products_internet:
#          for product in standardized_products_internet:
#             print(product.model_dump_json(indent=2))
#      else:
#         print("No standardized internet products were generated.")
