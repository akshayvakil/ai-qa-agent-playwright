import os
import json

from dotenv import load_dotenv
from google import genai


# ============================================================
# Load environment variables
# ============================================================

# Load variables from .env
load_dotenv()

# Read Gemini API key
api_key = os.getenv("GEMINI_API_KEY")

# Create Gemini client
client = genai.Client(api_key=api_key)


# ============================================================
# Test Manager Agent
# ============================================================

def create_test_cases(requirement):
    """
    Send a QA requirement to Gemini
    and generate structured test cases.
    """

    # Tell Gemini exactly what JSON structure we need.
    prompt = f"""
You are an experienced QA Test Manager.

Analyze the following requirement:

{requirement}

Generate test cases.

Return ONLY valid JSON.
Do not add markdown or explanations.

Use exactly this structure:

{{
    "test_cases": [
        {{
            "id": "TC01",
            "title": "Test case title",
            "type": "UI",
            "steps": [
                "Step 1",
                "Step 2"
            ],
            "expected_result": "Expected result"
        }}
    ]
}}

The "type" must be either:
"UI" or "API".
"""

    # Send requirement to Gemini
    interaction = client.interactions.create(
        model="gemini-3.8-flash",
        input=prompt
    )

    # Get Gemini response
    response_text = interaction.output_text

    # Convert JSON text into a Python dictionary
    test_cases = json.loads(response_text)

    # Return the Python dictionary
    return test_cases


# ============================================================
# Main execution
# ============================================================

# Example requirement
requirement = """
Verify that a user can login to SauceDemo
and add the Sauce Labs Backpack to the shopping cart.
"""


# Generate test cases
test_cases = create_test_cases(requirement)


# ============================================================
# Save test cases to JSON file
# ============================================================

# Define output file
output_file = "reports/generated_test_cases.json"

# Create the reports folder if it does not exist
os.makedirs("reports", exist_ok=True)

# Write test cases to JSON file
with open(output_file, "w", encoding="utf-8") as file:
    json.dump(test_cases, file, indent=4)


# ============================================================
# Display results
# ============================================================

print(json.dumps(test_cases, indent=4))

print(f"\nTest cases saved to: {output_file}")


# ============================================================
# REVISION NOTES
# ============================================================
#
# PYTHON:
# os.makedirs() -> creates a directory if it does not exist
# open() -> opens/creates a file
# with -> automatically closes the file
# json.dump() -> writes Python dictionary to JSON file
# json.dumps() -> converts Python dictionary to JSON text
#
# AI:
# Gemini generates structured test cases.
#
# OUTPUT:
# generated_test_cases.json
#
# ARCHITECTURE:
#
# Requirement
#     ↓
# Test Manager Agent
#     ↓
# Gemini
#     ↓
# Python Dictionary
#     ↓
# generated_test_cases.json
#     ↓
# Playwright Agent / API Agent
#
# ============================================================