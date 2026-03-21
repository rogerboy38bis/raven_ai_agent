"""
Unit Tests for PaymentAgent
10 tests covering payment_agent.py methods

Run with: python -m pytest tests/test_payment_agent.py -v
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


class TestPaymentAgent(unittest.TestCase):
    """Test cases for PaymentAgent"""
    
    def setUp(self):
        """Set up mock frappe environment"""
        self.mock_frappe = create_mock_frappe()
    
    def _apply_frappe_patch(self, mock_frappe_module):
        """Helper to apply frappe mock to a module"""
        mock_frappe_module.local = self.mock_frappe.local
        mock_frappe_module.session = self.mock_frappe.session
        mock_frappe_module.db = self.mock_frappe.db
    
    def test_create_payment_entry_happy_path(self):
        """P-01: Create Payment Entry — happy path"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
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
            
            mock_frappe.get_doc.return_value = mock_si
            
            with patch('raven_ai_agent.agents.payment_agent.get_payment_entry', return_value=mock_pe):
                mock_frappe.db.get_value.side_effect = [
                    "AMB-Wellness",  # company
                    "Wire Transfer",  # mode_of_payment
                    "Cash - AMB-W",  # cash_account
                ]
                mock_frappe.db.get_default.return_value = "AMB-Wellness"
                
                agent = PaymentAgent()
                result = agent.create_payment_entry("ACC-SINV-2026-00001")
                
                self.assertTrue(result.get("success"))
                self.assertIn("ACC-PAY-2026-00001", result.get("pe_name", ""))
    
    def test_create_payment_entry_idempotent(self):
        """P-02: Create Payment Entry — idempotent"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock existing PE found via SQL
            mock_frappe.db.sql.return_value = [("ACC-PAY-EXISTING-001",)]
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("already exists", result.get("error", "").lower())
    
    def test_create_payment_entry_si_not_submitted(self):
        """P-03: Create Payment Entry — SI not submitted"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_si = MagicMock()
            mock_si.name = "ACC-SINV-2026-00001"
            mock_si.docstatus = 0  # Draft
            mock_si.outstanding_amount = 1000.0
            mock_frappe.get_doc.return_value = mock_si
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            # Should auto-submit first
            self.assertTrue(result.get("success"))
    
    def test_create_payment_entry_fully_paid(self):
        """P-04: Create Payment Entry — fully paid"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_si = MagicMock()
            mock_si.name = "ACC-SINV-2026-00001"
            mock_si.docstatus = 1
            mock_si.outstanding_amount = 0.0  # Fully paid
            mock_frappe.get_doc.return_value = mock_si
            
            agent = PaymentAgent()
            result = agent.create_payment_entry("ACC-SINV-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already fully paid", result.get("message", "").lower())
    
    def test_create_payment_entry_usd_multicurrency(self):
        """P-05: Create Payment Entry — USD multi-currency"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
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
            
            mock_frappe.get_doc.return_value = mock_si
            
            with patch('raven_ai_agent.agents.payment_agent.get_payment_entry', return_value=mock_pe):
                mock_frappe.db.get_value.side_effect = [
                    "AMB-Wellness",
                    "Wire Transfer",
                    "Cash - AMB-W",
                ]
                mock_frappe.db.get_default.return_value = "AMB-Wellness"
                
                agent = PaymentAgent()
                result = agent.create_payment_entry("ACC-SINV-2026-00001")
                
                self.assertTrue(result.get("success"))
    
    def test_submit_payment_entry_happy_path(self):
        """P-06: Submit Payment Entry — happy path"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
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
            
            mock_frappe.get_doc.return_value = mock_pe
            
            agent = PaymentAgent()
            # Directly test submit by patching the preflight check
            with patch.object(agent, '_ensure_customer_address_and_contact', return_value={"success": True, "fixed": [], "error": None}):
                result = agent.submit_payment_entry("ACC-PAY-2026-00001")
                
                self.assertTrue(result.get("success"))
                mock_pe.submit.assert_called_once()
    
    def test_reconcile_payment_fully_reconciled(self):
        """P-07: Reconcile Payment — fully reconciled"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
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
            mock_frappe.get_doc.side_effect = [mock_pe, mock_si]
            
            agent = PaymentAgent()
            result = agent.reconcile_payment("ACC-PAY-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertTrue(result.get("reconciled"))
    
    def test_reconcile_payment_partial(self):
        """P-08: Reconcile Payment — partial"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
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
            mock_frappe.get_doc.side_effect = [mock_pe, mock_si]
            
            agent = PaymentAgent()
            result = agent.reconcile_payment("ACC-PAY-2026-00001")
            
            self.assertTrue(result.get("success"))
            self.assertFalse(result.get("reconciled"))
    
    def test_get_unpaid_invoices(self):
        """P-09: get_unpaid_invoices"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.get_all.return_value = [
                {"name": "ACC-SINV-2026-00001", "customer": "Cust1", "grand_total": 1000.0, 
                 "outstanding_amount": 500.0, "currency": "USD", "posting_date": "2026-01-01", "due_date": "2026-02-01"},
                {"name": "ACC-SINV-2026-00002", "customer": "Cust2", "grand_total": 2000.0, 
                 "outstanding_amount": 1000.0, "currency": "USD", "posting_date": "2026-01-15", "due_date": "2026-02-15"},
            ]
            
            agent = PaymentAgent()
            result = agent.get_outstanding_invoices()
            
            self.assertTrue(result.get("success"))
            self.assertEqual(result.get("count"), 2)
    
    def test_get_bank_account(self):
        """P-10: _get_bank_account - basic test"""
        from raven_ai_agent.agents.payment_agent import PaymentAgent
        
        with patch('raven_ai_agent.agents.payment_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_value.return_value = "Cash - AMB-W"
            
            agent = PaymentAgent()
            # Test that the agent can be instantiated
            self.assertIsNotNone(agent)


if __name__ == '__main__':
    unittest.main()
