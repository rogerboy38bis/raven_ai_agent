"""
Quality Management Agent - Phase 3: QMS Implementation
Handles quality management commands for AMB Wellness.

Features:
- Quality Document Configuration (SOPs, numbering, approval workflows)
- Non-Conformity (NC) logging with RCA and CAPA tracking
- Internal Audit scheduling and reporting
- Quality KPI dashboards
- Training matrix and competency tracking

Commands:
  @ai quality setup status       — Show QMS configuration status
  @ai quality create sop [name]  — Create SOP document
  @ai quality create nc [subject] — Log non-conformity
  @ai quality nc status          — Show NC/CAPA status
  @ai quality audit schedule     — Show audit schedule
  @ai quality audit create [name] — Create audit
  @ai quality kpi dashboard      — Show quality KPIs
  @ai quality training matrix    — Show training matrix
  @ai quality training create [name] — Create training program
"""
import frappe
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class QualityManagementMixin:
    """
    Mixin that adds Quality Management System commands to the agent.
    Requires: self.user
    """

    def _handle_quality_commands(self, query: str, query_lower: str, is_confirm: bool = False) -> Optional[Dict]:
        """Route quality management commands"""

        if not any(kw in query_lower for kw in [
            "quality", "calidad", "sop", "non conform", "no conformidad",
            "audit", "auditoría", "auditoria", "kpi", "training", "capacitación",
            "capacitacion", "competenc", "nc ", "capa", "inspection template"
        ]):
            return None

        # ── QMS Setup Status ─────────────────────────────────────────
        if any(kw in query_lower for kw in ["setup status", "qms status", "estado calidad", "quality status"]):
            return self._quality_setup_status()

        # ── Non-Conformity Commands ──────────────────────────────────
        if "create nc" in query_lower or "crear no conformidad" in query_lower or "log nc" in query_lower:
            return self._create_non_conformance(query, is_confirm)

        if ("nc status" in query_lower or "nc list" in query_lower or
                "no conformidad" in query_lower and "list" in query_lower):
            return self._list_non_conformances()

        if "nc dashboard" in query_lower or "nc trend" in query_lower:
            return self._nc_dashboard()

        # ── CAPA Commands ────────────────────────────────────────────
        if "capa" in query_lower and ("overdue" in query_lower or "pending" in query_lower or "vencid" in query_lower):
            return self._capa_status()

        if "create capa" in query_lower or "crear capa" in query_lower:
            return self._create_quality_action(query, is_confirm)

        # ── SOP / Quality Procedure Commands ─────────────────────────
        if "create sop" in query_lower or "crear sop" in query_lower or "create procedure" in query_lower:
            return self._create_quality_procedure(query, is_confirm)

        if "list sop" in query_lower or "show sop" in query_lower or "show procedure" in query_lower:
            return self._list_quality_procedures()

        # ── Audit Commands ───────────────────────────────────────────
        if "audit schedule" in query_lower or "programa auditoría" in query_lower:
            return self._audit_schedule()

        if "create audit" in query_lower or "crear auditoría" in query_lower:
            return self._create_audit(query, is_confirm)

        if "audit finding" in query_lower or "hallazgo" in query_lower:
            return self._audit_findings()

        # ── KPI / Dashboard ──────────────────────────────────────────
        if "kpi" in query_lower or "dashboard" in query_lower or "indicador" in query_lower:
            return self._quality_kpi_dashboard()

        # ── Training Commands ────────────────────────────────────────
        if "training matrix" in query_lower or "matriz capacitación" in query_lower:
            return self._training_matrix()

        if "create training" in query_lower or "crear capacitación" in query_lower:
            return self._create_training_program(query, is_confirm)

        if "training status" in query_lower or "estado capacitación" in query_lower:
            return self._training_status()

        # ── Quality Inspection Templates ─────────────────────────────
        if "inspection template" in query_lower or "plantilla inspección" in query_lower:
            return self._list_inspection_templates()

        # ── Quality Review ───────────────────────────────────────────
        if "quality review" in query_lower or "revisión calidad" in query_lower:
            return self._quality_review()

        return None

    # ══════════════════════════════════════════════════════════════════
    # Setup Status
    # ══════════════════════════════════════════════════════════════════

    def _quality_setup_status(self) -> Dict:
        """Show overall QMS configuration status"""
        counts = {}
        doctypes = [
            ("Quality Procedure", "SOPs/Procedures"),
            ("Quality Goal", "Quality Goals"),
            ("Quality Inspection", "Inspections"),
            ("Quality Inspection Template", "Inspection Templates"),
            ("Non Conformance", "Non-Conformances"),
            ("Quality Action", "CAPA Actions"),
            ("Quality Review", "Quality Reviews"),
            ("Quality Meeting", "Quality Meetings"),
            ("Quality Feedback", "Feedback"),
            ("Training Program", "Training Programs"),
            ("Training Event", "Training Events"),
        ]

        for doctype, label in doctypes:
            try:
                count = frappe.db.count(doctype)
                counts[label] = count
            except Exception:
                counts[label] = "N/A"

        # Build status report
        lines = ["## 📊 QMS Configuration Status\n"]
        lines.append("| Module | Records | Status |")
        lines.append("|--------|---------|--------|")

        for label, count in counts.items():
            if count == "N/A":
                status = "⚪ Not Available"
            elif count == 0:
                status = "🔴 Not Configured"
            elif count < 5:
                status = "🟡 In Progress"
            else:
                status = "🟢 Active"
            lines.append(f"| {label} | {count} | {status} |")

        # Subtask progress
        lines.append("\n### Phase 3 Subtask Progress")
        lines.append("| Subtask | Status |")
        lines.append("|---------|--------|")

        st1 = "🟢 Done" if counts.get("SOPs/Procedures", 0) >= 10 else "🟡 In Progress" if counts.get("SOPs/Procedures", 0) > 0 else "🔴 Pending"
        st2 = "🟢 Done" if counts.get("Non-Conformances", 0) > 0 or counts.get("CAPA Actions", 0) > 0 else "🔴 Pending"
        st3 = "🟢 Done" if counts.get("Quality Meetings", 0) > 0 else "🔴 Pending"
        st4 = "🟢 Done" if counts.get("Quality Goals", 0) >= 5 else "🟡 In Progress" if counts.get("Quality Goals", 0) > 0 else "🔴 Pending"
        st5 = "🟢 Done" if counts.get("Training Programs", 0) > 0 else "🔴 Pending"

        lines.append(f"| 1. Document Configuration | {st1} |")
        lines.append(f"| 2. Non-Conformity System | {st2} |")
        lines.append(f"| 3. Internal Audits | {st3} |")
        lines.append(f"| 4. Management KPIs | {st4} |")
        lines.append(f"| 5. Training & Competencies | {st5} |")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Non-Conformity
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _sanitize_name(text: str, max_len: int = 140) -> str:
        """Truncate and clean text for ERPNext name/subject fields"""
        # Take only the first line
        text = text.split('\n')[0].strip()
        # Remove any trailing bot/menu artifacts
        for stop in ['Ready to test', 'Would you like', '1.', '2.', '3.', '\n']:
            idx = text.find(stop)
            if idx > 0:
                text = text[:idx].strip()
        if len(text) > max_len:
            text = text[:max_len - 3].strip() + '...'
        return text or "Untitled"

    def _create_non_conformance(self, query: str, is_confirm: bool) -> Dict:
        """Create a Non Conformance record"""
        import re

        # Extract subject from query
        subject_match = re.search(r'(?:create nc|log nc|crear no conformidad)\s+(.+)', query, re.IGNORECASE)
        subject = self._sanitize_name(subject_match.group(1)) if subject_match else "New Non-Conformance"

        # Get first quality procedure for linking
        procedures = frappe.get_list("Quality Procedure", limit=1, fields=["name"])
        procedure = procedures[0]["name"] if procedures else None

        if not is_confirm:
            preview = f"📋 **Create Non-Conformance?**\n"
            preview += f"  Subject: {subject}\n"
            preview += f"  Status: Open\n"
            preview += f"  Process Owner: {self.user}\n"
            if procedure:
                preview += f"  Linked Procedure: {procedure}\n"
            preview += f"\nUse `!` prefix to execute directly."
            return {"requires_confirmation": True, "preview": preview}

        try:
            nc_doc = frappe.get_doc({
                "doctype": "Non Conformance",
                "subject": subject,
                "status": "Open",
                "process_owner": frappe.get_value("Employee", {"user_id": self.user}, "employee_name") or self.user,
                "procedure": procedure,
                "details": f"Non-conformance logged via AI Agent on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            })
            nc_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            site = frappe.local.site
            return {
                "success": True,
                "message": f"✅ Non-Conformance **{nc_doc.name}** created\n"
                           f"  Subject: {subject}\n"
                           f"  Status: Open\n"
                           f"  Link: https://{site}/app/non-conformance/{nc_doc.name}\n\n"
                           f"Next: Add corrective/preventive actions with `@ai create capa for {nc_doc.name}`",
                "link_doctype": "Non Conformance",
                "link_document": nc_doc.name,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create NC: {str(e)}"}

    def _list_non_conformances(self) -> Dict:
        """List Non-Conformance records"""
        ncs = frappe.get_list(
            "Non Conformance",
            fields=["name", "subject", "status", "process_owner", "creation"],
            order_by="creation desc",
            limit=20
        )

        if not ncs:
            return {"success": True, "message": "📋 No non-conformances recorded yet.\nUse `@ai create nc [subject]` to log one."}

        lines = ["## 📋 Non-Conformances\n"]
        lines.append("| # | Subject | Status | Owner | Date |")
        lines.append("|---|---------|--------|-------|------|")

        site = frappe.local.site
        for nc in ncs:
            link = f"[{nc['name']}](https://{site}/app/non-conformance/{nc['name']})"
            date = nc["creation"].strftime("%Y-%m-%d") if nc.get("creation") else ""
            lines.append(f"| {link} | {nc.get('subject', '')} | {nc.get('status', '')} | {nc.get('process_owner', '')} | {date} |")

        return {"success": True, "message": "\n".join(lines)}

    def _nc_dashboard(self) -> Dict:
        """Non-Conformance trend dashboard"""
        # Count by status
        statuses = frappe.db.sql("""
            SELECT status, COUNT(*) as cnt
            FROM `tabNon Conformance`
            GROUP BY status
        """, as_dict=True)

        # Count by month (last 6 months)
        monthly = frappe.db.sql("""
            SELECT DATE_FORMAT(creation, '%%Y-%%m') as month, COUNT(*) as cnt
            FROM `tabNon Conformance`
            WHERE creation >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
            GROUP BY month
            ORDER BY month
        """, as_dict=True)

        lines = ["## 📊 NC Trend Dashboard\n"]

        if statuses:
            lines.append("### By Status")
            lines.append("| Status | Count |")
            lines.append("|--------|-------|")
            for s in statuses:
                lines.append(f"| {s['status']} | {s['cnt']} |")
        else:
            lines.append("No non-conformances recorded yet.")

        if monthly:
            lines.append("\n### Monthly Trend")
            lines.append("| Month | Count |")
            lines.append("|-------|-------|")
            for m in monthly:
                lines.append(f"| {m['month']} | {m['cnt']} |")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # CAPA (Quality Actions)
    # ══════════════════════════════════════════════════════════════════

    def _capa_status(self) -> Dict:
        """Show CAPA status including overdue actions"""
        actions = frappe.get_list(
            "Quality Action",
            fields=["name", "status", "modified", "corrective_preventive"],
            order_by="modified desc",
            limit=20
        )

        if not actions:
            return {"success": True, "message": "📋 No CAPA actions recorded yet."}

        lines = ["## 🔧 CAPA Status\n"]
        lines.append("| Action | Type | Status | Last Updated |")
        lines.append("|--------|------|--------|--------------|")

        site = frappe.local.site
        for a in actions:
            link = f"[{a['name']}](https://{site}/app/quality-action/{a['name']})"
            modified = a["modified"].strftime("%Y-%m-%d") if a.get("modified") else ""
            lines.append(f"| {link} | {a.get('corrective_preventive', '')} | {a.get('status', '')} | {modified} |")

        return {"success": True, "message": "\n".join(lines)}

    def _create_quality_action(self, query: str, is_confirm: bool) -> Dict:
        """Create a Quality Action (CAPA)"""
        import re

        # Try to extract NC reference
        nc_match = re.search(r'(?:for|para)\s+(QA-NC-\d+|NC-\d+|[\w-]+)', query, re.IGNORECASE)
        nc_ref = nc_match.group(1) if nc_match else None

        if not is_confirm:
            preview = f"📋 **Create Quality Action (CAPA)?**\n"
            preview += f"  Type: Corrective\n"
            if nc_ref:
                preview += f"  Linked NC: {nc_ref}\n"
            preview += f"\nUse `!` prefix to execute directly."
            return {"requires_confirmation": True, "preview": preview}

        try:
            action_doc = frappe.get_doc({
                "doctype": "Quality Action",
                "corrective_preventive": "Corrective",
                "status": "Open",
            })
            if nc_ref and frappe.db.exists("Non Conformance", nc_ref):
                action_doc.non_conformance = nc_ref
            action_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            site = frappe.local.site
            return {
                "success": True,
                "message": f"✅ Quality Action **{action_doc.name}** created\n"
                           f"  Type: Corrective\n"
                           f"  Status: Open\n"
                           f"  Link: https://{site}/app/quality-action/{action_doc.name}",
                "link_doctype": "Quality Action",
                "link_document": action_doc.name,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create CAPA: {str(e)}"}

    # ══════════════════════════════════════════════════════════════════
    # SOPs / Quality Procedures
    # ══════════════════════════════════════════════════════════════════

    def _create_quality_procedure(self, query: str, is_confirm: bool) -> Dict:
        """Create a Quality Procedure (SOP)"""
        import re

        name_match = re.search(r'(?:create sop|create procedure|crear sop)\s+(.+)', query, re.IGNORECASE)
        proc_name = self._sanitize_name(name_match.group(1)) if name_match else "New SOP"

        if not is_confirm:
            preview = f"📋 **Create Quality Procedure?**\n"
            preview += f"  Name: {proc_name}\n"
            preview += f"\nUse `!` prefix to execute directly."
            return {"requires_confirmation": True, "preview": preview}

        try:
            proc_doc = frappe.get_doc({
                "doctype": "Quality Procedure",
                "procedure_name": proc_name,
            })
            proc_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            site = frappe.local.site
            return {
                "success": True,
                "message": f"✅ Quality Procedure **{proc_doc.name}** created\n"
                           f"  Name: {proc_name}\n"
                           f"  Link: https://{site}/app/quality-procedure/{proc_doc.name}",
                "link_doctype": "Quality Procedure",
                "link_document": proc_doc.name,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create SOP: {str(e)}"}

    def _list_quality_procedures(self) -> Dict:
        """List Quality Procedures"""
        procs = frappe.get_list(
            "Quality Procedure",
            fields=["name", "procedure_name", "modified"],
            order_by="modified desc",
            limit=20
        )

        if not procs:
            return {"success": True, "message": "📋 No quality procedures found.\nUse `@ai create sop [name]` to create one."}

        lines = ["## 📋 Quality Procedures (SOPs)\n"]
        lines.append("| # | Name | Last Updated |")
        lines.append("|---|------|--------------|")

        site = frappe.local.site
        for p in procs:
            link = f"[{p['name']}](https://{site}/app/quality-procedure/{p['name']})"
            modified = p["modified"].strftime("%Y-%m-%d") if p.get("modified") else ""
            lines.append(f"| {link} | {p.get('procedure_name', '')} | {modified} |")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Audits
    # ══════════════════════════════════════════════════════════════════

    def _audit_schedule(self) -> Dict:
        """Show internal audit schedule (via Quality Meetings)"""
        meetings = frappe.get_list(
            "Quality Meeting",
            fields=["name", "status", "modified"],
            order_by="modified desc",
            limit=20
        )

        if not meetings:
            return {
                "success": True,
                "message": "📅 No audits scheduled yet.\n"
                           "Use `@ai create audit [name]` to schedule one.\n\n"
                           "ERPNext uses **Quality Meeting** doctype for audit scheduling."
            }

        lines = ["## 📅 Audit Schedule\n"]
        lines.append("| Meeting | Status | Date |")
        lines.append("|---------|--------|------|")

        site = frappe.local.site
        for m in meetings:
            link = f"[{m['name']}](https://{site}/app/quality-meeting/{m['name']})"
            modified = m["modified"].strftime("%Y-%m-%d") if m.get("modified") else ""
            lines.append(f"| {link} | {m.get('status', '')} | {modified} |")

        return {"success": True, "message": "\n".join(lines)}

    def _create_audit(self, query: str, is_confirm: bool) -> Dict:
        """Create an internal audit (Quality Meeting)"""
        import re

        name_match = re.search(r'(?:create audit|crear auditoría)\s+(.+)', query, re.IGNORECASE)
        audit_name = self._sanitize_name(name_match.group(1)) if name_match else "Internal Audit"

        if not is_confirm:
            preview = f"📅 **Create Internal Audit?**\n"
            preview += f"  Subject: {audit_name}\n"
            preview += f"  Status: Open\n"
            preview += f"\nUse `!` prefix to execute directly."
            return {"requires_confirmation": True, "preview": preview}

        try:
            meeting_doc = frappe.get_doc({
                "doctype": "Quality Meeting",
                "status": "Open",
            })
            meeting_doc.append("agenda", {
                "agenda": audit_name,
            })
            meeting_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            site = frappe.local.site
            return {
                "success": True,
                "message": f"✅ Audit **{meeting_doc.name}** created\n"
                           f"  Subject: {audit_name}\n"
                           f"  Status: Open\n"
                           f"  Link: https://{site}/app/quality-meeting/{meeting_doc.name}",
                "link_doctype": "Quality Meeting",
                "link_document": meeting_doc.name,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create audit: {str(e)}"}

    def _audit_findings(self) -> Dict:
        """Show audit findings (from Quality Meeting minutes)"""
        minutes = frappe.db.sql("""
            SELECT qm.name as meeting, qmm.minute
            FROM `tabQuality Meeting` qm
            JOIN `tabQuality Meeting Minutes` qmm ON qmm.parent = qm.name
            ORDER BY qm.modified DESC
            LIMIT 20
        """, as_dict=True)

        if not minutes:
            return {"success": True, "message": "📋 No audit findings recorded yet."}

        lines = ["## 🔍 Audit Findings\n"]
        for m in minutes:
            lines.append(f"**{m['meeting']}**: {m.get('minute', 'No details')}\n")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # KPI Dashboard
    # ══════════════════════════════════════════════════════════════════

    def _quality_kpi_dashboard(self) -> Dict:
        """Quality KPI dashboard with key metrics"""
        kpis = {}

        # NC metrics
        kpis["Total NCs"] = frappe.db.count("Non Conformance")
        kpis["Open NCs"] = frappe.db.count("Non Conformance", {"status": "Open"})
        kpis["Closed NCs"] = frappe.db.count("Non Conformance", {"status": "Closed"})

        # CAPA metrics
        kpis["Total CAPAs"] = frappe.db.count("Quality Action")
        kpis["Open CAPAs"] = frappe.db.count("Quality Action", {"status": "Open"})

        # Inspection metrics
        kpis["Total Inspections"] = frappe.db.count("Quality Inspection")
        kpis["Accepted"] = frappe.db.count("Quality Inspection", {"status": "Accepted"})
        kpis["Rejected"] = frappe.db.count("Quality Inspection", {"status": "Rejected"})

        # Procedure metrics
        kpis["SOPs"] = frappe.db.count("Quality Procedure")
        kpis["Quality Goals"] = frappe.db.count("Quality Goal")

        # Training metrics
        kpis["Training Programs"] = frappe.db.count("Training Program")
        kpis["Training Events"] = frappe.db.count("Training Event")

        # Calculate rates
        total_insp = kpis["Total Inspections"]
        accept_rate = f"{(kpis['Accepted'] / total_insp * 100):.1f}%" if total_insp > 0 else "N/A"
        nc_close_rate = f"{(kpis['Closed NCs'] / kpis['Total NCs'] * 100):.1f}%" if kpis['Total NCs'] > 0 else "N/A"

        lines = ["## 📊 Quality KPI Dashboard\n"]
        lines.append("### Inspection Performance")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total Inspections | {kpis['Total Inspections']} |")
        lines.append(f"| Acceptance Rate | {accept_rate} |")
        lines.append(f"| Rejected | {kpis['Rejected']} |")

        lines.append(f"\n### Non-Conformity")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Total NCs | {kpis['Total NCs']} |")
        lines.append(f"| Open | {kpis['Open NCs']} |")
        lines.append(f"| Close Rate | {nc_close_rate} |")
        lines.append(f"| Open CAPAs | {kpis['Open CAPAs']} |")

        lines.append(f"\n### Documentation")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| SOPs | {kpis['SOPs']} |")
        lines.append(f"| Quality Goals | {kpis['Quality Goals']} |")
        lines.append(f"| Training Programs | {kpis['Training Programs']} |")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Training & Competencies
    # ══════════════════════════════════════════════════════════════════

    def _training_matrix(self) -> Dict:
        """Show training matrix by department/role"""
        # Get employees with training data
        employees = frappe.db.sql("""
            SELECT e.name, e.employee_name, e.designation, e.department,
                   COUNT(te.name) as training_count
            FROM `tabEmployee` e
            LEFT JOIN `tabTraining Event Employee` tee ON tee.employee = e.name
            LEFT JOIN `tabTraining Event` te ON te.name = tee.parent
            GROUP BY e.name, e.employee_name, e.designation, e.department
            ORDER BY e.department, e.employee_name
            LIMIT 30
        """, as_dict=True)

        if not employees:
            return {"success": True, "message": "📋 No employees found for training matrix.\nEnsure employees are set up in HR module."}

        lines = ["## 📚 Training Matrix\n"]
        lines.append("| Employee | Designation | Department | Trainings |")
        lines.append("|----------|-------------|------------|-----------|")

        for emp in employees:
            count = emp.get("training_count", 0)
            status = "🟢" if count >= 3 else "🟡" if count >= 1 else "🔴"
            lines.append(
                f"| {emp.get('employee_name', '')} | {emp.get('designation', '')} | "
                f"{emp.get('department', '')} | {status} {count} |"
            )

        # Training Programs
        programs = frappe.get_list(
            "Training Program",
            fields=["name", "modified"],
            order_by="modified desc",
            limit=10
        )

        if programs:
            lines.append(f"\n### Active Training Programs")
            site = frappe.local.site
            for p in programs:
                lines.append(f"- [{p['name']}](https://{site}/app/training-program/{p['name']})")
        else:
            lines.append("\n⚠️ No training programs defined yet. Use `@ai create training [name]` to create one.")

        return {"success": True, "message": "\n".join(lines)}

    def _create_training_program(self, query: str, is_confirm: bool) -> Dict:
        """Create a Training Program"""
        import re

        name_match = re.search(r'(?:create training|crear capacitación)\s+(.+)', query, re.IGNORECASE)
        prog_name = self._sanitize_name(name_match.group(1)) if name_match else "New Training Program"

        if not is_confirm:
            preview = f"📚 **Create Training Program?**\n"
            preview += f"  Name: {prog_name}\n"
            preview += f"\nUse `!` prefix to execute directly."
            return {"requires_confirmation": True, "preview": preview}

        try:
            # Get default company
            company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")

            prog_doc = frappe.get_doc({
                "doctype": "Training Program",
                "training_program": prog_name,
                "company": company,
                "description": f"Training program: {prog_name}. Created via AI Agent.",
            })
            prog_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            site = frappe.local.site
            return {
                "success": True,
                "message": f"✅ Training Program **{prog_doc.name}** created\n"
                           f"  Name: {prog_name}\n"
                           f"  Link: https://{site}/app/training-program/{prog_doc.name}",
                "link_doctype": "Training Program",
                "link_document": prog_doc.name,
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to create training program: {str(e)}"}

    def _training_status(self) -> Dict:
        """Show training completion status"""
        events = frappe.get_list(
            "Training Event",
            fields=["name", "event_name", "event_status", "type", "modified"],
            order_by="modified desc",
            limit=20
        )

        if not events:
            return {"success": True, "message": "📋 No training events found.\nSet up training programs first."}

        lines = ["## 📚 Training Events\n"]
        lines.append("| Event | Type | Status | Date |")
        lines.append("|-------|------|--------|------|")

        site = frappe.local.site
        for ev in events:
            link = f"[{ev.get('event_name', ev['name'])}](https://{site}/app/training-event/{ev['name']})"
            modified = ev["modified"].strftime("%Y-%m-%d") if ev.get("modified") else ""
            lines.append(f"| {link} | {ev.get('type', '')} | {ev.get('event_status', '')} | {modified} |")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Quality Inspection Templates
    # ══════════════════════════════════════════════════════════════════

    def _list_inspection_templates(self) -> Dict:
        """List Quality Inspection Templates"""
        templates = frappe.get_list(
            "Quality Inspection Template",
            fields=["name", "modified"],
            order_by="modified desc",
            limit=20
        )

        if not templates:
            return {"success": True, "message": "📋 No inspection templates found."}

        lines = ["## 🔬 Quality Inspection Templates\n"]
        site = frappe.local.site
        for t in templates:
            lines.append(f"- [{t['name']}](https://{site}/app/quality-inspection-template/{t['name']})")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Quality Review
    # ══════════════════════════════════════════════════════════════════

    def _quality_review(self) -> Dict:
        """Show quality review data"""
        reviews = frappe.get_list(
            "Quality Review",
            fields=["name", "modified"],
            order_by="modified desc",
            limit=10
        )

        goals = frappe.get_list(
            "Quality Goal",
            fields=["name", "goal", "frequency", "revision"],
            order_by="modified desc",
            limit=10
        )

        lines = ["## 📊 Quality Review\n"]

        if goals:
            lines.append("### Quality Goals")
            lines.append("| Goal | Frequency | Revision |")
            lines.append("|------|-----------|----------|")
            site = frappe.local.site
            for g in goals:
                link = f"[{g['name']}](https://{site}/app/quality-goal/{g['name']})"
                lines.append(f"| {link} | {g.get('frequency', '')} | {g.get('revision', '')} |")

        if reviews:
            lines.append("\n### Recent Reviews")
            site = frappe.local.site
            for r in reviews:
                modified = r["modified"].strftime("%Y-%m-%d") if r.get("modified") else ""
                lines.append(f"- [{r['name']}](https://{site}/app/quality-review/{r['name']}) — {modified}")
        else:
            lines.append("\nNo quality reviews recorded yet.")

        return {"success": True, "message": "\n".join(lines)}
