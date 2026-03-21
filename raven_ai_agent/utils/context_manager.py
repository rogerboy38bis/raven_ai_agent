"""
Context Manager for Multi-Agent Orchestration.

Provides session context tracking across agent interactions with TTL support.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Set
import threading
import uuid


class SessionContext:
    """
    Stores per-user conversation state for context-aware responses.
    
    Attributes:
        user: The user identifier
        last_intent: The last resolved intent
        last_document: The last referenced document
        last_agent: The last agent that handled a request
        last_command: The last command string
        session_start: When the session was created
        turn_count: Number of interactions in this session
        context_data: Arbitrary key-value data for agents
    """
    
    # Intents that are considered related follow-ups
    FOLLOW_UP_RELATIONS: Dict[str, Set[str]] = {
        'list': {'status', 'detail', 'info'},
        'status': {'diagnose', 'detail', 'info'},
        'diagnose': {'fix', 'workflow', 'action'},
        'payment': {'status', 'detail', 'check'},
        'workflow': {'run', 'execute', 'start'},
    }
    
    def __init__(self, user: str):
        """
        Initialize a new session context for a user.
        
        Args:
            user: The user identifier
        """
        self.user = user
        self.last_intent: Optional[str] = None
        self.last_document: Optional[str] = None
        self.last_agent: Optional[str] = None
        self.last_command: Optional[str] = None
        self.session_start: datetime = datetime.now()
        self.turn_count: int = 0
        self.context_data: Dict[str, Any] = {}
        self._last_update: datetime = datetime.now()
    
    def update(
        self,
        intent: Optional[str] = None,
        document: Optional[str] = None,
        agent: Optional[str] = None,
        command: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Update session context fields and increment turn count.
        
        Args:
            intent: The new intent to store
            document: The document reference to store
            agent: The agent name to store
            command: The command string to store
            **kwargs: Additional context data to merge into context_data
        """
        if intent is not None:
            self.last_intent = intent
        if document is not None:
            self.last_document = document
        if agent is not None:
            self.last_agent = agent
        if command is not None:
            self.last_command = command
        
        if kwargs:
            self.context_data.update(kwargs)
        
        self.turn_count += 1
        self._last_update = datetime.now()
    
    def get_context(self) -> Dict[str, Any]:
        """
        Get all current context fields as a dictionary.
        
        Returns:
            Dict containing all context fields
        """
        return {
            'user': self.user,
            'last_intent': self.last_intent,
            'last_document': self.last_document,
            'last_agent': self.last_agent,
            'last_command': self.last_command,
            'session_start': self.session_start.isoformat(),
            'turn_count': self.turn_count,
            'context_data': self.context_data.copy(),
            'last_update': self._last_update.isoformat(),
        }
    
    def clear(self) -> None:
        """Reset the session to its initial state."""
        self.last_intent = None
        self.last_document = None
        self.last_agent = None
        self.last_command = None
        self.context_data = {}
        self.turn_count = 0
        self.session_start = datetime.now()
        self._last_update = datetime.now()
    
    def is_follow_up(self, new_intent: str) -> bool:
        """
        Check if new_intent is related to the last_intent.
        
        Args:
            new_intent: The new intent to check
            
        Returns:
            True if the new intent relates to the last intent
        """
        if not self.last_intent:
            return False
        
        new_intent_lower = new_intent.lower().strip()
        last_intent_lower = self.last_intent.lower().strip()
        
        # Direct match
        if new_intent_lower == last_intent_lower:
            return True
        
        # Check predefined relations
        if last_intent_lower in self.FOLLOW_UP_RELATIONS:
            related_intents = self.FOLLOW_UP_RELATIONS[last_intent_lower]
            if new_intent_lower in related_intents:
                return True
        
        # Check reverse relation
        for intent, related in self.FOLLOW_UP_RELATIONS.items():
            if last_intent_lower in related and new_intent_lower == intent:
                return True
        
        return False
    
    @property
    def is_expired(self) -> bool:
        """Check if the session has expired based on last update time."""
        return datetime.now() - self._last_update > timedelta(minutes=30)


class ContextStore:
    """
    In-memory store for user session contexts with TTL support.
    
    Manages session lifecycle with automatic cleanup of expired sessions.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Ensure singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the context store."""
        if self._initialized:
            return
        
        self._sessions: Dict[str, SessionContext] = {}
        self._session_ttl = timedelta(minutes=30)
        self._lock = threading.Lock()
        self._initialized = True
    
    def get_or_create(self, user: str) -> SessionContext:
        """
        Get or create a session context for a user.
        
        Args:
            user: The user identifier
            
        Returns:
            The session context for the user
        """
        with self._lock:
            if user not in self._sessions:
                self._sessions[user] = SessionContext(user)
            return self._sessions[user]
    
    def get(self, user: str) -> Optional[SessionContext]:
        """
        Get an existing session context without creating a new one.
        
        Args:
            user: The user identifier
            
        Returns:
            The session context or None if not found
        """
        return self._sessions.get(user)
    
    def remove(self, user: str) -> bool:
        """
        Remove a user's session context.
        
        Args:
            user: The user identifier
            
        Returns:
            True if a session was removed
        """
        with self._lock:
            if user in self._sessions:
                del self._sessions[user]
                return True
            return False
    
    def cleanup_expired(self) -> int:
        """
        Remove sessions older than the TTL (30 minutes).
        
        Returns:
            Number of sessions removed
        """
        with self._lock:
            expired_users = [
                user for user, ctx in self._sessions.items()
                if ctx.is_expired
            ]
            for user in expired_users:
                del self._sessions[user]
            return len(expired_users)
    
    def get_active_session_count(self) -> int:
        """
        Get the number of active sessions.
        
        Returns:
            Number of non-expired sessions
        """
        self.cleanup_expired()
        return len(self._sessions)
    
    def clear_all(self) -> None:
        """Clear all sessions."""
        with self._lock:
            self._sessions.clear()


def get_context_store() -> ContextStore:
    """
    Get the singleton ContextStore instance.
    
    Returns:
        The shared ContextStore instance
    """
    return ContextStore()
