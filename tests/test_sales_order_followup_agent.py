"""
Unit Tests for SalesOrderFollowupAgent
18 tests covering sales_order_followup_agent.py methods

Run with: python -m pytest tests/test_sales_order_followup_agent.py -v
"""
import unittest
from unittest.mock import MagicMock, patch


class TestSalesOrderFollowupAgent(unittest.TestCase):
    """Test cases for SalesOrderFollowupAgent"""
    
    def test_create_from_quotation_happy_path(self):
        """S-01: Create from Quotation — happy path"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_qtn = MagicMock()
            mock_qtn.name = "SAL-QTN-2026-00001"
            mock_qtn.docstatus = 1
            mock_qtn.party_name = "Test Customer"
            
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.insert = MagicMock()
            
            mock_frappe.get_doc.return_value = mock_qtn
            
            with patch('erpnext.selling.doctype.quotation.quotation.make_sales_order', return_value=mock_so):
                agent = SalesOrderFollowupAgent()
                result = agent.create_from_quotation("SAL-QTN-2026-00001")
                
                self.assertTrue(result.get("success"))
    
    def test_create_from_quotation_idempotent(self):
        """S-02: Create from Quotation — idempotent"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_qtn = MagicMock()
            mock_qtn.name = "SAL-QTN-2026-00001"
            mock_qtn.docstatus = 1
            
            mock_frappe.get_all.return_value = [{"name": "SO-EXISTING-001"}]
            mock_frappe.get_doc.return_value = mock_qtn
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_from_quotation("SAL-QTN-2026-00001")
            
            self.assertTrue(result.get("success"))
    
    def test_create_from_quotation_not_submitted(self):
        """S-03: Create from Quotation — qtn not submitted"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_qtn = MagicMock()
            mock_qtn.name = "SAL-QTN-2026-00001"
            mock_qtn.docstatus = 0
            
            mock_frappe.get_doc.return_value = mock_qtn
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_from_quotation("SAL-QTN-2026-00001")
            
            self.assertFalse(result.get("success"))
    
    def test_get_so_status(self):
        """S-04: get_so_status"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100, warehouse="WH-001")]
            mock_so.status = "To Deliver"
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_so_status("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    def test_get_pending_orders(self):
        """S-05: get_pending_orders"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [
                {"name": "SO-001", "customer": "Cust1", "grand_total": 1000.0, "status": "To Deliver"},
                {"name": "SO-002", "customer": "Cust2", "grand_total": 2000.0, "status": "To Deliver"},
            ]
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_pending_orders()
            
            self.assertTrue(result.get("success"))
    
    def test_check_inventory(self):
        """S-06: check_inventory"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.items = [MagicMock(item_code="0307", warehouse="WH-001", qty=100)]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.db.get_value.return_value = 150
            
            agent = SalesOrderFollowupAgent()
            result = agent.check_inventory("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    def test_get_next_steps(self):
        """S-07: get_next_steps"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100)]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_next_steps("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    def test_create_delivery_note(self):
        """S-08: create_delivery_note"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100, warehouse="WH-001")]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            mock_dn = MagicMock()
            mock_dn.name = "DN-TEST-001"
            mock_dn.insert = MagicMock()
            mock_dn.submit = MagicMock()
            
            with patch('erpnext.selling.doctype.sales_order.sales_order.make_delivery_note', return_value=mock_dn):
                agent = SalesOrderFollowupAgent()
                result = agent.create_delivery_note("SO-TEST-001")
                
                self.assertTrue(result.get("success"))
    
    def test_create_sales_invoice(self):
        """S-09: create_sales_invoice"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100)]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            mock_si = MagicMock()
            mock_si.name = "SI-TEST-001"
            mock_si.insert = MagicMock()
            mock_si.submit = MagicMock()
            
            with patch('erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice', return_value=mock_si):
                agent = SalesOrderFollowupAgent()
                result = agent.create_sales_invoice("SO-TEST-001")
                
                self.assertTrue(result.get("success"))
    
    def test_track_purchase_cycle(self):
        """S-10: track_purchase_cycle"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.customer = "Test Customer"
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            agent = SalesOrderFollowupAgent()
            result = agent.track_purchase_cycle("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    def test_process_command_diagnose(self):
        """S-11: Process command — diagnose"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100, warehouse="WH-001")]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            agent = SalesOrderFollowupAgent()
            result = agent.process_command("diagnose SO-TEST-001")
            
            self.assertIsInstance(result, str)
    
    def test_process_command_status(self):
        """S-12: Process command — status"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
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
        """S-13: Process command — help"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        agent = SalesOrderFollowupAgent()
        result = agent.process_command("help")
        
        self.assertIsInstance(result, str)
        self.assertIn("Sales Order", result)
    
    def test_process_command_create(self):
        """S-14: Process command — create"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_qtn = MagicMock()
            mock_qtn.name = "SAL-QTN-2026-00001"
            mock_qtn.docstatus = 1
            mock_qtn.party_name = "Test Customer"
            
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.insert = MagicMock()
            
            mock_frappe.get_doc.return_value = mock_qtn
            
            with patch('erpnext.selling.doctype.quotation.quotation.make_sales_order', return_value=mock_so):
                agent = SalesOrderFollowupAgent()
                result = agent.process_command("create so from SAL-QTN-2026-00001")
                
                self.assertIsInstance(result, str)
    
    def test_process_command_pending(self):
        """S-15: Process command — pending"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_frappe.get_all.return_value = [
                {"name": "SO-001", "customer": "Cust1", "grand_total": 1000.0, "status": "To Deliver"},
            ]
            
            agent = SalesOrderFollowupAgent()
            result = agent.process_command("pending orders")
            
            self.assertIsInstance(result, str)
    
    def test_process_command_check_inventory(self):
        """S-16: Process command — check inventory"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.items = [MagicMock(item_code="0307", warehouse="WH-001", qty=100)]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.db.get_value.return_value = 150
            
            agent = SalesOrderFollowupAgent()
            result = agent.process_command("check inventory SO-TEST-001")
            
            self.assertIsInstance(result, str)
    
    def test_process_command_next_steps(self):
        """S-17: Process command — next steps"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.name = "SO-TEST-001"
            mock_so.docstatus = 1
            mock_so.customer = "Test Customer"
            mock_so.items = [MagicMock(item_code="0307", qty=100)]
            
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []
            
            agent = SalesOrderFollowupAgent()
            result = agent.process_command("next steps SO-TEST-001")
            
            self.assertIsInstance(result, str)
    
    def test_help_text(self):
        """S-18: _help_text"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        agent = SalesOrderFollowupAgent()
        result = agent._help_text()
        
        self.assertIsInstance(result, str)
        self.assertIn("Sales Order", result)


if __name__ == '__main__':
    unittest.main()
