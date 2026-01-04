"""
Centralized OpenAI client wrapper with rate limiting and cost controls.
"""
import time
from typing import Optional, Dict, Any
from openai import OpenAI, OpenAIError
from autonomous_workflow_agent.app.config import get_settings
from autonomous_workflow_agent.app.utils.logging import get_logger

logger = get_logger(__name__)


class OpenAIClientWrapper:
    """
    Wrapper around OpenAI client with built-in safety controls.
    
    Features:
    - Rate limiting (max calls per run)
    - Token caps
    - Timeout enforcement
    - Error handling with graceful fallbacks
    """
    
    def __init__(self):
        """Initialize the OpenAI client with settings."""
        self.settings = get_settings()
        self.client = OpenAI(
            api_key=self.settings.openai_api_key,
            timeout=self.settings.openai_timeout_seconds
        )
        self.call_count = 0
        self.max_calls = self.settings.openai_max_calls_per_run
        
    def reset_call_count(self):
        """Reset the call counter for a new workflow run."""
        self.call_count = 0
        logger.info("OpenAI call counter reset")
        
    def _check_rate_limit(self) -> bool:
        """
        Check if we've exceeded the rate limit.
        
        Returns:
            True if we can make another call, False otherwise
        """
        if self.call_count >= self.max_calls:
            logger.warning(
                f"OpenAI rate limit reached: {self.call_count}/{self.max_calls} calls"
            )
            return False
        return True
    
    def generate_completion(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generate a completion using OpenAI API with safety controls.
        
        Args:
            prompt: User prompt
            system_message: Optional system message
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate (defaults to config value)
            
        Returns:
            Dictionary with 'success', 'content', 'error', and 'usage' keys
        """
        # Check rate limit
        if not self._check_rate_limit():
            return {
                "success": False,
                "content": None,
                "error": "Rate limit exceeded",
                "usage": None
            }
        
        # Use configured max tokens if not specified
        if max_tokens is None:
            max_tokens = self.settings.openai_max_tokens
        
        # Ensure we don't exceed the configured limit
        max_tokens = min(max_tokens, self.settings.openai_max_tokens)
        
        # Build messages
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        try:
            logger.info(f"Making OpenAI API call ({self.call_count + 1}/{self.max_calls})")
            start_time = time.time()
            
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            elapsed = time.time() - start_time
            self.call_count += 1
            
            content = response.choices[0].message.content
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            logger.info(
                f"OpenAI call successful in {elapsed:.2f}s. "
                f"Tokens: {usage['total_tokens']}"
            )
            
            return {
                "success": True,
                "content": content,
                "error": None,
                "usage": usage
            }
            
        except OpenAIError as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return {
                "success": False,
                "content": None,
                "error": str(e),
                "usage": None
            }
        except Exception as e:
            logger.error(f"Unexpected error in OpenAI call: {str(e)}")
            return {
                "success": False,
                "content": None,
                "error": f"Unexpected error: {str(e)}",
                "usage": None
            }
    
    def summarize_text(self, text: str, max_length: int = 200) -> str:
        """
        Summarize text using OpenAI.
        
        Args:
            text: Text to summarize
            max_length: Maximum length of summary in words
            
        Returns:
            Summary text or fallback message
        """
        system_message = "You are a helpful assistant that creates concise summaries."
        prompt = f"Summarize the following text in no more than {max_length} words:\n\n{text}"
        
        result = self.generate_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.5
        )
        
        if result["success"]:
            return result["content"]
        else:
            logger.warning(f"Summarization failed: {result['error']}")
            # Fallback: return truncated text
            words = text.split()[:max_length]
            return " ".join(words) + "..."
    
    def extract_insights(self, data: str) -> str:
        """
        Extract key insights from data using OpenAI.
        
        Args:
            data: Data to analyze
            
        Returns:
            Insights text or fallback message
        """
        system_message = (
            "You are an analytical assistant that extracts key insights "
            "and patterns from data."
        )
        prompt = f"Analyze the following data and provide 3-5 key insights:\n\n{data}"
        
        result = self.generate_completion(
            prompt=prompt,
            system_message=system_message,
            temperature=0.7
        )
        
        if result["success"]:
            return result["content"]
        else:
            logger.warning(f"Insight extraction failed: {result['error']}")
            return "Unable to generate insights at this time."


# Global client instance
_client: Optional[OpenAIClientWrapper] = None


def get_openai_client() -> OpenAIClientWrapper:
    """Get or create the global OpenAI client instance."""
    global _client
    if _client is None:
        _client = OpenAIClientWrapper()
    return _client
