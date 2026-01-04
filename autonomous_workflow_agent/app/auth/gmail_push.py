"""
Gmail Push API integration for real-time email notifications.
"""
import base64
import json
from typing import Optional
from googleapiclient.errors import HttpError
from autonomous_workflow_agent.app.auth.google_oauth import get_auth_manager
from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class GmailPushManager:
    """Manages Gmail Push API notifications."""
    
    def __init__(self):
        """Initialize Gmail Push manager."""
        self.auth_manager = get_auth_manager()
        self.settings = get_settings()
        self.service = None
    
    def _ensure_service(self) -> bool:
        """Ensure Gmail service is available."""
        if not self.service:
            self.service = self.auth_manager.get_gmail_service()
        return self.service is not None
    
    def setup_watch(self, topic_name: str, label_ids: Optional[list] = None) -> dict:
        """
        Set up Gmail push notifications.
        
        Args:
            topic_name: Google Cloud Pub/Sub topic name (e.g., 'projects/myproject/topics/gmail')
            label_ids: Optional list of label IDs to watch (default: ['INBOX'])
            
        Returns:
            Watch response dictionary
        """
        if not self._ensure_service():
            raise Exception("Gmail service not available")
        
        if label_ids is None:
            label_ids = ['INBOX']
        
        try:
            request = {
                'labelIds': label_ids,
                'topicName': topic_name
            }
            
            result = self.service.users().watch(
                userId='me',
                body=request
            ).execute()
            
            logger.info(f"Gmail watch setup successful: {result}")
            return result
            
        except HttpError as e:
            logger.error(f"Failed to setup Gmail watch: {e}")
            raise
    
    def stop_watch(self) -> bool:
        """
        Stop Gmail push notifications.
        
        Returns:
            True if successful
        """
        if not self._ensure_service():
            return False
        
        try:
            self.service.users().stop(userId='me').execute()
            logger.info("Gmail watch stopped successfully")
            return True
            
        except HttpError as e:
            logger.error(f"Failed to stop Gmail watch: {e}")
            return False
    
    def process_notification(self, notification_data: dict) -> Optional[str]:
        """
        Process a Gmail push notification.
        
        Args:
            notification_data: Notification data from Pub/Sub
            
        Returns:
            History ID if valid notification, None otherwise
        """
        try:
            # Decode the Pub/Sub message
            if 'message' in notification_data:
                message = notification_data['message']
                
                # Decode data
                if 'data' in message:
                    decoded_data = base64.b64decode(message['data']).decode('utf-8')
                    data = json.loads(decoded_data)
                    
                    email_address = data.get('emailAddress')
                    history_id = data.get('historyId')
                    
                    logger.info(f"Received notification for {email_address}, history ID: {history_id}")
                    return history_id
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing notification: {e}")
            return None


def get_gmail_push_manager() -> GmailPushManager:
    """Get Gmail Push manager instance."""
    return GmailPushManager()
