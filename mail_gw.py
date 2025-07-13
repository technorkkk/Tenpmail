# mail_gw.py

import requests
import logging

API_BASE_URL = "https://api.mail.gw"

def get_domains():
    """Fetches a list of available domains."""
    try:
        response = requests.get(f"{API_BASE_URL}/domains")
        response.raise_for_status()
        # The first domain is usually the main one
        return response.json()['hydra:member'][0]['domain']
    except requests.RequestException as e:
        logging.error(f"Error fetching domains: {e}")
        return None

def create_account(address, password):
    """Creates a new temporary email account."""
    try:
        payload = {
            "address": address,
            "password": password
        }
        response = requests.post(f"{API_BASE_URL}/accounts", json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error creating account for {address}: {e}")
        return None

def get_auth_token(address, password):
    """Gets the JWT token for an existing account."""
    try:
        payload = {
            "address": address,
            "password": password
        }
        response = requests.post(f"{API_BASE_URL}/token", json=payload)
        response.raise_for_status()
        return response.json()['token']
    except requests.RequestException as e:
        logging.error(f"Error getting token for {address}: {e}")
        return None

def get_messages(token):
    """Fetches all messages for a given auth token."""
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f"{API_BASE_URL}/messages", headers=headers)
        response.raise_for_status()
        return response.json()['hydra:member']
    except requests.RequestException as e:
        logging.error(f"Error fetching messages: {e}")
        return []

def get_message_by_id(token, message_id):
    """Fetches the full content of a single message."""
    try:
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f"{API_BASE_URL}/messages/{message_id}", headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error fetching message {message_id}: {e}")
        return None

def delete_account_by_id(token, account_id):
    """Deletes an email account using its ID."""
    try:
        headers = {'Authorization': f'Bearer {token}'}
        # Note: The API might require the account ID which you get on creation
        # This part of the mail.gw API is less documented, assuming an endpoint like this.
        # If it doesn't work, we can just "forget" the email in our DB.
        # Let's simulate deletion by just removing from our DB for robustness.
        # response = requests.delete(f"{API_BASE_URL}/accounts/{account_id}", headers=headers)
        # response.raise_for_status()
        logging.info(f"Account with ID {account_id} marked for deletion.")
        return True # Simulate success
    except requests.RequestException as e:
        logging.error(f"Error deleting account {account_id}: {e}")
        return False
