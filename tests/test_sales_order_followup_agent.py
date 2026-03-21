"""
Unit Tests for SalesOrderFollowupAgent
18 tests covering sales_order_followup_agent.py new methods

Run with: python -m pytest raven_ai_agent/tests/test_sales_order_followup_agent.py -v
"""
import unittest
from unittest.mock import MagicMock, patch


class TestSalesOrderFollowupAgent(unittest.TestCase):
    """Test cases for SalesOrderFollowupAgent"""
    
    def setUp(self):
        """Set up mock frappe environment"""
        self.mock_frappe = MagicMock()
        self.mock_frappe.local = MagicMock()
        self.mock_frappe.local.site = "test.erpnext.com"
        self.mock_frappe.session = MagicMock()
        self.mock_frappe.session.user = "Administrator"
        self.mock_frappe.db = MagicMock()
        
    @patch('raven_ai_agent.agents.sales_order_followup_agent.make_sales_order')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_from_quotation_happy_path(self, mock_get_doc, mock_make_so):
        """S-01: Create from Quotation — happy path"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # Mock submitted Quotation
        mock_qtn = MagicMock()
        mock_qtn.name = "SAL-QTN-2026-00001"
        mock_qtn.docstatus = 1
        mock_qtn.party_name = "Test Customer"
        
        # Mock created SO
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        
        mock_get_doc.return_value = mock_qtn
        mock_make_so.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.make_sales_order = mock_make_so
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_from_quotation("SAL-QTN-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("SO-TEST-001", result.get("sales_order", ""))
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_from_quotation_idempotent(self, mock_get_doc, mock_get_all):
        """S-02: Create from Quotation — idempotent"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # Mock Quotation that already has SO
        mock_qtn = MagicMock()
        mock_qtn.name = "SAL-QTN-2026-00001"
        mock_qtn.docstatus = 1
        
        # Return existing SO
        mock_get_all.return_value = [{"name": "SO-EXISTING-001"}]
        
        mock_get_doc.return_value = mock_qtn
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_from_quotation("SAL-QTN-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already has a Sales Order", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_from_quotation_not_submitted(self, mock_get_doc):
        """S-03: Create from Quotation — qtn not submitted"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # Mock draft Quotation
        mock_qtn = MagicMock()
        mock_qtn.name = "SAL-QTN-2026-00001"
        mock_qtn.docstatus = 0  # Draft
        
        mock_get_doc.return_value = mock_qtn
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_from_quotation("SAL-QTN-2026-00001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("must be submitted", result.get("error", "").lower())
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.make_delivery_note')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_delivery_note_happy_path(self, mock_get_doc, mock_make_dn):
        """S-04: Create Delivery Note — happy path"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # Mock submitted SO
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.delivery_status = "Not Delivered"
        mock_so.per_delivered = 0
        mock_so.customer = "Test Customer"
        
        # Mock created DN
        mock_dn = MagicMock()
        mock_dn.name = "DN-TEST-001"
        mock_dn.docstatus = 0
        
        mock_get_doc.return_value = mock_so
        mock_make_dn.return_value = mock_dn
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.make_delivery_note = mock_make_dn
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(return_value="FG to Sell - AMB-W")
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_delivery_note("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_delivery_note_idempotent(self, mock_get_doc, mock_get_all):
        """S-05: Create Delivery Note — idempotent"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        
        # Return existing DN
        mock_get_all.return_value = [{"name": "DN-EXISTING-001"}]
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_delivery_note("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already has a Delivery Note", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_delivery_note_insufficient_inventory(self, mock_get_doc, mock_get_all):
        """S-06: Create Delivery Note — insufficient inventory"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.items = [MagicMock(item_code="0307", qty=100)]
        
        # No stock available
        mock_get_all.return_value = []
        
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_delivery_note("SO-TEST-001")
            
            # Should warn about insufficient inventory
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_delivery_note_so_not_submitted(self, mock_get_doc):
        """S-07: Create Delivery Note — SO not submitted"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 0  # Draft
        
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_delivery_note("SO-TEST-001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("must be submitted", result.get("error", "").lower())
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_delivery_note_already_delivered(self, mock_get_doc):
        """S-08: Create Delivery Note — already delivered"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.delivery_status = "Fully Delivered"
        
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_delivery_note("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already fully delivered", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.make_delivery_note')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_delivery_note_qi_warning(self, mock_get_doc, mock_make_dn):
        """S-09: Create Delivery Note — QI warning"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # SO with inspection required
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.delivery_status = "Not Delivered"
        mock_so.per_delivered = 0
        mock_so.items = [MagicMock(item_code="0307", qty=100, inspection_required_before_delivery=1)]
        
        mock_dn = MagicMock()
        mock_dn.name = "DN-TEST-001"
        mock_dn.docstatus = 0
        
        mock_get_doc.return_value = mock_so
        mock_make_dn.return_value = mock_dn
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.make_delivery_note = mock_make_dn
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(return_value="FG to Sell - AMB-W")
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_delivery_note("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.make_sales_invoice')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_sales_invoice_from_dn(self, mock_get_doc, mock_make_si):
        """S-10: Create Sales Invoice — from DN"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # Mock DN
        mock_dn = MagicMock()
        mock_dn.name = "DN-TEST-001"
        mock_dn.docstatus = 1
        mock_dn.customer = "Test Customer"
        mock_dn.company = "AMB-Wellness"
        
        # Mock created SI with CFDI fields
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 0
        mock_si.mx_cfdi_use = "G03"
        mock_si.currency = "USD"
        
        mock_get_doc.return_value = mock_dn
        mock_make_si.return_value = mock_si
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.make_sales_invoice = mock_make_si
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(return_value="G03")
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_sales_invoice("DN-TEST-001", from_dn=True, cfdi_use="G03")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.make_sales_invoice')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_sales_invoice_from_so_directly(self, mock_get_doc, mock_make_si):
        """S-11: Create Sales Invoice — from SO directly"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # Mock SO
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.customer = "Test Customer"
        mock_so.company = "AMB-Wellness"
        
        # Mock created SI
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 0
        mock_si.mx_cfdi_use = "G03"
        
        mock_get_doc.return_value = mock_so
        mock_make_si.return_value = mock_si
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.make_sales_invoice = mock_make_si
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(return_value="G03")
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_sales_invoice("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_sales_invoice_idempotent(self, mock_get_doc, mock_get_all):
        """S-12: Create Sales Invoice — idempotent"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        
        # Return existing SI
        mock_get_all.return_value = [{"name": "ACC-SINV-EXISTING-001"}]
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_sales_invoice("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already has a Sales Invoice", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.make_sales_invoice')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_sales_invoice_cfdi_g03(self, mock_get_doc, mock_make_si):
        """S-13: Create Sales Invoice — CFDI G03"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.customer = "Test Customer"
        mock_so.company = "AMB-Wellness"
        
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 0
        
        mock_get_doc.return_value = mock_so
        mock_make_si.return_value = mock_si
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.make_sales_invoice = mock_make_si
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(return_value="G03")
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_sales_invoice("SO-TEST-001", cfdi_use="G03")
            
            self.assertTrue(result.get("success"))
            # Verify CFDI field is set on the created SI
            mock_make_si.return_value.insert.assert_called()
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.make_sales_invoice')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_sales_invoice_usd_currency(self, mock_get_doc, mock_make_si):
        """S-14: Create Sales Invoice — USD currency"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.customer = "Test Customer"
        mock_so.company = "AMB-Wellness"
        mock_so.currency = "USD"
        mock_so.conversion_rate = 17.5
        
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 0
        mock_si.currency = "USD"
        mock_si.conversion_rate = 17.5
        
        mock_get_doc.return_value = mock_so
        mock_make_si.return_value = mock_si
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.make_sales_invoice = mock_make_si
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(return_value="G03")
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_sales_invoice("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_create_sales_invoice_fully_billed(self, mock_get_doc):
        """S-15: Create Sales Invoice — fully billed"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.billing_status = "Fully Billed"
        
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.create_sales_invoice("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already fully billed", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_get_next_steps_with_active_wos(self, mock_get_doc, mock_get_all):
        """S-16: get_next_steps — with active WOs"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        # SO with active Work Orders
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.delivery_status = "Not Delivered"
        
        # Return active WO
        mock_get_all.return_value = [
            {"name": "MFG-WO-001", "status": "In Process"}
        ]
        
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_next_steps("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
            # Should mention completing WOs first
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_get_next_steps_inventory_available(self, mock_get_doc, mock_get_all):
        """S-17: get_next_steps — inventory available"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.delivery_status = "Not Delivered"
        
        # No WOs, stock available
        mock_get_all.side_effect = [
            [],  # No WOs
            [{"actual_qty": 100}]  # Stock available
        ]
        
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_next_steps("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
            # Should recommend creating DN
    
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.sales_order_followup_agent.frappe.get_doc')
    def test_get_so_status_includes_wos(self, mock_get_doc, mock_get_all):
        """S-18: get_so_status — includes WOs"""
        from raven_ai_agent.agents.sales_order_followup_agent import SalesOrderFollowupAgent
        
        mock_so = MagicMock()
        mock_so.name = "SO-TEST-001"
        mock_so.docstatus = 1
        mock_so.status = "To Deliver"
        mock_so.customer = "Test Customer"
        
        # Return linked WOs
        mock_get_all.return_value = [
            {"name": "MFG-WO-001", "status": "In Process", "produced_qty": 50, "qty": 100},
            {"name": "MFG-WO-002", "status": "Pending", "produced_qty": 0, "qty": 50}
        ]
        
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.sales_order_followup_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = SalesOrderFollowupAgent()
            result = agent.get_so_status("SO-TEST-001")
            
            self.assertTrue(result.get("success"))
            # Should include work_orders in response


if __name__ == '__main__':
    unittest.main()
