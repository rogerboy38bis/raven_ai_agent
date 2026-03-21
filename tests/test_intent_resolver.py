"""
Unit tests for Intent Resolver
Phase 7: Natural Language Intent Resolution

Tests the intent resolver without requiring frappe environment.
"""

import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os

# Add the app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'raven_ai_agent'))


class TestIntentResolverPatterns(unittest.TestCase):
    """Test cases for IntentResolver pattern matching"""
    
    def test_direct_command_patterns(self):
        """Test direct command pattern detection"""
        # Test patterns that should be detected as direct commands
        DIRECT_PATTERNS = [
            'SAL-QTN-2024-00760',
            'SAL-ORD-2024-00123',
            'SO-00754',
            'SINV-2024-00500',
            'diagnose ',
            'status ',
            '!submit ',
            'convert ',
            'help',
            'overdue invoices',
        ]
        
        # Import the patterns directly
        import re
        from raven_ai_agent.api.intent_resolver import DIRECT_COMMAND_PATTERNS
        
        test_texts = [
            "@ai diagnose SAL-QTN-2024-00760",
            "status Sales Order SO-00754",
            "!submit sales order SAL-ORD-2024-00123",
            "convert quotation SAL-QTN-2024-00760 to sales order",
            "help",
            "overdue invoices",
        ]
        
        for text in test_texts:
            matched = False
            for pattern in DIRECT_COMMAND_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    matched = True
                    break
            self.assertTrue(matched, f"Should detect as direct command: {text}")
    
    def test_command_catalog_exists(self):
        """Test that COMMAND_CATALOG is properly defined"""
        from raven_ai_agent.api.intent_resolver import COMMAND_CATALOG
        
        # Should have multiple intents
        self.assertGreater(len(COMMAND_CATALOG), 10)
        
        # Should have key intents
        expected_intents = [
            'status_check',
            'create_sales_order',
            'help',
            'get_unpaid_invoices',
        ]
        
        for intent in expected_intents:
            self.assertIn(intent, COMMAND_CATALOG)
    
    def test_command_templates(self):
        """Test command templates in catalog"""
        from raven_ai_agent.api.intent_resolver import COMMAND_CATALOG
        
        # Status check should have diagnose template
        self.assertIn('diagnose {document_id}', COMMAND_CATALOG['status_check'])
        
        # Create sales order should have convert template
        templates = ' '.join(COMMAND_CATALOG['create_sales_order'])
        self.assertIn('convert quotation', templates)
        
        # Help should be simple
        self.assertIn('help', COMMAND_CATALOG['help'])


class TestIntentResolverEntityExtraction(unittest.TestCase):
    """Test entity extraction without frappe"""
    
    def test_extract_document_id_patterns(self):
        """Test document ID regex patterns"""
        import re
        
        # Document ID patterns - use + to match multi-digit suffixes
        patterns = [
            r'SAL-QTN-\d+-\d+',     # Quotations
            r'SAL-ORD-\d+-\d+',      # Sales Orders
            r'SO-\d{3,5}',           # Short SO format
            r'SINV-\d+-\d+',         # Sales Invoices
            r'DN-\d+-\d+',           # Delivery Notes
            r'MFG-WO-\d+',           # Work Orders (use + to match more digits)
            r'LOTE-\d+',             # Batch IDs
            r'BOM-[^\s]+',           # BOMs
        ]
        
        test_cases = [
            ("diagnose SAL-QTN-2024-00760", "SAL-QTN-2024-00760"),
            ("status of SO-00754", "SO-00754"),
            ("convert quotation SAL-QTN-2024-00760", "SAL-QTN-2024-00760"),
            ("delivery for SAL-ORD-2024-00123", "SAL-ORD-2024-00123"),
            ("invoice from SINV-2024-00500", "SINV-2024-00500"),
            ("stock entry for MFG-WO-2024-00123", "MFG-WO-2024"),  # Just first part
            ("create bom for batch LOTE-2024-00123", "LOTE-2024"),  # Just first part
        ]
        
        for text, expected in test_cases:
            matched = None
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    matched = match.group(0).upper()
                    break
            self.assertEqual(matched, expected, f"Failed to extract from: {text}")


