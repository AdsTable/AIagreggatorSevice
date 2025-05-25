# data_fetcher.py
import requests
import json
from typing import Dict, Any, Optional

def fetch_product_data_from_api(api_url: str, api_key: Optional[str] = None) -> Dict[str, Any] | None:
    """
    Fetches data from a real provider's API.
    Handles HTTP requests, authentication (optional), and basic error handling.
    """
    headers = {}
    if api_key:
        # Common way to send API key (e.g., Bearer token)
        # Adjust 'Authorization' and 'Bearer' based on your API's documentation
        headers["Authorization"] = f"Bearer {api_key}"
        # Some APIs use a custom header or a query parameter.
        # Example for a custom header: headers["X-API-Key"] = api_key
        # Example for a query parameter: params = {"api_key": api_key}

    try:
        print(f"Attempting to fetch data from API: {api_url}")
        # Include params if your API uses query parameters for the key
        response = requests.get(api_url, headers=headers, timeout=15) # Increased timeout slightly

        # Raise an HTTPError for bad responses (4xx or 5xx)
        response.raise_for_status()

        print("Data fetched successfully from API.")
        return response.json() # Assume the API returns JSON data

    except requests.exceptions.Timeout:
        print(f"Error fetching data from API {api_url}: Request timed out.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from API {api_url}: {e}")
        return None
    except json.JSONDecodeError:
        # If the response is not valid JSON
        print(f"Error decoding JSON from API {api_url}. Response content: {response.text}")
        return None

# Removed the get_simulated_raw_data() function entirely
# since we are now fetching real data.
