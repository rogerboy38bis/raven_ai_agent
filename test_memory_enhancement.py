"""
Test Plan - Memory Enhancement Phases 1-3

Tests for:
1. Importance Scoring (Phase 1)
2. Consolidation Agent (Phase 2)
3. Citations (Phase 3)
"""
import frappe
import json
import unittest
from unittest.mock import Mock, patch, MagicMock


class TestImportanceScoring(unittest.TestCase):
    """Phase 1: Test auto importance scoring"""

    def test_importance_score_field_exists(self):
        """Test that ai_memory has importance_score field"""
        meta = frappe.get_meta("AI Memory")
        self.assertTrue(meta.has_field("importance_score"))

    def test_entities_field_exists(self):
        """Test that ai_memory has entities field"""
        meta = frappe.get_meta("AI Memory")
        self.assertTrue(meta.has_field("entities"))

    def test_topics_field_exists(self):
        """Test that ai_memory has topics field"""
        meta = frappe.get_meta("AI Memory")
        self.assertTrue(meta.has_field("topics"))

    def test_consolidated_field_exists(self):
        """Test that ai_memory has consolidated field"""
        meta = frappe.get_meta("AI Memory")
        self.assertTrue(meta.has_field("consolidated"))

    def test_analyze_memory_content_returns_dict(self):
        """Test LLM analysis returns proper structure"""
        # Mock the LLM client
        with patch('raven_ai_agent.api.memory_manager.MemoryMixin') as MockMixin:
            instance = MockMixin()
            instance.client = Mock()
            instance.model = "gpt-4o"
            
            # Mock LLM response
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = '{"importance_score": 0.85, "entities": "John, Project X", "topics": "manufacturing"}'
            instance.client.chat.completions.create = Mock(return_value=mock_response)
            
            result = instance._analyze_memory_content("User John works on Project X manufacturing")
            
            self.assertIn("importance_score", result)
            self.assertIn("entities", result)
            self.assertIn("topics", result)


class TestConsolidationAgent(unittest.TestCase):
    """Phase 2: Test consolidation agent"""

    def test_consolidation_agent_import(self):
        """Test that consolidation agent can be imported"""
        from raven_ai_agent.api.consolidation_agent import ConsolidationAgent
        self.assertIsNotNone(ConsolidationAgent)

    def test_find_connections_by_entities(self):
        """Test memory connections via shared entities"""
        from raven_ai_agent.api.consolidation_agent import ConsolidationAgent
        
        agent = ConsolidationAgent()
        
        memories = [
            {"name": "mem1", "entities": "John, Project X", "topics": "manufacturing"},
            {"name": "mem2", "entities": "John, Project Y", "topics": "sales"},
            {"name": "mem3", "entities": "Alice", "topics": "manufacturing"},
        ]
        
        connections = agent._find_connections(memories)
        
        # mem1 and mem2 share "John"
        self.assertIn("mem2", connections["mem1"])
        # mem1 and mem3 share "manufacturing" topic
        self.assertIn("mem3", connections["mem1"])

    def test_find_connections_by_topics(self):
        """Test memory connections via shared topics"""
        from raven_ai_agent.api.consolidation_agent import ConsolidationAgent
        
        agent = ConsolidationAgent()
        
        memories = [
            {"name": "mem1", "entities": "", "topics": "quality, production"},
            {"name": "mem2", "entities": "", "topics": "quality, shipping"},
        ]
        
        connections = agent._find_connections(memories)
        
        # Both have "quality" topic
        self.assertIn("mem2", connections["mem1"])


class TestCitations(unittest.TestCase):
    """Phase 3: Test citation formatting"""

    def test_search_memories_returns_citations(self):
        """Test that search_memories returns citation field"""
        with patch('raven_ai_agent.api.memory_manager.MemoryMixin') as MockMixin:
            instance = MockMixin()
            instance.user = "Administrator"
            instance.settings = {}
            
            # Mock frappe.get_list
            with patch('frappe.get_list') as mock_get_list:
                mock_get_list.return_value = [
                    {"name": "mem1", "content": "Test memory", "importance": "High", 
                     "importance_score": 0.8, "source": "Conversation", 
                     "creation": frappe.utils.now()}
                ]
                
                results = instance.search_memories("test")
                
                self.assertTrue(len(results) > 0)
                self.assertIn("citation", results[0])

    def test_citation_format(self):
        """Test citation format"""
        with patch('raven_ai_agent.api.memory_manager.MemoryMixin') as MockMixin:
            instance = MockMixin()
            
            memory = {
                "content": "Test",
                "importance": "High",
                "importance_score": 0.8,
                "source": "Conversation",
                "creation": frappe.utils.now()
            }
            
            citation = instance._format_citation(memory)
            
            self.assertIn("Conversation", citation)
            self.assertIn("High", citation)
            self.assertIn("80%", citation)


class TestMemoryStorage(unittest.TestCase):
    """Test memory storage with new fields"""

    def test_store_memory_with_all_fields(self):
        """Test storing memory with importance_score, entities, topics"""
        # Create test memory
        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": "Administrator",
            "content": "Test memory for importance scoring",
            "importance": "High",
            "importance_score": 0.85,
            "entities": "TestUser, TestSystem",
            "topics": "testing, validation",
            "memory_type": "Fact",
            "source": "Test"
        )
        
        # Check all fields are present
        self.assertEqual(doc.importance_score, 0.85)
        self.assertEqual(doc.entities, "TestUser, TestSystem")
        self.assertEqual(doc.topics, "testing, validation")


def run_tests():
    """Run all tests and return results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestImportanceScoring))
    suite.addTests(loader.loadTestsFromTestCase(TestConsolidationAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestCitations))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryStorage))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result


if __name__ == "__main__":
    result = run_tests()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"Success: {result.wasSuccessful()}")
    print("="*60)
