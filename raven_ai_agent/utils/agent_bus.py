"""
Agent Bus for Inter-Agent Communication.

Provides a publish-subscribe event bus for agents to communicate
without direct coupling.
"""

from datetime import datetime
from typing import Callable, Dict, List, Any, Optional
from collections import deque
import threading
import uuid


# Common event types
EVENT_SO_UPDATED = "sales_order_updated"
EVENT_WO_CREATED = "work_order_created"
EVENT_PAYMENT_PROCESSED = "payment_processed"
EVENT_AGENT_ERROR = "agent_error"
EVENT_WORKFLOW_TRIGGERED = "workflow_triggered"
EVENT_AGENT_START = "agent_start"
EVENT_AGENT_COMPLETE = "agent_complete"
EVENT_DOCUMENT_CREATED = "document_created"
EVENT_DOCUMENT_UPDATED = "document_updated"


class AgentEvent:
    """
    Represents an event emitted by an agent.
    
    Attributes:
        event_type: The type of event (e.g., EVENT_SO_UPDATED)
        source_agent: The name of the agent that emitted the event
        target_agent: Optional target agent for directed events
        payload: Dictionary containing event data
        timestamp: When the event was created
        correlation_id: UUID to trace related events across agents
    """
    
    def __init__(
        self,
        event_type: str,
        source_agent: str,
        payload: Dict[str, Any],
        target_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ):
        """
        Create a new agent event.
        
        Args:
            event_type: The type of event
            source_agent: The agent emitting the event
            payload: Event data
            target_agent: Optional specific target
            correlation_id: Optional correlation ID (generated if not provided)
        """
        self.event_type = event_type
        self.source_agent = source_agent
        self.target_agent = target_agent
        self.payload = payload
        self.timestamp = datetime.now()
        self.correlation_id = correlation_id or str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary representation.
        
        Returns:
            Dict containing all event fields
        """
        return {
            'event_type': self.event_type,
            'source_agent': self.source_agent,
            'target_agent': self.target_agent,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat(),
            'correlation_id': self.correlation_id,
        }
    
    def __repr__(self) -> str:
        """String representation of the event."""
        return (
            f"AgentEvent(type={self.event_type}, "
            f"source={self.source_agent}, "
            f"correlation={self.correlation_id[:8]}...)"
        )


class AgentBus:
    """
    Singleton event bus for inter-agent communication.
    
    Provides thread-safe pub/sub functionality with event queuing.
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
        """Initialize the event bus."""
        if self._initialized:
            return
        
        self._queue: deque = deque(maxlen=500)
        self._handlers: Dict[str, List[Callable]] = {}
        self._handler_lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._initialized = True
    
    def publish(self, event: AgentEvent) -> None:
        """
        Add an event to the internal queue.
        
        Args:
            event: The event to publish
        """
        with self._queue_lock:
            self._queue.append(event)
    
    def subscribe(self, event_type: str, handler: Callable[[AgentEvent], None]) -> None:
        """
        Register a handler for a specific event type.
        
        Args:
            event_type: The event type to subscribe to
            handler: Callable that handles the event
        """
        with self._handler_lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable[[AgentEvent], None]) -> bool:
        """
        Remove a handler for a specific event type.
        
        Args:
            event_type: The event type
            handler: The handler to remove
            
        Returns:
            True if handler was found and removed
        """
        with self._handler_lock:
            if event_type in self._handlers:
                if handler in self._handlers[event_type]:
                    self._handlers[event_type].remove(handler)
                    return True
        return False
    
    def dispatch(self, event: AgentEvent) -> None:
        """
        Call all registered handlers for the event type.
        
        Args:
            event: The event to dispatch
        """
        handlers_to_call = []
        
        with self._handler_lock:
            if event.event_type in self._handlers:
                handlers_to_call = self._handlers[event.event_type].copy()
        
        for handler in handlers_to_call:
            try:
                handler(event)
            except Exception:
                # Log but don't propagate - handlers shouldn't break the bus
                pass
    
    def publish_and_dispatch(self, event: AgentEvent) -> None:
        """
        Publish an event and immediately dispatch to handlers.
        
        Args:
            event: The event to publish and dispatch
        """
        self.publish(event)
        self.dispatch(event)
    
    def get_queue_size(self) -> int:
        """
        Get the number of events in the queue.
        
        Returns:
            Number of queued events
        """
        with self._queue_lock:
            return len(self._queue)
    
    def get_handlers_count(self, event_type: str) -> int:
        """
        Get the number of handlers for an event type.
        
        Args:
            event_type: The event type
            
        Returns:
            Number of registered handlers
        """
        with self._handler_lock:
            return len(self._handlers.get(event_type, []))
    
    def clear_handlers(self, event_type: Optional[str] = None) -> None:
        """
        Clear handlers for a specific event type or all handlers.
        
        Args:
            event_type: Optional event type to clear (clears all if None)
        """
        with self._handler_lock:
            if event_type is None:
                self._handlers.clear()
            elif event_type in self._handlers:
                del self._handlers[event_type]
    
    def clear_queue(self) -> None:
        """Clear all events from the queue."""
        with self._queue_lock:
            self._queue.clear()


def get_bus() -> AgentBus:
    """
    Get the singleton AgentBus instance.
    
    Returns:
        The shared AgentBus instance
    """
    return AgentBus()
