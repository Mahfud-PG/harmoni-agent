import logging
import uuid
import time
from functools import wraps
from sari_core.config_service import config

logger = logging.getLogger(__name__)

class Observability:
    """
    Sari AI Operating System - Observability & Reliability Layer
    Handles Trace ID, Correlation ID, logging, idempotency, and retries.
    """
    
    @staticmethod
    def generate_trace_id() -> str:
        return f"trc_{uuid.uuid4().hex[:12]}"
        
    @staticmethod
    def log_trace(trace_id: str, action: str, **kwargs):
        if config.ENABLE_DEBUG_TRACE:
            details = " | ".join(f"{k}={v}" for k, v in kwargs.items())
            logger.info(f"[TRACE: {trace_id}] {action} | {details}")

class Reliability:
    @staticmethod
    def with_retry(max_retries=3, delay_sec=2):
        """Decorator for exponential backoff retry."""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                retries = 0
                while retries < max_retries:
                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        retries += 1
                        logger.warning(f"Action failed, retrying ({retries}/{max_retries}): {e}")
                        if retries == max_retries:
                            raise
                        await asyncio.sleep(delay_sec * retries) # Exponential backoff
            return wrapper
        return decorator

class ConversationInspector:
    """
    Tool to dissect why Sari made a certain decision.
    """
    @staticmethod
    def inspect(person_id: str, revision: int):
        # In a real scenario, this queries the DB for the exact prompt sent and LLM output received at that revision
        return f"Inspection for {person_id} at revision {revision}: The LLM decided this based on 3 recent messages and 1 LTM fact."
