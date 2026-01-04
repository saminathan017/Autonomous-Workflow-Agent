"""
Gmail reader task - fetches and parses emails.
"""
import base64
from datetime import datetime
from typing import List, Optional
from googleapiclient.errors import HttpError
from autonomous_workflow_agent.app.auth.google_oauth import get_auth_manager
from autonomous_workflow_agent.app.workflows.models import EmailData
from autonomous_workflow_agent.app.ai.email_classifier import get_email_classifier
from autonomous_workflow_agent.app.ai.sentiment_analyzer import get_sentiment_analyzer
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class GmailReader:
    """Reads emails from Gmail API."""
    
    def __init__(self, enable_classification: bool = True, enable_sentiment: bool = True):
        """Initialize the Gmail reader.
        
        Args:
            enable_classification: Whether to classify emails
            enable_sentiment: Whether to analyze sentiment
        """
        self.auth_manager = get_auth_manager()
        self.service = None
        self.enable_classification = enable_classification
        self.enable_sentiment = enable_sentiment
        
        if enable_classification:
            self.classifier = get_email_classifier()
        if enable_sentiment:
            self.sentiment_analyzer = get_sentiment_analyzer()
    
    def _ensure_service(self) -> bool:
        """Ensure Gmail service is available."""
        if not self.service:
            self.service = self.auth_manager.get_gmail_service()
        return self.service is not None
    
    def _decode_body(self, payload: dict) -> str:
        """
        Decode email body from payload.
        
        Args:
            payload: Email payload from Gmail API
            
        Returns:
            Decoded body text
        """
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(
                            part['body']['data']
                        ).decode('utf-8')
                        break
        elif 'body' in payload and 'data' in payload['body']:
            body = base64.urlsafe_b64decode(
                payload['body']['data']
            ).decode('utf-8')
        
        return body
    
    def _parse_email(self, message: dict) -> Optional[EmailData]:
        """
        Parse Gmail message into EmailData.
        
        Args:
            message: Gmail message object
            
        Returns:
            EmailData object or None
        """
        try:
            headers = {h['name']: h['value'] for h in message['payload']['headers']}
            
            # Extract fields
            subject = headers.get('Subject', '(No Subject)')
            sender = headers.get('From', 'Unknown')
            recipient = headers.get('To', 'Unknown')
            date_str = headers.get('Date', '')
            
            # Parse date
            try:
                # Gmail date format is complex, use current time as fallback
                date = datetime.now()
            except:
                date = datetime.now()
            
            # Get body
            body = self._decode_body(message['payload'])
            snippet = message.get('snippet', '')
            
            email_data = EmailData(
                message_id=message['id'],
                subject=subject,
                sender=sender,
                recipient=recipient,
                date=date,
                body=body,
                snippet=snippet
            )
            
            # Add classification if enabled
            if self.enable_classification:
                try:
                    email_data.classification = self.classifier.classify(email_data)
                    logger.debug(f"Classified as {email_data.classification.category.value}")
                except Exception as e:
                    logger.warning(f"Classification failed: {e}")
            
            # Add sentiment analysis if enabled
            if self.enable_sentiment:
                try:
                    email_data.sentiment = self.sentiment_analyzer.analyze(email_data)
                    logger.debug(f"Sentiment: {email_data.sentiment.sentiment.value}, Urgency: {email_data.sentiment.urgency_score}")
                except Exception as e:
                    logger.warning(f"Sentiment analysis failed: {e}")
            
            return email_data
        except Exception as e:
            logger.error(f"Error parsing email: {e}")
            return None
    
    def fetch_emails(self, max_results: int = 10, query: str = "") -> List[EmailData]:
        """
        Fetch emails from Gmail.
        
        Args:
            max_results: Maximum number of emails to fetch
            query: Gmail search query (e.g., "is:unread")
            
        Returns:
            List of EmailData objects
        """
        if not self._ensure_service():
            logger.error("Gmail service not available")
            return []
        
        try:
            # List messages
            logger.info(f"Fetching up to {max_results} emails with query: '{query}'")
            results = self.service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q=query
            ).execute()
            
            messages = results.get('messages', [])
            logger.info(f"Found {len(messages)} messages")
            
            # Fetch full message details
            emails = []
            for msg in messages:
                try:
                    full_msg = self.service.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='full'
                    ).execute()
                    
                    email_data = self._parse_email(full_msg)
                    if email_data:
                        emails.append(email_data)
                        logger.debug(f"Parsed email: {email_data.subject}")
                except HttpError as e:
                    logger.error(f"Error fetching message {msg['id']}: {e}")
                    continue
            
            logger.info(f"Successfully parsed {len(emails)} emails")
            return emails
            
        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching emails: {e}")
            return []


def get_gmail_reader() -> GmailReader:
    """Get a Gmail reader instance."""
    return GmailReader()
