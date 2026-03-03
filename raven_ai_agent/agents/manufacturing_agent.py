"""
Manufacturing Agent - Work Orders & Stock Entries for Manufacturing
Handles Steps 1, 2, 4, 5 of the 8-step fulfillment workflow:
  Step 1: Create Work Order (Manufacturing) → Submit
  Step 2: Stock Entry (Manufacture) from WO
  Step 4: Create Sales Work Order from Sales Order
  Step 5: Stock Entry (Manufacture for Sales WO)

IMPORTANT: This is a Frappe Server Script compatible module.
- Uses frappe.call() patterns — NO `import frappe` at module top in Server Scripts
- All frappe references are safe when run inside Frappe context
- Designed for raven_ai_agent (Frappe app)

Based on verified 8-step workflow:
  MFG-WO-03726 pilot (2026-03-03)
  BOM hierarchy: Sales BOM-0307-001 → Mix BOM-0307-005 → Production BOMs
"""
import frappe
from typing import Dict, List, Optional
from frappe.utils import nowdate, add_days, flt


class ManufacturingAgent:
    """AI Agent for Manufacturing Work Orders and Stock Entries"""

    # Work Order status progression
    WO_STATUS_FLOW = {
        "Draft": "Submit the Work Order",
        "Not Started": "Start the Work Order (transfer materials)",
        "In Process": "Complete manufacturing (create Manufacture Stock Entry)",
        "Completed": "Work Order fully manufactured",
        "Stopped": "Work Order stopped — resume or cancel",
        "Cancelled": "Work Order cancelled — no action"
    }

    # BOM level mapping for the hierarchical structure
    BOM_LEVELS = {
        "sales": {
            "description": "Sales BOM (FG + customer label)",
            "pattern": "BOM-{item}-001",
            "example": "BOM-0307-001: 0307 + LBL0307"
        },
        "mix": {
            "description": "Mix/Formulation BOM (FG = formulated SFG + blank label)",
            "pattern": "BOM-{item}-005",
            "example": "BOM-0307-005: ITEM_0612185231 + LBL4INX6INBL"
        },
        "production": {
            "description": "Full production BOM (leaf to powder)",
            "pattern": "BOM-{item}-006",
            "example": "BOM-0307-006: full recipe incl. M033 Aloe Vera Leaf"
        }
    }

    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site

    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"

    # ========================================================================
    # STEP 1: CREATE WORK ORDER (Manufacturing)
    # ========================================================================

    def create_work_order(
        self,
        item_code: str,
        qty: float,
        bom: str = None,
        sales_order: str = None,
        project: str = None,
        use_multi_level_bom: bool = False,
        fg_warehouse: str = None,
        wip_warehouse: str = None,
        confirm: bool = False
    ) -> Dict:
        """
        Create a Work Order from a BOM.

        Args:
            item_code: Item to manufacture (e.g., '0307')
            qty: Quantity in Kg (e.g., 150)
            bom: BOM name (auto-detects default if not provided)
            sales_order: Link to Sales Order (for sales-linked WOs)
            project: Project name (e.g., 'PROJ-0024')
            use_multi_level_bom: If True, MRP explodes sub-assemblies
            fg_warehouse: Finished Goods warehouse (auto-detects if not set)
            wip_warehouse: Work In Progress warehouse (auto-detects if not set)
            confirm: If False, returns preview; if True, creates WO

        Returns:
            Dict with work_order name, link, and details
        """
        try:
            # Auto-detect BOM if not provided
            if not bom:
                bom = self._get_default_bom(item_code)
                if not bom:
                    return {
                        "success": False,
                        "error": f"No active BOM found for item '{item_code}'. "
                                 f"Create a BOM first or specify one explicitly."
                    }

            # Validate BOM exists and is active
            bom_doc = frappe.get_doc("BOM", bom)
            if not bom_doc.is_active:
                return {"success": False, "error": f"BOM {bom} is not active"}

            # Auto-detect warehouses
            if not fg_warehouse:
                fg_warehouse = self._get_fg_warehouse()
            if not wip_warehouse:
                wip_warehouse = self._get_wip_warehouse(bom)

            # Idempotency: check for existing draft WO with same params
            existing = frappe.db.get_value("Work Order", {
                "production_item": item_code,
                "bom_no": bom,
                "qty": flt(qty),
                "docstatus": 0  # Draft
            }, "name")

            if existing:
                return {
                    "success": True,
                    "action": "existing_found",
                    "work_order": existing,
                    "link": self.make_link("Work Order", existing),
                    "message": f"Draft Work Order already exists: {existing}"
                }

            # Preview mode
            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create Work Order?**\n\n"
                        f"| Field | Value |\n|-------|-------|\n"
                        f"| Item | {item_code} |\n"
                        f"| Qty | {qty} Kg |\n"
                        f"| BOM | {bom} |\n"
                        f"| FG Warehouse | {fg_warehouse} |\n"
                        f"| WIP Warehouse | {wip_warehouse} |\n"
                        f"| Sales Order | {sales_order or 'None'} |\n"
                        f"| Multi-Level BOM | {'Yes' if use_multi_level_bom else 'No'} |\n\n"
                        f"⚠️ **Confirm?** Reply: `@ai confirm create work order`"
                    )
                }

            # Create the Work Order
            wo = frappe.new_doc("Work Order")
            wo.production_item = item_code
            wo.bom_no = bom
            wo.qty = flt(qty)
            wo.fg_warehouse = fg_warehouse
            wo.wip_warehouse = wip_warehouse
            wo.use_multi_level_bom = use_multi_level_bom
            wo.planned_start_date = nowdate()
            wo.expected_delivery_date = add_days(nowdate(), 7)
            wo.company = bom_doc.company or frappe.defaults.get_defaults().get("company")

            if sales_order:
                wo.sales_order = sales_order
            if project:
                wo.project = project

            wo.flags.ignore_permissions = True
            wo.insert()
            frappe.db.commit()

            return {
                "success": True,
                "action": "created",
                "work_order": wo.name,
                "link": self.make_link("Work Order", wo.name),
                "item_code": item_code,
                "qty": qty,
                "bom": bom,
                "status": wo.status,
                "message": f"✅ Work Order **{wo.name}** created ({qty} Kg of {item_code})"
            }
        except Exception as e:
            frappe.log_error(f"ManufacturingAgent.create_work_order error: {str(e)}")
            return {"success": False, "error": str(e)}

    def submit_work_order(self, wo_name: str, confirm: bool = False) -> Dict:
        """
        Submit a Work Order (Draft → Submitted/Not Started).

        The 'Starting Work Order' workflow transitions:
          Not Started (docstatus=0) → Start (docstatus=1)
        """
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            if wo.docstatus == 1:
                return {
                    "success": True,
                    "message": f"✅ Work Order **{wo_name}** is already submitted (status: {wo.status})",
                    "link": self.make_link("Work Order", wo_name)
                }

            if wo.docstatus == 2:
                return {"success": False, "error": f"Work Order {wo_name} is cancelled"}

            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Submit Work Order {wo_name}?**\n\n"
                        f"| Field | Value |\n|-------|-------|\n"
                        f"| Item | {wo.production_item} |\n"
                        f"| Qty | {wo.qty} |\n"
                        f"| BOM | {wo.bom_no} |\n\n"
                        f"⚠️ This will make the WO ready for manufacturing."
                    )
                }

            wo.flags.ignore_permissions = True
            wo.submit()
            frappe.db.commit()

            return {
                "success": True,
                "action": "submitted",
                "work_order": wo_name,
                "link": self.make_link("Work Order", wo_name),
                "status": wo.status,
                "message": f"✅ Work Order **{wo_name}** submitted"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========================================================================
    # STEP 2 / STEP 5: STOCK ENTRY (Manufacture)
    # ========================================================================

    def create_stock_entry_manufacture(
        self,
        wo_name: str,
        qty: float = None,
        confirm: bool = False
    ) -> Dict:
        """
        Create Stock Entry (Manufacture) from a Work Order.
        This consumes raw materials from WIP warehouse and produces
        the finished good into the FG warehouse.

        Flow: WO must be submitted & have materials transferred first.

        Args:
            wo_name: Work Order name (e.g., 'MFG-WO-03726')
            qty: Quantity to manufacture (defaults to WO full qty)
            confirm: If False, returns preview

        Returns:
            Dict with stock_entry name and details
        """
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            if wo.docstatus != 1:
                return {"success": False, "error": f"Work Order {wo_name} must be submitted first (current docstatus={wo.docstatus})"}

            if wo.status == "Completed":
                return {"success": True, "message": f"Work Order {wo_name} is already completed"}

            # Check material transferred
            if flt(wo.material_transferred_for_manufacturing) <= 0:
                return {
                    "success": False,
                    "error": (
                        f"No materials transferred yet for {wo_name}. "
                        f"Create a 'Material Transfer for Manufacture' Stock Entry first.\n"
                        f"Use: `@ai transfer materials for {wo_name}`"
                    )
                }

            # Calculate qty to manufacture
            manufacture_qty = flt(qty) if qty else flt(wo.qty) - flt(wo.produced_qty)
            if manufacture_qty <= 0:
                return {"success": True, "message": f"Nothing left to manufacture for {wo_name}"}

            if not confirm:
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create Manufacture Stock Entry for {wo_name}?**\n\n"
                        f"| Field | Value |\n|-------|-------|\n"
                        f"| Item | {wo.production_item} |\n"
                        f"| Qty to Manufacture | {manufacture_qty} |\n"
                        f"| Materials Transferred | {wo.material_transferred_for_manufacturing} |\n"
                        f"| Already Produced | {wo.produced_qty} |\n\n"
                        f"This will consume raw materials and produce finished goods."
                    )
                }

            # Use ERPNext's built-in method
            from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
            se = make_stock_entry(wo_name, "Manufacture", manufacture_qty)

            se.flags.ignore_permissions = True
            se.insert()
            frappe.db.commit()

            return {
                "success": True,
                "action": "created",
                "stock_entry": se.name,
                "link": self.make_link("Stock Entry", se.name),
                "work_order": wo_name,
                "qty_manufactured": manufacture_qty,
                "purpose": "Manufacture",
                "status": "Draft",
                "message": (
                    f"✅ Stock Entry **{se.name}** (Manufacture) created for {wo_name}.\n"
                    f"Review and submit to complete manufacturing."
                )
            }
        except Exception as e:
            frappe.log_error(f"ManufacturingAgent.create_stock_entry_manufacture error: {str(e)}")
            return {"success": False, "error": str(e)}

    def create_material_transfer_for_manufacture(
        self,
        wo_name: str,
        qty: float = None,
        confirm: bool = False
    ) -> Dict:
        """
        Create Material Transfer for Manufacture Stock Entry.
        Transfers raw materials from source warehouse to WIP warehouse.
        Must be done BEFORE creating the Manufacture entry.

        Args:
            wo_name: Work Order name
            qty: Quantity (defaults to WO full qty)
            confirm: If False, returns preview
        """
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            if wo.docstatus != 1:
                return {"success": False, "error": f"Work Order {wo_name} must be submitted first"}

            transfer_qty = flt(qty) if qty else flt(wo.qty) - flt(wo.material_transferred_for_manufacturing)
            if transfer_qty <= 0:
                return {"success": True, "message": f"Materials already fully transferred for {wo_name}"}

            if not confirm:
                # Get BOM items for preview
                bom_items = frappe.get_all("BOM Item",
                    filters={"parent": wo.bom_no},
                    fields=["item_code", "qty", "source_warehouse"],
                    order_by="idx")

                items_preview = "\n".join([
                    f"- {bi.item_code}: {flt(bi.qty * transfer_qty / flt(wo.qty)):.2f} "
                    f"from {bi.source_warehouse or 'default'}"
                    for bi in bom_items
                ])
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Transfer Materials for {wo_name}?**\n\n"
                        f"Items to transfer:\n{items_preview}\n\n"
                        f"⚠️ This moves raw materials to WIP warehouse."
                    )
                }

            from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
            se = make_stock_entry(wo_name, "Material Transfer for Manufacture", transfer_qty)

            se.flags.ignore_permissions = True
            se.insert()
            frappe.db.commit()

            return {
                "success": True,
                "action": "created",
                "stock_entry": se.name,
                "link": self.make_link("Stock Entry", se.name),
                "work_order": wo_name,
                "qty_transferred": transfer_qty,
                "purpose": "Material Transfer for Manufacture",
                "message": f"✅ Material Transfer **{se.name}** created. Review and submit."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========================================================================
    # STEP 4: CREATE WORK ORDER FROM SALES ORDER (SO → WO)
    # ========================================================================

    def create_work_order_from_so(
        self,
        so_name: str,
        bom_level: str = "sales",
        confirm: bool = False
    ) -> Dict:
        """
        Create Work Order(s) from a Sales Order.
        Supports both sales-level and mix-level WO creation.

        The hierarchy:
          Sales BOM (BOM-0307-001): 0307 + LBL0307 → for customer labeling
          Mix BOM (BOM-0307-005): ITEM_0612185231 + LBL4INX6INBL → formulation

        Sales team only sees sales items. Manufacturing handles the mix/production
        BOMs internally. The SO item stays as-is (e.g., 0307).

        Args:
            so_name: Sales Order name
            bom_level: 'sales' for sales BOM, 'mix' for mix BOM
            confirm: If False, returns preview

        Returns:
            Dict with created Work Orders
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order {so_name} must be submitted first"}

            # Gather items that have BOMs
            items_for_wo = []
            for item in so.items:
                # Get the appropriate BOM based on level
                bom = self._get_bom_for_level(item.item_code, bom_level)
                if bom:
                    items_for_wo.append({
                        "item_code": item.item_code,
                        "qty": item.qty,
                        "bom": bom,
                        "bom_level": bom_level,
                        "warehouse": item.warehouse
                    })

            if not items_for_wo:
                return {
                    "success": False,
                    "error": (
                        f"No items with {bom_level}-level BOM found in {so_name}. "
                        f"Check that BOMs exist for the SO items."
                    )
                }

            if not confirm:
                items_preview = "\n".join([
                    f"- {i['item_code']}: {i['qty']} Kg → BOM: {i['bom']}"
                    for i in items_for_wo
                ])
                return {
                    "success": True,
                    "requires_confirmation": True,
                    "preview": (
                        f"**Create {bom_level.title()} Work Orders from {so_name}?**\n\n"
                        f"{items_preview}\n\n"
                        f"These WOs will be linked to {so_name}."
                    )
                }

            # Create Work Orders
            created = []
            for item_info in items_for_wo:
                result = self.create_work_order(
                    item_code=item_info["item_code"],
                    qty=item_info["qty"],
                    bom=item_info["bom"],
                    sales_order=so_name,
                    project=so.project if hasattr(so, 'project') else None,
                    confirm=True
                )
                created.append(result)

            success_count = sum(1 for r in created if r.get("success"))
            return {
                "success": True,
                "message": f"Created {success_count}/{len(items_for_wo)} Work Orders from {so_name}",
                "work_orders": created,
                "sales_order": so_name,
                "bom_level": bom_level
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========================================================================
    # STATUS & TRACKING
    # ========================================================================

    def get_wo_status(self, wo_name: str) -> Dict:
        """Get detailed Work Order status with next action recommendation"""
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            # Get linked stock entries
            stock_entries = frappe.get_all("Stock Entry",
                filters={"work_order": wo_name, "docstatus": ["!=", 2]},
                fields=["name", "purpose", "docstatus", "total_outgoing_value"],
                order_by="creation")

            transfers = [se for se in stock_entries if se.purpose == "Material Transfer for Manufacture"]
            manufactures = [se for se in stock_entries if se.purpose == "Manufacture"]

            return {
                "success": True,
                "work_order": wo_name,
                "link": self.make_link("Work Order", wo_name),
                "item": wo.production_item,
                "qty": wo.qty,
                "bom": wo.bom_no,
                "status": wo.status,
                "docstatus": wo.docstatus,
                "produced_qty": wo.produced_qty,
                "material_transferred": wo.material_transferred_for_manufacturing,
                "sales_order": wo.sales_order,
                "project": wo.project,
                "next_action": self.WO_STATUS_FLOW.get(wo.status, "Review Work Order"),
                "stock_entries": {
                    "material_transfers": [{
                        "name": se.name,
                        "link": self.make_link("Stock Entry", se.name),
                        "status": "Submitted" if se.docstatus == 1 else "Draft"
                    } for se in transfers],
                    "manufactures": [{
                        "name": se.name,
                        "link": self.make_link("Stock Entry", se.name),
                        "status": "Submitted" if se.docstatus == 1 else "Draft"
                    } for se in manufactures]
                }
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order '{wo_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_work_orders_for_so(self, so_name: str) -> Dict:
        """List all Work Orders linked to a Sales Order"""
        try:
            wos = frappe.get_all("Work Order",
                filters={"sales_order": so_name},
                fields=["name", "production_item", "qty", "produced_qty",
                         "status", "bom_no", "docstatus"],
                order_by="creation")

            return {
                "success": True,
                "sales_order": so_name,
                "count": len(wos),
                "work_orders": [{
                    "name": wo.name,
                    "link": self.make_link("Work Order", wo.name),
                    "item": wo.production_item,
                    "qty": wo.qty,
                    "produced": wo.produced_qty,
                    "status": wo.status,
                    "bom": wo.bom_no,
                    "progress": f"{flt(wo.produced_qty / wo.qty * 100, 1)}%" if wo.qty else "0%"
                } for wo in wos]
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    def _get_default_bom(self, item_code: str) -> Optional[str]:
        """Get the default active BOM for an item"""
        bom = frappe.db.get_value("BOM", {
            "item": item_code,
            "is_active": 1,
            "is_default": 1,
            "docstatus": 1
        }, "name")

        if not bom:
            # Fallback: any active submitted BOM
            bom = frappe.db.get_value("BOM", {
                "item": item_code,
                "is_active": 1,
                "docstatus": 1
            }, "name", order_by="creation desc")

        return bom

    def _get_bom_for_level(self, item_code: str, level: str) -> Optional[str]:
        """
        Get the BOM for a specific manufacturing level.

        Level mapping:
          sales → BOM-{item}-001 (default, customer-facing)
          mix   → BOM-{item}-005 (formulation/mix plant)
          production → BOM-{item}-006 (full production)
        """
        suffix_map = {"sales": "001", "mix": "005", "production": "006"}
        suffix = suffix_map.get(level, "001")

        # Try exact pattern first
        bom_name = f"BOM-{item_code}-{suffix}"
        if frappe.db.exists("BOM", {"name": bom_name, "is_active": 1}):
            return bom_name

        # Fallback to default BOM
        if level == "sales":
            return self._get_default_bom(item_code)

        return None

    def _get_fg_warehouse(self) -> str:
        """Get Finished Goods warehouse"""
        # Try company default first
        wh = frappe.db.get_value("Warehouse", {"warehouse_name": "FG to Sell Warehouse"}, "name")
        if wh:
            return wh
        default = frappe.db.get_single_value("Stock Settings", "default_warehouse")
        return default or "FG to Sell Warehouse - AMB-W"

    def _get_wip_warehouse(self, bom: str = None) -> str:
        """
        Get WIP warehouse based on BOM context.
        Mix BOMs use 'WIP in Mix', production BOMs use default WIP.
        """
        if bom and "-005" in bom:
            # Mix plant WIP
            wh = frappe.db.get_value("Warehouse", {"warehouse_name": "WIP in Mix"}, "name")
            if wh:
                return wh

        default = frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")
        return default or "WIP in Mix - AMB-W"

    # ========================================================================
    # COMMAND HANDLER
    # ========================================================================

    def process_command(self, message: str) -> str:
        """Process natural language commands for manufacturing operations"""
        message_lower = message.lower().strip()

        import re

        # Extract WO name
        wo_pattern = r'(MFG-WO-\d+)'
        wo_match = re.search(wo_pattern, message, re.IGNORECASE)
        wo_name = wo_match.group(1) if wo_match else None

        # Extract SO name
        so_pattern = r'(SO-\d+-[\w\s]+|SAL-ORD-\d+-\d+)'
        so_match = re.search(so_pattern, message, re.IGNORECASE)
        so_name = so_match.group(1).strip() if so_match else None

        # Extract item code
        item_pattern = r'\b(0[0-9]{3}|ITEM_\d+)\b'
        item_match = re.search(item_pattern, message)
        item_code = item_match.group(1) if item_match else None

        # Extract quantity
        qty_pattern = r'(\d+(?:\.\d+)?)\s*(?:kg|Kg|KG)'
        qty_match = re.search(qty_pattern, message)
        qty = float(qty_match.group(1)) if qty_match else None

        # Route commands
        confirm = "confirm" in message_lower or message.startswith("!")

        if wo_name:
            if "status" in message_lower or "check" in message_lower:
                result = self.get_wo_status(wo_name)
            elif "submit" in message_lower or "start" in message_lower:
                result = self.submit_work_order(wo_name, confirm=confirm)
            elif "transfer" in message_lower and "material" in message_lower:
                result = self.create_material_transfer_for_manufacture(wo_name, confirm=confirm)
            elif "manufacture" in message_lower or "finish" in message_lower or "produce" in message_lower:
                result = self.create_stock_entry_manufacture(wo_name, confirm=confirm)
            else:
                result = self.get_wo_status(wo_name)
        elif so_name and ("work order" in message_lower or "wo" in message_lower):
            if "list" in message_lower or "show" in message_lower:
                result = self.get_work_orders_for_so(so_name)
            else:
                bom_level = "mix" if "mix" in message_lower else "sales"
                result = self.create_work_order_from_so(so_name, bom_level=bom_level, confirm=confirm)
        elif "create" in message_lower and ("work order" in message_lower or "wo" in message_lower):
            if item_code and qty:
                result = self.create_work_order(item_code, qty, confirm=confirm)
            else:
                result = {
                    "success": False,
                    "error": "Please specify item code and quantity. Example: `@ai create work order 0307 150 Kg`"
                }
        else:
            result = {
                "success": True,
                "message": (
                    "**Manufacturing Agent Commands:**\n\n"
                    "- `@ai create work order 0307 150 Kg` — Create WO\n"
                    "- `@ai submit MFG-WO-03726` — Submit WO\n"
                    "- `@ai transfer materials for MFG-WO-03726` — Transfer materials\n"
                    "- `@ai manufacture MFG-WO-03726` — Create Manufacture SE\n"
                    "- `@ai status MFG-WO-03726` — Check WO status\n"
                    "- `@ai create work order from SO-00752 mix` — WO from SO\n"
                    "- `@ai list work orders for SO-00752` — List WOs for SO"
                )
            }

        return self._format_response(result)

    def _format_response(self, result: Dict) -> str:
        """Format result dict into readable response"""
        if result.get("requires_confirmation"):
            return result["preview"]

        if not result.get("success"):
            return f"❌ {result.get('error', 'Unknown error')}"

        if result.get("message"):
            return result["message"]

        return str(result)
