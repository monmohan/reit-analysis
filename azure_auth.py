import os
import requests
from dotenv import load_dotenv


def get_azure_ad_token():
    """
    Retrieves an Azure AD access token using client credentials flow.

    Required environment variables:
    - AZURE_TOKEN_URL: The token endpoint URL
    - AZURE_CLIENT_ID: The application (client) ID
    - AZURE_CLIENT_SECRET: The client secret

    Returns:
        str: The access token for Azure Cognitive Services

    Raises:
        requests.exceptions.HTTPError: If the token request fails
    """
    load_dotenv()

    token_url = os.getenv("AZURE_TOKEN_URL")
    payload = {
        'client_id': os.getenv("AZURE_CLIENT_ID"),
        'client_secret': os.getenv("AZURE_CLIENT_SECRET"),
        'grant_type': 'client_credentials',
        'scope': 'https://cognitiveservices.azure.com/.default'
    }
    response = requests.post(token_url, data=payload)
    response.raise_for_status()
    return response.json()['access_token']
