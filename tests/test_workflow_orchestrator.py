"""
Unit Tests for WorkflowOrchestrator Agent
Tests the master orchestrator that chains all 8 steps of the verified workflow.

Run with: python -m pytest tests/test_workflow_orchestrator.py -v
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


class TestWorkflowOrchestrator(unittest.TestCase):
    """Test cases for WorkflowOrchestrator class"""

    def setUp(self):
        """Set up mock frappe environment before each test"""
        self.mock_frappe = create_mock_frappe()

    def _apply_frappe_patch(self, mock_frappe_module):
        """Helper to apply frappe mock to a module"""
        mock_frappe_module.local = self.mock_frappe.local
        mock_frappe_module.session = self.mock_frappe.session
        mock_frappe_module.db = self.mock_frappe.db

    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_1_create_mfg_wo')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_2_manufacture')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_3_submit_so')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_4_create_sales_wo')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_5_manufacture_sales')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_6_delivery_note')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_7_sales_invoice')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_8_payment_entry')
    def test_run_full_cycle_success(self, mock_pe, mock_si, mock_dn, mock_sales_mfg,
                                     mock_sales_wo, mock_submit_so, mock_mfg, mock_mfg_wo):
        """Test successful full cycle execution through all 8 steps"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        # Mock step results
        mock_mfg_wo.return_value = {"step": 1, "success": True, "wo_name": "WO-001"}
        mock_mfg.return_value = {"step": 2, "success": True, "se_name": "SE-001"}
        mock_submit_so.return_value = {"step": 3, "success": True}
        mock_sales_wo.return_value = {"step": 4, "success": True, "wo_name": "WO-002"}
        mock_sales_mfg.return_value = {"step": 5, "success": True, "se_name": "SE-002"}
        mock_dn.return_value = {"step": 6, "success": True, "dn_name": "DN-001"}
        mock_si.return_value = {"step": 7, "success": True, "si_name": "SI-001"}
        mock_pe.return_value = {"step": 8, "success": True, "pe_name": "PE-001"}

        # Mock Sales Order document
        mock_so = MagicMock()
        mock_so.name = "SO-001"
        mock_so.items = [MagicMock(item_code="ITEM-001", qty=100, warehouse="WH-001")]
        mock_so.project = None

        with patch('raven_ai_agent.agents.workflow_orchestrator.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.db.get_value.side_effect = ["BOM-001", "BOM-002"]

            orchestrator = WorkflowOrchestrator()
            result = orchestrator.run_full_cycle("SO-001", "BOM-MFG", "BOM-SALES")

            # Assertions
            self.assertTrue(result["success"])
            self.assertEqual(len(result["results"]), 8)
            self.assertIsNotNone(result["state"]["so_name"])

    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_1_create_mfg_wo')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_2_manufacture')
    @patch('raven_ai_agent.agents.workflow_orchestrator.WorkflowOrchestrator._step_3_submit_so')
    def test_run_full_cycle_skip_steps(self, mock_submit_so, mock_mfg, mock_mfg_wo):
        """Test execution with skipped steps"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        mock_mfg_wo.return_value = {"step": 1, "success": True, "wo_name": "WO-001"}

        # Mock Sales Order
        mock_so = MagicMock()
        mock_so.name = "SO-001"
        mock_so.items = [MagicMock(item_code="ITEM-001", qty=100, warehouse="WH-001")]
        mock_so.project = None

        with patch('raven_ai_agent.agents.workflow_orchestrator.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.db.get_value.side_effect = ["BOM-001", "BOM-002"]

            orchestrator = WorkflowOrchestrator()

            # Skip steps 1 and 2 (manufacturing already done)
            result = orchestrator.run_full_cycle("SO-001", skip_steps=[1, 2])

            self.assertTrue(result["success"])
            # Verify steps 1 and 2 are marked as skipped
            self.assertTrue(result["results"][0]["skipped"])
            self.assertTrue(result["results"][1]["skipped"])
            # Step 3 should execute
            mock_submit_so.assert_called_once()

    def test_run_full_cycle_so_not_found(self):
        """Test handling when Sales Order does not exist"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        with patch('raven_ai_agent.agents.workflow_orchestrator.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            mock_frappe.get_doc.side_effect = Exception("DoesNotExistError")

            orchestrator = WorkflowOrchestrator()
            result = orchestrator.run_full_cycle("SO-001")

            self.assertFalse(result["success"])
            self.assertIn("not found", result["error"])

    def test_get_pipeline_status(self):
        """Test pipeline status retrieval for a Sales Order"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        # Mock Sales Order
        mock_so = MagicMock()
        mock_so.name = "SO-001"
        mock_so.customer = "Test Customer"
        mock_so.items = [MagicMock(item_code="ITEM-001", qty=100)]
        mock_so.docstatus = 1
        mock_so.status = "To Deliver"

        with patch('raven_ai_agent.agents.workflow_orchestrator.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            mock_frappe.get_doc.return_value = mock_so
            mock_frappe.get_all.return_value = []

            orchestrator = WorkflowOrchestrator()
            result = orchestrator.get_pipeline_status("SO-001")

            self.assertTrue(result["success"])
            self.assertIn("dashboard", result)
            self.assertEqual(result["progress"], 0)

    def test_create_so_from_quotation_success(self):
        """Test successful creation of Sales Order from Quotation"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        # Mock Quotation
        mock_qt = MagicMock()
        mock_qt.name = "QTN-001"
        mock_qt.docstatus = 1
        mock_qt.status = "Open"
        mock_qt.customer = "Test Customer"
        mock_qt.grand_total = 1000.0
        mock_qt.currency = "USD"

        # Mock make_sales_order
        mock_so = MagicMock()
        mock_so.name = "SO-001"
        mock_so.customer = "Test Customer"
        mock_so.grand_total = 1000.0
        mock_so.currency = "USD"
        mock_so.transaction_date = "2026-03-21"
        mock_so.delivery_date = "2026-04-20"
        mock_so.payment_schedule = []

        with patch('raven_ai_agent.agents.workflow_orchestrator.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            mock_frappe.get_doc.return_value = mock_qt

            with patch('raven_ai_agent.agents.workflow_orchestrator.make_sales_order', return_value=mock_so):
                orchestrator = WorkflowOrchestrator()
                result = orchestrator.create_so_from_quotation("QTN-001")

                self.assertTrue(result["success"])
                self.assertEqual(result["so_name"], "SO-001")

    def test_create_so_from_quotation_not_submitted(self):
        """Test handling when Quotation is not submitted"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        # Mock Quotation in draft state
        mock_qt = MagicMock()
        mock_qt.name = "QTN-001"
        mock_qt.docstatus = 0  # Draft

        with patch('raven_ai_agent.agents.workflow_orchestrator.frappe') as mock_frappe:
            self._apply_frappe_patch(mock_frappe)
            mock_frappe.get_doc.return_value = mock_qt

            orchestrator = WorkflowOrchestrator()
            result = orchestrator.create_so_from_quotation("QTN-001")

            self.assertFalse(result["success"])
            self.assertIn("must be submitted", result["error"])

    def test_process_command_help(self):
        """Test help command processing"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        orchestrator = WorkflowOrchestrator()
        result = orchestrator.process_command("@workflow help")

        self.assertIn("Workflow Orchestrator", result)
        self.assertIn("@workflow run", result)

    def test_process_command_run_with_so(self):
        """Test run command with Sales Order"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        with patch.object(WorkflowOrchestrator, 'run_full_cycle') as mock_run:
            mock_run.return_value = {
                "success": True,
                "message": "✅ Workflow completed"
            }

            orchestrator = WorkflowOrchestrator()
            result = orchestrator.process_command("@workflow run SO-001")

            mock_run.assert_called_once_with("SO-001", None, None, None)
            self.assertIn("completed", result)

    def test_process_command_status_with_so(self):
        """Test status command with Sales Order"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        with patch.object(WorkflowOrchestrator, 'get_pipeline_status') as mock_status:
            mock_status.return_value = {
                "success": True,
                "message": "📊 Pipeline Dashboard for SO-001"
            }

            orchestrator = WorkflowOrchestrator()
            result = orchestrator.process_command("@workflow status SO-001")

            mock_status.assert_called_once_with("SO-001")
            self.assertIn("Pipeline Dashboard", result)

    def test_build_pipeline_response_all_success(self):
        """Test pipeline response building when all steps succeed"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        orchestrator = WorkflowOrchestrator()
        results = [
            {"step": 1, "success": True, "message": "Step 1 OK"},
            {"step": 2, "success": True, "message": "Step 2 OK"},
        ]
        state = {"so_name": "SO-001", "errors": []}

        result = orchestrator._build_pipeline_response(results, state)

        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 2)

    def test_build_pipeline_response_with_failure(self):
        """Test pipeline response building when a step fails"""
        from raven_ai_agent.agents.workflow_orchestrator import WorkflowOrchestrator

        orchestrator = WorkflowOrchestrator()
        results = [
            {"step": 1, "success": True, "message": "Step 1 OK"},
            {"step": 2, "success": False, "error": "Step 2 failed"},
        ]
        state = {"so_name": "SO-001", "errors": [{"step": 2}]}

        result = orchestrator._build_pipeline_response(results, state)

        self.assertFalse(result["success"])
        self.assertEqual(len(result["results"]), 2)


if __name__ == "__main__":
    unittest.main()
