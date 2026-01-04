"""
AI-powered email classification module.
"""
from typing import Dict
from autonomous_workflow_agent.app.ai.openai_client import get_openai_client
from autonomous_workflow_agent.app.workflows.models import EmailData, EmailClassification, EmailCategory
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class EmailClassifier:
    """Classifies emails using AI."""
    
    def __init__(self):
        """Initialize the email classifier."""
        self.openai_client = get_openai_client()
    
    def classify(self, email: EmailData) -> EmailClassification:
        """
        Classify an email into a category.
        
        Args:
            email: EmailData object to classify
            
        Returns:
            EmailClassification with category, confidence, and reasoning
        """
        # Build classification prompt
        system_message = """You are an email classification expert. Classify emails into these categories:
- URGENT: Time-sensitive emails requiring immediate attention
- CUSTOMER_INQUIRY: Questions or requests from customers
- INVOICE: Bills, invoices, payment requests
- NEWSLETTER: Marketing emails, newsletters, promotions
- SPAM: Unwanted or suspicious emails
- GENERAL: Everything else

Respond in JSON format:
{
  "category": "category_name",
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}"""
        
        prompt = f"""Classify this email:

Subject: {email.subject}
From: {email.sender}
Preview: {email.snippet[:200]}

Provide classification in JSON format."""
        
        try:
            result = self.openai_client.generate_completion(
                prompt=prompt,
                system_message=system_message,
                temperature=0.3  # Lower temperature for more consistent classification
            )
            
            if result["success"]:
                # Parse JSON response
                import json
                try:
                    data = json.loads(result["content"])
                    
                    # Map category string to enum
                    category_map = {
                        "URGENT": EmailCategory.URGENT,
                        "CUSTOMER_INQUIRY": EmailCategory.CUSTOMER_INQUIRY,
                        "INVOICE": EmailCategory.INVOICE,
                        "NEWSLETTER": EmailCategory.NEWSLETTER,
                        "SPAM": EmailCategory.SPAM,
                        "GENERAL": EmailCategory.GENERAL
                    }
                    
                    category = category_map.get(
                        data.get("category", "GENERAL").upper(),
                        EmailCategory.GENERAL
                    )
                    
                    return EmailClassification(
                        category=category,
                        confidence=float(data.get("confidence", 0.5)),
                        reasoning=data.get("reasoning", "AI classification")
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse classification response: {e}")
                    # Fallback classification
                    return self._fallback_classification(email)
            else:
                logger.warning(f"Classification failed: {result['error']}")
                return self._fallback_classification(email)
                
        except Exception as e:
            logger.error(f"Error classifying email: {e}")
            return self._fallback_classification(email)
    
    def _fallback_classification(self, email: EmailData) -> EmailClassification:
        """
        Fallback rule-based classification when AI fails.
        
        Args:
            email: EmailData object
            
        Returns:
            EmailClassification based on simple rules
        """
        subject_lower = email.subject.lower()
        sender_lower = email.sender.lower()
        
        # Simple keyword-based classification
        if any(word in subject_lower for word in ['urgent', 'asap', 'immediate', 'critical']):
            return EmailClassification(
                category=EmailCategory.URGENT,
                confidence=0.6,
                reasoning="Contains urgency keywords"
            )
        elif any(word in subject_lower for word in ['invoice', 'payment', 'bill', 'receipt']):
            return EmailClassification(
                category=EmailCategory.INVOICE,
                confidence=0.7,
                reasoning="Contains invoice keywords"
            )
        elif any(word in subject_lower for word in ['unsubscribe', 'newsletter', 'promotion']):
            return EmailClassification(
                category=EmailCategory.NEWSLETTER,
                confidence=0.7,
                reasoning="Contains newsletter keywords"
            )
        elif any(word in sender_lower for word in ['noreply', 'no-reply', 'donotreply']):
            return EmailClassification(
                category=EmailCategory.NEWSLETTER,
                confidence=0.6,
                reasoning="Automated sender"
            )
        else:
            return EmailClassification(
                category=EmailCategory.GENERAL,
                confidence=0.5,
                reasoning="Default classification"
            )


def get_email_classifier() -> EmailClassifier:
    """Get an email classifier instance."""
    return EmailClassifier()
