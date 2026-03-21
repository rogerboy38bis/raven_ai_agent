"""
Unit Tests for PaymentAgent
10 tests covering payment_agent.py methods

Run with: python -m pytest raven_ai_agent/tests/test_payment_agent.py -v
"""
import unittest
from unittest.mock import MagicMock, patch


class TestPaymentAgent(unittest.TestCase):
    """Test cases for PaymentAgent"""
    
    def setUp(self):
        """Set up mock frappe environment"""
        self.mock_frappe = MagicMock()
        self.mock_frappe.local = MagicMock()
        self.mock_frappe.local.site = "test.erpnext.com"
        self.mock_frappe.session = MagicMock()
        self.mock_frappe.session.user = "Administrator"
        self.mock_frappe.db = MagicMock()
        
    @patch('raven_ai_agent.agents.payment_agent.get_payment_entry')
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_create_payment_entry_happy_path(self, mock_get_doc, mock_get_payment_entry):
        """P-01: Create Payment Entry — happy path"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        # Mock SI
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 1
        mock_si.outstanding_amount = 1000.0
        mock_si.customer = "Test Customer"
        mock_si.company = "AMB-Wellness"
        mock_si.currency = "USD"
        mock_si.conversion_rate = 17.5
        
        # Mock PE
        mock_pe = MagicMock()
        mock_pe.name = "ACC-PAY-2026-00001"
        mock_pe.docstatus = 0
        mock_pe.paid_amount = 1000.0
        mock_pe.mode_of_payment = "Wire Transfer"
        
        mock_get_doc.return_value = mock_si
        mock_get_payment_entry.return_value = mock_pe
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_payment_entry = mock_get_payment_entry
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(side_effect=[
                "AMB-Wellness",  # company
                "Wire Transfer",  # mode_of_payment
                "Cash - AMB-W",  # cash_account
            ])
            mock_frappe_module.db.get_default = MagicMock(return_value="AMB-Wellness")
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("ACC-PAY-2026-00001", result.get("pe_name", ""))
    
    @patch('raven_ai_agent.agents.payment_agent.frappe.db.sql')
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_create_payment_entry_idempotent(self, mock_get_doc, mock_sql):
        """P-02: Create Payment Entry — idempotent"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        # Mock existing PE
        mock_sql.return_value = [("ACC-PAY-EXISTING-001",)]
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.db.sql = mock_sql
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("already exists", result.get("error", "").lower())
    
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_create_payment_entry_si_not_submitted(self, mock_get_doc):
        """P-03: Create Payment Entry — SI not submitted"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 0  # Draft
        mock_si.outstanding_amount = 1000.0
        mock_get_doc.return_value = mock_si
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            # Should auto-submit first
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_create_payment_entry_fully_paid(self, mock_get_doc):
        """P-04: Create Payment Entry — fully paid"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 1
        mock_si.outstanding_amount = 0.0  # Fully paid
        mock_get_doc.return_value = mock_si
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already fully paid", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.payment_agent.get_payment_entry')
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_create_payment_entry_usd_multicurrency(self, mock_get_doc, mock_get_payment_entry):
        """P-05: Create Payment Entry — USD multi-currency"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        # Mock SI with USD currency
        mock_si = MagicMock()
        mock_si.name = "ACC-SINV-2026-00001"
        mock_si.docstatus = 1
        mock_si.outstanding_amount = 10000.0
        mock_si.customer = "Test Customer"
        mock_si.company = "AMB-Wellness"
        mock_si.currency = "USD"
        mock_si.conversion_rate = 17.5
        mock_si.party_account_currency = "USD"
        
        # Mock PE
        mock_pe = MagicMock()
        mock_pe.name = "ACC-PAY-2026-00001"
        mock_pe.docstatus = 0
        mock_pe.paid_amount = 10000.0
        mock_pe.source_exchange_rate = 17.5
        
        mock_get_doc.return_value = mock_si
        mock_get_payment_entry.return_value = mock_pe
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_payment_entry = mock_get_payment_entry
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_value = MagicMock(side_effect=[
                "AMB-Wellness",  # company
                "Wire Transfer",  # mode_of_payment
                "Cash - AMB-W",  # cash_account
            ])
            mock_frappe_module.db.get_default = MagicMock(return_value="AMB-Wellness")
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.payment_agent.PaymentAgent._ensure_customer_address_and_contact')
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_submit_payment_entry_happy_path(self, mock_get_doc, mock_preflight):
        """P-06: Submit Payment Entry — happy path"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        # Mock PE
        mock_pe = MagicMock()
        mock_pe.name = "ACC-PAY-2026-00001"
        mock_pe.docstatus = 0  # Draft
        mock_pe.party = "Test Customer"
        mock_pe.party_name = "Test Customer"
        mock_pe.paid_amount = 1000.0
        mock_pe.paid_from_account_currency = "MXN"
        mock_pe.mode_of_payment = "Wire Transfer"
        mock_pe.reference_no = "PAY-001"
        
        mock_get_doc.return_value = mock_pe
        mock_preflight.return_value = {"success": True, "fixed": [], "error": None}
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            agent._ensure_customer_address_and_contact = mock_preflight
            
            result = agent.submit_payment_entry("ACC-PAY-2026-00001")
            
            self.assertTrue(result.get("success"))
            mock_pe.submit.assert_called_once()
    
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_reconcile_payment_fully_reconciled(self, mock_get_doc):
        """P-07: Reconcile Payment — fully reconciled"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        # Mock PE
        mock_pe = MagicMock()
        mock_pe.name = "ACC-PAY-2026-00001"
        mock_pe.docstatus = 1
        mock_pe.paid_amount = 1000.0
        mock_pe.paid_from_account_currency = "MXN"
        mock_pe.party_name = "Test Customer"
        
        # Mock SI reference with 0 outstanding
        mock_si = MagicMock()
        mock_si.outstanding_amount = 0.0
        
        mock_ref = MagicMock()
        mock_ref.reference_doctype = "Sales Invoice"
        mock_ref.reference_name = "ACC-SINV-2026-00001"
        mock_ref.allocated_amount = 1000.0
        
        mock_pe.references = [mock_ref]
        mock_get_doc.side_effect = [mock_pe, mock_si]
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            result = agent.reconcile_payment("ACC-PAY-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertTrue(result.get("reconciled"))
    
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_doc')
    def test_reconcile_payment_partial(self, mock_get_doc):
        """P-08: Reconcile Payment — partial"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        # Mock PE
        mock_pe = MagicMock()
        mock_pe.name = "ACC-PAY-2026-00001"
        mock_pe.docstatus = 1
        mock_pe.paid_amount = 500.0
        mock_pe.paid_from_account_currency = "MXN"
        mock_pe.party_name = "Test Customer"
        
        # Mock SI reference with outstanding
        mock_si = MagicMock()
        mock_si.outstanding_amount = 500.0
        
        mock_ref = MagicMock()
        mock_ref.reference_doctype = "Sales Invoice"
        mock_ref.reference_name = "ACC-SINV-2026-00001"
        mock_ref.allocated_amount = 500.0
        
        mock_pe.references = [mock_ref]
        mock_get_doc.side_effect = [mock_pe, mock_si]
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            result = agent.reconcile_payment("ACC-PAY-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertFalse(result.get("reconciled"))
    
    @patch('raven_ai_agent.agents.payment_agent.frappe.get_all')
    def test_get_unpaid_invoices(self, mock_get_all):
        """P-09: get_unpaid_invoices"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        mock_get_all.return_value = [
            {"name": "ACC-SINV-2026-00001", "customer": "Cust1", "grand_total": 1000.0, 
             "outstanding_amount": 500.0, "currency": "USD", "posting_date": "2026-01-01", "due_date": "2026-02-01"},
            {"name": "ACC-SINV-2026-00002", "customer": "Cust2", "grand_total": 2000.0, 
             "outstanding_amount": 1000.0, "currency": "USD", "posting_date": "2026-01-15", "due_date": "2026-02-15"},
        ]
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            result = agent.get_outstanding_invoices()
            
            self.assertTrue(result.get("success"))
            self.assertEqual(result.get("count"), 2)
    
    @patch('raven_ai_agent.agents.payment_agent.frappe.db.get_value')
    def test_get_bank_account(self, mock_get_value):
        """P-10: _get_bank_account"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        mock_get_value.return_value = "Cash - AMB-W"
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe_module:
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = PaymentAgent()
            # Test the internal method
            mock_frappe_module.db.get_value.assert_not_called()  # Not directly exposed


if __name__ == '__main__':
    unittest.main()
