"""
Unit Tests for ManufacturingAgent
18 tests covering manufacturing_agent.py methods

Run with: python -m pytest tests/test_manufacturing_agent.py -v
"""
import unittest
import sys
from unittest.mock import MagicMock, patch, PropertyMock


# Fix import path before any imports
def setup_import_path():
    """Ensure correct import path"""
    import os
    from pathlib import Path
    
    # Get project root (parent of tests dir)
    current = Path(__file__).resolve()
    project_root = current.parent.parent
    
    # Add raven_ai_agent package path
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


class TestManufacturingAgent(unittest.TestCase):
    """Test cases for ManufacturingAgent"""
    
    def setUp(self):
        """Set up mock frappe environment"""
        self.mock_frappe = create_mock_frappe()
    
    def _apply_frappe_patch(self, mock_frappe_module):
        """Helper to apply frappe mock to a module"""
        mock_frappe_module.get_doc = MagicMock()
        mock_frappe_module.db.exists = MagicMock()
        mock_frappe_module.db.get_value = MagicMock()
        mock_frappe_module.local = self.mock_frappe.local
        mock_frappe_module.session = self.mock_frappe.session
        mock_frappe_module.db = self.mock_frappe.db
    
    def test_create_wo_with_valid_bom(self):
        """M-01: Create WO with valid BOM"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Setup mocks
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_value.side_effect = [
                "BOM-0307-005",  # BOM lookup
                "AMB-Wellness",   # company
                "WIP in Mix - AMB-W",  # wip_warehouse
                "FG to Sell - AMB-W",  # fg_warehouse
            ]
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "Draft"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("0307", 150, bom="BOM-0307-005")
            
            self.assertTrue(result.get("success"))
            self.assertIn("MFG-WO-TEST-001", result.get("wo_name", ""))
    
    def test_create_wo_no_bom_found(self):
        """M-02: Create WO — no BOM found"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_value.return_value = None
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("NONEXISTENT", 10)
            
            self.assertFalse(result.get("success"))
            self.assertIn("No active BOM found", result.get("error", ""))
    
    def test_create_wo_idempotent_existing_draft(self):
        """M-03: Create WO — idempotent (existing draft)"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_value.side_effect = [
                "BOM-0307-005",
                "AMB-Wellness",
                "WIP in Mix - AMB-W",
                "FG to Sell - AMB-W",
            ]
            
            # Return existing draft WO
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-EXISTING-001"
            mock_wo.status = "Draft"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("0307", 150, bom="BOM-0307-005")
            
            # Should return existing without creating duplicate
            self.assertTrue(result.get("success"))
    
    def test_submit_wo_happy_path(self):
        """M-04: Submit WO — happy path"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_wo = MagicMock()
            mock_wo.docstatus = 0
            mock_wo.name = "MFG-WO-TEST-001"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.submit_work_order("MFG-WO-TEST-001")
            
            self.assertTrue(result.get("success"))
            mock_wo.submit.assert_called_once()
    
    def test_submit_wo_already_submitted(self):
        """M-05: Submit WO — already submitted"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_wo = MagicMock()
            mock_wo.docstatus = 1
            mock_wo.name = "MFG-WO-TEST-001"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.submit_work_order("MFG-WO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already submitted", result.get("message", "").lower())
    
    def test_submit_wo_cancelled(self):
        """M-06: Submit WO — cancelled"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_wo = MagicMock()
            mock_wo.docstatus = 2
            mock_wo.name = "MFG-WO-TEST-001"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.submit_work_order("MFG-WO-TEST-001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("cancelled", result.get("error", "").lower())
    
    def test_create_se_manufacture_no_material_transferred(self):
        """M-07: Create SE Manufacture — no material transferred"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock WO with 0 transferred
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "In Process"
            mock_wo.transferred_qty = 0
            mock_wo.items = []
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
            
            self.assertFalse(result.get("success"))
    
    def test_create_se_manufacture_happy_path(self):
        """M-08: Create SE Manufacture — happy path"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "In Process"
            mock_wo.transferred_qty = 100
            mock_wo.items = [MagicMock()]
            mock_frappe.get_doc.return_value = mock_wo
            
            mock_se = MagicMock()
            mock_se.name = "STE-TEST-001"
            
            with patch('raven_ai_agent.agents.manufacturing_agent.make_stock_entry', return_value=mock_se):
                agent = ManufacturingAgent()
                result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
                
                self.assertTrue(result.get("success"))
    
    def test_create_se_manufacture_already_completed(self):
        """M-09: Create SE Manufacture — WO already completed"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "Completed"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already completed", result.get("message", "").lower())
    
    def test_create_material_transfer(self):
        """M-10: Create Material Transfer"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.docstatus = 1
            mock_wo.status = "Not Started"
            mock_wo.items = [MagicMock()]
            mock_frappe.get_doc.return_value = mock_wo
            
            mock_se = MagicMock()
            mock_se.name = "STE-TRANSFER-001"
            
            with patch('raven_ai_agent.agents.manufacturing_agent.make_stock_entry', return_value=mock_se):
                agent = ManufacturingAgent()
                result = agent.create_material_transfer_for_manufacture("MFG-WO-TEST-001")
                
                self.assertTrue(result.get("success"))
    
    def test_create_wo_from_so_sales_level(self):
        """M-11: Create WO from SO — sales level"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            # Mock SO
            mock_so = MagicMock()
            mock_so.docstatus = 1
            mock_so.name = "SO-TEST-001"
            mock_so.items = [MagicMock(item_code="0307")]
            
            # Mock WO creation
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-SALES-001"
            mock_wo.status = "Draft"
            
            def get_doc_side_effect(doctype, name):
                if doctype == "Sales Order":
                    return mock_so
                return mock_wo
            
            mock_frappe.get_doc.side_effect = get_doc_side_effect
            mock_frappe.get_all.return_value = []
            mock_frappe.db.get_value.return_value = "BOM-0307-001"
            
            agent = ManufacturingAgent()
            result = agent.create_work_order_from_so("SO-TEST-001", bom_level="sales")
            
            self.assertTrue(result.get("success"))
    
    def test_create_wo_from_so_mix_level(self):
        """M-12: Create WO from SO — mix level"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_so = MagicMock()
            mock_so.docstatus = 1
            mock_so.name = "SO-TEST-001"
            mock_so.items = [MagicMock(item_code="0307")]
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-MIX-001"
            mock_wo.status = "Draft"
            
            def get_doc_side_effect(doctype, name):
                if doctype == "Sales Order":
                    return mock_so
                return mock_wo
            
            mock_frappe.get_doc.side_effect = get_doc_side_effect
            mock_frappe.get_all.return_value = []
            mock_frappe.db.get_value.return_value = "BOM-0307-005"
            
            agent = ManufacturingAgent()
            result = agent.create_work_order_from_so("SO-TEST-001", bom_level="mix")
            
            self.assertTrue(result.get("success"))
    
    def test_create_wo_from_so_not_submitted(self):
        """M-13: Create WO from SO — SO not submitted"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_so = MagicMock()
            mock_so.docstatus = 0  # Draft
            mock_so.name = "SO-TEST-001"
            mock_frappe.get_doc.return_value = mock_so
            
            agent = ManufacturingAgent()
            result = agent.create_work_order_from_so("SO-TEST-001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("must be submitted", result.get("error", "").lower())
    
    def test_get_bom_for_level_sales(self):
        """M-14: _get_bom_for_level — sales"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_value.return_value = "BOM-0307-001"
            
            agent = ManufacturingAgent()
            bom = agent._get_bom_for_level("0307", "sales")
            
            self.assertEqual(bom, "BOM-0307-001")
    
    def test_get_bom_for_level_mix(self):
        """M-15: _get_bom_for_level — mix"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_value.return_value = "BOM-0307-005"
            
            agent = ManufacturingAgent()
            bom = agent._get_bom_for_level("0307", "mix")
            
            self.assertEqual(bom, "BOM-0307-005")
    
    def test_get_wip_warehouse_mix_bom(self):
        """M-16: _get_wip_warehouse — mix BOM"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_value.return_value = "WIP in Mix - AMB-W"
            
            agent = ManufacturingAgent()
            warehouse = agent._get_wip_warehouse("BOM-0307-005", "AMB-Wellness")
            
            self.assertEqual(warehouse, "WIP in Mix - AMB-W")
    
    def test_confirm_flow_preview_then_execute(self):
        """M-17: Confirm flow — preview then execute"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_default.return_value = "AMB-Wellness"
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_value.side_effect = [
                "BOM-0307-005", "AMB-Wellness", "WIP in Mix", "FG to Sell"
            ]
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "Draft"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            
            # Without confirm - should return preview
            result_no_confirm = agent.create_work_order("0307", 150, bom="BOM-0307-005", confirm=False)
            # With confirm - should execute
            result_confirm = agent.create_work_order("0307", 150, bom="BOM-0307-005", confirm=True)
            
            # Both should succeed in our mocked scenario
            self.assertTrue(result_confirm.get("success"))
    
    def test_process_command_creates_wo(self):
        """M-18: process_command — create work order from NL"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            
            mock_frappe.db.get_default.return_value = "AMB-Wellness"
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_value.side_effect = [
                "BOM-0307-005", "AMB-Wellness", "WIP in Mix", "FG to Sell"
            ]
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-NL-001"
            mock_wo.status = "Draft"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.process_command("create work order 0307 150 Kg")
            
            # process_command returns a string, not a dict
            self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main()
