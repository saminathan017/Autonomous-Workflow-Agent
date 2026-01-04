"""
AI-powered sentiment analysis module.
"""
import json
from autonomous_workflow_agent.app.ai.openai_client import get_openai_client
from autonomous_workflow_agent.app.workflows.models import EmailData, SentimentAnalysis, Sentiment
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class SentimentAnalyzer:
    """Analyzes email sentiment and urgency."""
    
    def __init__(self):
        """Initialize the sentiment analyzer."""
        self.openai_client = get_openai_client()
    
    def analyze(self, email: EmailData) -> SentimentAnalysis:
        """
        Analyze email sentiment and urgency.
        
        Args:
            email: EmailData object to analyze
            
        Returns:
            SentimentAnalysis with sentiment, urgency score, and recommendations
        """
        system_message = """You are a sentiment analysis expert. Analyze emails for:
1. Sentiment: POSITIVE, NEGATIVE, or NEUTRAL
2. Urgency Score: 0.0 (not urgent) to 1.0 (extremely urgent)
3. Human Review: Whether this needs human attention

Consider:
- Tone and language
- Time sensitivity
- Emotional content
- Request complexity

Respond in JSON format:
{
  "sentiment": "POSITIVE|NEGATIVE|NEUTRAL",
  "urgency_score": 0.75,
  "requires_human": true,
  "confidence": 0.90
}"""
        
        prompt = f"""Analyze this email:

Subject: {email.subject}
From: {email.sender}
Content: {email.snippet[:300]}

Provide sentiment analysis in JSON format."""
        
        try:
            result = self.openai_client.generate_completion(
                prompt=prompt,
                system_message=system_message,
                temperature=0.3
            )
            
            if result["success"]:
                try:
                    data = json.loads(result["content"])
                    
                    # Map sentiment string to enum
                    sentiment_map = {
                        "POSITIVE": Sentiment.POSITIVE,
                        "NEGATIVE": Sentiment.NEGATIVE,
                        "NEUTRAL": Sentiment.NEUTRAL
                    }
                    
                    sentiment = sentiment_map.get(
                        data.get("sentiment", "NEUTRAL").upper(),
                        Sentiment.NEUTRAL
                    )
                    
                    return SentimentAnalysis(
                        sentiment=sentiment,
                        urgency_score=float(data.get("urgency_score", 0.5)),
                        requires_human=bool(data.get("requires_human", False)),
                        confidence=float(data.get("confidence", 0.5))
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse sentiment response: {e}")
                    return self._fallback_analysis(email)
            else:
                logger.warning(f"Sentiment analysis failed: {result['error']}")
                return self._fallback_analysis(email)
                
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return self._fallback_analysis(email)
    
    def _fallback_analysis(self, email: EmailData) -> SentimentAnalysis:
        """
        Fallback rule-based sentiment analysis.
        
        Args:
            email: EmailData object
            
        Returns:
            SentimentAnalysis based on simple rules
        """
        subject_lower = email.subject.lower()
        snippet_lower = email.snippet.lower()
        combined = f"{subject_lower} {snippet_lower}"
        
        # Positive indicators
        positive_words = ['thank', 'great', 'excellent', 'appreciate', 'wonderful', 'love']
        positive_count = sum(1 for word in positive_words if word in combined)
        
        # Negative indicators
        negative_words = ['urgent', 'problem', 'issue', 'error', 'complaint', 'angry', 'disappointed']
        negative_count = sum(1 for word in negative_words if word in combined)
        
        # Urgency indicators
        urgency_words = ['urgent', 'asap', 'immediate', 'critical', 'emergency', 'now']
        urgency_count = sum(1 for word in urgency_words if word in combined)
        
        # Determine sentiment
        if positive_count > negative_count:
            sentiment = Sentiment.POSITIVE
        elif negative_count > positive_count:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.NEUTRAL
        
        # Calculate urgency score
        urgency_score = min(urgency_count * 0.25, 1.0)
        
        # Determine if human review needed
        requires_human = (
            negative_count > 2 or
            urgency_count > 1 or
            'complaint' in combined or
            'legal' in combined
        )
        
        return SentimentAnalysis(
            sentiment=sentiment,
            urgency_score=urgency_score,
            requires_human=requires_human,
            confidence=0.6
        )


def get_sentiment_analyzer() -> SentimentAnalyzer:
    """Get a sentiment analyzer instance."""
    return SentimentAnalyzer()
