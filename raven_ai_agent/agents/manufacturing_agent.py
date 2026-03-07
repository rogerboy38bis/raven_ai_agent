"""
Manufacturing AI Agent
Handles the complete manufacturing cycle: Work Order creation, submission,
Stock Entry (Manufacture), and SO→WO linking.

Covers Workflow Steps 1, 2, 4, 5:
  Step 1: WO (Manufacturing) → Submit
  Step 2: Stock Entry (Manufacture)
  Step 4: Sales WO (Work Order from SO)
  Step 5: Stock Entry (Manufacture for Sales)

Key Intelligence:
  - Item validation: Ensure manufactured item (e.g. 0307) matches SO item
  - BOM hierarchy: Sales BOM (-001) vs Mix BOM (-005) vs Full BOM (-006)
  - Inventory check before manufacture
  - No `import frappe` in Server Scripts (use frappe already available)

Author: raven_ai_agent
"""
import frappe
import re
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate, flt


class ManufacturingAgent:
    """AI Agent for manufacturing operations: Work Orders and Stock Entries"""

    # Work Order status flow
    WO_STATUS_FLOW = {
        "Draft": "Submit the Work Order to start manufacturing",
        "Not Started": "Issue materials or start production",
        "In Process": "Complete manufacture via Stock Entry (Manufacture)",
        "Completed": "Work Order fully completed — proceed to Delivery Note if sales-linked",
        "Stopped": "Work Order was stopped — review and resume or cancel",
        "Cancelled": "Work Order was cancelled — no action needed"
    }

    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site

    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link for ERPNext documents"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"

    # ========== WORK ORDER OPERATIONS (Steps 1, 4) ==========

    def create_work_order(self, item_code: str, qty: float,
                          bom: str = None, sales_order: str = None,
                          project: str = None, use_multi_level_bom: int = 0) -> Dict:
        """Create a Work Order from BOM.
        
        Args:
            item_code: Item to manufacture (e.g. '0307')
            qty: Quantity to manufacture in Kg or base UOM
            bom: Specific BOM name (e.g. 'BOM-0307-005'). If None, uses default BOM.
            sales_order: Link to Sales Order (e.g. 'SO-00752-LEGOSAN AB')
            project: Link to Project (e.g. 'PROJ-0024')
            use_multi_level_bom: 0 = single level (migration), 1 = multi-level (MRP explosion)
        
        Returns:
            Dict with success status, WO name, and link
        """
        try:
            # Validate item exists
            if not frappe.db.exists("Item", item_code):
                return {"success": False, "error": f"Item '{item_code}' not found in ERPNext."}

            # Get BOM — if not specified, use smart resolution (variant → template fallback)
            if not bom:
                bom = self.resolve_bom(item_code)
            
            if not bom:
                return {"success": False, "error": f"No active BOM found for item '{item_code}'. Create and submit a BOM first."}

            # Validate BOM exists and is submitted
            bom_doc = frappe.get_doc("BOM", bom)
            if bom_doc.docstatus != 1:
                return {"success": False, "error": f"BOM '{bom}' is not submitted (docstatus={bom_doc.docstatus}). Submit it first."}

            # Get warehouses — smart resolution based on BOM type and company
            company = frappe.db.get_default("company") or "AMB-Wellness"
            wip_warehouse, fg_warehouse, source_warehouse = self._resolve_warehouses(
                bom, item_code, company
            )

            # Build Work Order doc
            wo_data = {
                "doctype": "Work Order",
                "production_item": item_code,
                "bom_no": bom,
                "qty": flt(qty),
                "wip_warehouse": wip_warehouse,
                "fg_warehouse": fg_warehouse,
                "use_multi_level_bom": use_multi_level_bom,
                "company": company
            }

            if sales_order:
                wo_data["sales_order"] = sales_order
            if project:
                wo_data["project"] = project

            wo = frappe.get_doc(wo_data)
            wo.insert(ignore_permissions=True)

            # Set source warehouses on required items (after insert populates them)
            if source_warehouse:
                self._set_item_source_warehouses(wo, source_warehouse, company)
                wo.save(ignore_permissions=True)

            frappe.db.commit()

            return {
                "success": True,
                "wo_name": wo.name,
                "link": self.make_link("Work Order", wo.name),
                "message": (
                    f"✅ Work Order created: {self.make_link('Work Order', wo.name)}\n\n"
                    f"  Item: {item_code}\n"
                    f"  BOM: {self.make_link('BOM', bom)}\n"
                    f"  Qty: {qty}\n"
                    f"  WIP: {wip_warehouse}\n"
                    f"  FG: {fg_warehouse}\n"
                    f"  Status: {wo.status}"
                    + (f"\n  Sales Order: {self.make_link('Sales Order', sales_order)}" if sales_order else "")
                    + (f"\n  Project: {project}" if project else "")
                )
            }

        except Exception as e:
            return {"success": False, "error": f"Error creating Work Order: {str(e)}"}

    def submit_work_order(self, wo_name: str) -> Dict:
        """Submit a Work Order to start manufacturing.
        
        Args:
            wo_name: Work Order name (e.g. 'MFG-WO-03726')
        
        Returns:
            Dict with success status
        """
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            if wo.docstatus == 1:
                return {
                    "success": True,
                    "message": f"✅ Work Order {self.make_link('Work Order', wo_name)} is already submitted.\n  Status: {wo.status}"
                }
            if wo.docstatus == 2:
                return {"success": False, "error": f"Work Order {wo_name} is cancelled and cannot be submitted."}

            wo.submit()
            frappe.db.commit()

            return {
                "success": True,
                "wo_name": wo.name,
                "link": self.make_link("Work Order", wo.name),
                "message": (
                    f"✅ Work Order submitted: {self.make_link('Work Order', wo.name)}\n\n"
                    f"  Item: {wo.production_item}\n"
                    f"  Qty: {wo.qty}\n"
                    f"  Status: {wo.status}\n\n"
                    f"💡 Next: Use `@manufacturing issue materials {wo.name}` to transfer materials to WIP"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order '{wo_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error submitting Work Order: {str(e)}"}

    def create_work_order_from_so(self, so_name: str, bom: str = None) -> Dict:
        """Create a Work Order linked to a Sales Order (Step 4).
        
        Looks up each SO item, finds the appropriate BOM (sales BOM -001),
        and creates a WO. Handles the item 0307 vs ITEM_0612 mapping
        by using the sales BOM which references the correct hierarchy.
        
        Args:
            so_name: Sales Order name (e.g. 'SO-00752-LEGOSAN AB')
            bom: Override BOM name. If None, uses the default BOM for the SO item.
        
        Returns:
            Dict with created Work Orders
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)

            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order '{so_name}' must be submitted first (current docstatus={so.docstatus})."}

            created_wos = []
            errors = []

            for item in so.items:
                item_code = item.item_code
                qty = item.qty

                # Get BOM for this item (using variant→template fallback)
                item_bom = bom or self.resolve_bom(item_code)

                if not item_bom:
                    errors.append(f"No active default BOM for item '{item_code}'")
                    continue

                # Create Work Order linked to SO
                result = self.create_work_order(
                    item_code=item_code,
                    qty=qty,
                    bom=item_bom,
                    sales_order=so_name,
                    project=so.project if hasattr(so, "project") else None,
                    use_multi_level_bom=0  # Single level for migration
                )

                if result["success"]:
                    created_wos.append({
                        "wo_name": result["wo_name"],
                        "item_code": item_code,
                        "qty": qty,
                        "bom": item_bom,
                        "link": result["link"]
                    })
                else:
                    errors.append(f"Item {item_code}: {result.get('error', 'Unknown error')}")

            if created_wos:
                msg = f"🏭 **Work Orders created from {self.make_link('Sales Order', so_name)}**\n\n"
                for wo_info in created_wos:
                    msg += (
                        f"• {wo_info['link']} — Item: {wo_info['item_code']}, "
                        f"Qty: {wo_info['qty']}, BOM: {wo_info['bom']}\n"
                    )
                if errors:
                    msg += f"\n⚠️ Errors:\n" + "\n".join(f"  • {e}" for e in errors)

                return {"success": True, "work_orders": created_wos, "errors": errors, "message": msg}
            else:
                return {"success": False, "error": "No Work Orders created.\n" + "\n".join(errors)}

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating WOs from SO: {str(e)}"}

    # ========== STOCK ENTRY OPERATIONS (Steps 2, 5) ==========

    def create_stock_entry_manufacture(self, wo_name: str, qty: float = None) -> Dict:
        """Create a Stock Entry of type 'Manufacture' from a Work Order (Steps 2 & 5).
        
        Consumes raw materials from WIP and produces finished goods into FG warehouse.
        
        Args:
            wo_name: Work Order name (e.g. 'MFG-WO-03726')
            qty: Quantity to manufacture. If None, uses full WO qty minus already manufactured.
        
        Returns:
            Dict with Stock Entry details
        """
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            if wo.docstatus != 1:
                return {"success": False, "error": f"Work Order '{wo_name}' must be submitted first."}

            if wo.status == "Completed":
                return {"success": False, "error": f"Work Order '{wo_name}' is already completed."}

            # Calculate remaining qty
            remaining_qty = flt(wo.qty) - flt(wo.produced_qty)
            if remaining_qty <= 0:
                return {"success": False, "error": f"Work Order '{wo_name}' has no remaining quantity to manufacture."}

            manufacture_qty = flt(qty) if qty else remaining_qty

            if manufacture_qty > remaining_qty:
                return {
                    "success": False,
                    "error": f"Requested qty ({manufacture_qty}) exceeds remaining ({remaining_qty})."
                }

            # Use ERPNext's built-in Stock Entry creation from Work Order
            from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

            se_dict = make_stock_entry(wo_name, "Manufacture", manufacture_qty)
            se = frappe.get_doc(se_dict)
            se.insert(ignore_permissions=True)
            se.submit()
            frappe.db.commit()

            return {
                "success": True,
                "se_name": se.name,
                "link": self.make_link("Stock Entry", se.name),
                "wo_link": self.make_link("Work Order", wo_name),
                "message": (
                    f"✅ Stock Entry (Manufacture) created: {self.make_link('Stock Entry', se.name)}\n\n"
                    f"  Work Order: {self.make_link('Work Order', wo_name)}\n"
                    f"  Item: {wo.production_item}\n"
                    f"  Qty Manufactured: {manufacture_qty}\n"
                    f"  Purpose: Manufacture\n\n"
                    f"📦 Raw materials consumed from WIP → FG produced into {wo.fg_warehouse}"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order '{wo_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating manufacture entry: {str(e)}"}

    def create_material_transfer(self, wo_name: str, qty: float = None) -> Dict:
        """Create a Material Transfer for Manufacture Stock Entry.
        
        Transfers raw materials from source warehouse to WIP warehouse
        based on Work Order requirements.
        
        Args:
            wo_name: Work Order name
            qty: Quantity basis for transfer. If None, uses full WO qty.
        
        Returns:
            Dict with Stock Entry details
        """
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            if wo.docstatus != 1:
                return {"success": False, "error": f"Work Order '{wo_name}' must be submitted first."}

            remaining_transfer = flt(wo.qty) - flt(wo.material_transferred_for_manufacturing)
            if remaining_transfer <= 0:
                return {
                    "success": True,
                    "message": f"✅ All materials already transferred for {self.make_link('Work Order', wo_name)}"
                }

            transfer_qty = flt(qty) if qty else remaining_transfer

            from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

            se_dict = make_stock_entry(wo_name, "Material Transfer for Manufacture", transfer_qty)
            se = frappe.get_doc(se_dict)
            se.insert(ignore_permissions=True)
            se.submit()
            frappe.db.commit()

            return {
                "success": True,
                "se_name": se.name,
                "link": self.make_link("Stock Entry", se.name),
                "message": (
                    f"✅ Material Transfer created: {self.make_link('Stock Entry', se.name)}\n\n"
                    f"  Work Order: {self.make_link('Work Order', wo_name)}\n"
                    f"  Qty Transferred: {transfer_qty}\n"
                    f"  Purpose: Material Transfer for Manufacture"
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order '{wo_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating material transfer: {str(e)}"}

    # ========== STATUS & INTELLIGENCE ==========

    def get_wo_status(self, wo_name: str) -> Dict:
        """Get detailed status of a Work Order with linked documents."""
        try:
            wo = frappe.get_doc("Work Order", wo_name)

            # Get linked stock entries
            stock_entries = frappe.get_all("Stock Entry",
                filters={"work_order": wo_name, "docstatus": ["!=", 2]},
                fields=["name", "stock_entry_type", "docstatus", "posting_date"],
                order_by="posting_date asc")

            se_list = []
            for se in stock_entries:
                se_list.append({
                    "name": se.name,
                    "link": self.make_link("Stock Entry", se.name),
                    "type": se.stock_entry_type,
                    "status": "Submitted" if se.docstatus == 1 else "Draft"
                })

            # Check Sales Order link
            so_link = None
            if wo.sales_order:
                so_link = self.make_link("Sales Order", wo.sales_order)

            next_action = self.WO_STATUS_FLOW.get(wo.status, "Review manually")

            return {
                "success": True,
                "wo_name": wo.name,
                "link": self.make_link("Work Order", wo.name),
                "production_item": wo.production_item,
                "bom_no": wo.bom_no,
                "qty": wo.qty,
                "produced_qty": wo.produced_qty,
                "material_transferred": wo.material_transferred_for_manufacturing,
                "status": wo.status,
                "sales_order": so_link,
                "project": wo.project,
                "stock_entries": se_list,
                "next_action": next_action,
                "message": (
                    f"📋 **Work Order {self.make_link('Work Order', wo.name)}**\n\n"
                    f"  Item: {wo.production_item}\n"
                    f"  BOM: {self.make_link('BOM', wo.bom_no)}\n"
                    f"  Qty: {wo.produced_qty}/{wo.qty}\n"
                    f"  Material Transferred: {wo.material_transferred_for_manufacturing}\n"
                    f"  Status: **{wo.status}**\n"
                    + (f"  Sales Order: {so_link}\n" if so_link else "")
                    + f"\n  ➡️ Next: {next_action}\n"
                    + (f"\n📦 Stock Entries:\n" + "\n".join(
                        f"  • {se['link']} ({se['type']}) — {se['status']}"
                        for se in se_list
                    ) if se_list else "")
                )
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order '{wo_name}' not found."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def check_materials_availability(self, wo_name: str) -> Dict:
        """Check material availability for a Work Order before manufacturing."""
        try:
            wo = frappe.get_doc("Work Order", wo_name)
            items_status = []
            all_available = True

            for item in wo.required_items:
                source_wh = item.source_warehouse or wo.wip_warehouse
                available = frappe.db.get_value("Bin",
                    {"item_code": item.item_code, "warehouse": source_wh},
                    "actual_qty") or 0

                shortage = max(0, flt(item.required_qty) - flt(available))
                sufficient = flt(available) >= flt(item.required_qty)

                if not sufficient:
                    all_available = False

                items_status.append({
                    "item_code": item.item_code,
                    "required_qty": item.required_qty,
                    "available_qty": available,
                    "warehouse": source_wh,
                    "shortage": shortage,
                    "status": "✅" if sufficient else f"❌ Short {shortage}"
                })

            msg = f"📦 **Material Check for {self.make_link('Work Order', wo_name)}**\n\n"
            msg += "| Item | Required | Available | Warehouse | Status |\n"
            msg += "|------|----------|-----------|-----------|--------|\n"
            for it in items_status:
                msg += (
                    f"| {it['item_code']} | {it['required_qty']} | "
                    f"{it['available_qty']} | {it['warehouse']} | {it['status']} |\n"
                )
            msg += f"\n{'✅ All materials available' if all_available else '❌ Some materials are short'}"

            return {
                "success": True,
                "all_available": all_available,
                "items": items_status,
                "message": msg
            }

        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order '{wo_name}' not found."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== WAREHOUSE RESOLUTION ==========

    # BOM suffix → warehouse mapping for AMB-Wellness manufacturing plants
    # Learned from existing Work Orders (e.g. MFG-WO-03826 for BOM-0307-005)
    BOM_WAREHOUSE_MAP = {
        # Mix Plant BOMs (suffix -005): powder mixing / labeling
        "-005": {
            "wip_warehouse": "WIP in Mix - AMB-W",
            "fg_warehouse": "FG to Sell Warehouse - AMB-W",
            "source_warehouse": "FG to Sell Warehouse - AMB-W",
        },
        # Sales BOMs (suffix -001): sales-level labeling / packaging
        "-001": {
            "wip_warehouse": "WIP in Mix - AMB-W",
            "fg_warehouse": "FG to Sell Warehouse - AMB-W",
            "source_warehouse": "FG to Sell Warehouse - AMB-W",
        },
        # Full/Production BOMs (suffix -006): full BOM explosion
        "-006": {
            "wip_warehouse": "WIP in Concentrate - AMB-W",
            "fg_warehouse": "FG to Sell Warehouse - AMB-W",
            "source_warehouse": None,  # uses BOM item source warehouses
        },
        # Dry Plant BOMs: powder drying
        "-dry": {
            "wip_warehouse": "WIP in Dry - AMB-W",
            "fg_warehouse": "SFG Aloe Vera Powder - AMB-W",
            "source_warehouse": "Cold Room Warehouse SFG - AMB-W",
        },
    }

    def _resolve_warehouses(self, bom_name: str, item_code: str, company: str):
        """Smart warehouse resolution based on BOM type, existing WOs, and company.
        
        Resolution priority:
        1. BOM suffix mapping (known plant patterns)
        2. Existing Work Orders for same BOM (learn from history)
        3. BOM default_source/target_warehouse fields
        4. Manufacturing Settings defaults (filtered by company)
        5. Item Default warehouse
        6. Fallback to safe company defaults
        
        Returns:
            Tuple of (wip_warehouse, fg_warehouse, source_warehouse)
        """
        wip_warehouse = None
        fg_warehouse = None
        source_warehouse = None

        # --- Step 1: BOM suffix mapping ---
        for suffix, warehouses in self.BOM_WAREHOUSE_MAP.items():
            if bom_name.endswith(suffix) or f"{suffix}-" in bom_name:
                # Verify warehouses exist and belong to the correct company
                wip_candidate = warehouses["wip_warehouse"]
                fg_candidate = warehouses["fg_warehouse"]
                src_candidate = warehouses.get("source_warehouse")

                if wip_candidate and frappe.db.get_value("Warehouse",
                        {"name": wip_candidate, "company": company}):
                    wip_warehouse = wip_candidate
                if fg_candidate and frappe.db.get_value("Warehouse",
                        {"name": fg_candidate, "company": company}):
                    fg_warehouse = fg_candidate
                if src_candidate and frappe.db.get_value("Warehouse",
                        {"name": src_candidate, "company": company}):
                    source_warehouse = src_candidate
                break

        # --- Step 2: Learn from existing Work Orders for same BOM ---
        if not wip_warehouse or not fg_warehouse:
            existing_wo = frappe.db.get_value("Work Order",
                {"bom_no": bom_name, "company": company, "docstatus": ["!=", 2]},
                ["wip_warehouse", "fg_warehouse", "source_warehouse"],
                order_by="modified desc", as_dict=True)
            if existing_wo:
                if not wip_warehouse and existing_wo.wip_warehouse:
                    # Validate it belongs to the correct company
                    wh_company = frappe.db.get_value("Warehouse",
                        existing_wo.wip_warehouse, "company")
                    if wh_company == company:
                        wip_warehouse = existing_wo.wip_warehouse
                if not fg_warehouse and existing_wo.fg_warehouse:
                    wh_company = frappe.db.get_value("Warehouse",
                        existing_wo.fg_warehouse, "company")
                    if wh_company == company:
                        fg_warehouse = existing_wo.fg_warehouse
                if not source_warehouse and existing_wo.source_warehouse:
                    wh_company = frappe.db.get_value("Warehouse",
                        existing_wo.source_warehouse, "company")
                    if wh_company == company:
                        source_warehouse = existing_wo.source_warehouse

        # --- Step 3: BOM default warehouses ---
        if not fg_warehouse or not source_warehouse:
            bom_doc = frappe.get_doc("BOM", bom_name)
            if not fg_warehouse and bom_doc.get("default_target_warehouse"):
                fg_warehouse = bom_doc.default_target_warehouse
            if not source_warehouse and bom_doc.get("default_source_warehouse"):
                source_warehouse = bom_doc.default_source_warehouse

        # --- Step 4: Manufacturing Settings (with company validation) ---
        if not wip_warehouse:
            try:
                ms_wip = frappe.db.get_single_value("Manufacturing Settings",
                    "default_wip_warehouse")
                if ms_wip:
                    wh_company = frappe.db.get_value("Warehouse", ms_wip, "company")
                    if wh_company == company:
                        wip_warehouse = ms_wip
            except Exception:
                pass

        if not fg_warehouse:
            try:
                ms_fg = frappe.db.get_single_value("Manufacturing Settings",
                    "default_fg_warehouse")
                if ms_fg:
                    wh_company = frappe.db.get_value("Warehouse", ms_fg, "company")
                    if wh_company == company:
                        fg_warehouse = ms_fg
            except Exception:
                pass

        # --- Step 5: Item Default warehouse ---
        if not fg_warehouse:
            item_default_wh = frappe.db.get_value("Item Default",
                {"parent": item_code, "company": company}, "default_warehouse")
            if item_default_wh:
                fg_warehouse = item_default_wh

        # --- Step 6: Company-safe fallback ---
        if not wip_warehouse:
            wip_warehouse = frappe.db.get_value("Warehouse",
                {"name": ["like", "%Work In Progress%"], "company": company,
                 "is_group": 1}, "name")
        if not fg_warehouse:
            fg_warehouse = frappe.db.get_value("Warehouse",
                {"name": ["like", "%FG to Sell%"], "company": company,
                 "is_group": 0}, "name")

        return wip_warehouse, fg_warehouse, source_warehouse

    def _set_item_source_warehouses(self, wo, source_warehouse: str, company: str):
        """Set source warehouses on Work Order required items.
        
        If a source_warehouse is determined from BOM mapping, apply it to all
        items that don't already have one. This ensures materials are pulled
        from the correct warehouse.
        """
        if not source_warehouse:
            return
        if not hasattr(wo, 'required_items') or not wo.required_items:
            return
        for item in wo.required_items:
            if not item.source_warehouse:
                item.source_warehouse = source_warehouse

    # ========== BOM RESOLUTION (GAP-02) ==========

    def resolve_bom(self, item_code: str) -> Optional[str]:
        """Smart BOM resolution: variant → template fallback.
        
        Resolution order:
        1. Default active BOM on the item itself
        2. Any active BOM on the item
        3. If variant, default active BOM on the template item
        4. If variant, any active BOM on the template item
        
        Returns BOM name or None.
        """
        # 1. Default active BOM on item
        bom = frappe.db.get_value("BOM",
            {"item": item_code, "is_active": 1, "is_default": 1, "docstatus": 1}, "name")
        if bom:
            return bom
        
        # 2. Any active BOM on item
        bom = frappe.db.get_value("BOM",
            {"item": item_code, "is_active": 1, "docstatus": 1}, "name")
        if bom:
            return bom
        
        # 3. If variant, try template item
        variant_of = frappe.db.get_value("Item", item_code, "variant_of")
        if variant_of:
            bom = frappe.db.get_value("BOM",
                {"item": variant_of, "is_active": 1, "is_default": 1, "docstatus": 1}, "name")
            if bom:
                return bom
            # 4. Any active BOM on template
            bom = frappe.db.get_value("BOM",
                {"item": variant_of, "is_active": 1, "docstatus": 1}, "name")
            if bom:
                return bom
        
        return None

    # ========== NAMED BATCH CREATION (GAP-04) ==========

    def create_named_batch(self, batch_name: str, item_code: str,
                           expiry_date: str = None,
                           manufacturing_date: str = None) -> Dict:
        """Create a batch with a user-defined name.
        
        Args:
            batch_name: The specific batch/lote name (e.g. '0803034251')
            item_code: Item code that must have has_batch_no=1
            expiry_date: Optional expiry date (YYYY-MM-DD)
            manufacturing_date: Optional manufacturing date
        """
        try:
            if not frappe.db.exists("Item", item_code):
                return {"success": False, "error": f"Item '{item_code}' not found."}
            
            has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")
            if not has_batch:
                return {"success": False, "error": f"Item '{item_code}' does not have batch tracking enabled."}
            
            # Check if batch already exists
            if frappe.db.exists("Batch", batch_name):
                existing_item = frappe.db.get_value("Batch", batch_name, "item")
                if existing_item == item_code:
                    return {
                        "success": True,
                        "batch_name": batch_name,
                        "message": f"✅ Batch **{batch_name}** already exists for item {item_code}"
                    }
                else:
                    return {"success": False, "error": f"Batch '{batch_name}' exists but belongs to item '{existing_item}', not '{item_code}'."}
            
            batch_data = {
                "doctype": "Batch",
                "batch_id": batch_name,
                "item": item_code,
            }
            if expiry_date:
                batch_data["expiry_date"] = expiry_date
            if manufacturing_date:
                batch_data["manufacturing_date"] = manufacturing_date
            
            batch = frappe.get_doc(batch_data)
            batch.insert(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "success": True,
                "batch_name": batch.name,
                "message": (
                    f"✅ Batch created: **{batch.name}**\n\n"
                    f"  Item: {item_code}\n"
                    f"  Batch ID: {batch_name}"
                    + (f"\n  Expiry: {expiry_date}" if expiry_date else "")
                    + (f"\n  Mfg Date: {manufacturing_date}" if manufacturing_date else "")
                )
            }
        except Exception as e:
            return {"success": False, "error": f"Error creating batch: {str(e)}"}

    # ========== MULTI-WO PLAN (GAP-03) ==========

    def create_wo_plan(self, so_name: str, plan: List[Dict]) -> Dict:
        """Create multiple Work Orders from a single SO with custom qty/lote splits.
        
        Args:
            so_name: Sales Order name
            plan: List of dicts with keys:
                - qty (float): Quantity for this WO
                - batch_name (str, optional): Lote/batch to assign
                - bom (str, optional): Override BOM
        
        Returns:
            Dict with all created WOs
        """
        try:
            so = frappe.get_doc("Sales Order", so_name)
            if so.docstatus != 1:
                return {"success": False, "error": f"Sales Order '{so_name}' must be submitted first."}
            
            if not so.items:
                return {"success": False, "error": f"Sales Order '{so_name}' has no items."}
            
            item = so.items[0]
            item_code = item.item_code
            so_qty = flt(item.qty)
            
            # Validate plan total
            plan_total = sum(flt(p.get("qty", 0)) for p in plan)
            
            created_wos = []
            errors = []
            
            for idx, wo_spec in enumerate(plan):
                wo_qty = flt(wo_spec.get("qty", 0))
                if wo_qty <= 0:
                    errors.append(f"WO{idx+1}: Invalid qty {wo_qty}")
                    continue
                
                batch_name = wo_spec.get("batch_name") or wo_spec.get("lote")
                wo_bom = wo_spec.get("bom")
                
                # Resolve BOM
                if not wo_bom:
                    wo_bom = self.resolve_bom(item_code)
                
                if not wo_bom:
                    errors.append(f"WO{idx+1}: No BOM found for '{item_code}'")
                    continue
                
                # Create named batch if specified and doesn't exist
                if batch_name:
                    has_batch = frappe.db.get_value("Item", item_code, "has_batch_no")
                    if has_batch and not frappe.db.exists("Batch", batch_name):
                        batch_result = self.create_named_batch(batch_name, item_code)
                        if not batch_result["success"]:
                            errors.append(f"WO{idx+1}: Batch error — {batch_result['error']}")
                
                # Create WO
                result = self.create_work_order(
                    item_code=item_code,
                    qty=wo_qty,
                    bom=wo_bom,
                    sales_order=so_name,
                    project=so.project if hasattr(so, "project") else None,
                    use_multi_level_bom=0
                )
                
                if result["success"]:
                    wo_info = {
                        "wo_name": result["wo_name"],
                        "qty": wo_qty,
                        "bom": wo_bom,
                        "batch": batch_name or "—",
                        "link": result["link"]
                    }
                    
                    # Store batch assignment as custom field if available
                    if batch_name:
                        try:
                            wo_doc = frappe.get_doc("Work Order", result["wo_name"])
                            if hasattr(wo_doc, "custom_lote"):
                                wo_doc.custom_lote = batch_name
                                wo_doc.save(ignore_permissions=True)
                        except Exception:
                            pass  # custom field may not exist yet
                    
                    created_wos.append(wo_info)
                else:
                    errors.append(f"WO{idx+1}: {result.get('error', 'Unknown error')}")
            
            if created_wos:
                msg = f"🏭 **WO Plan for {self.make_link('Sales Order', so_name)}**\n\n"
                msg += f"  SO Qty: {so_qty} | Plan Total: {plan_total}"
                if abs(plan_total - so_qty) > 0.01:
                    msg += f" ⚠️ (difference: {plan_total - so_qty:+.1f})"
                msg += "\n\n"
                msg += "| # | Work Order | Qty | Lote | BOM |\n"
                msg += "|---|-----------|-----|------|-----|\n"
                for idx, wo in enumerate(created_wos):
                    msg += f"| {idx+1} | {wo['link']} | {wo['qty']} | {wo['batch']} | {wo['bom']} |\n"
                
                if errors:
                    msg += f"\n⚠️ Errors:\n" + "\n".join(f"  • {e}" for e in errors)
                
                msg += f"\n\n💡 Next: `@ai submit all WOs for {so_name}`"
                
                frappe.db.commit()
                return {"success": True, "work_orders": created_wos, "errors": errors, "message": msg}
            else:
                return {"success": False, "error": "No Work Orders created.\n" + "\n".join(errors)}
        
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found."}
        except Exception as e:
            return {"success": False, "error": f"Error creating WO plan: {str(e)}"}

    # ========== SHOW WORK ORDERS (ARCH-03 fix) ==========

    def show_work_orders(self, so_name: str = None, item_code: str = None) -> str:
        """List active work orders, optionally filtered by SO or item."""
        try:
            filters = {"docstatus": ["<", 2]}
            if so_name:
                filters["sales_order"] = so_name
            if item_code:
                filters["production_item"] = ["like", f"%{item_code}%"]
            
            work_orders = frappe.get_list("Work Order",
                filters=filters,
                fields=["name", "production_item", "qty", "produced_qty", 
                        "status", "planned_start_date", "sales_order",
                        "material_transferred_for_manufacturing"],
                order_by="modified desc",
                limit=20
            )
            
            if not work_orders:
                filter_desc = ""
                if so_name:
                    filter_desc = f" for {so_name}"
                elif item_code:
                    filter_desc = f" for item {item_code}"
                return f"No active work orders found{filter_desc}."
            
            msg = "📋 **ACTIVE WORK ORDERS**\n\n"
            msg += "| Work Order | Product | Qty | Transferred | Status | SO |\n"
            msg += "|------------|---------|-----|-------------|--------|-----|\n"
            for wo in work_orders:
                progress = f"{wo.produced_qty or 0}/{wo.qty}"
                transferred = wo.material_transferred_for_manufacturing or 0
                wo_link = self.make_link("Work Order", wo.name)
                so_ref = wo.sales_order or "—"
                msg += f"| {wo_link} | {wo.production_item[:30]} | {progress} | {transferred} | {wo.status} | {so_ref} |\n"
            
            return msg
        except Exception as e:
            return f"❌ Error listing work orders: {str(e)}"

    # ========== MAIN COMMAND HANDLER ==========

    def process_command(self, message: str) -> str:
        """Process incoming Raven command and return formatted response.
        
        Commands:
            @manufacturing show work orders [for SO-NAME | for ITEM]
            @manufacturing create wo [item] qty [qty] bom [bom]
            @manufacturing create wo from so [SO-NAME]
            @manufacturing create wo plan for [SO-NAME] ...
            @manufacturing create batch [NAME] for [ITEM]
            @manufacturing submit wo [WO-NAME]
            @manufacturing manufacture [WO-NAME] qty [qty]
            @manufacturing transfer materials [WO-NAME] [batch BATCH]
            @manufacturing status [WO-NAME]
            @manufacturing check materials [WO-NAME]
            @manufacturing help
        """
        message_lower = message.lower().strip()

        # Extract Work Order name
        wo_pattern = r'(MFG-WO-\d+|WO-[^\s]+)'
        wo_match = re.search(wo_pattern, message, re.IGNORECASE)
        wo_name = wo_match.group(1) if wo_match else None

        # Extract Sales Order name
        so_pattern = r'(SO-[\w-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b|each\b|plan\b)[\w\.]+)*|SAL-ORD-[\d-]+)'
        so_match = re.search(so_pattern, message, re.IGNORECASE)
        so_name = so_match.group(1) if so_match else None

        # ---- HELP ----
        if "help" in message_lower or "capabilities" in message_lower:
            return self._help_text()

        # ---- SHOW / LIST WORK ORDERS (ARCH-03 fix) ----
        if ("show work order" in message_lower or "list work order" in message_lower 
                or "mis ordenes" in message_lower or "show wo" in message_lower):
            return self.show_work_orders(so_name=so_name)

        # ---- CREATE NAMED BATCH (GAP-04) ----
        if "create batch" in message_lower:
            # @ai create batch 0803034251 for ITEM-CODE [expiry 2027-03-07]
            batch_match = re.search(r'create\s+batch\s+([\w-]+)', message, re.IGNORECASE)
            item_match = re.search(r'(?:for|item)\s+([\S]+)', message, re.IGNORECASE)
            expiry_match = re.search(r'expiry\s+([\d-]+)', message, re.IGNORECASE)
            mfg_date_match = re.search(r'mfg[_-]?date\s+([\d-]+)', message, re.IGNORECASE)
            
            if not batch_match:
                return "❌ Specify batch name. Example: `@ai create batch 0803034251 for 0803-VARIANT`"
            if not item_match:
                return "❌ Specify item. Example: `@ai create batch 0803034251 for 0803-VARIANT`"
            
            batch_name = batch_match.group(1).strip()
            item_code = item_match.group(1).strip()
            expiry = expiry_match.group(1) if expiry_match else None
            mfg_date = mfg_date_match.group(1) if mfg_date_match else None
            
            result = self.create_named_batch(batch_name, item_code, 
                                              expiry_date=expiry,
                                              manufacturing_date=mfg_date)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- CREATE WO PLAN (GAP-03) ----
        # Format: @ai create wo plan for SO-00763: WO1 qty 1055 lote 0803034251, WO2 qty 600 lote 0803080241
        # Or: @ai wo plan SO-00763 each 500
        if ("wo plan" in message_lower or "work order plan" in message_lower) and so_name:
            plan = []
            
            # Check for "each QTY" shortcut: splits SO qty into equal WOs
            each_match = re.search(r'each\s+(\d+\.?\d*)\s*(?:kg)?', message, re.IGNORECASE)
            if each_match:
                each_qty = flt(each_match.group(1))
                if each_qty > 0:
                    try:
                        so = frappe.get_doc("Sales Order", so_name)
                        total_qty = flt(so.items[0].qty) if so.items else 0
                        num_wos = int(total_qty / each_qty)
                        remainder = total_qty - (num_wos * each_qty)
                        
                        for i in range(num_wos):
                            plan.append({"qty": each_qty})
                        if remainder > 0:
                            plan.append({"qty": remainder})
                    except Exception as e:
                        return f"❌ Error reading SO: {str(e)}"
            else:
                # Parse detailed plan: WO1 qty 1055 lote ABC, WO2 qty 600 lote DEF
                wo_specs = re.findall(
                    r'(?:WO\d*)?\s*qty\s+(\d+\.?\d*)(?:\s+(?:lote|batch)\s+([\w-]+))?',
                    message, re.IGNORECASE
                )
                for spec in wo_specs:
                    entry = {"qty": flt(spec[0])}
                    if spec[1]:
                        entry["lote"] = spec[1]
                    plan.append(entry)
            
            if not plan:
                return (
                    "❌ Could not parse WO plan. Examples:\n\n"
                    f"`@ai wo plan {so_name} each 500`\n"
                    f"`@ai wo plan {so_name}: qty 1055 lote ABC, qty 600 lote DEF`"
                )
            
            result = self.create_wo_plan(so_name, plan)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- CREATE WO FROM SO (Step 4) ----
        has_wo_keyword = ("wo" in message_lower or "work order" in message_lower)
        has_so_ref = ("from so" in message_lower or "from sales" in message_lower or so_name is not None)
        if has_wo_keyword and has_so_ref and ("create" in message_lower or so_name is not None):
            if not so_name:
                return "❌ Please specify a Sales Order. Example: `@manufacturing create wo from so SO-00752-LEGOSAN AB`"
            bom_match = re.search(r'bom\s+(BOM-[\w-]+)', message, re.IGNORECASE)
            bom = bom_match.group(1) if bom_match else None
            result = self.create_work_order_from_so(so_name, bom=bom)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- CREATE WO (Step 1) ----
        if "create" in message_lower and ("wo" in message_lower or "work order" in message_lower):
            item_match = re.search(r'(?:for|item|para)\s+(\S+)', message, re.IGNORECASE)
            qty_match = re.search(r'(?:qty|quantity|cantidad)\s+(\d+\.?\d*)', message, re.IGNORECASE)
            bom_match = re.search(r'bom\s+(BOM-[\w-]+)', message, re.IGNORECASE)

            if not item_match:
                return "❌ Please specify an item. Example: `@manufacturing create wo for 0307 qty 150 bom BOM-0307-005`"

            item_code = item_match.group(1).strip()
            qty = float(qty_match.group(1)) if qty_match else 1
            bom = bom_match.group(1) if bom_match else None

            result = self.create_work_order(item_code, qty, bom=bom,
                                            sales_order=so_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- SUBMIT WO (Step 1) ----
        if ("submit" in message_lower) and wo_name:
            result = self.submit_work_order(wo_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- MANUFACTURE / FINISH (Steps 2, 5) ----
        if ("manufacture" in message_lower or "finish" in message_lower
                or "produce" in message_lower) and wo_name:
            qty_match = re.search(r'(?:qty|quantity|cantidad)\s+(\d+\.?\d*)', message, re.IGNORECASE)
            qty = float(qty_match.group(1)) if qty_match else None
            result = self.create_stock_entry_manufacture(wo_name, qty)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- TRANSFER MATERIALS ----
        if ("transfer" in message_lower or "issue" in message_lower) and wo_name:
            qty_match = re.search(r'(?:qty|quantity|cantidad)\s+(\d+\.?\d*)', message, re.IGNORECASE)
            qty = float(qty_match.group(1)) if qty_match else None
            result = self.create_material_transfer(wo_name, qty)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- STATUS ----
        if ("status" in message_lower or "estado" in message_lower) and wo_name:
            result = self.get_wo_status(wo_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- CHECK MATERIALS ----
        if ("check" in message_lower or "verify" in message_lower
                or "material" in message_lower) and wo_name:
            result = self.check_materials_availability(wo_name)
            return result.get("message", result.get("error", "Unknown error"))

        # ---- FALLBACK ----
        return self._help_text()

    def _help_text(self) -> str:
        return (
            "🏭 **Manufacturing Agent — Commands**\n\n"
            "**Work Order Creation**\n"
            "`@ai create wo for [ITEM] qty [QTY]` — Create WO (variant→template BOM auto-resolve)\n"
            "`@ai create wo for [ITEM] qty [QTY] bom [BOM-NAME]` — Create WO with specific BOM\n"
            "`@ai create wo from so [SO-NAME]` — Create WO linked to Sales Order\n\n"
            "**Multi-WO Plan (GAP-03)**\n"
            "`@ai wo plan [SO-NAME] each 500` — Split SO into multiple WOs of 500 each\n"
            "`@ai wo plan [SO-NAME]: qty 1055 lote ABC, qty 600 lote DEF` — Custom split with batches\n\n"
            "**Batch Management (GAP-04)**\n"
            "`@ai create batch [NAME] for [ITEM]` — Create named batch/lote\n"
            "`@ai create batch [NAME] for [ITEM] expiry 2027-12-31` — With expiry date\n\n"
            "**Work Order Actions**\n"
            "`@ai submit wo [WO-NAME]` — Submit Work Order\n"
            "`@ai transfer materials [WO-NAME]` — Transfer materials to WIP\n"
            "`@ai manufacture [WO-NAME]` — Create Stock Entry (Manufacture)\n"
            "`@ai manufacture [WO-NAME] qty [QTY]` — Partial manufacture\n\n"
            "**Status & Listing**\n"
            "`@ai show work orders` — List active work orders (ARCH-03)\n"
            "`@ai show work orders for [SO-NAME]` — Filter by Sales Order\n"
            "`@ai status [WO-NAME]` — Detailed WO status with linked docs\n"
            "`@ai check materials [WO-NAME]` — Verify material availability\n\n"
            "**Example (Full Cycle)**\n"
            "```\n"
            "@ai create wo for 0307 qty 150 bom BOM-0307-005\n"
            "@ai submit wo MFG-WO-03726\n"
            "@ai transfer materials MFG-WO-03726\n"
            "@ai manufacture MFG-WO-03726\n"
            "```"
        )
