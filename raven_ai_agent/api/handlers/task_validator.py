"""
Task Validator - Pipeline Diagnosis & Validation

Commands:
  @ai diagnose SAL-QTN-XXXX          → Full pipeline diagnosis from quotation
  @ai validate SO-XXXXX               → Validate SO against its source quotation
  @ai audit pipeline SAL-QTN-XXXX     → Deep audit: QTN → SO → WO → DN → SINV
  @ai check payments SAL-QTN-XXXX     → Verify payment terms consistency

Quotation is the TRUTH SOURCE. Everything downstream must match.
"""
import frappe
import json
import re
from typing import Optional, Dict, List, Tuple
from datetime import datetime


class TaskValidatorMixin:
    """Mixin for pipeline diagnosis and validation — mixed into RaymondLucyAgent"""

    # ─── Fields that MUST match between Quotation and Sales Order ───
    CRITICAL_FIELDS = {
        # Header-level fields
        "header": [
            ("party_name", "customer", "Customer"),
            ("currency", "currency", "Currency"),
            ("selling_price_list", "selling_price_list", "Price List"),
            ("payment_terms_template", "payment_terms_template", "Payment Terms"),
            ("tc_name", "tc_name", "Terms & Conditions"),
            ("incoterm", "incoterm", "Incoterm"),
            ("named_place", "named_place", "Named Place"),
        ],
        # Item-level fields (per row)
        "items": [
            ("item_code", "item_code", "Item Code"),
            ("item_name", "item_name", "Item Name"),
            ("qty", "qty", "Quantity"),
            ("rate", "rate", "Rate"),
            ("uom", "uom", "UOM"),
            ("conversion_factor", "conversion_factor", "Conversion Factor"),
            ("discount_percentage", "discount_percentage", "Discount %"),
        ],
        # Tax/charges
        "taxes": [
            ("charge_type", "charge_type", "Charge Type"),
            ("account_head", "account_head", "Account Head"),
            ("rate", "rate", "Tax Rate"),
            ("tax_amount", "tax_amount", "Tax Amount"),
        ],
        # Payment schedule
        "payment_schedule": [
            ("due_date", "due_date", "Due Date"),
            ("invoice_portion", "invoice_portion", "Invoice Portion %"),
            ("payment_amount", "payment_amount", "Payment Amount"),
        ],
    }

    def _handle_validator_commands(self, query: str, query_lower: str) -> Optional[Dict]:
        """Route validator commands — dispatched from router.py"""
        
        site_name = frappe.local.site

        # ═══════════════════════════════════════════════════════════
        # SYNC/FIX: Apply quotation truth to downstream SO
        # @ai !sync SO-XXXXX from quotation
        # @ai !fix SO-XXXXX from quotation  
        # @ai sync sales order SO-XXXXX
        # ═══════════════════════════════════════════════════════════
        if any(kw in query_lower for kw in ["sync so", "sync sales order", "fix so", "fix sales order"]):
            so_match = re.search(r'(SO-[\w\-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b)[\w\.]+)*|SAL-ORD-\d+-\d+)', query, re.IGNORECASE)
            if so_match:
                is_force = query.strip().startswith("!") or "!fix" in query_lower or "!sync" in query_lower
                return self._sync_so_from_quotation(so_match.group(1), confirm=is_force)
            else:
                return {"success": False, "error": "**Usage:** `@ai !sync SO-XXXXX from quotation`"}

        # ═══════════════════════════════════════════════════════════
        # DIAGNOSE: Full pipeline diagnosis from a quotation
        # @ai diagnose SAL-QTN-XXXX
        # ═══════════════════════════════════════════════════════════
        if "diagnose" in query_lower or "diagnosis" in query_lower:
            qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-[\w\-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b)[\w\.]+)*)', query, re.IGNORECASE)
            wo_match = re.search(r'(MFG-WO-\d+)', query, re.IGNORECASE)
            
            if qtn_match:
                return self._diagnose_from_quotation(qtn_match.group(1).upper())
            elif so_match:
                return self._diagnose_from_sales_order(so_match.group(1).upper())
            elif wo_match:
                return self._diagnose_from_work_order(wo_match.group(1).upper())
            else:
                return {
                    "success": False,
                    "error": "**Usage:** `@ai diagnose SAL-QTN-2024-XXXXX`\n"
                             "or `@ai diagnose SO-XXXXX` or `@ai diagnose MFG-WO-XXXXX`"
                }

        # ═══════════════════════════════════════════════════════════
        # VALIDATE: Check SO against source quotation
        # @ai validate SO-XXXXX
        # ═══════════════════════════════════════════════════════════
        if "validate" in query_lower and "pipeline" not in query_lower:
            so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-[\w\-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b)[\w\.]+)*)', query, re.IGNORECASE)
            qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            
            if so_match:
                return self._validate_sales_order(so_match.group(1).upper())
            elif qtn_match:
                # Validate all SOs linked to this quotation
                return self._validate_quotation_downstream(qtn_match.group(1).upper())
            else:
                return {
                    "success": False,
                    "error": "**Usage:** `@ai validate SO-XXXXX` or `@ai validate SAL-QTN-XXXX`"
                }

        # ═══════════════════════════════════════════════════════════
        # AUDIT PIPELINE: Deep audit across entire flow
        # @ai audit pipeline SAL-QTN-XXXX
        # ═══════════════════════════════════════════════════════════
        if "audit" in query_lower and "pipeline" in query_lower:
            qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            if qtn_match:
                return self._audit_full_pipeline(qtn_match.group(1).upper())
            else:
                return {
                    "success": False,
                    "error": "**Usage:** `@ai audit pipeline SAL-QTN-2024-XXXXX`"
                }

        # ═══════════════════════════════════════════════════════════
        # CHECK PAYMENTS: Verify payment terms consistency
        # @ai check payments SAL-QTN-XXXX
        # ═══════════════════════════════════════════════════════════
        if "check" in query_lower and ("payment" in query_lower or "pago" in query_lower):
            qtn_match = re.search(r'(SAL-QTN-\d+-\d+)', query, re.IGNORECASE)
            so_match = re.search(r'(SAL-ORD-\d+-\d+|SO-[\w\-]+(?:\s+(?!from\b|to\b|pipeline\b|status\b|check\b|audit\b|validate\b|diagnose\b|bom\b|qty\b|quantity\b|item\b|warehouse\b|wh\b)[\w\.]+)*)', query, re.IGNORECASE)
            
            doc_name = None
            doc_type = None
            if qtn_match:
                doc_name = qtn_match.group(1).upper()
                doc_type = "Quotation"
            elif so_match:
                doc_name = so_match.group(1).upper()
                doc_type = "Sales Order"
            
            if doc_name:
                return self._check_payment_terms(doc_name, doc_type)
            else:
                return {
                    "success": False,
                    "error": "**Usage:** `@ai check payments SAL-QTN-XXXX` or `@ai check payments SO-XXXXX`"
                }

        return None

    # ═══════════════════════════════════════════════════════════════
    # CORE: Diagnose from Quotation
    # ═══════════════════════════════════════════════════════════════
    def _diagnose_from_quotation(self, qtn_name: str) -> Dict:
        """Full diagnosis starting from a quotation — trace entire pipeline"""
        site_name = frappe.local.site
        
        try:
            qtn = frappe.get_doc("Quotation", qtn_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Quotation **{qtn_name}** not found."}

        qtn_link = f"https://{site_name}/app/quotation/{qtn_name}"
        issues = []
        warnings = []
        info = []
        pipeline = {}

        # ── Step 1: Quotation Health Check ──
        status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
        qtn_status = status_map.get(qtn.docstatus, "Unknown")
        
        pipeline["quotation"] = {
            "name": qtn_name,
            "status": qtn_status,
            "customer": qtn.party_name,
            "total": qtn.grand_total,
            "currency": qtn.currency,
            "items": len(qtn.items),
        }

        # Check quotation completeness
        if not qtn.party_name:
            issues.append("Quotation has no customer/party set")
        if not qtn.items:
            issues.append("Quotation has no items")
        if qtn.grand_total == 0:
            warnings.append("Quotation total is $0.00")
        if not qtn.payment_terms_template and not qtn.get("payment_schedule"):
            warnings.append("No payment terms set on quotation")
        if not qtn.tc_name:
            warnings.append("No Terms & Conditions template linked")
        if qtn.docstatus == 2:
            issues.append("Quotation is CANCELLED — cannot proceed in pipeline")
        
        # Check valid_till
        if qtn.valid_till:
            if qtn.valid_till < datetime.now().date():
                warnings.append(f"Quotation expired on {qtn.valid_till}")

        # Check items for template vs variant
        for idx, item in enumerate(qtn.items, 1):
            item_doc = frappe.get_doc("Item", item.item_code)
            if item_doc.has_variants:
                issues.append(f"Row {idx}: Item '{item.item_code}' is a TEMPLATE — must use a variant for SO/WO")
            if not item.rate or item.rate == 0:
                warnings.append(f"Row {idx}: Item '{item.item_code}' has rate = 0")
            if not item.qty or item.qty == 0:
                issues.append(f"Row {idx}: Item '{item.item_code}' has qty = 0")

        # ── Step 2: Find linked Sales Orders ──
        linked_sos = frappe.get_all(
            "Sales Order Item",
            filters={"prevdoc_docname": qtn_name},
            fields=["parent"],
            group_by="parent"
        )

        if not linked_sos:
            info.append("No Sales Order created from this quotation yet")
        else:
            for so_row in linked_sos:
                so_name = so_row.parent
                so_result = self._validate_sales_order_against_quotation(so_name, qtn)
                pipeline.setdefault("sales_orders", []).append(so_result)
                issues.extend(so_result.get("issues", []))
                warnings.extend(so_result.get("warnings", []))

                # ── Step 3: Find Work Orders from SO ──
                work_orders = frappe.get_all(
                    "Work Order",
                    filters={"sales_order": so_name, "docstatus": ["<", 2]},
                    fields=["name", "production_item", "qty", "status", "produced_qty"]
                )
                for wo in work_orders:
                    wo_link = f"https://{site_name}/app/work-order/{wo.name}"
                    wo_info = {
                        "name": wo.name,
                        "item": wo.production_item,
                        "qty": wo.qty,
                        "produced": wo.produced_qty,
                        "status": wo.status,
                    }
                    pipeline.setdefault("work_orders", []).append(wo_info)
                    
                    if wo.status == "Not Started":
                        warnings.append(f"WO [{wo.name}]({wo_link}) not started yet")
                    if wo.produced_qty < wo.qty and wo.status == "Completed":
                        issues.append(f"WO [{wo.name}]({wo_link}) marked Complete but produced {wo.produced_qty}/{wo.qty}")

                # ── Step 4: Find Delivery Notes from SO ──
                dn_items = frappe.get_all(
                    "Delivery Note Item",
                    filters={"against_sales_order": so_name, "docstatus": ["<", 2]},
                    fields=["parent", "item_code", "qty"],
                    group_by="parent"
                )
                for dn_row in dn_items:
                    dn = frappe.get_doc("Delivery Note", dn_row.parent)
                    dn_link = f"https://{site_name}/app/delivery-note/{dn.name}"
                    pipeline.setdefault("delivery_notes", []).append({
                        "name": dn.name,
                        "status": status_map.get(dn.docstatus, "Unknown"),
                        "total": dn.grand_total,
                    })

                # ── Step 5: Find Sales Invoices from SO ──
                si_items = frappe.get_all(
                    "Sales Invoice Item",
                    filters={"sales_order": so_name, "docstatus": ["<", 2]},
                    fields=["parent"],
                    group_by="parent"
                )
                for si_row in si_items:
                    si = frappe.get_doc("Sales Invoice", si_row.parent)
                    si_link = f"https://{site_name}/app/sales-invoice/{si.name}"
                    pipeline.setdefault("sales_invoices", []).append({
                        "name": si.name,
                        "status": status_map.get(si.docstatus, "Unknown"),
                        "total": si.grand_total,
                        "outstanding": si.outstanding_amount if hasattr(si, 'outstanding_amount') else None,
                    })

        # ── Build Report ──
        return self._build_diagnosis_report(qtn_name, qtn_link, pipeline, issues, warnings, info)

    def _diagnose_from_sales_order(self, so_name: str) -> Dict:
        """Diagnose starting from a Sales Order — find source QTN and trace forward"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order **{so_name}** not found."}

        # Find source quotation
        qtn_name = None
        for item in so.items:
            if item.prevdoc_docname:
                qtn_name = item.prevdoc_docname
                break

        if qtn_name:
            return self._diagnose_from_quotation(qtn_name)
        else:
            # No quotation found — diagnose SO directly
            site_name = frappe.local.site
            so_link = f"https://{site_name}/app/sales-order/{so_name}"
            return {
                "success": True,
                "message": f"**Sales Order [{so_name}]({so_link})** has no linked Quotation.\n\n"
                           f"Customer: {so.customer}\n"
                           f"Total: {so.currency} {so.grand_total:,.2f}\n"
                           f"Status: {so.status}\n\n"
                           f"⚠️ Cannot validate against quotation (truth source missing)."
            }

    def _diagnose_from_work_order(self, wo_name: str) -> Dict:
        """Diagnose starting from a Work Order — trace back to SO and QTN"""
        try:
            wo = frappe.get_doc("Work Order", wo_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order **{wo_name}** not found."}

        if wo.sales_order:
            return self._diagnose_from_sales_order(wo.sales_order)
        
        site_name = frappe.local.site
        wo_link = f"https://{site_name}/app/work-order/{wo_name}"
        return {
            "success": True,
            "message": f"**Work Order [{wo_name}]({wo_link})** has no linked Sales Order.\n\n"
                       f"Item: {wo.production_item}\n"
                       f"Qty: {wo.qty} / Produced: {wo.produced_qty}\n"
                       f"Status: {wo.status}\n\n"
                       f"⚠️ Standalone WO — cannot trace back to quotation."
        }

    # ═══════════════════════════════════════════════════════════════
    # CORE: Validate Sales Order against Quotation
    # ═══════════════════════════════════════════════════════════════
    def _validate_sales_order(self, so_name: str) -> Dict:
        """Validate a Sales Order against its source quotation"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order **{so_name}** not found."}

        site_name = frappe.local.site
        so_link = f"https://{site_name}/app/sales-order/{so_name}"

        # Find source quotation
        qtn_name = None
        for item in so.items:
            if item.prevdoc_docname:
                qtn_name = item.prevdoc_docname
                break

        if not qtn_name:
            return {
                "success": True,
                "message": f"**SO [{so_name}]({so_link})**: No linked quotation found.\n"
                           f"⚠️ Cannot validate — quotation is the truth source."
            }

        try:
            qtn = frappe.get_doc("Quotation", qtn_name)
        except frappe.DoesNotExistError:
            return {
                "success": False,
                "error": f"Source Quotation **{qtn_name}** not found (but SO references it)."
            }

        result = self._validate_sales_order_against_quotation(so_name, qtn)
        
        qtn_link = f"https://{site_name}/app/quotation/{qtn_name}"
        issues = result.get("issues", [])
        warnings = result.get("warnings", [])
        matches = result.get("matches", [])

        msg = f"## Validation: [{so_name}]({so_link}) vs [{qtn_name}]({qtn_link})\n\n"
        msg += f"**Quotation** is the truth source.\n\n"
        
        if not issues and not warnings:
            msg += "✅ **ALL CHECKS PASSED** — Sales Order matches Quotation perfectly.\n\n"
        
        if issues:
            msg += f"### ❌ Issues ({len(issues)})\n"
            for issue in issues:
                msg += f"- {issue}\n"
            msg += "\n"
        
        if warnings:
            msg += f"### ⚠️ Warnings ({len(warnings)})\n"
            for w in warnings:
                msg += f"- {w}\n"
            msg += "\n"
        
        if matches:
            msg += f"### ✅ Matched ({len(matches)})\n"
            for m in matches[:10]:  # Show first 10
                msg += f"- {m}\n"
            if len(matches) > 10:
                msg += f"- ... and {len(matches) - 10} more\n"

        return {"success": True, "message": msg}

    def _validate_sales_order_against_quotation(self, so_name: str, qtn) -> Dict:
        """Core comparison logic — returns issues, warnings, matches"""
        site_name = frappe.local.site
        
        try:
            so = frappe.get_doc("Sales Order", so_name)
        except frappe.DoesNotExistError:
            return {"issues": [f"Sales Order {so_name} not found"], "warnings": [], "matches": []}

        so_link = f"https://{site_name}/app/sales-order/{so_name}"
        issues = []
        warnings = []
        matches = []

        # ── Header-level comparison ──
        for qtn_field, so_field, label in self.CRITICAL_FIELDS["header"]:
            qtn_val = getattr(qtn, qtn_field, None)
            so_val = getattr(so, so_field, None)
            
            # Normalize for comparison
            qtn_val_str = str(qtn_val or "").strip()
            so_val_str = str(so_val or "").strip()
            
            if qtn_val_str != so_val_str:
                if label in ("Payment Terms", "Terms & Conditions", "Incoterm"):
                    # These are critical — payment terms mismatch is a big deal
                    issues.append(
                        f"**{label}** mismatch: QTN=`{qtn_val_str or '(empty)'}` vs SO=`{so_val_str or '(empty)'}`"
                    )
                elif qtn_val_str and so_val_str:
                    warnings.append(
                        f"**{label}** differs: QTN=`{qtn_val_str}` vs SO=`{so_val_str}`"
                    )
            else:
                if qtn_val_str:
                    matches.append(f"{label}: `{qtn_val_str}`")

        # ── Item-level comparison ──
        qtn_items = {(i.item_code, i.idx): i for i in qtn.items}
        so_items = {(i.item_code, i.idx): i for i in so.items}

        # Check each QTN item exists in SO with correct values
        for (item_code, idx), qtn_item in qtn_items.items():
            # Find matching SO item (by item_code, allow different idx)
            matching_so_item = None
            for (so_item_code, so_idx), so_item in so_items.items():
                if so_item_code == item_code:
                    matching_so_item = so_item
                    break

            if not matching_so_item:
                issues.append(f"Item `{item_code}` (QTN row {idx}) missing from Sales Order")
                continue

            for qtn_field, so_field, label in self.CRITICAL_FIELDS["items"]:
                qtn_val = getattr(qtn_item, qtn_field, None)
                so_val = getattr(matching_so_item, so_field, None)

                # Numeric comparison with tolerance
                if isinstance(qtn_val, (int, float)) and isinstance(so_val, (int, float)):
                    if abs(float(qtn_val) - float(so_val)) > 0.01:
                        if label in ("Quantity", "Rate"):
                            issues.append(
                                f"Item `{item_code}` **{label}**: QTN=`{qtn_val}` vs SO=`{so_val}`"
                            )
                        else:
                            warnings.append(
                                f"Item `{item_code}` {label}: QTN=`{qtn_val}` vs SO=`{so_val}`"
                            )
                    else:
                        matches.append(f"Item `{item_code}` {label}: `{qtn_val}`")
                else:
                    qtn_str = str(qtn_val or "").strip()
                    so_str = str(so_val or "").strip()
                    if qtn_str != so_str:
                        warnings.append(
                            f"Item `{item_code}` {label}: QTN=`{qtn_str}` vs SO=`{so_str}`"
                        )
                    elif qtn_str:
                        matches.append(f"Item `{item_code}` {label}: `{qtn_str}`")

        # Check for extra items in SO not in QTN
        for (item_code, idx), so_item in so_items.items():
            found = any(qtn_ic == item_code for (qtn_ic, _) in qtn_items.keys())
            if not found:
                warnings.append(f"Item `{item_code}` in SO (row {idx}) but NOT in Quotation")

        # ── Tax comparison ──
        if hasattr(qtn, 'taxes') and hasattr(so, 'taxes'):
            qtn_taxes = qtn.taxes or []
            so_taxes = so.taxes or []
            
            if len(qtn_taxes) != len(so_taxes):
                warnings.append(
                    f"Tax rows count differs: QTN has {len(qtn_taxes)}, SO has {len(so_taxes)}"
                )
            
            for idx, (qt, st) in enumerate(zip(qtn_taxes, so_taxes)):
                for qtn_field, so_field, label in self.CRITICAL_FIELDS["taxes"]:
                    qtn_val = getattr(qt, qtn_field, None)
                    so_val = getattr(st, so_field, None)
                    if str(qtn_val or "") != str(so_val or ""):
                        issues.append(
                            f"Tax row {idx+1} **{label}**: QTN=`{qtn_val}` vs SO=`{so_val}`"
                        )

        # ── Payment Schedule comparison ──
        qtn_schedule = getattr(qtn, 'payment_schedule', []) or []
        so_schedule = getattr(so, 'payment_schedule', []) or []
        
        if len(qtn_schedule) != len(so_schedule):
            if qtn_schedule:
                issues.append(
                    f"**Payment Schedule** rows differ: QTN has {len(qtn_schedule)}, SO has {len(so_schedule)}"
                )
        
        for idx, (qp, sp) in enumerate(zip(qtn_schedule, so_schedule)):
            for qtn_field, so_field, label in self.CRITICAL_FIELDS["payment_schedule"]:
                qtn_val = getattr(qp, qtn_field, None)
                so_val = getattr(sp, so_field, None)
                
                if isinstance(qtn_val, (int, float)) and isinstance(so_val, (int, float)):
                    if abs(float(qtn_val) - float(so_val)) > 0.01:
                        issues.append(
                            f"Payment row {idx+1} **{label}**: QTN=`{qtn_val}` vs SO=`{so_val}`"
                        )
                elif str(qtn_val or "") != str(so_val or ""):
                    issues.append(
                        f"Payment row {idx+1} **{label}**: QTN=`{qtn_val}` vs SO=`{so_val}`"
                    )

        # ── Grand Total sanity ──
        if abs(float(qtn.grand_total or 0) - float(so.grand_total or 0)) > 0.01:
            issues.append(
                f"**Grand Total** mismatch: QTN=`{qtn.currency} {qtn.grand_total:,.2f}` "
                f"vs SO=`{so.currency} {so.grand_total:,.2f}`"
            )
        else:
            matches.append(f"Grand Total: `{qtn.currency} {qtn.grand_total:,.2f}`")

        return {
            "so_name": so_name,
            "so_link": so_link,
            "status": so.status,
            "issues": issues,
            "warnings": warnings,
            "matches": matches,
        }

    # ═══════════════════════════════════════════════════════════════
    # VALIDATE: All SOs downstream of a quotation
    # ═══════════════════════════════════════════════════════════════
    def _validate_quotation_downstream(self, qtn_name: str) -> Dict:
        """Validate all Sales Orders linked to a quotation"""
        try:
            qtn = frappe.get_doc("Quotation", qtn_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Quotation **{qtn_name}** not found."}

        site_name = frappe.local.site
        qtn_link = f"https://{site_name}/app/quotation/{qtn_name}"

        linked_sos = frappe.get_all(
            "Sales Order Item",
            filters={"prevdoc_docname": qtn_name},
            fields=["parent"],
            group_by="parent"
        )

        if not linked_sos:
            return {
                "success": True,
                "message": f"**[{qtn_name}]({qtn_link})**: No Sales Orders found.\n"
                           f"Pipeline hasn't progressed past quotation stage."
            }

        msg = f"## Validation Report: [{qtn_name}]({qtn_link})\n\n"
        total_issues = 0
        total_warnings = 0

        for so_row in linked_sos:
            result = self._validate_sales_order_against_quotation(so_row.parent, qtn)
            so_issues = result.get("issues", [])
            so_warnings = result.get("warnings", [])
            total_issues += len(so_issues)
            total_warnings += len(so_warnings)

            so_link = result.get("so_link", "")
            status_icon = "✅" if not so_issues else "❌"
            msg += f"### {status_icon} [{so_row.parent}]({so_link}) — {result.get('status', 'Unknown')}\n"
            
            if so_issues:
                for issue in so_issues:
                    msg += f"- ❌ {issue}\n"
            if so_warnings:
                for w in so_warnings:
                    msg += f"- ⚠️ {w}\n"
            if not so_issues and not so_warnings:
                msg += "- All fields match quotation ✓\n"
            msg += "\n"

        msg += f"---\n**Summary:** {total_issues} issues, {total_warnings} warnings across {len(linked_sos)} Sales Order(s)\n"
        
        return {"success": True, "message": msg}

    # ═══════════════════════════════════════════════════════════════
    # AUDIT: Full pipeline trace
    # ═══════════════════════════════════════════════════════════════
    def _audit_full_pipeline(self, qtn_name: str) -> Dict:
        """Deep audit: check every stage of the pipeline"""
        # This is essentially diagnose + validate combined
        return self._diagnose_from_quotation(qtn_name)

    # ═══════════════════════════════════════════════════════════════
    # CHECK PAYMENTS: Payment terms deep inspection
    # ═══════════════════════════════════════════════════════════════
    def _check_payment_terms(self, doc_name: str, doc_type: str) -> Dict:
        """Deep check of payment terms, schedule, and consistency"""
        site_name = frappe.local.site
        
        try:
            doc = frappe.get_doc(doc_type, doc_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"{doc_type} **{doc_name}** not found."}

        doc_link = f"https://{site_name}/app/{doc_type.lower().replace(' ', '-')}/{doc_name}"
        
        msg = f"## Payment Check: [{doc_name}]({doc_link})\n\n"
        issues = []
        info_items = []

        # Payment Terms Template
        pt_template = doc.payment_terms_template
        if pt_template:
            info_items.append(f"Payment Terms Template: `{pt_template}`")
        else:
            issues.append("No Payment Terms Template set")

        # Payment Schedule
        schedule = getattr(doc, 'payment_schedule', []) or []
        if schedule:
            msg += "### Payment Schedule\n"
            msg += "| # | Due Date | Portion % | Amount | Description |\n"
            msg += "|---|----------|-----------|--------|-------------|\n"
            
            total_portion = 0
            total_amount = 0
            for idx, row in enumerate(schedule, 1):
                due_date = row.due_date or "Not set"
                portion = row.invoice_portion or 0
                amount = row.payment_amount or 0
                desc = getattr(row, 'description', '') or getattr(row, 'payment_term', '') or ''
                total_portion += portion
                total_amount += amount
                msg += f"| {idx} | {due_date} | {portion}% | {doc.currency} {amount:,.2f} | {desc} |\n"
            
            msg += f"| **Total** | | **{total_portion}%** | **{doc.currency} {total_amount:,.2f}** | |\n\n"
            
            # Validate totals
            if abs(total_portion - 100) > 0.01:
                issues.append(f"Payment portions sum to {total_portion}% — should be 100%")
            
            if abs(total_amount - float(doc.grand_total or 0)) > 0.01:
                issues.append(
                    f"Payment amounts sum to {doc.currency} {total_amount:,.2f} "
                    f"but grand total is {doc.currency} {doc.grand_total:,.2f}"
                )
            
            # Check for past-due dates
            today = datetime.now().date()
            for row in schedule:
                if row.due_date and row.due_date < today:
                    issues.append(f"Payment due date {row.due_date} is in the past")
        else:
            issues.append("No payment schedule rows found")

        # If this is a Quotation, also check downstream SOs
        if doc_type == "Quotation":
            linked_sos = frappe.get_all(
                "Sales Order Item",
                filters={"prevdoc_docname": doc_name},
                fields=["parent"],
                group_by="parent"
            )
            
            if linked_sos:
                msg += "### Downstream Sales Orders — Payment Terms Comparison\n\n"
                for so_row in linked_sos:
                    try:
                        so = frappe.get_doc("Sales Order", so_row.parent)
                        so_link = f"https://{site_name}/app/sales-order/{so_row.parent}"
                        so_pt = so.payment_terms_template or "(none)"
                        
                        if (doc.payment_terms_template or "") != (so.payment_terms_template or ""):
                            issues.append(
                                f"[{so_row.parent}]({so_link}): Payment Terms Template = `{so_pt}` "
                                f"≠ QTN `{pt_template or '(none)'}`"
                            )
                        else:
                            info_items.append(f"[{so_row.parent}]({so_link}): Payment terms match ✓")
                        
                        # Compare payment schedules
                        so_schedule = getattr(so, 'payment_schedule', []) or []
                        if len(schedule) != len(so_schedule):
                            issues.append(
                                f"[{so_row.parent}]({so_link}): {len(so_schedule)} payment rows "
                                f"vs QTN {len(schedule)} rows"
                            )
                    except Exception as e:
                        issues.append(f"Could not check {so_row.parent}: {str(e)}")

        # Build final message
        if issues:
            msg += f"### ❌ Issues ({len(issues)})\n"
            for issue in issues:
                msg += f"- {issue}\n"
            msg += "\n"
        
        if info_items:
            msg += f"### ✅ OK\n"
            for item in info_items:
                msg += f"- {item}\n"
            msg += "\n"

        if not issues:
            msg += "✅ **All payment checks passed.**\n"

        return {"success": True, "message": msg}

    # ═══════════════════════════════════════════════════════════════
    # HELPER: Build diagnosis report
    # ═══════════════════════════════════════════════════════════════
    def _build_diagnosis_report(self, qtn_name: str, qtn_link: str, 
                                 pipeline: Dict, issues: List, 
                                 warnings: List, info: List) -> Dict:
        """Format the diagnosis output as a readable report"""
        site_name = frappe.local.site
        qtn_data = pipeline.get("quotation", {})

        msg = f"## Pipeline Diagnosis: [{qtn_name}]({qtn_link})\n\n"
        msg += f"**Customer:** {qtn_data.get('customer', 'N/A')}\n"
        msg += f"**Total:** {qtn_data.get('currency', '')} {qtn_data.get('total', 0):,.2f}\n"
        msg += f"**Items:** {qtn_data.get('items', 0)}\n\n"

        # Pipeline flow visualization
        msg += "### Pipeline Status\n"
        msg += "```\n"
        
        # Quotation
        qtn_icon = "✅" if qtn_data.get("status") == "Submitted" else "📝" if qtn_data.get("status") == "Draft" else "❌"
        msg += f"{qtn_icon} Quotation: {qtn_data.get('status', 'N/A')}\n"
        
        # Sales Orders
        sos = pipeline.get("sales_orders", [])
        if sos:
            for so in sos:
                so_icon = "✅" if not so.get("issues") else "❌"
                msg += f"  └─ {so_icon} SO: {so.get('so_name', 'N/A')} ({so.get('status', 'N/A')})"
                if so.get("issues"):
                    msg += f" — {len(so['issues'])} issue(s)"
                msg += "\n"
        else:
            msg += "  └─ ⏳ No Sales Order yet\n"

        # Work Orders
        wos = pipeline.get("work_orders", [])
        if wos:
            for wo in wos:
                wo_icon = "✅" if wo.get("status") == "Completed" else "🔄" if wo.get("status") == "In Process" else "⏳"
                msg += f"      └─ {wo_icon} WO: {wo.get('name', 'N/A')} ({wo.get('status', 'N/A')}) — {wo.get('produced', 0)}/{wo.get('qty', 0)}\n"

        # Delivery Notes
        dns = pipeline.get("delivery_notes", [])
        if dns:
            for dn in dns:
                dn_icon = "✅" if dn.get("status") == "Submitted" else "📝"
                msg += f"         └─ {dn_icon} DN: {dn.get('name', 'N/A')} ({dn.get('status', 'N/A')})\n"
        elif sos:
            msg += "         └─ ⏳ No Delivery Note yet\n"

        # Sales Invoices
        sis = pipeline.get("sales_invoices", [])
        if sis:
            for si in sis:
                si_icon = "✅" if si.get("status") == "Submitted" else "📝"
                outstanding = f" — Outstanding: {si.get('outstanding', 'N/A')}" if si.get("outstanding") else ""
                msg += f"            └─ {si_icon} SINV: {si.get('name', 'N/A')} ({si.get('status', 'N/A')}){outstanding}\n"
        elif dns:
            msg += "            └─ ⏳ No Sales Invoice yet\n"

        msg += "```\n\n"

        # Issues
        if issues:
            msg += f"### ❌ Issues ({len(issues)})\n"
            for issue in issues:
                msg += f"- {issue}\n"
            msg += "\n"

        # Warnings
        if warnings:
            msg += f"### ⚠️ Warnings ({len(warnings)})\n"
            for w in warnings:
                msg += f"- {w}\n"
            msg += "\n"

        # Info
        if info:
            msg += f"### ℹ️ Info\n"
            for i in info:
                msg += f"- {i}\n"
            msg += "\n"

        # Summary + INTELLIGENT ACTIONS
        if not issues and not warnings:
            msg += "### ✅ All checks passed — pipeline is healthy.\n"
        else:
            msg += f"---\n**Summary:** {len(issues)} issue(s), {len(warnings)} warning(s)\n\n"
            
            # Generate actionable recommendations
            msg += "### 🤖 Recommended Actions\n"
            
            # If SO exists with issues, offer to sync
            sos = pipeline.get("sales_orders", [])
            for so in sos:
                if so.get("issues"):
                    so_name = so.get("so_name", "")
                    so_status = so.get("status", "")
                    issue_count = len(so.get("issues", []))
                    
                    # Check if SO is in Draft (can be modified)
                    if so_status == "Draft":
                        msg += (f"\n**SO [{so_name}]** has {issue_count} issue(s) vs Quotation (truth source).\n"
                                f"The SO is in Draft — I can sync it to match the Quotation.\n\n"
                                f"👉 Say `@ai !sync SO {so_name} from quotation` to auto-fix all mismatches\n"
                                f"👉 Or `@ai sync SO {so_name} from quotation` to preview changes first\n")
                    elif so_status == "Submitted":
                        msg += (f"\n**SO [{so_name}]** has {issue_count} issue(s) but is **Submitted**.\n"
                                f"⚠️ Cannot auto-fix a submitted SO. Options:\n"
                                f"1. Amend the SO in ERPNext (Menu → Amend)\n"
                                f"2. Cancel and recreate from quotation: `@ai !sales order {qtn_name}`\n")
                    else:
                        msg += f"\n**SO [{so_name}]** has {issue_count} issue(s). Status: {so_status}\n"
            
            # If no SO exists yet
            if not sos:
                qtn_status = pipeline.get("quotation", {}).get("status", "")
                if qtn_status == "Draft":
                    msg += (f"\nNo Sales Order exists yet. Next steps:\n"
                            f"1. Review and submit the quotation: `@ai !submit quotation {qtn_name}`\n"
                            f"2. Create SO: `@ai !sales order {qtn_name}`\n")
                elif qtn_status == "Submitted":
                    msg += f"\nQuotation is Submitted. Create SO: `@ai !sales order {qtn_name}`\n"
            
            # Pipeline progression suggestions
            if sos and not pipeline.get("work_orders"):
                for so in sos:
                    if so.get("status") in ("To Deliver and Bill", "To Deliver"):
                        msg += f"\n📦 SO is ready — create Work Order: `@ai !work order {so.get('so_name', '')}`\n"
            
            if pipeline.get("work_orders") and not pipeline.get("delivery_notes"):
                for wo in pipeline["work_orders"]:
                    if wo.get("status") == "Completed":
                        msg += f"\n🚚 WO completed — create Delivery Note: `@ai !delivery {sos[0].get('so_name', '') if sos else ''}`\n"
                    elif wo.get("status") == "Not Started":
                        msg += f"\n⚙️ WO not started — transfer materials: `@ai transfer materials {wo.get('name', '')}`\n"

        return {"success": True, "message": msg}

    # ═══════════════════════════════════════════════════════════════
    # SYNC: Apply Quotation truth to Sales Order
    # ═══════════════════════════════════════════════════════════════
    def _sync_so_from_quotation(self, so_name: str, confirm: bool = False) -> Dict:
        """Sync a Sales Order to match its source Quotation (truth source)"""
        site_name = frappe.local.site
        
        try:
            so = frappe.get_doc("Sales Order", so_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order **{so_name}** not found."}

        so_link = f"https://{site_name}/app/sales-order/{so_name}"

        # SO must be in Draft to modify
        if so.docstatus != 0:
            return {
                "success": False,
                "error": f"SO [{so_name}]({so_link}) is **{'Submitted' if so.docstatus == 1 else 'Cancelled'}**.\n"
                         f"Only Draft SOs can be synced. Amend it first in ERPNext."
            }

        # Find source quotation
        qtn_name = None
        for item in so.items:
            if item.prevdoc_docname:
                qtn_name = item.prevdoc_docname
                break

        if not qtn_name:
            return {"success": False, "error": f"SO [{so_name}]({so_link}) has no linked Quotation."}

        try:
            qtn = frappe.get_doc("Quotation", qtn_name)
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Source Quotation **{qtn_name}** not found."}

        qtn_link = f"https://{site_name}/app/quotation/{qtn_name}"

        # Build change plan
        changes = []

        # Header fields
        for qtn_field, so_field, label in self.CRITICAL_FIELDS["header"]:
            qtn_val = getattr(qtn, qtn_field, None)
            so_val = getattr(so, so_field, None)
            qtn_str = str(qtn_val or "").strip()
            so_str = str(so_val or "").strip()
            if qtn_str != so_str:
                changes.append({
                    "type": "header",
                    "field": so_field,
                    "label": label,
                    "from": so_str or "(empty)",
                    "to": qtn_str or "(empty)",
                    "value": qtn_val,
                })

        # Item fields
        for qtn_item in qtn.items:
            matching_so_item = None
            for so_item in so.items:
                if so_item.item_code == qtn_item.item_code:
                    matching_so_item = so_item
                    break
            if not matching_so_item:
                continue

            for qtn_field, so_field, label in self.CRITICAL_FIELDS["items"]:
                qtn_val = getattr(qtn_item, qtn_field, None)
                so_val = getattr(matching_so_item, so_field, None)
                if isinstance(qtn_val, (int, float)) and isinstance(so_val, (int, float)):
                    if abs(float(qtn_val) - float(so_val)) > 0.01:
                        changes.append({
                            "type": "item",
                            "item_code": qtn_item.item_code,
                            "field": so_field,
                            "label": label,
                            "from": str(so_val),
                            "to": str(qtn_val),
                            "value": qtn_val,
                            "so_item_idx": matching_so_item.idx,
                        })
                else:
                    qtn_str = str(qtn_val or "").strip()
                    so_str = str(so_val or "").strip()
                    if qtn_str != so_str:
                        changes.append({
                            "type": "item",
                            "item_code": qtn_item.item_code,
                            "field": so_field,
                            "label": label,
                            "from": so_str or "(empty)",
                            "to": qtn_str or "(empty)",
                            "value": qtn_val,
                            "so_item_idx": matching_so_item.idx,
                        })

        # Payment schedule sync
        schedule_change = False
        qtn_schedule = getattr(qtn, 'payment_schedule', []) or []
        so_schedule = getattr(so, 'payment_schedule', []) or []
        if len(qtn_schedule) != len(so_schedule):
            schedule_change = True
        else:
            for qp, sp in zip(qtn_schedule, so_schedule):
                for qtn_field, so_field, label in self.CRITICAL_FIELDS["payment_schedule"]:
                    qv = getattr(qp, qtn_field, None)
                    sv = getattr(sp, so_field, None)
                    if str(qv or "") != str(sv or ""):
                        schedule_change = True
                        break
        if schedule_change:
            changes.append({
                "type": "payment_schedule",
                "label": "Payment Schedule",
                "from": f"{len(so_schedule)} row(s)",
                "to": f"{len(qtn_schedule)} row(s) from Quotation",
            })

        if not changes:
            return {
                "success": True,
                "message": f"✅ SO [{so_name}]({so_link}) already matches Quotation [{qtn_name}]({qtn_link}). No changes needed."
            }

        # ── Preview mode (no ! prefix) ──
        if not confirm:
            msg = f"## Sync Plan: [{so_name}]({so_link}) ← [{qtn_name}]({qtn_link})\n\n"
            msg += f"**{len(changes)} change(s)** will be applied to match the Quotation (truth source):\n\n"
            msg += "| # | Field | Current (SO) | New (from QTN) |\n"
            msg += "|---|-------|-------------|----------------|\n"
            for idx, c in enumerate(changes, 1):
                item_prefix = f"`{c['item_code']}` " if c.get("item_code") else ""
                msg += f"| {idx} | {item_prefix}**{c['label']}** | `{c['from']}` | `{c['to']}` |\n"
            msg += f"\n👉 Say `@ai !sync SO {so_name} from quotation` to apply these changes\n"
            return {"success": True, "message": msg}

        # ── Execute sync ──
        try:
            applied = []

            for c in changes:
                if c["type"] == "header":
                    setattr(so, c["field"], c["value"])
                    applied.append(f"Header `{c['label']}`: `{c['from']}` → `{c['to']}`")

                elif c["type"] == "item":
                    for so_item in so.items:
                        if so_item.idx == c.get("so_item_idx"):
                            setattr(so_item, c["field"], c["value"])
                            applied.append(f"Item `{c['item_code']}` `{c['label']}`: `{c['from']}` → `{c['to']}`")
                            break

                elif c["type"] == "payment_schedule":
                    # Replace SO payment schedule with QTN's
                    so.payment_schedule = []
                    so.payment_terms_template = qtn.payment_terms_template
                    for qp in qtn_schedule:
                        so.append("payment_schedule", {
                            "due_date": qp.due_date,
                            "invoice_portion": qp.invoice_portion,
                            "payment_amount": qp.payment_amount,
                            "description": getattr(qp, 'description', ''),
                            "payment_term": getattr(qp, 'payment_term', ''),
                        })
                    applied.append(f"Payment Schedule: replaced with {len(qtn_schedule)} row(s) from Quotation")

            so.flags.ignore_validate = True
            so.save()
            frappe.db.commit()
            frappe.clear_cache(doctype="Sales Order")

            msg = f"## ✅ Synced: [{so_name}]({so_link}) ← [{qtn_name}]({qtn_link})\n\n"
            msg += f"**{len(applied)} change(s) applied:**\n\n"
            for a in applied:
                msg += f"- ✅ {a}\n"
            msg += f"\n⚠️ Hard-refresh your browser (Ctrl+Shift+R) to see changes.\n"
            msg += f"\n👉 Re-check: `@ai diagnose {qtn_name}`\n"
            return {"success": True, "message": msg}

        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": f"Sync failed: {str(e)}"}