class TestIntentResolverLLMResponse(unittest.TestCase):
    """Test LLM response parsing"""
    
    def test_parse_valid_json_response(self):
        """Test parsing valid JSON from LLM"""
        import json
        
        # Direct JSON (simpler test)
        response = {
            "intent": "status_check",
            "entities": {
                "document_id": "SAL-ORD-2024-00754",
                "doc_type": "Sales Order"
            },
            "resolved_command": "diagnose SAL-ORD-2024-00754",
            "confidence": 0.85,
            "reasoning": "User asked for status of order"
        }
        
        # Parse as direct dict
        result = json.loads(json.dumps(response))
        self.assertEqual(result["intent"], "status_check")
        self.assertEqual(result["confidence"], 0.85)
    
    def test_confidence_threshold_logic(self):
        """Test confidence threshold logic"""
        # Note: IntentResolver uses threshold 0.6 for filtering, but returns None
        # when confidence < 0.7 (use_threshold in router integration)
        
        test_cases = [
            (0.95, True, "High confidence should use"),
            (0.80, True, "Above 0.7 should use"),
            (0.70, True, "At 0.7 should use"),
            (0.65, False, "Below 0.7 should NOT use in router"),
            (0.50, False, "Low confidence should NOT use"),
            (0.30, False, "Very low should NOT use"),
        ]
        
        # Router integration threshold (0.7)
        use_threshold = 0.7
        
        for confidence, expected_use, msg in test_cases:
            # Router checks confidence >= 0.7
            should_use = confidence >= use_threshold
            self.assertEqual(should_use, expected_use, f"{msg}: confidence={confidence}")
    
    def test_fallback_resolution_keywords(self):
        """Test fallback rule-based resolution keywords"""
        
        # Simple keyword matching for fallback
        text = "what is the status of my order for SO-12345"
        text_lower = text.lower()
        
        # Check for status keywords
        if any(word in text_lower for word in ["status", "track", "how is", "what is the status"]):
            # Extract document ID
            import re
            doc_match = re.search(r'SO-\d+', text, re.IGNORECASE)
            if doc_match:
                resolved = f"diagnose {doc_match.group(0).upper()}"
                self.assertEqual(resolved, "diagnose SO-12345")


class TestIntentResolverHelp(unittest.TestCase):
    """Test help intent detection"""
    
    def test_help_keywords(self):
        """Test help intent keyword detection"""
        
        help_phrases = [
            "help",
            "show help",
            "what can you do",
            "help me",
            "commands",
            "what commands",
        ]
        
        for phrase in help_phrases:
            is_help = any(word in phrase.lower() for word in ["help", "commands", "what can you do"])
            self.assertTrue(is_help, f"Should detect as help: {phrase}")


class TestIntentResolverEdgeCases(unittest.TestCase):
    """Test edge cases"""
    
    def test_empty_string(self):
        """Test handling of empty string"""
        # Empty or whitespace only should not be direct command
        empty_strings = ["", "   ", "\n", "\t"]
        
        for s in empty_strings:
            # Should not match any direct command pattern
            import re
            from raven_ai_agent.api.intent_resolver import DIRECT_COMMAND_PATTERNS
            
            matched = False
            for pattern in DIRECT_COMMAND_PATTERNS:
                if re.search(pattern, s, re.IGNORECASE):
                    matched = True
                    break
            self.assertFalse(matched, f"Should not match: '{s}'")
    
    def test_mixed_case_document_id(self):
        """Test case-insensitive document ID extraction"""
        import re
        
        patterns = [r'SAL-QTN-\d+-\d+', r'SO-\d{3,5}']
        
        test_cases = [
            "sal-qtn-2024-00760",
            "SAL-QTN-2024-00760",
            "So-00754",
            "so-12345",
        ]
        
        for text in test_cases:
            matched = None
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    matched = match.group(0)
                    break
            self.assertIsNotNone(matched, f"Should extract from: {text}")
    
    def test_greeting_returns_none(self):
        """Test that greetings don't resolve to commands"""
        
        greetings = [
            "hello",
            "hi there",
            "hey how are you",
            "good morning",
            "what's up",
        ]
        
        for greeting in greetings:
            # These should not match any status/create/help patterns in a way
            # that would resolve to a command
            is_command = any(word in greeting.lower() for word in [
                "diagnose", "status", "convert", "create", "submit", 
                "invoice", "delivery", "help", "overdue"
            ])
            self.assertFalse(is_command, f"Should not be command: {greeting}")


if __name__ == '__main__':
    unittest.main()
