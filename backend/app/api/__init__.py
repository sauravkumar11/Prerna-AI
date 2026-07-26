from .chat import router as chat_router
from .tts import router as tts_router
from .health import router as health_router

__all__ = ["chat_router", "tts_router", "health_router"]
