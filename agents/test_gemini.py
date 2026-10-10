import os

from dotenv import load_dotenv
from google import genai


# Load environment variables from the .env file
load_dotenv()

# Read the Gemini API key from the environment variable
api_key = os.getenv("GEMINI_API_KEY")

# Create the Gemini client using our API key
client = genai.Client(api_key=api_key)

# Send a simple request to Gemini
interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="Say hello from my AI QA Agent project."
)

# Print the response returned by Gemini
print(interaction.output_text)