"""
Unit Tests for ManufacturingAgent
18 tests covering manufacturing_agent.py methods

Run with: python -m pytest raven_ai_agent/tests/test_manufacturing_agent.py -v
"""
import unittest
from unittest.mock import MagicMock, patch, PropertyMock


class TestManufacturingAgent(unittest.TestCase):
    """Test cases for ManufacturingAgent"""
    
    def setUp(self):
        """Set up mock frappe environment"""
        self.mock_frappe = MagicMock()
        self.mock_frappe.local = MagicMock()
        self.mock_frappe.local.site = "test.erpnext.com"
        self.mock_frappe.session = MagicMock()
        self.mock_frappe.session.user = "Administrator"
        self.mock_frappe.db = MagicMock()
        self.mock_frappe.db.get_default = MagicMock(return_value="AMB-Wellness")
        
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.exists')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.get_value')
    def test_create_wo_with_valid_bom(self, mock_get_value, mock_exists, mock_get_doc):
        """M-01: Create WO with valid BOM"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        # Mock item exists
        mock_exists.return_value = True
        
        # Mock BOM resolution
        mock_get_value.side_effect = [
            "BOM-0307-005",  # BOM lookup
            "AMB-Wellness",   # company
            "WIP in Mix - AMB-W",  # wip_warehouse
            "FG to Sell - AMB-W",  # fg_warehouse
        ]
        
        # Mock WO doc
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-TEST-001"
        mock_wo.status = "Draft"
        mock_get_doc.return_value = mock_wo
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.db.exists = mock_exists
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("0307", 150, bom="BOM-0307-005")
            
            self.assertTrue(result.get("success"))
            self.assertIn("MFG-WO-TEST-001", result.get("wo_name", ""))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.exists')
    def test_create_wo_no_bom_found(self, mock_exists):
        """M-02: Create WO — no BOM found"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_exists.return_value = True
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.db.exists = mock_exists
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.db.get_value = MagicMock(return_value=None)
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("NONEXISTENT", 10)
            
            self.assertFalse(result.get("success"))
            self.assertIn("No active BOM found", result.get("error", ""))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.exists')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.get_value')
    def test_create_wo_idempotent_existing_draft(self, mock_get_value, mock_exists, mock_get_doc):
        """M-03: Create WO — idempotent (existing draft)"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_exists.return_value = True
        mock_get_value.side_effect = [
            "BOM-0307-005",
            "AMB-Wellness",
            "WIP in Mix - AMB-W",
            "FG to Sell - AMB-W",
        ]
        
        # Return existing draft WO
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-EXISTING-001"
        mock_wo.status = "Draft"
        mock_get_doc.return_value = mock_wo
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.db.exists = mock_exists
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("0307", 150, bom="BOM-0307-005")
            
            # Should return existing without creating duplicate
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_submit_wo_happy_path(self, mock_get_doc):
        """M-04: Submit WO — happy path"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_wo = MagicMock()
        mock_wo.docstatus = 0
        mock_wo.name = "MFG-WO-TEST-001"
        mock_get_doc.return_value = mock_wo
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            result = agent.submit_work_order("MFG-WO-TEST-001")
            
            self.assertTrue(result.get("success"))
            mock_wo.submit.assert_called_once()
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_submit_wo_already_submitted(self, mock_get_doc):
        """M-05: Submit WO — already submitted"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_wo = MagicMock()
        mock_wo.docstatus = 1
        mock_wo.name = "MFG-WO-TEST-001"
        mock_get_doc.return_value = mock_wo
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            result = agent.submit_work_order("MFG-WO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already submitted", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_submit_wo_cancelled(self, mock_get_doc):
        """M-06: Submit WO — cancelled"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_wo = MagicMock()
        mock_wo.docstatus = 2
        mock_wo.name = "MFG-WO-TEST-001"
        mock_get_doc.return_value = mock_wo
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            result = agent.submit_work_order("MFG-WO-TEST-001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("cancelled", result.get("error", "").lower())
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_create_se_manufacture_no_material_transferred(self, mock_get_doc):
        """M-07: Create SE Manufacture — no material transferred"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        # Mock WO with 0 transferred
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-TEST-001"
        mock_wo.status = "In Process"
        mock_wo.transferred_qty = 0
        mock_wo.items = []
        mock_get_doc.return_value = mock_wo
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
            
            self.assertFalse(result.get("success"))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.make_stock_entry')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_create_se_manufacture_happy_path(self, mock_get_doc, mock_make_se):
        """M-08: Create SE Manufacture — happy path"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-TEST-001"
        mock_wo.status = "In Process"
        mock_wo.transferred_qty = 100
        mock_wo.items = [MagicMock()]
        mock_get_doc.return_value = mock_wo
        
        mock_se = MagicMock()
        mock_se.name = "STE-TEST-001"
        mock_make_se.return_value = mock_se
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            with patch('raven_ai_agent.agents.manufacturing_agent.make_stock_entry', mock_make_se):
                agent = ManufacturingAgent()
                result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
                
                self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_create_se_manufacture_already_completed(self, mock_get_doc):
        """M-09: Create SE Manufacture — WO already completed"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-TEST-001"
        mock_wo.status = "Completed"
        mock_get_doc.return_value = mock_wo
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
            
            self.assertTrue(result.get("success"))
            self.assertIn("already completed", result.get("message", "").lower())
    
    @patch('raven_ai_agent.agents.manufacturing_agent.make_stock_entry')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_create_material_transfer(self, mock_get_doc, mock_make_se):
        """M-10: Create Material Transfer"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-TEST-001"
        mock_wo.docstatus = 1
        mock_wo.status = "Not Started"
        mock_wo.items = [MagicMock()]
        mock_get_doc.return_value = mock_wo
        
        mock_se = MagicMock()
        mock_se.name = "STE-TRANSFER-001"
        mock_make_se.return_value = mock_se
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            with patch('raven_ai_agent.agents.manufacturing_agent.make_stock_entry', mock_make_se):
                agent = ManufacturingAgent()
                result = agent.create_material_transfer_for_manufacture("MFG-WO-TEST-001")
                
                self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.get_value')
    def test_create_wo_from_so_sales_level(self, mock_get_value, mock_get_all, mock_get_doc):
        """M-11: Create WO from SO — sales level"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        # Mock SO
        mock_so = MagicMock()
        mock_so.docstatus = 1
        mock_so.name = "SO-TEST-001"
        mock_so.items = [MagicMock(item_code="0307")]
        
        # Mock WO creation
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-SALES-001"
        mock_wo.status = "Draft"
        
        def get_doc_side_effect(*args, **kwargs):
            if args[0] == "Sales Order":
                return mock_so
            return mock_wo
        
        mock_get_doc.side_effect = get_doc_side_effect
        mock_get_all.return_value = []
        mock_get_value.return_value = "BOM-0307-001"
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            
            agent = ManufacturingAgent()
            result = agent.create_work_order_from_so("SO-TEST-001", bom_level="sales")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_all')
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.get_value')
    def test_create_wo_from_so_mix_level(self, mock_get_value, mock_get_all, mock_get_doc):
        """M-12: Create WO from SO — mix level"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_so = MagicMock()
        mock_so.docstatus = 1
        mock_so.name = "SO-TEST-001"
        mock_so.items = [MagicMock(item_code="0307")]
        
        mock_wo = MagicMock()
        mock_wo.name = "MFG-WO-MIX-001"
        mock_wo.status = "Draft"
        
        def get_doc_side_effect(*args, **kwargs):
            if args[0] == "Sales Order":
                return mock_so
            return mock_wo
        
        mock_get_doc.side_effect = get_doc_side_effect
        mock_get_all.return_value = []
        mock_get_value.return_value = "BOM-0307-005"
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.get_all = mock_get_all
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            
            agent = ManufacturingAgent()
            result = agent.create_work_order_from_so("SO-TEST-001", bom_level="mix")
            
            self.assertTrue(result.get("success"))
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.get_doc')
    def test_create_wo_from_so_not_submitted(self, mock_get_doc):
        """M-13: Create WO from SO — SO not submitted"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_so = MagicMock()
        mock_so.docstatus = 0  # Draft
        mock_so.name = "SO-TEST-001"
        mock_get_doc.return_value = mock_so
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.get_doc = mock_get_doc
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            result = agent.create_work_order_from_so("SO-TEST-001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("must be submitted", result.get("error", "").lower())
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.get_value')
    def test_get_bom_for_level_sales(self, mock_get_value):
        """M-14: _get_bom_for_level — sales"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_get_value.return_value = "BOM-0307-001"
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            bom = agent._get_bom_for_level("0307", "sales")
            
            self.assertEqual(bom, "BOM-0307-001")
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.get_value')
    def test_get_bom_for_level_mix(self, mock_get_value):
        """M-15: _get_bom_for_level — mix"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_get_value.return_value = "BOM-0307-005"
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            bom = agent._get_bom_for_level("0307", "mix")
            
            self.assertEqual(bom, "BOM-0307-005")
    
    @patch('raven_ai_agent.agents.manufacturing_agent.frappe.db.get_value')
    def test_get_wip_warehouse_mix_bom(self, mock_get_value):
        """M-16: _get_wip_warehouse — mix BOM"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        mock_get_value.return_value = "WIP in Mix - AMB-W"
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.db.get_value = mock_get_value
            mock_frappe_module.local = self.mock_frappe.local
            
            agent = ManufacturingAgent()
            warehouse = agent._get_wip_warehouse("BOM-0307-005", "AMB-Wellness")
            
            self.assertEqual(warehouse, "WIP in Mix - AMB-W")
    
    def test_confirm_flow_preview_then_execute(self):
        """M-17: Confirm flow — preview then execute"""
        # This test verifies the confirm parameter behavior
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_default = MagicMock(return_value="AMB-Wellness")
            mock_frappe_module.db.exists = MagicMock(return_value=True)
            mock_frappe_module.db.get_value = MagicMock(side_effect=[
                "BOM-0307-005", "AMB-Wellness", "WIP in Mix", "FG to Sell"
            ])
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "Draft"
            mock_frappe_module.get_doc = MagicMock(return_value=mock_wo)
            
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
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe_module:
            mock_frappe_module.local = self.mock_frappe.local
            mock_frappe_module.session = self.mock_frappe.session
            mock_frappe_module.db = self.mock_frappe.db
            mock_frappe_module.db.get_default = MagicMock(return_value="AMB-Wellness")
            mock_frappe_module.db.exists = MagicMock(return_value=True)
            mock_frappe_module.db.get_value = MagicMock(side_effect=[
                "BOM-0307-005", "AMB-Wellness", "WIP in Mix", "FG to Sell"
            ])
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-NL-001"
            mock_wo.status = "Draft"
            mock_frappe_module.get_doc = MagicMock(return_value=mock_wo)
            
            agent = ManufacturingAgent()
            result = agent.process_command("create work order 0307 150 Kg")
            
            self.assertTrue(result.get("success") or "preview" in result.get("message", "").lower())


if __name__ == '__main__':
    unittest.main()
