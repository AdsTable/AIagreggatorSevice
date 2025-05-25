# data_discoverer.py
import requests
import json
from typing import List, Dict, Any, Optional, Union
import os
from urllib.parse import urljoin # Helper for joining URLs
from data_parser import parse_and_standardize
# --- Placeholder for Search Integration ---
# In a real application, this would interact with a search API
def perform_web_search(query: str) -> List[str]:
    """
    Performs a web search and returns a list of potentially relevant URLs.

    Args:
        query: The search query (e.g., "electricity providers in California").

    Returns:
        A list of URLs.
    """
    search_api_url = os.environ.get("SEARCH_API_URL")
    search_api_key = os.environ.get("SEARCH_API_KEY")

    if search_api_url and search_api_key:
        print(f"Performing real web search for: {query} using API")
        params = {"q": query, "num": 10} # Adjust 'num' as needed
        headers = {"Authorization": f"Bearer {search_api_key}"} # Common API key header
        try:
            response = requests.get(search_api_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            search_results = response.json()
            # *** IMPORTANT: Adjust the following line based on the actual structure of your search API's JSON response. ***
            # The example assumes a 'results' key containing a list of dictionaries with a 'url' key.
            urls = [result.get('url') for result in search_results.get('results', []) if result.get('url')]
            return urls
        except requests.exceptions.RequestException as e:
            print(f"Error performing real search via API: {e}")
            return []

    print("Using dummy search results.")
    dummy_urls = [
        "https://dummy-provider-a.com/plans",
        "https://dummy-provider-b.com/pricing",
        "https://comparison-site.com/energy"
    ]
    return dummy_urls
    # ---------------------------------------------------


def fetch_content_from_url(url: str, timeout: int = 15) -> str:
    """
    Fetches content from a given URL. Includes a higher timeout for web pages.

    Args:
        url: The URL to fetch content from.
        timeout: The timeout for the request in seconds.

    Returns:
        The text content of the page, or an empty string if fetching fails.
    """
    print(f"Attempting to fetch content from: {url}")
    try:
        # Added headers to mimic a browser, might help with some sites
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(url, timeout=timeout, headers=headers)
        response.raise_for_status()
        print("Content fetched successfully.")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch content from {url}: {e}")
        return ""
    except Exception as e:
         print(f"An unexpected error occurred during content retrieval: {e}")
         return ""


def call_ai_for_web_extraction(html_content: str, category: str, prompt_instructions: str) -> List[Dict[str, Any]] | None:
    """
    Sends HTML content and specific instructions to an AI model for structured data extraction.

    Args:
        html_content: The HTML content of the web page.
        category: The category of data being sought (e.g., "electricity", "mobile").
        prompt_instructions: Specific instructions for the AI on what data to extract and how
                             (e.g., "Find all electricity plans, extract name, price, and contract term").

    Returns:
        A list of dictionaries with extracted raw data, or None if extraction fails.
    """
    ai_api_url = os.environ.get("AI_EXTRACTION_API_URL")
    ai_api_key = os.environ.get("AI_EXTRACTION_API_KEY")

    # This AI call is more advanced; it needs to handle HTML structure.
    # You might need a model specifically tuned for web data extraction or
    # a very capable general-purpose model with a detailed prompt.
    # The prompt should guide the AI on how to identify relevant sections (e.g., price tables, plan descriptions)
    # and what specific pieces of information to pull out.

    if ai_api_url and ai_api_key:
        print(f"Calling real AI for web data extraction for category: {category} using API")
        headers = {"Authorization": f"Bearer {ai_api_key}"} # Common API key header
        payload = {
            "html": html_content,
            "instructions": prompt_instructions, # Pass the specific instructions
            "category": category # Context for the AI
        }

        try:
            response = requests.post(ai_api_url, headers=headers, json=payload, timeout=30) # Increased timeout for AI
            response.raise_for_status()
            extracted_data = response.json() # Assuming the AI returns a list of dicts
            print("AI web extraction successful.")
            # *** IMPORTANT: Verify the structure of the AI's JSON response. Ensure it's a List[Dict[str, Any]]. ***
            return extracted_data
        except requests.exceptions.RequestException as e:
            print(f"Error calling real AI web extraction API: {e}")
            return None
        except json.JSONDecodeError:
            print(f"Error decoding JSON from real AI web extraction API response: {response.text}")
            return None

    # --- Dummy Web Extraction Data (for testing the flow) ---
    print("Using dummy web extraction data.")
    # This dummy data simulates what an AI might extract from a web page
    dummy_extracted_data = [
        {
            "source_url": "https://dummy-provider-a.com/plans",
            "product_name_on_page": "Basic Home Plan",
            "price_info": "Starts at 0.18 USD per kWh. Plus a $10 monthly fee.",
            "contract_details": "24-month contract. Early termination fees apply.",
            "other_info": "Requires smart meter."
        },
        {
            "source_url": "https://dummy-provider-a.com/plans",
            "product_name_on_page": "Premium Green Plan",
            "price_info": "0.22 USD/kWh, no monthly fee.",
            "contract_details": "No contract. Cancel anytime.",
            "other_info": "100% renewable energy."
        },
         {
            "source_url": "https://dummy-provider-b.com/pricing",
            "plan_title": "Mobile Pro 50GB",
            "monthly_price_text": "$50/month",
            "data_allowance_text": "50 GB high-speed data",
            "contract_term_text": "12mo agreement"
         }
    ]
    return dummy_extracted_data
    # --------------------------------------------------------

# --- Configuration for AI Extraction Instructions (Can be edited by user or AI) ---
# This dictionary stores instructions for the AI based on category.
# You can expand this and potentially store it in a file or database
# to allow for dynamic updates.
EXTRACTION_INSTRUCTIONS = {
    "electricity_plan": "Find all electricity plans listed on this page. For each plan, extract the plan name, price per kilowatt-hour (kWh), any fixed monthly charges, contract duration, and any other significant terms.",
    "mobile_plan": "Identify mobile phone plans on this page. For each plan, extract the plan name, monthly cost, data allowance (in GB), details about calls and texts, and contract duration."
    # Add instructions for other categories
}

def discover_and_extract_data(source_identifier: str, category: str) -> List[Dict[str, Any]] | None:
    """
    Discovers and extracts product data from a source using AI,
    including performing web searches if needed.

    Args:
        source_identifier: A string identifying the data source (e.g., a URL,
                           a file path, or a search query).
        category: The category of products to search for (e.g., "electricity_plan").

    Returns:
        A list of dictionaries containing raw product data extracted by AI,
        or None if the process fails.
    """
    print(f"Attempting to discover and extract data for category: {category} from source: {source_identifier}")

    text_content = None
    source_urls = [] # List to store URLs to process

    # --- Step 1: Determine Source Type and Get Content/URLs ---
    if source_identifier.startswith("http://") or source_identifier.startswith("https://"):
        # If it's a URL, fetch content directly
        source_urls.append(source_identifier)
    elif source_identifier.startswith("file://"):
        # If it's a file, read content directly
        file_path = source_identifier[len("file://"):]
        try:
            print(f"Attempting to read content from file: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                text_content = f.read()
            print("Content read successfully from file.")
        except FileNotFoundError:
            print(f"Error reading from file: File not found at {file_path}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during file reading: {e}")
            return None
    else:
        # If not a URL or file, treat as a search query
        search_query = f"{source_identifier} {category} plans" # Construct a search query
        print(f"Source identifier is not a URL or file path. Performing web search with query: {search_query}")
        source_urls = perform_web_search(search_query)
        if not source_urls:
            print("Web search did not return any relevant URLs.")
            return None

    # --- Step 2: Process URLs and Extract Data (if URLs were found) ---
    all_extracted_data = []
    if source_urls:
        print(f"Processing {len(source_urls)} URLs for extraction.")
        prompt_instructions = EXTRACTION_INSTRUCTIONS.get(category, "Extract product information.") # Get instructions for the category

        for url in source_urls:
            html_content = fetch_content_from_url(url)
            if html_content:
                extracted_data_from_url = call_ai_for_web_extraction(html_content, category, prompt_instructions)
                if extracted_data_from_url:
                    # Add the source URL to each extracted item for context/debugging
                    for item in extracted_data_from_url:
                        item['source_url'] = url
                    all_extracted_data.extend(extracted_data_from_url)
            else:
                print(f"Skipping extraction from {url} due to content fetching failure.")

    # --- Step 3: Process Direct Text Content (if a file was read) ---
    elif text_content:
         print("Processing direct text content with AI extraction.")
         # For direct text content (e.g., from a file), we can also use AI extraction
         # The prompt might need to be slightly different than for HTML
         prompt_instructions = EXTRACTION_INSTRUCTIONS.get(category, "Extract product information from this text.") # Get instructions for the category
         extracted_data_from_text = call_ai_for_web_extraction(text_content, category, prompt_instructions) # Reuse the web extraction function, AI needs to handle it
         if extracted_data_from_text:
             all_extracted_data.extend(extracted_data_from_text) # No source_url for direct text content

    if not all_extracted_data:
        print("AI failed to extract any product data from the source(s).")
        return None

    print(f"Successfully extracted a total of {len(all_extracted_data)} potential product items using AI.")
    return all_extracted_data

# Example Usage (for testing the discoverer independently):
# if __name__ == "__main__":
#     # Example with a search query
#     # discovered_data = discover_and_extract_data(source_identifier="best mobile plans", category="mobile_plan")

#     # Example with a dummy URL
#     # discovered_data = discover_and_extract_data(source_identifier="https://dummy-provider-a.com/plans", category="electricity_plan")

#     # Example with a dummy file path (create a dummy_data.txt file first)
#     # with open("dummy_data.txt", "w") as f:
#     #     f.write("Some text about an electricity plan with price 0.15 USD/kWh and 12 months contract.")
#     # discovered_data = discover_and_extract_data(source_identifier="file://dummy_data.txt", category="electricity_plan")


#     print("\n--- Discovered and Extracted Raw Data ---")
#     if discovered_data:
#         # In a real scenario, you'd then pass this to the parser
#         # from data_parser import parse_and_standardize
#         # standardized_products = parse_and_standardize(discovered_data)
#         # print(json.dumps(standardized_products, indent=2)) # Print standardized data
#         print(json.dumps(discovered_data, indent=2)) # Print raw extracted data
#     else:
#         print("Failed to discover and extract data.")