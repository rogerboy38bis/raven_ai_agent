"""
Tests for Anti-Hallucination Guard - truth_hierarchy.py validation functions

Phase 8A Task 3
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExtractNumericValues(unittest.TestCase):
    """Test numeric value extraction from text"""
    
    def test_extract_currency_values(self):
        """Test extraction of currency values"""
        from raven_ai_agent.api.truth_hierarchy import extract_numeric_values
        
        text = "The total amount is $1,234.56 and the balance is $500.00"
        values = extract_numeric_values(text)
        
        # Should find at least 2 currency values
        currency_values = [v for v in values if v["type"] == "currency"]
        self.assertGreaterEqual(len(currency_values), 2)
    
    def test_extract_quantity_values(self):
        """Test extraction of quantity values"""
        from raven_ai_agent.api.truth_hierarchy import extract_numeric_values
        
        text = "Order contains 50 units and 10 boxes"
        values = extract_numeric_values(text)
        
        quantity_values = [v for v in values if v["type"] == "quantity"]
        self.assertGreaterEqual(len(quantity_values), 1)
    
    def test_extract_percentage_values(self):
        """Test extraction of percentage values"""
        from raven_ai_agent.api.truth_hierarchy import extract_numeric_values
        
        text = "The discount is 15% and tax is 10%"
        values = extract_numeric_values(text)
        
        percent_values = [v for v in values if v["type"] == "percentage"]
        self.assertEqual(len(percent_values), 2)
    
    def test_extract_date_values(self):
        """Test extraction of date values"""
        from raven_ai_agent.api.truth_hierarchy import extract_numeric_values
        
        text = "Delivery date: 2024-01-29 and invoice date: 2024-02-15"
        values = extract_numeric_values(text)
        
        date_values = [v for v in values if v["type"] == "date"]
        self.assertEqual(len(date_values), 2)


class TestSanitizeResponse(unittest.TestCase):
    """Test response sanitization"""
    
    def test_remove_placeholder_brackets(self):
        """Test removal of [Placeholder] text"""
        from raven_ai_agent.api.truth_hierarchy import sanitize_response
        
        response = "Customer: [Customer Name], Amount: [Amount], Date: [2024-01-29]"
        result = sanitize_response(response)
        
        self.assertEqual(result["safe"], True)
        self.assertIn("[DATA UNAVAILABLE]", result["cleaned"])
        self.assertGreater(len(result["removed"]), 0)
    
    def test_remove_todo_fixme(self):
        """Test removal of TODO/FIXME placeholders"""
        from raven_ai_agent.api.truth_hierarchy import sanitize_response
        
        response = "This is a [TODO] and this needs [FIXME]"
        result = sanitize_response(response)
        
        self.assertEqual(result["safe"], True)
        self.assertGreater(len(result["removed"]), 0)
    
    def test_clean_text_passes_through(self):
        """Test that clean text passes through unchanged"""
        from raven_ai_agent.api.truth_hierarchy import sanitize_response
        
        response = "Sales Order SO-00754-Calipso s.r.l has status Completed"
        result = sanitize_response(response)
        
        self.assertEqual(result["safe"], True)
        self.assertEqual(result["cleaned"], response)
        self.assertEqual(len(result["removed"]), 0)
    
    def test_hallucinated_field_patterns(self):
        """Test removal of hallucinated field patterns"""
        from raven_ai_agent.api.truth_hierarchy import sanitize_response
        
        response = "Customer: [John Doe], Total: [$50,000], Status: [Completed]"
        result = sanitize_response(response)
        
        self.assertTrue(result["safe"])
        # Should have removed the placeholders


class TestValidateResponse(unittest.TestCase):
    """Test response validation against context data"""
    
    def test_validate_correct_data(self):
        """Test validation passes for correct data"""
        from raven_ai_agent.api.truth_hierarchy import validate_response
        
        response = "Sales Order SO-00754-Calipso has total $69,189.12 and status Completed"
        context = {
            "document_name": "SO-00754-Calipso",
            "amount": 69189.12,
            "status": "Completed"
        }
        
        result = validate_response(response, context)
        
        # Should validate successfully
        self.assertTrue(result["validated"])
        self.assertGreaterEqual(result["confidence"], 0.6)
    
    def test_validate_hallucinated_amount(self):
        """Test validation fails for hallucinated amounts"""
        from raven_ai_agent.api.truth_hierarchy import validate_response
        
        response = "The total is $50,000 and status is Completed"
        context = {
            "document_name": "SO-00754-Calipso",
            "amount": 69189.12,
            "status": "Completed"
        }
        
        result = validate_response(response, context)
        
        # Should fail validation due to amount mismatch (confidence should be low)
        self.assertFalse(result["validated"])
        self.assertLess(result["confidence"], 0.7)
        self.assertGreater(len(result["corrections"]), 0)
    
    def test_validate_placeholder_text(self):
        """Test validation fails for placeholder text"""
        from raven_ai_agent.api.truth_hierarchy import validate_response
        
        response = "Customer: [Customer Name], Amount: [$0.00]"
        context = {
            "document_name": "SO-00754-Calipso",
            "amount": 69189.12,
            "customer": "Calipso s.r.l"
        }
        
        result = validate_response(response, context)
        
        # Should have issues due to placeholders
        self.assertGreater(len(result["issues"]), 0)
    
    def test_validate_empty_response(self):
        """Test validation of empty response"""
        from raven_ai_agent.api.truth_hierarchy import validate_response
        
        result = validate_response("", {})
        
        self.assertFalse(result["validated"])
        self.assertEqual(result["confidence"], 0.0)
    
    def test_validate_partial_match(self):
        """Test validation with partial customer name match"""
        from raven_ai_agent.api.truth_hierarchy import validate_response
        
        response = "Sales Order for Calipso has status Completed"
        context = {
            "document_name": "SO-00754-Calipso s.r.l",
            "customer": "Calipso s.r.l",
            "status": "Completed"
        }
        
        result = validate_response(response, context)
        
        # Should validate because "calipso" appears in customer name
        self.assertTrue(result["validated"])


class TestValidateAndSanitize(unittest.TestCase):
    """Test combined validation and sanitization"""
    
    def test_combined_sanitize_and_validate(self):
        """Test full pipeline with placeholders and wrong amount"""
        from raven_ai_agent.api.truth_hierarchy import validate_and_sanitize
        
        response = "Total: $50,000 and Customer: [Customer Name]"
        context = {
            "amount": 69189.12,
            "customer": "Calipso s.r.l"
        }
        
        result = validate_and_sanitize(response, context)
        
        # Should be sanitized but not validated
        self.assertIn("$50,000", result["original"])
        self.assertGreater(len(result["corrections"]), 0)
    
    def test_clean_response_passes(self):
        """Test clean response passes through"""
        from raven_ai_agent.api.truth_hierarchy import validate_and_sanitize
        
        response = "Sales Order SO-00754-Calipso - Status: Completed, Total: $69,189.12"
        context = {
            "document_name": "SO-00754-Calipso",
            "amount": 69189.12,
            "status": "Completed"
        }
        
        result = validate_and_sanitize(response, context)
        
        self.assertTrue(result["validated"])
        self.assertGreaterEqual(result["confidence"], 0.6)
        self.assertEqual(result["final_response"], response)
    
    def test_unsafe_response_gets_error_message(self):
        """Test that unsafe responses get error message"""
        from raven_ai_agent.api.truth_hierarchy import validate_and_sanitize
        
        # Response that's only placeholders
        response = "[Customer Name] - [Amount]"
        context = {}
        
        result = validate_and_sanitize(response, context)
        
        # Should return safe error message
        self.assertIn("cannot provide accurate", result["final_response"].lower())


class TestIntegrationWithResponseFormatter(unittest.TestCase):
    """Test integration with response_formatter"""
    
    def test_response_formatter_exists(self):
        """Test that response_formatter module exists and is importable"""
        try:
            from raven_ai_agent.api.response_formatter import format_response
            # Should be able to call format_response
            result = format_response("Test message", {})
            self.assertIsNotNone(result)
        except ImportError:
            self.skipTest("response_formatter not available")


if __name__ == "__main__":
    unittest.main()
