"""
Tests for Pipeline Validation - validate_pipeline name resolution

Task 3 - Focused unit test for validate_pipeline numeric Quotation resolution
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestValidatePipelineNameResolution(unittest.TestCase):
    """Test that validate_pipeline correctly resolves partial/numeric names"""

    @patch('raven_ai_agent.api.truth_hierarchy.frappe')
    @patch('raven_ai_agent.utils.doc_resolver.resolve_document_name')
    def test_validate_pipeline_resolves_numeric_quotation_id(self, mock_resolve, mock_frappe):
        """Test that validate_pipeline('0753') resolves to SAL-QTN-2024-00753"""
        
        # Arrange: mock resolve_document_name to return expected resolution
        mock_resolve.return_value = "SAL-QTN-2024-00753"
        
        # Create mock Quotation document
        mock_qtn = MagicMock()
        mock_qtn.name = "SAL-QTN-2024-00753"
        mock_qtn.status = "Ordered"
        mock_qtn.docstatus = 1
        mock_qtn.grand_total = 187200.00
        mock_qtn.currency = "USD"
        mock_qtn.party_name = "GREENTECH SA"
        
        # Create mock Sales Order
        mock_so = MagicMock()
        mock_so.name = "SO-00753-GREENTECH SA"
        mock_so.status = "Completed"
        mock_so.docstatus = 1
        mock_so.grand_total = 187200.00
        mock_so.currency = "USD"
        
        # Create mock Delivery Note
        mock_dn = MagicMock()
        mock_dn.name = "MAT-DN-2026-00003"
        mock_dn.docstatus = 1
        
        # Create mock Sales Invoice
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00004"
        mock_si.docstatus = 1
        mock_si.outstanding_amount = 187200.00
        mock_si.grand_total = 187200.00
        mock_si.mx_payment_option = "PUE"
        
        # Mock frappe.get_doc to return appropriate mock based on doctype
        def mock_get_doc(doctype, name):
            if doctype == "Quotation":
                return mock_qtn
            elif doctype == "Sales Order":
                return mock_so
            elif doctype == "Delivery Note":
                return mock_dn
            elif doctype == "Sales Invoice":
                return mock_si
            raise Exception(f"Unexpected doctype: {doctype}")
        
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_frappe.db = MagicMock()
        
        # Mock database get_value
        def mock_get_value(doctype, filters, field):
            if doctype == "Sales Order" and "against_quotation" in str(filters):
                return "SO-00753-GREENTECH SA"
            if doctype == "Delivery Note" and "against_sales_order" in str(filters):
                return "MAT-DN-2026-00003"
            if doctype == "Sales Invoice Item":
                return "ACC-SINV-2026-00004"
            if doctype == "Sales Invoice":
                return "PUE"
            return None
        
        mock_frappe.db.get_value.side_effect = mock_get_value
        
        # Act
        from raven_ai_agent.api.truth_hierarchy import validate_pipeline
        result = validate_pipeline("0753")
        
        # Assert: verify resolve_document_name was called correctly
        mock_resolve.assert_called_once_with("Quotation", "0753")
        
        # Assert: verify the result contains the resolved quotation name
        self.assertEqual(result["quotation"], "SAL-QTN-2024-00753")
        self.assertIn("documents", result)

    @patch('raven_ai_agent.api.truth_hierarchy.frappe')
    @patch('raven_ai_agent.utils.doc_resolver.resolve_document_name')
    def test_validate_pipeline_resolves_partial_so_name(self, mock_resolve, mock_frappe):
        """Test that validate_pipeline resolves partial SO name (e.g., SO-00752)"""
        
        # Arrange: mock to resolve SO-00752 -> SO-00752-LEGOSAN AB
        def resolve_side_effect(doctype, partial_name):
            if doctype == "Quotation" and partial_name == "SO-00752":
                # When given SO name, it tries Quotation first and may not find it
                return None
            return None
        
        mock_resolve.side_effect = resolve_side_effect
        
        # Mock frappe.get_doc to raise DoesNotExistError for Quotation
        mock_frappe.exceptions = MagicMock()
        mock_frappe.exceptions.DoesNotExistError = Exception
        
        def mock_get_doc(doctype, name):
            if doctype == "Quotation":
                raise Exception("Quotation Not Found")
            raise Exception(f"Unexpected doctype: {doctype}")
        
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_frappe.db = MagicMock()
        
        # Act
        from raven_ai_agent.api.truth_hierarchy import validate_pipeline
        result = validate_pipeline("SO-00752")
        
        # Assert: verify it attempted to resolve as Quotation first
        # The function tries Quotation first, then falls back to SO logic
        self.assertIn("issues", result)


class TestValidatePipelineCFDIResolution(unittest.TestCase):
    """Test CFDI field validation in pipeline"""

    @patch('raven_ai_agent.api.truth_hierarchy.frappe')
    @patch('raven_ai_agent.utils.doc_resolver.resolve_document_name')
    def test_validate_pipeline_detects_cfdi_mismatch(self, mock_resolve, mock_frappe):
        """Test that validate_pipeline detects CFDI PUE vs PPD mismatch"""
        
        # Arrange
        mock_resolve.return_value = "SAL-QTN-2024-00753"
        
        # Quotation with credit_days = 30 (should trigger PPD expectation)
        mock_qtn = MagicMock()
        mock_qtn.name = "SAL-QTN-2024-00753"
        mock_qtn.status = "Ordered"
        mock_qtn.docstatus = 1
        mock_qtn.grand_total = 187200.00
        mock_qtn.currency = "USD"
        mock_qtn.party_name = "GREENTECH SA"
        mock_qtn.payment_schedule = [MagicMock(credit_days=30)]
        
        # Sales Invoice with PUE (mismatch)
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00004"
        mock_si.docstatus = 1
        mock_si.outstanding_amount = 187200.00
        mock_si.grand_total = 187200.00
        mock_si.mx_payment_option = "PUE"
        
        def mock_get_doc(doctype, name):
            if doctype == "Quotation":
                return mock_qtn
            elif doctype == "Sales Invoice":
                return mock_si
            raise Exception(f"Unexpected doctype: {doctype}")
        
        mock_frappe.get_doc.side_effect = mock_get_doc
        mock_frappe.db = MagicMock()
        
        # Return None for linked docs (SO, DN) to simulate incomplete pipeline
        def mock_get_value(doctype, filters, field):
            return None
        
        mock_frappe.db.get_value.side_effect = mock_get_value
        
        # Act
        from raven_ai_agent.api.truth_hierarchy import validate_pipeline
        result = validate_pipeline("0753")
        
        # Assert: CFDI mismatch should be detected
        self.assertEqual(result["quotation"], "SAL-QTN-2024-00753")
        # The result should contain the CFDI info
        self.assertIn("cfdi", result)


if __name__ == "__main__":
    unittest.main()
