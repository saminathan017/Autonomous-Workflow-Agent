"""
Google OAuth 2.0 flow and API service builders.
"""
import os
import json
from pathlib import Path
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from autonomous_workflow_agent.app.config import get_settings, get_project_root
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)

# OAuth scopes
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
SHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
ALL_SCOPES = GMAIL_SCOPES + SHEETS_SCOPES


class GoogleAuthManager:
    """Manages Google OAuth authentication and API service creation."""
    
    def __init__(self):
        """Initialize the auth manager."""
        self.settings = get_settings()
        self.token_path = get_project_root() / "token.json"
        self.credentials_path = get_project_root() / "credentials.json"
        self.creds: Optional[Credentials] = None
        
    def _load_credentials(self) -> Optional[Credentials]:
        """Load credentials from token.json if it exists."""
        if self.token_path.exists():
            try:
                self.creds = Credentials.from_authorized_user_file(
                    str(self.token_path), ALL_SCOPES
                )
                logger.info("Loaded credentials from token.json")
                return self.creds
            except Exception as e:
                logger.error(f"Error loading credentials: {e}")
                return None
        return None
    
    def _save_credentials(self):
        """Save credentials to token.json."""
        if self.creds:
            try:
                with open(self.token_path, 'w') as token:
                    token.write(self.creds.to_json())
                logger.info("Saved credentials to token.json")
            except Exception as e:
                logger.error(f"Error saving credentials: {e}")
    
    def _refresh_credentials(self) -> bool:
        """
        Refresh expired credentials.
        
        Returns:
            True if refresh successful, False otherwise
        """
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_credentials()
                logger.info("Refreshed expired credentials")
                return True
            except Exception as e:
                logger.error(f"Error refreshing credentials: {e}")
                return False
        return False
    
    def authenticate(self) -> bool:
        """
        Authenticate with Google OAuth.
        
        Returns:
            True if authentication successful, False otherwise
        """
        # Try to load existing credentials
        self.creds = self._load_credentials()
        
        # Refresh if expired
        if self.creds and not self.creds.valid:
            if not self._refresh_credentials():
                self.creds = None
        
        # If no valid credentials, run OAuth flow
        if not self.creds:
            if not self.credentials_path.exists():
                logger.error(
                    f"credentials.json not found at {self.credentials_path}. "
                    "Please download it from Google Cloud Console."
                )
                return False
            
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), ALL_SCOPES
                )
                self.creds = flow.run_local_server(port=8080)
                self._save_credentials()
                logger.info("OAuth flow completed successfully")
                return True
            except Exception as e:
                logger.error(f"OAuth flow failed: {e}")
                return False
        
        return True
    
    def get_gmail_service(self):
        """
        Get Gmail API service.
        
        Returns:
            Gmail service object or None
        """
        if not self.creds:
            if not self.authenticate():
                return None
        
        try:
            service = build('gmail', 'v1', credentials=self.creds)
            logger.info("Gmail service created successfully")
            return service
        except HttpError as e:
            logger.error(f"Error creating Gmail service: {e}")
            return None
    
    def get_sheets_service(self):
        """
        Get Google Sheets API service.
        
        Returns:
            Sheets service object or None
        """
        if not self.creds:
            if not self.authenticate():
                return None
        
        try:
            service = build('sheets', 'v4', credentials=self.creds)
            logger.info("Sheets service created successfully")
            return service
        except HttpError as e:
            logger.error(f"Error creating Sheets service: {e}")
            return None


# Global auth manager instance
_auth_manager: Optional[GoogleAuthManager] = None


def get_auth_manager() -> GoogleAuthManager:
    """Get or create the global auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = GoogleAuthManager()
    return _auth_manager
