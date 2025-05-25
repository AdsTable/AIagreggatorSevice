# data_parser.py
from typing import List, Dict, Any, Optional
from models import StandardizedProduct # Import the StandardizedProduct model
import json
import re # Import regular expressions
import math # Import math for infinity


# --- Configuration for Mapping Extracted Fields to StandardizedProduct Fields ---
# This dictionary defines how keys in the raw extracted data (from the AI)
# should map to the fields in the StandardizedProduct model.
# This can be edited by the user or potentially updated by AI.
# Keys are categories, values are dictionaries mapping extracted keys to standardized keys.
FIELD_MAPPINGS = {
    "electricity_plan": {
        "product_name_on_page": "name",
        "price_info": "price_kwh", # The parser will need to extract the float from the string
        "standing_charge_info": "standing_charge", # Mapping for standing charge
        "contract_details": "contract_duration_months", # Parser extracts months from string
        "provider_name_on_page": "provider_name", # Assuming AI extracts provider name directly sometimes
        "contract_type_info": "contract_type", # Mapping for contract type
        "validity_info": "available", # Mapping for availability
        "source_url": "source_url" # Example: Store the source URL
    },
    "mobile_plan": {
        "plan_title": "name",
        "monthly_price_text": "monthly_cost", # Parser extracts float from string
        "data_allowance_text": "data_gb", # Parser extracts float/handles "Unlimited"
        "calls_info": "calls", # Mapping for calls
        "texts_info": "texts", # Mapping for texts
        "contract_term_text": "contract_duration_months", # Parser extracts months from string
        "provider_name_on_page": "provider_name", # Mapping "operator" to "provider_name"
        "network_type_info": "network_type", # Mapping for network type
        "source_url": "source_url" # Store the source URL
    },
    "internet_plan": {
        "plan_title": "name",
        "provider_name_on_page": "provider_name",
        "download_speed_info": "download_speed", # Mapping for download speed
        "upload_speed_info": "upload_speed", # Mapping for upload speed
        "connection_type_info": "connection_type", # Mapping for connection type
        "data_cap_info": "data_cap_gb", # Mapping for data cap
        "monthly_price_text": "monthly_cost",
        "contract_term_text": "contract_duration_months", # Mapping for contract duration
         "source_url": "source_url" # Store the source URL
    }
    # Add mappings for other categories
}

# --- Configuration for How to Parse Specific Fields ---
# This dictionary provides instructions for the parser on how to handle
# the raw string values for certain fields (e.g., extracting numbers, handling units).
PARSING_INSTRUCTIONS = {
    "price_kwh": {
        "method": "extract_float_with_units",
        "units": ["kwh", "usd", "$", "kr"], # Units to look for
        "unit_conversion": {"usd": 1.0} # Example conversion (if needed)
    },
     "standing_charge": { # Instructions for standing charge
        "method": "extract_float_with_units",
        "units": ["usd", "$", "month", "kr"],
        "unit_conversion": {}
    },
    "monthly_cost": {
        "method": "extract_float_with_units",
        "units": ["month", "$", "kr"],
        "unit_conversion": {} # No conversion needed for now
    },
    "data_gb": {
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "no data cap"], # Added more terms
        "units": ["gb", "gigabyte"]
    },
    "calls": { # Instructions for calls
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит"],
        "units": ["minutes", "мин"]
    },
     "texts": { # Instructions for texts
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит"],
        "units": ["texts", "sms"]
    },
    "contract_duration_months": {
        "method": "extract_duration_in_months",
        "month_terms": ["month", "mo", "месяц"],
        "year_terms": ["year", "yr", "год"]
    },
    "available": { # Instructions for availability
        "method": "parse_availability"
    },
    "download_speed": { # Instructions for download speed
        "method": "extract_float_with_units",
        "units": ["mbps", "mbit/s"],
        "unit_conversion": {}
    },
    "upload_speed": { # Instructions for upload speed
        "method": "extract_float_with_units",
        "units": ["mbps", "mbit/s"],
        "unit_conversion": {}
    },
     "data_cap_gb": { # Instructions for data cap (using data_gb logic)
        "method": "extract_float_or_handle_unlimited",
        "unlimited_terms": ["unlimited", "ubegrenset", "безлимит", "no data cap"],
        "units": ["gb", "gigabyte"]
    }
    # Add instructions for other fields that require specific parsing logic
}

# --- Helper Parsing Functions (used by standardize_extracted_product) ---

def extract_float_with_units(value: Any, units: List[str], unit_conversion: Dict[str, float]) -> Optional[float]:
    """Extracts a float number from a string, considering potential units."""
    if not isinstance(value, str):
        # Handle numeric types directly
        if isinstance(value, (int, float)):
            return float(value)
        return None

    lowered_value = value.lower()

    # Extract potential number using regex, allowing for decimal points and commas
    # This regex is more robust for various number formats
    match = re.search(r'(\d+([\.,]\d+)?)', lowered_value)
    if not match:
        return None # No number found

    try:
        # Replace comma with dot for consistent float conversion
        number_str = match.group(1).replace(',', '.')
        number = float(number_str)
    except ValueError:
        return None # Should not happen if regex matched, but good practice

    if not units: # If no specific units are provided, just return the number
         return number

    # Check for units and apply conversion (simplified logic)
    for unit in units:
        if unit in lowered_value:
             # For now, we just return the number if any relevant unit is found
             # More complex logic for unit conversion (using unit_conversion) would go here
             return number

    # If a number is found but no specified unit is present,
    # we might still return the number assuming it's in the base unit,
    # depending on the data format. Let's return the number in this case.
    return number


