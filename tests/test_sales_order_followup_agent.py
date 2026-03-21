"""
Unit Tests for SalesOrderFollowupAgent
18 tests covering sales_order_followup_agent.py new methods

Run with: python -m pytest tests/test_sales_order_followup_agent.py -v
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# Fix import path before any imports
def setup_import_path():
    """Ensure correct import path"""
    current = Path(__file__).resolve()
    project_root = current.parent.parent
    package_path = project_root / 'raven_ai_agent'
    if str(package_path) not in sys.path:
        sys.path.insert(0, str(project_root))
    if str(package_path) not in sys.path:
        sys.path.insert(0, str(package_path))


setup_import_path()


def create_mock_frappe():
    """Create a complete mock frappe module"""
    mock = MagicMock()
    mock.local = MagicMock()
    mock.local.site = "test.erpnext.com"
    mock.session = MagicMock()
    mock.session.user = "Administrator"
    mock.db = MagicMock()
    mock.DoesNotExistError = Exception
    mock.logger = MagicMock()
    return mock


class TestSalesOrderFollowupAgent(unittest.TestCase):
    """Test cases for SalesOrderFollowupAgent"""
    
    def setUp(self):
        """Set up mock frappe environment"""
        self.mock_frappe = create_mock_frappe()
    
    def _apply_frappe_patch(self, mock_frappe_module):
        """Helper to apply frappe mock to a module"""
        mock_frappe_module.local = self.mock_frappe.local
        mock_frappe_module.session = self.mock_frappe.session
        mock_frappe_module.db = self.mock_frappe.db
    
    def test_create_from_quotation_happy_path(self):
        """S-01: Create from Quotation — happy path"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock submitted Quotation
            mock_qtn = MagicMock()
            mock_qtn.name = "SAL-QTN-2026-00001"
            mock_qtn.docstatus = 1
            mock_qtn.party_name = "Test Customer"
            
            # Mock created SO
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            
            mock_frappe.get_doc.return_value = mock_qtn
            
            with patch('raven_ai_agent.agents.sales_order_followup_agent.make_sales_order', return_value=mock_so):
                agent = SalesOrderFollowupAgent()
                result = agent.create_from_quotation("SAL-QTN-2026-00001")
                
                self.assertTrue(result.get("success"))
                self.assertIn("SO-TEST-001", result.get("sales_order", ""))
    
    def test_create_from_quotation_idempotent(self):
        """S-02: Create from Quotation — idempotent"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock Quotation that already has SO
            mock_qtn = MagicMock()
            mock_qtn.name = "SAL-QTN-2026-00001"
            mock_qtn.docstatus = 1
            
            # Return existing SO
            mock_frappe.get_all.return_value = [{"name": "SO-EXISTING-001"}]
            mock_frappe.get_doc.return_value = mock_qtn
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_from_quotation("SAL-QTN-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already has a Sales Order", result.get("message", "").lower())
    
    def test_create_from_quotation_not_submitted(self):
        """S-03: Create from Quotation — qtn not submitted"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock draft Quotation
            mock_qtn = MagicMock()
            mock_qtn.name = "SAL-QTN-2026-00001"
            mock_qtn.docstatus = 0  # Draft
            
            mock_frappe.get_doc.return_value = mock_qtn
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_from_quotation("SAL-QTN-2026-00001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("must be submitted", result.get("error", "").lower())
    
    def test_get_pipeline_status_all_complete(self):
        """S-04: Get pipeline status — all complete"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock fully completed pipeline
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100, warehouse="WH-001")]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []  # No further docs
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_pipeline_status("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    def test_get_pipeline_status_partial(self):
        """S-05: Get pipeline status — partial"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock partial pipeline
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100, warehouse="WH-001")]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []  # No delivery note yet
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_pipeline_status("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    def test_check_document_status_draft(self):
        """S-06: Check document status — draft"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_doc = MagicMock()
            mock_doc.docstatus = 0
            mock_doc.name = "TEST-DOC-001"
            mock_frappe.get_doc.return_value = mock_doc
            
            agent = SalesOrderFollowupAgent()
            status = agent.check_document_status("TEST-DOC-001", "Sales Order")
            
            self.assertEqual(status, "Draft")
    
    def test_check_document_status_submitted(self):
        """S-07: Check document status — submitted"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_doc = MagicMock()
            mock_doc.docstatus = 1
            mock_doc.name = "TEST-DOC-001"
            mock_frappe.get_doc.return_value = mock_doc
            
            agent = SalesOrderFollowupAgent()
            status = agent.check_document_status("TEST-DOC-001", "Sales Order")
            
            self.assertEqual(status, "Submitted")
    
    def test_trace_source_quotation(self):
        """S-08: Trace source quotation"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock SO with quotation link
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.quotation = "SAL-QTN-2026-00001"
            
            mock_frappe.get_doc.return_value = mock_so
            
            agent = SalesOrderFollowupAgent()
            qtn_name = agent.trace_source_quotation("SO-TEST-001")
            
            self.assertEqual(qtn_name, "SAL-QTN-2026-00001")
    
    def test_trace_source_quotation_no_link(self):
        """S-09: Trace source quotation — no link"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock SO without quotation link
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.quotation = None
            
            mock_frappe.get_doc.return_value = mock_so
            
            agent = SalesOrderFollowupAgent()
            qtn_name = agent.trace_source_quotation("SO-TEST-001")
            
            self.assertIsNone(qtn_name)
    
    def test_process_command_diagnose(self):
        """S-10: Process command — diagnose"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock empty pipeline
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100, warehouse="WH-001")]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            agent = SalesOrderFollowupAgent()
            result = agent.process_command("diagnose SO-TEST-001")
            
            # process_command returns a string
            self.assertIsInstance(result, str)
    
    def test_process_command_status(self):
        """S-11: Process command — status"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100, warehouse="WH-001")]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            agent = SalesOrderFollowupAgent()
            result = agent.process_command("status SO-TEST-001")
            
            self.assertIsInstance(result, str)
    
    def test_process_command_help(self):
        """S-12: Process command — help"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        agent = SalesOrderFollowupAgent()
        result = agent.process_command("help")
        
        self.assertIsInstance(result, str)
        self.assertIn("Sales Order", result)
    
    def test_build_pipeline_report_empty(self):
        """S-13: Build pipeline report — empty"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        agent = SalesOrderFollowupAgent()
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100)]
            mock_so.currency = "USD"
            mock_so.grand_total = 1000.0
            
            mock_frappe.get_doc.return_value = mock_so
            
            result = agent._build_diagnosis_report("SO-TEST-001", [])
            
            self.assertIsInstance(result, str)
    
    def test_format_currency(self):
        """S-14: Format currency"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        agent = SalesOrderFollowupAgent()
        formatted = agent._format_currency(1000.50, "USD")
        
        self.assertIn("1,000.50", formatted)
        self.assertIn("USD", formatted)
    
    def test_get_overdue_days(self):
        """S-15: Get overdue days"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        agent = SalesOrderFollowupAgent()
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.getdate') as mock_getdate:
            from datetime import date
            mock_getdate.return_value = date(2026, 3, 21)
            
            overdue = agent._get_overdue_days("2026-03-01")
            
            self.assertEqual(overdue, 20)
    
    def test_check_item_availability(self):
        """S-16: Check item availability"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_value.return_value = 150  # available qty
            
            agent = SalesOrderFollowupAgent()
            available = agent.check_item_availability("0307", "WH-001", 100)
            
            self.assertTrue(available)
    
    def test_check_item_availability_insufficient(self):
        """S-17: Check item availability — insufficient"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_value.return_value = 50  # available qty
            
            agent = SalesOrderFollowupAgent()
            available = agent.check_item_availability("0307", "WH-001", 100)
            
            self.assertFalse(available)
    
    def test_reserve_stock(self):
        """S-18: Reserve stock"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            agent = SalesOrderFollowupAgent()
            result = agent.reserve_stock("SO-TEST-001")
            
            # Just check it returns a dict (actual implementation may vary)
            self.assertIsInstance(result, dict)


if __name__ == '__main__':
    unittest.main()
