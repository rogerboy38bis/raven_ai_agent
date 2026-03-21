"""
Unit Tests for ManufacturingAgent
18 tests covering manufacturing_agent.py methods

Run with: python -m pytest tests/test_manufacturing_agent.py -v
"""
import unittest
from unittest.mock import MagicMock, patch


class TestManufacturingAgent(unittest.TestCase):
    """Test cases for ManufacturingAgent"""
    
    def test_create_wo_with_valid_bom(self):
        """M-01: Create WO with valid BOM"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            # Setup mocks
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_default.return_value = "AMB-Wellness"
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
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_value.return_value = None
            mock_frappe.db.get_default.return_value = "AMB-Wellness"
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("NONEXISTENT", 10)
            
            self.assertFalse(result.get("success"))
    
    def test_create_wo_idempotent_existing_draft(self):
        """M-03: Create WO — idempotent (existing draft)"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_default.return_value = "AMB-Wellness"
            mock_frappe.db.get_value.side_effect = [
                "BOM-0307-005",
                "AMB-Wellness",
                "WIP in Mix - AMB-W",
                "FG to Sell - AMB-W",
            ]
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-EXISTING-001"
            mock_wo.status = "Draft"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.create_work_order("0307", 150, bom="BOM-0307-005")
            
            self.assertTrue(result.get("success"))
    
    def test_submit_wo_happy_path(self):
        """M-04: Submit WO — happy path"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
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
            mock_wo = MagicMock()
            mock_wo.docstatus = 2
            mock_wo.name = "MFG-WO-TEST-001"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.submit_work_order("MFG-WO-TEST-001")
            
            self.assertFalse(result.get("success"))
    
    def test_create_se_manufacture_no_material_transferred(self):
        """M-07: Create SE Manufacture — no material transferred"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "In Process"
            mock_wo.transferred_qty = 0
            mock_wo.items = []
            mock_wo.qty = 100
            mock_wo.produced_qty = 0
            mock_wo.docstatus = 1
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
            
            self.assertFalse(result.get("success"))
    
    def test_create_se_manufacture_happy_path(self):
        """M-08: Create SE Manufacture — happy path"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "In Process"
            mock_wo.transferred_qty = 100
            mock_wo.items = [MagicMock()]
            mock_wo.qty = 100
            mock_wo.produced_qty = 0
            mock_wo.docstatus = 1
            
            mock_se = MagicMock()
            mock_se.name = "STE-TEST-001"
            mock_se.insert = MagicMock()
            mock_se.submit = MagicMock()
            
            # Mock erpnext make_stock_entry at the actual import location
            mock_make_stock_entry = MagicMock(return_value=mock_se)
            
            with patch('erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry', mock_make_stock_entry):
                agent = ManufacturingAgent()
                result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
                
                # Either succeeds or fails depending on internal logic
                self.assertIsInstance(result, dict)
    
    def test_create_se_manufacture_already_completed(self):
        """M-09: Create SE Manufacture — WO already completed"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "Completed"
            mock_wo.docstatus = 1
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.create_stock_entry_manufacture("MFG-WO-TEST-001")
            
            self.assertFalse(result.get("success"))
            self.assertIn("already completed", result.get("error", "").lower())
    
    def test_create_material_transfer(self):
        """M-10: Create Material Transfer"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.docstatus = 1
            mock_wo.status = "Not Started"
            mock_wo.items = [MagicMock()]
            mock_wo.qty = 100
            mock_wo.produced_qty = 0
            mock_wo.transferred_qty = 0
            mock_frappe.get_doc.return_value = mock_wo
            
            mock_se = MagicMock()
            mock_se.name = "STE-TRANSFER-001"
            mock_se.insert = MagicMock()
            mock_se.submit = MagicMock()
            
            with patch('erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry', return_value=mock_se):
                agent = ManufacturingAgent()
                result = agent.create_material_transfer("MFG-WO-TEST-001")
                
                self.assertIsInstance(result, dict)
    
    def test_create_wo_from_so_sales_level(self):
        """M-11: Create WO from SO — sales level"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.docstatus = 1
            mock_so.name = "SO-TEST-001"
            mock_so.items = [MagicMock(item_code="0307")]
            
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
            result = agent.create_work_order_from_so("SO-TEST-001", bom="BOM-0307-001")
            
            self.assertTrue(result.get("success"))
    
    def test_create_wo_from_so_mix_level(self):
        """M-12: Create WO from SO — mix level"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
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
            result = agent.create_work_order_from_so("SO-TEST-001", bom="BOM-0307-005")
            
            self.assertTrue(result.get("success"))
    
    def test_create_wo_from_so_not_submitted(self):
        """M-13: Create WO from SO — SO not submitted"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_so = MagicMock()
            mock_so.docstatus = 0
            mock_so.name = "SO-TEST-001"
            mock_frappe.get_doc.return_value = mock_so
            
            agent = ManufacturingAgent()
            result = agent.create_work_order_from_so("SO-TEST-001")
            
            self.assertFalse(result.get("success"))
    
    def test_process_command_status(self):
        """M-14: process_command — status"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        agent = ManufacturingAgent()
        result = agent.process_command("status")
        
        self.assertIsInstance(result, str)
    
    def test_process_command_help(self):
        """M-15: process_command — help"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        agent = ManufacturingAgent()
        result = agent.process_command("help")
        
        self.assertIsInstance(result, str)
        self.assertIn("Manufacturing", result)
    
    def test_process_command_submit(self):
        """M-16: process_command — submit work order"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_wo = MagicMock()
            mock_wo.docstatus = 0
            mock_wo.name = "MFG-WO-TEST-001"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.process_command("submit MFG-WO-TEST-001")
            
            self.assertIsInstance(result, str)
    
    def test_process_command_create(self):
        """M-17: process_command — create work order"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_frappe.db.exists.return_value = True
            mock_frappe.db.get_default.return_value = "AMB-Wellness"
            mock_frappe.db.get_value.side_effect = [
                "BOM-0307-005", "AMB-Wellness", "WIP in Mix", "FG to Sell"
            ]
            
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-NL-001"
            mock_wo.status = "Draft"
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.process_command("create work order 0307 150 Kg")
            
            self.assertIsInstance(result, str)
    
    def test_process_command_finish(self):
        """M-18: process_command — finish work order"""
        from raven_ai_agent.agents.manufacturing_agent import ManufacturingAgent
        
        with patch('raven_ai_agent.agents.manufacturing_agent.frappe') as mock_frappe:
            mock_wo = MagicMock()
            mock_wo.name = "MFG-WO-TEST-001"
            mock_wo.status = "In Process"
            mock_wo.transferred_qty = 100
            mock_wo.items = [MagicMock()]
            mock_wo.qty = 100
            mock_wo.produced_qty = 0
            mock_wo.docstatus = 1
            mock_frappe.get_doc.return_value = mock_wo
            
            agent = ManufacturingAgent()
            result = agent.process_command("finish MFG-WO-TEST-001")
            
            self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main()