def extract_float_or_handle_unlimited(value: Any, unlimited_terms: List[str], units: List[str]) -> Optional[float]:
    """Extracts a float number or handles 'unlimited' terms."""
    if not isinstance(value, str):
        # Handle non-string types directly if they are numeric (e.g., int, float)
        if isinstance(value, (int, float)):
             return float(value)
        return None

    lowered_value = value.lower()

    # Check for unlimited terms first
    for term in unlimited_terms:
        if term in lowered_value:
            return float('inf') # Represent unlimited as infinity

    # If not unlimited, try to extract a float with units
    # Pass unlimited_terms here so extract_float_with_units can ignore them
    return extract_float_with_units(value, units, {})


def extract_duration_in_months(value: Any, month_terms: List[str], year_terms: List[str]) -> Optional[int]:
    """Extracts duration from a string and converts to months."""
    if not isinstance(value, str):
        # Handle integer input directly (assume it's months if it's an integer)
        if isinstance(value, int):
            return value
        return None

    lowered_value = value.lower()

    # Handle "no contract" or similar terms first
    no_contract_terms = ["no contract", "без контракта", "cancel anytime"]
    if any(term in lowered_value for term in no_contract_terms):
        return 0 # Represent no contract as 0 months

    # Extract a potential number
    match = re.search(r'(\d+)', lowered_value)
    if not match:
        return None # No number found

    try:
        number = int(match.group(1))
    except ValueError:
        return None # Should not happen if regex matched

    # Check for month terms
    if any(term in lowered_value for term in month_terms):
        return number # Assume number is already in months

    # Check for year terms
    if any(term in lowered_value for term in year_terms):
        return number * 12 # Convert years to months

    # If a number is found but no specific duration unit (month/year),
    # and it's not a "no contract" term, return None.
    return None


def parse_availability(value: Any) -> bool:
    """ Parses a value to determine product availability.
    Returns True if available, False if unavailable. Defaults to True if status cannot be determined as "unavailable".
    """
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        # Define keywords indicating unavailability
        unavailable_keywords = ["expired", "sold out", "inactive", "недоступен", "нет в наличии", "unavailable"] # Added "unavailable"
        for keyword in unavailable_keywords:
            if keyword in normalized_value:
                return False
    # If not explicitly determined as unavailable, assume available
    # This includes None, empty string, and strings without unavailability keywords
    return True


# --- Main Standardization Function ---

def standardize_extracted_product(extracted_data: Dict[str, Any], category: str) -> Optional[StandardizedProduct]:
    """
    Standardizes data extracted by the AI into the StandardizedProduct format
    using configurable mappings and parsing instructions.
    """
    print(f"Attempting to standardize data for category: {category}")
    mapping = FIELD_MAPPINGS.get(category)
    if not mapping:
        print(f"Warning: No field mapping defined for category: {extracted_data}. Skipping standardization.")
        # Changed print to show extracted_data instead of category in warning, seems more helpful
        return None

    standardized_fields: Dict[str, Any] = {}
    raw_data_storage: Dict[str, Any] = extracted_data.copy() # Store a copy of the original extracted data

    for extracted_key, standardized_key in mapping.items():
        raw_value = extracted_data.get(extracted_key)

        # Check if there are specific parsing instructions for this standardized field
        parsing_instruction = PARSING_INSTRUCTIONS.get(standardized_key)

        parsed_value = raw_value # Default to raw value if no specific parsing applies

        if parsing_instruction:
            method = parsing_instruction.get("method")
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
                print(f"Warning: Unknown parsing method '{method}' for field '{standardized_key}'. Storing raw value.")
                # Fallback to storing raw value if method is unknown

        # Assign the parsed value to the standardized field
        standardized_fields[standardized_key] = parsed_value

    standardized_fields['category'] = category

    # Include the original extracted data in the raw_data field
    standardized_fields['raw_data'] = raw_data_storage

    # Debugging output before validation
    print(f"Attempting to validate with data: {standardized_fields}")

    try:
        # Use model_validate to create the StandardizedProduct instance,
        # which handles type checking and validation.
        # Any fields in standardized_fields that are not in StandardizedProduct model_fields
        # will be ignored by model_validate, which is expected.
        return StandardizedProduct.model_validate(standardized_fields)
    except Exception as e:
        print(f"Error validating StandardizedProduct model for category {category}:")
        print(f"Error details: {e}")
        print(f"Data being validated: {standardized_fields}")
        print("-" * 20) # Separator for clarity
        return None

# --- Function to Parse a List of Raw Data ---

def parse_and_standardize(raw_data: List[Dict[str, Any]], category: str) -> List[StandardizedProduct]:
    """
    Parses raw data (expected to be a list of dictionaries from AI extraction)
    and standardizes it into a list of StandardizedProduct models,
    using the configured mappings and parsing instructions.
    """
    standardized_products: List[StandardizedProduct] = []

    if not isinstance(raw_data, list):
        print(f"Invalid raw data format for AI extraction output: Expected a list of dictionaries, but got {type(raw_data)}. Cannot parse.")
        return standardized_products

    if not raw_data:
        print("No raw product data provided for parsing.")
        return standardized_products

    print(f"Attempting to standardize {len(raw_data)} items from AI extraction for category: {category}.")

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
