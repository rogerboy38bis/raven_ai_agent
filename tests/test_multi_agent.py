"""
Tests for Multi-Agent Orchestration - context_manager.py, agent_bus.py, multi_agent_router.py

Phase 8B Task 5
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import time
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSessionContext(unittest.TestCase):
    """Test SessionContext class"""
    
    def test_initial_state(self):
        """Test that SessionContext initializes with correct defaults"""
        from raven_ai_agent.utils.context_manager import SessionContext
        
        ctx = SessionContext("test_user")
        
        self.assertEqual(ctx.user, "test_user")
        self.assertIsNone(ctx.last_intent)
        self.assertIsNone(ctx.last_document)
        self.assertIsNone(ctx.last_agent)
        self.assertIsNone(ctx.last_command)
        self.assertEqual(ctx.turn_count, 0)
        self.assertEqual(ctx.context_data, {})
    
    def test_update_increments_turn_count(self):
        """Test that update() increments turn_count"""
        from raven_ai_agent.utils.context_manager import SessionContext
        
        ctx = SessionContext("test_user")
        
        ctx.update(intent="status")
        self.assertEqual(ctx.turn_count, 1)
        
        ctx.update(intent="diagnose")
        self.assertEqual(ctx.turn_count, 2)
        
        ctx.update(command="list sales orders")
        self.assertEqual(ctx.turn_count, 3)
    
    def test_is_follow_up_returns_true_for_related_intents(self):
        """Test that is_follow_up() returns True for related intents"""
        from raven_ai_agent.utils.context_manager import SessionContext
        
        ctx = SessionContext("test_user")
        
        # Set last intent to "list"
        ctx.last_intent = "list"
        
        # status is related to list
        self.assertTrue(ctx.is_follow_up("status"))
        
        # detail is related to list
        self.assertTrue(ctx.is_follow_up("detail"))
    
    def test_is_follow_up_returns_false_for_unrelated(self):
        """Test that is_follow_up() returns False for unrelated intents"""
        from raven_ai_agent.utils.context_manager import SessionContext
        
        ctx = SessionContext("test_user")
        
        # Set last intent to "list"
        ctx.last_intent = "list"
        
        # workflow is not related to list
        self.assertFalse(ctx.is_follow_up("workflow"))
    
    def test_clear_resets_state(self):
        """Test that clear() resets all state"""
        from raven_ai_agent.utils.context_manager import SessionContext
        
        ctx = SessionContext("test_user")
        
        # Update with some data
        ctx.update(
            intent="status",
            document="SO-0001",
            agent="sales_order",
            command="status SO-0001"
        )
        ctx.context_data["key"] = "value"
        
        # Clear
        ctx.clear()
        
        # Verify reset
        self.assertIsNone(ctx.last_intent)
        self.assertIsNone(ctx.last_document)
        self.assertIsNone(ctx.last_agent)
        self.assertIsNone(ctx.last_command)
        self.assertEqual(ctx.turn_count, 0)
        self.assertEqual(ctx.context_data, {})


class TestContextStore(unittest.TestCase):
    """Test ContextStore class"""
    
    def setUp(self):
        """Clear context store before each test"""
        from raven_ai_agent.utils.context_manager import ContextStore
        # Get a fresh instance for testing
        ContextStore._instance = None
        self.store = ContextStore()
        self.store.clear_all()
    
    def tearDown(self):
        """Clean up after each test"""
        self.store.clear_all()
    
    def test_get_or_create_returns_same_instance(self):
        """Test that get_or_create returns the same instance for same user"""
        ctx1 = self.store.get_or_create("user1")
        ctx2 = self.store.get_or_create("user1")
        
        self.assertIs(ctx1, ctx2)
    
    def test_get_or_create_new_user_creates_fresh_context(self):
        """Test that get_or_create creates new context for new user"""
        ctx1 = self.store.get_or_create("user1")
        ctx2 = self.store.get_or_create("user2")
        
        self.assertIsNot(ctx1, ctx2)
        self.assertEqual(ctx1.user, "user1")
        self.assertEqual(ctx2.user, "user2")
    
    def test_cleanup_expired_removes_old_sessions(self):
        """Test that cleanup_expired removes old sessions"""
        from raven_ai_agent.utils.context_manager import SessionContext
        from datetime import timedelta
        
        ctx = self.store.get_or_create("old_user")
        # Manually set last_update to past (simulate expired)
        ctx._last_update = ctx._last_update - timedelta(hours=1)
        
        # Add a fresh user
        self.store.get_or_create("new_user")
        
        # Cleanup
        removed = self.store.cleanup_expired()
        
        # Should have removed at least the expired session
        self.assertGreaterEqual(removed, 1)
    
    def test_multiple_users_independent_contexts(self):
        """Test that multiple users have independent contexts"""
        ctx1 = self.store.get_or_create("user1")
        ctx2 = self.store.get_or_create("user2")
        
        ctx1.update(intent="status")
        ctx2.update(intent="diagnose")
        
        self.assertEqual(ctx1.last_intent, "status")
        self.assertEqual(ctx2.last_intent, "diagnose")


class TestAgentEvent(unittest.TestCase):
    """Test AgentEvent class"""
    
    def test_event_has_correlation_id(self):
        """Test that event generates correlation_id if not provided"""
        from raven_ai_agent.utils.agent_bus import AgentEvent
        
        event = AgentEvent(
            event_type="test_event",
            source_agent="agent1",
            payload={"data": "value"}
        )
        
        self.assertIsNotNone(event.correlation_id)
        self.assertIsInstance(event.correlation_id, str)
    
    def test_event_timestamp_is_set(self):
        """Test that event timestamp is set on creation"""
        from raven_ai_agent.utils.agent_bus import AgentEvent
        
        before = time.time()
        event = AgentEvent(
            event_type="test_event",
            source_agent="agent1",
            payload={}
        )
        after = time.time()
        
        self.assertIsNotNone(event.timestamp)
        self.assertGreaterEqual(event.timestamp.timestamp(), before)
        self.assertLessEqual(event.timestamp.timestamp(), after)
    
    def test_event_payload_accessible(self):
        """Test that event payload is accessible"""
        from raven_ai_agent.utils.agent_bus import AgentEvent
        
        payload = {"key": "value", "number": 42}
        event = AgentEvent(
            event_type="test_event",
            source_agent="agent1",
            payload=payload
        )
        
        self.assertEqual(event.payload, payload)
        self.assertEqual(event.payload["key"], "value")


class TestAgentBus(unittest.TestCase):
    """Test AgentBus class"""
    
    def setUp(self):
        """Get fresh AgentBus instance for each test"""
        from raven_ai_agent.utils.agent_bus import AgentBus
        AgentBus._instance = None
        self.bus = AgentBus()
        self.bus.clear_queue()
        self.bus.clear_handlers()
    
    def test_publish_adds_to_queue(self):
        """Test that publish() adds event to queue"""
        from raven_ai_agent.utils.agent_bus import AgentEvent, AgentBus
        AgentBus._instance = None
        bus = AgentBus()
        
        event = AgentEvent("test", "agent1", {})
        bus.publish(event)
        
        self.assertEqual(bus.get_queue_size(), 1)
    
    def test_subscribe_and_dispatch_calls_handler(self):
        """Test that subscribe() and dispatch() work together"""
        from raven_ai_agent.utils.agent_bus import AgentEvent, AgentBus
        AgentBus._instance = None
        bus = AgentBus()
        
        called = []
        def handler(e):
            called.append(e)
        
        bus.subscribe("test_event", handler)
        
        event = AgentEvent("test_event", "agent1", {"data": "test"})
        bus.dispatch(event)
        
        self.assertEqual(len(called), 1)
        self.assertEqual(called[0].event_type, "test_event")
    
    def test_unsubscribe_removes_handler(self):
        """Test that unsubscribe() removes handler"""
        from raven_ai_agent.utils.agent_bus import AgentEvent, AgentBus
        AgentBus._instance = None
        bus = AgentBus()
        
        def handler(e):
            pass
        
        bus.subscribe("test_event", handler)
        bus.unsubscribe("test_event", handler)
        
        self.assertEqual(bus.get_handlers_count("test_event"), 0)
    
    def test_publish_and_dispatch_triggers_handler(self):
        """Test that publish_and_dispatch() publishes and dispatches"""
        from raven_ai_agent.utils.agent_bus import AgentEvent, AgentBus
        AgentBus._instance = None
        bus = AgentBus()
        
        called = []
        def handler(e):
            called.append(e)
        
        bus.subscribe("test_event", handler)
        
        event = AgentEvent("test_event", "agent1", {})
        bus.publish_and_dispatch(event)
        
        # Should be in queue AND dispatched
        self.assertEqual(bus.get_queue_size(), 1)
        self.assertEqual(len(called), 1)
    
    def test_event_constants_exist(self):
        """Test that event constants are defined"""
        from raven_ai_agent.utils import agent_bus
        
        self.assertTrue(hasattr(agent_bus, 'EVENT_SO_UPDATED'))
        self.assertTrue(hasattr(agent_bus, 'EVENT_WO_CREATED'))
        self.assertTrue(hasattr(agent_bus, 'EVENT_PAYMENT_PROCESSED'))
        self.assertTrue(hasattr(agent_bus, 'EVENT_AGENT_ERROR'))
        self.assertTrue(hasattr(agent_bus, 'EVENT_WORKFLOW_TRIGGERED'))


class TestMultiAgentRouter(unittest.TestCase):
    """Test multi_agent_router functions"""
    
    def test_is_multi_agent_command_true_for_workflow_run(self):
        """Test workflow run is detected as multi-agent"""
        from raven_ai_agent.api.multi_agent_router import is_multi_agent_command
        
        self.assertTrue(is_multi_agent_command("workflow run SO-0001"))
        self.assertTrue(is_multi_agent_command("execute workflow SO-0001"))
    
    def test_is_multi_agent_command_true_for_full_status(self):
        """Test full status is detected as multi-agent"""
        from raven_ai_agent.api.multi_agent_router import is_multi_agent_command
        
        self.assertTrue(is_multi_agent_command("full status SO-0001"))
        self.assertTrue(is_multi_agent_command("complete status SO-0001"))
        self.assertTrue(is_multi_agent_command("detailed status SO-0001"))
    
    def test_is_multi_agent_command_false_for_simple_status(self):
        """Test simple status is NOT detected as multi-agent"""
        from raven_ai_agent.api.multi_agent_router import is_multi_agent_command
        
        self.assertFalse(is_multi_agent_command("status SO-0001"))
        self.assertFalse(is_multi_agent_command("list sales orders"))
        self.assertFalse(is_multi_agent_command("help"))
    
    def test_build_pipeline_workflow_run_has_3_steps(self):
        """Test workflow run pipeline has correct steps"""
        from raven_ai_agent.api.multi_agent_router import build_agent_pipeline
        
        pipeline = build_agent_pipeline("workflow run SO-0001")
        
        self.assertEqual(len(pipeline), 3)
        self.assertEqual(pipeline[0]["agent"], "sales_order_followup")
        self.assertEqual(pipeline[1]["agent"], "manufacturing")
        self.assertEqual(pipeline[2]["agent"], "payment")
    
    def test_handle_multi_agent_command_returns_none_for_simple_commands(self):
        """Test that simple commands return None (not handled)"""
        from raven_ai_agent.api.multi_agent_router import handle_multi_agent_command
        
        result = handle_multi_agent_command("status SO-0001", "test_user")
        
        self.assertIsNone(result)
    
    def test_build_pipeline_morning_briefing(self):
        """Test morning briefing pipeline has correct steps"""
        from raven_ai_agent.api.multi_agent_router import build_agent_pipeline
        
        pipeline = build_agent_pipeline("morning briefing")
        
        self.assertEqual(len(pipeline), 3)
        self.assertEqual(pipeline[0]["agent"], "sales_order_followup")
        self.assertEqual(pipeline[1]["agent"], "manufacturing")
        self.assertEqual(pipeline[2]["agent"], "payment")
    
    def test_build_pipeline_diagnose_and_fix(self):
        """Test diagnose and fix pipeline"""
        from raven_ai_agent.api.multi_agent_router import build_agent_pipeline
        
        pipeline = build_agent_pipeline("diagnose and fix SO-0001")
        
        self.assertEqual(len(pipeline), 3)
        self.assertEqual(pipeline[0]["agent"], "sales_order_followup")
        self.assertEqual(pipeline[1]["agent"], "data_quality_scanner")
        self.assertEqual(pipeline[2]["agent"], "workflow_orchestrator")
    
    def test_extract_so_from_command(self):
        """Test SO extraction from command"""
        from raven_ai_agent.api.multi_agent_router import _extract_so_from_command
        
        so = _extract_so_from_command("status SO-0001")
        self.assertEqual(so, "SO-0001")
        
        so = _extract_so_from_command("full status SO-12345-Test")
        self.assertEqual(so, "SO-12345-Test")
        
        so = _extract_so_from_command("list sales orders")
        self.assertIsNone(so)


if __name__ == "__main__":
    unittest.main()
