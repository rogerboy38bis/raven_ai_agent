"""
Analytics & Reporting Agent - Phase 4: Advanced Analytics Module
Handles dashboard widgets, smart aggregations, scheduled reports, and alert rules.

Features:
- Manufacturing KPIs (OEE, throughput, cycle times)
- Quality metrics (NC rates, inspection pass rates, CAPA closure)
- Financial snapshots (revenue, outstanding, cash flow)
- Cross-module trend calculations
- Scheduled daily/weekly/monthly reports
- Threshold-based alert rules

Commands:
  @ai dashboard manufacturing   — Manufacturing KPI dashboard
  @ai dashboard quality         — Quality metrics dashboard
  @ai dashboard financial       — Financial snapshot
  @ai dashboard overview        — Combined executive overview
  @ai trend [metric] [period]   — Trend analysis (e.g., trend revenue 6m)
  @ai report daily              — Generate daily summary report
  @ai report weekly             — Generate weekly summary report
  @ai report monthly            — Generate monthly summary report
  @ai alerts status             — Show active alerts
  @ai alerts check              — Run alert rules and report findings
  @ai alerts configure          — Show/edit alert thresholds
"""
import frappe
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class AnalyticsMixin:
    """
    Mixin that adds Analytics & Reporting commands to the agent.
    Requires: self.user
    """

    def _handle_analytics_commands(self, query: str, query_lower: str, is_confirm: bool = False) -> Optional[Dict]:
        """Route analytics and reporting commands"""

        if not any(kw in query_lower for kw in [
            "dashboard", "tablero", "kpi", "trend", "tendencia",
            "report", "reporte", "informe", "alert", "alerta",
            "overview", "resumen", "snapshot", "financial", "financiero",
            "manufacturing kpi", "quality metric", "executive"
        ]):
            return None

        # ── Dashboard Commands ───────────────────────────────────────
        if "dashboard" in query_lower or "tablero" in query_lower:
            if any(kw in query_lower for kw in ["manufactur", "producción", "production", "oee"]):
                return self._dashboard_manufacturing()
            if any(kw in query_lower for kw in ["quality", "calidad"]):
                return self._dashboard_quality()
            if any(kw in query_lower for kw in ["financ", "revenue", "ingreso", "cash"]):
                return self._dashboard_financial()
            if any(kw in query_lower for kw in ["overview", "resumen", "executive", "ejecutivo"]):
                return self._dashboard_overview()
            # Default to overview
            return self._dashboard_overview()

        # ── Trend Commands ───────────────────────────────────────────
        if "trend" in query_lower or "tendencia" in query_lower:
            return self._trend_analysis(query, query_lower)

        # ── Report Commands ──────────────────────────────────────────
        if "report" in query_lower or "reporte" in query_lower or "informe" in query_lower:
            if "daily" in query_lower or "diario" in query_lower:
                return self._report_daily()
            if "weekly" in query_lower or "semanal" in query_lower:
                return self._report_weekly()
            if "monthly" in query_lower or "mensual" in query_lower:
                return self._report_monthly()
            # Default to daily
            return self._report_daily()

        # ── Alert Commands ───────────────────────────────────────────
        if "alert" in query_lower or "alerta" in query_lower:
            if "check" in query_lower or "run" in query_lower or "ejecutar" in query_lower:
                return self._alerts_check()
            if "configure" in query_lower or "config" in query_lower or "threshold" in query_lower:
                return self._alerts_configure()
            # Default: show status
            return self._alerts_status()

        return None

    # ══════════════════════════════════════════════════════════════════
    # Dashboard: Manufacturing KPIs
    # ══════════════════════════════════════════════════════════════════

    def _dashboard_manufacturing(self) -> Dict:
        """Manufacturing KPI dashboard"""
        now = datetime.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0)

        # Work Order metrics
        wo_total = frappe.db.count("Work Order", {"creation": [">=", month_start.strftime("%Y-%m-%d")]})
        wo_completed = frappe.db.count("Work Order", {
            "creation": [">=", month_start.strftime("%Y-%m-%d")],
            "status": "Completed"
        })
        wo_in_progress = frappe.db.count("Work Order", {"status": "In Process"})
        wo_not_started = frappe.db.count("Work Order", {"status": "Not Started"})
        wo_overdue = frappe.db.count("Work Order", {
            "status": ["in", ["Not Started", "In Process"]],
            "expected_delivery_date": ["<", now.strftime("%Y-%m-%d")]
        })

        # Production quantity MTD
        produced_qty = frappe.db.sql("""
            SELECT COALESCE(SUM(produced_qty), 0) as total
            FROM `tabWork Order`
            WHERE creation >= %s AND status = 'Completed'
        """, (month_start.strftime("%Y-%m-%d"),), as_dict=True)
        total_produced = produced_qty[0]["total"] if produced_qty else 0

        # Stock Entry counts (Manufacture type)
        se_manufacture = frappe.db.count("Stock Entry", {
            "creation": [">=", month_start.strftime("%Y-%m-%d")],
            "stock_entry_type": "Manufacture",
            "docstatus": 1
        })

        # Completion rate
        completion_rate = f"{(wo_completed / wo_total * 100):.1f}%" if wo_total > 0 else "N/A"

        # Average cycle time (completed WOs this month)
        cycle_data = frappe.db.sql("""
            SELECT AVG(DATEDIFF(modified, creation)) as avg_days
            FROM `tabWork Order`
            WHERE creation >= %s AND status = 'Completed'
        """, (month_start.strftime("%Y-%m-%d"),), as_dict=True)
        avg_cycle = f"{cycle_data[0]['avg_days']:.1f} days" if cycle_data and cycle_data[0]["avg_days"] else "N/A"

        lines = [f"## 🏭 Manufacturing Dashboard — {now.strftime('%B %Y')}\n"]

        lines.append("### Work Order Summary")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total WOs (MTD) | {wo_total} |")
        lines.append(f"| Completed | {wo_completed} |")
        lines.append(f"| In Process | {wo_in_progress} |")
        lines.append(f"| Not Started | {wo_not_started} |")
        lines.append(f"| ⚠️ Overdue | {wo_overdue} |")
        lines.append(f"| Completion Rate | {completion_rate} |")
        lines.append(f"| Avg Cycle Time | {avg_cycle} |")

        lines.append(f"\n### Production Output")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Produced (MTD) | {total_produced:,.1f} Kg |")
        lines.append(f"| Stock Entries (Manufacture) | {se_manufacture} |")

        if wo_overdue > 0:
            lines.append(f"\n⚠️ **{wo_overdue} overdue work orders** require attention.")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Dashboard: Quality Metrics
    # ══════════════════════════════════════════════════════════════════

    def _dashboard_quality(self) -> Dict:
        """Quality metrics dashboard"""
        now = datetime.now()
        month_start = now.replace(day=1)

        # Inspection metrics
        insp_total = frappe.db.count("Quality Inspection", {"creation": [">=", month_start.strftime("%Y-%m-%d")]})
        insp_accepted = frappe.db.count("Quality Inspection", {
            "creation": [">=", month_start.strftime("%Y-%m-%d")],
            "status": "Accepted"
        })
        insp_rejected = frappe.db.count("Quality Inspection", {
            "creation": [">=", month_start.strftime("%Y-%m-%d")],
            "status": "Rejected"
        })
        pass_rate = f"{(insp_accepted / insp_total * 100):.1f}%" if insp_total > 0 else "N/A"

        # NC metrics
        nc_total = frappe.db.count("Non Conformance")
        nc_open = frappe.db.count("Non Conformance", {"status": "Open"})
        nc_closed = frappe.db.count("Non Conformance", {"status": "Closed"})
        nc_mtd = frappe.db.count("Non Conformance", {"creation": [">=", month_start.strftime("%Y-%m-%d")]})
        nc_close_rate = f"{(nc_closed / nc_total * 100):.1f}%" if nc_total > 0 else "N/A"

        # CAPA metrics
        capa_total = frappe.db.count("Quality Action")
        capa_open = frappe.db.count("Quality Action", {"status": "Open"})

        # Quality Goals
        goal_count = frappe.db.count("Quality Goal")

        # Quality Reviews
        review_count = frappe.db.count("Quality Review")

        lines = [f"## 📊 Quality Dashboard — {now.strftime('%B %Y')}\n"]

        lines.append("### Inspection Performance (MTD)")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Inspections (MTD) | {insp_total} |")
        lines.append(f"| Accepted | {insp_accepted} |")
        lines.append(f"| Rejected | {insp_rejected} |")
        lines.append(f"| Pass Rate | {pass_rate} |")

        lines.append(f"\n### Non-Conformity")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total NCs | {nc_total} |")
        lines.append(f"| Open | {nc_open} |")
        lines.append(f"| New (MTD) | {nc_mtd} |")
        lines.append(f"| Close Rate | {nc_close_rate} |")
        lines.append(f"| Open CAPAs | {capa_open} / {capa_total} |")

        lines.append(f"\n### Quality System")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Quality Goals | {goal_count} |")
        lines.append(f"| Quality Reviews | {review_count} |")
        lines.append(f"| SOPs | {frappe.db.count('Quality Procedure')} |")
        lines.append(f"| Training Programs | {frappe.db.count('Training Program')} |")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Dashboard: Financial Snapshot
    # ══════════════════════════════════════════════════════════════════

    def _dashboard_financial(self) -> Dict:
        """Financial snapshot dashboard"""
        now = datetime.now()
        month_start = now.replace(day=1)

        # Revenue MTD (submitted invoices)
        revenue = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total,
                   COALESCE(SUM(base_grand_total), 0) as total_base,
                   COUNT(*) as count
            FROM `tabSales Invoice`
            WHERE posting_date >= %s AND docstatus = 1
        """, (month_start.strftime("%Y-%m-%d"),), as_dict=True)
        rev = revenue[0] if revenue else {"total": 0, "total_base": 0, "count": 0}

        # Outstanding receivables
        outstanding = frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) as total,
                   COUNT(*) as count
            FROM `tabSales Invoice`
            WHERE outstanding_amount > 0 AND docstatus = 1
        """, as_dict=True)
        ar = outstanding[0] if outstanding else {"total": 0, "count": 0}

        # Overdue invoices
        overdue = frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) as total,
                   COUNT(*) as count
            FROM `tabSales Invoice`
            WHERE outstanding_amount > 0 AND docstatus = 1 AND due_date < %s
        """, (now.strftime("%Y-%m-%d"),), as_dict=True)
        od = overdue[0] if overdue else {"total": 0, "count": 0}

        # Sales Orders pipeline
        so_pipeline = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total,
                   COUNT(*) as count
            FROM `tabSales Order`
            WHERE status IN ('To Deliver and Bill', 'To Bill', 'To Deliver')
            AND docstatus = 1
        """, as_dict=True)
        pipeline = so_pipeline[0] if so_pipeline else {"total": 0, "count": 0}

        # Purchase Orders pending
        po_pending = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total,
                   COUNT(*) as count
            FROM `tabPurchase Order`
            WHERE status IN ('To Receive and Bill', 'To Receive', 'To Bill')
            AND docstatus = 1
        """, as_dict=True)
        po = po_pending[0] if po_pending else {"total": 0, "count": 0}

        # Payment Entries MTD
        payments = frappe.db.sql("""
            SELECT COALESCE(SUM(paid_amount), 0) as total,
                   COUNT(*) as count
            FROM `tabPayment Entry`
            WHERE posting_date >= %s AND docstatus = 1
        """, (month_start.strftime("%Y-%m-%d"),), as_dict=True)
        pay = payments[0] if payments else {"total": 0, "count": 0}

        lines = [f"## 💰 Financial Dashboard — {now.strftime('%B %Y')}\n"]

        lines.append("### Revenue (MTD)")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Invoiced (MTD) | ${rev['total']:,.2f} |")
        lines.append(f"| Invoices Count | {rev['count']} |")
        lines.append(f"| Payments Received (MTD) | ${pay['total']:,.2f} |")

        lines.append(f"\n### Accounts Receivable")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Outstanding | ${ar['total']:,.2f} ({ar['count']} invoices) |")
        lines.append(f"| 🔴 Overdue | ${od['total']:,.2f} ({od['count']} invoices) |")

        lines.append(f"\n### Pipeline")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Open Sales Orders | ${pipeline['total']:,.2f} ({pipeline['count']} orders) |")
        lines.append(f"| Pending POs | ${po['total']:,.2f} ({po['count']} orders) |")

        if od["count"] > 0:
            lines.append(f"\n⚠️ **{od['count']} overdue invoices** totaling ${od['total']:,.2f}")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Dashboard: Executive Overview
    # ══════════════════════════════════════════════════════════════════

    def _dashboard_overview(self) -> Dict:
        """Combined executive overview dashboard"""
        now = datetime.now()
        month_start = now.replace(day=1)

        # Financial
        revenue = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as cnt
            FROM `tabSales Invoice`
            WHERE posting_date >= %s AND docstatus = 1
        """, (month_start.strftime("%Y-%m-%d"),), as_dict=True)
        rev = revenue[0] if revenue else {"total": 0, "cnt": 0}

        outstanding = frappe.db.sql("""
            SELECT COALESCE(SUM(outstanding_amount), 0) as total
            FROM `tabSales Invoice`
            WHERE outstanding_amount > 0 AND docstatus = 1
        """, as_dict=True)
        ar_total = outstanding[0]["total"] if outstanding else 0

        overdue_cnt = frappe.db.count("Sales Invoice", {
            "outstanding_amount": [">", 0], "docstatus": 1,
            "due_date": ["<", now.strftime("%Y-%m-%d")]
        })

        # Manufacturing
        wo_completed = frappe.db.count("Work Order", {
            "creation": [">=", month_start.strftime("%Y-%m-%d")], "status": "Completed"
        })
        wo_overdue = frappe.db.count("Work Order", {
            "status": ["in", ["Not Started", "In Process"]],
            "expected_delivery_date": ["<", now.strftime("%Y-%m-%d")]
        })

        produced_qty = frappe.db.sql("""
            SELECT COALESCE(SUM(produced_qty), 0) as total
            FROM `tabWork Order` WHERE creation >= %s AND status = 'Completed'
        """, (month_start.strftime("%Y-%m-%d"),), as_dict=True)
        total_produced = produced_qty[0]["total"] if produced_qty else 0

        # Quality
        nc_open = frappe.db.count("Non Conformance", {"status": "Open"})
        capa_open = frappe.db.count("Quality Action", {"status": "Open"})
        insp_mtd = frappe.db.count("Quality Inspection", {"creation": [">=", month_start.strftime("%Y-%m-%d")]})

        # Sales pipeline
        so_open = frappe.db.sql("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(grand_total), 0) as total
            FROM `tabSales Order`
            WHERE status IN ('To Deliver and Bill', 'To Deliver', 'To Bill') AND docstatus = 1
        """, as_dict=True)
        pipeline = so_open[0] if so_open else {"cnt": 0, "total": 0}

        lines = [f"## 🚀 Executive Overview — {now.strftime('%B %d, %Y')}\n"]

        lines.append("### 💰 Financial")
        lines.append(f"| Revenue MTD | Outstanding AR | Overdue |")
        lines.append(f"|-------------|----------------|---------|")
        lines.append(f"| ${rev['total']:,.2f} ({rev['cnt']} inv) | ${ar_total:,.2f} | {overdue_cnt} invoices |")

        lines.append(f"\n### 🏭 Manufacturing")
        lines.append(f"| WOs Completed | Produced (MTD) | Overdue WOs |")
        lines.append(f"|---------------|----------------|-------------|")
        lines.append(f"| {wo_completed} | {total_produced:,.1f} Kg | {wo_overdue} |")

        lines.append(f"\n### 📊 Quality")
        lines.append(f"| Open NCs | Open CAPAs | Inspections (MTD) |")
        lines.append(f"|----------|------------|-------------------|")
        lines.append(f"| {nc_open} | {capa_open} | {insp_mtd} |")

        lines.append(f"\n### 📦 Sales Pipeline")
        lines.append(f"| Open Orders | Pipeline Value |")
        lines.append(f"|-------------|---------------|")
        lines.append(f"| {pipeline['cnt']} | ${pipeline['total']:,.2f} |")

        # Alerts summary
        alerts = []
        if overdue_cnt > 0:
            alerts.append(f"🔴 {overdue_cnt} overdue invoices")
        if wo_overdue > 0:
            alerts.append(f"🟠 {wo_overdue} overdue work orders")
        if nc_open > 0:
            alerts.append(f"🟡 {nc_open} open non-conformances")
        if capa_open > 0:
            alerts.append(f"🟡 {capa_open} open CAPAs")

        if alerts:
            lines.append(f"\n### ⚠️ Alerts")
            for a in alerts:
                lines.append(f"- {a}")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Trend Analysis
    # ══════════════════════════════════════════════════════════════════

    def _trend_analysis(self, query: str, query_lower: str) -> Dict:
        """Cross-module trend analysis"""
        import re

        # Determine period (default 6 months)
        period_match = re.search(r'(\d+)\s*m(?:onth)?', query_lower)
        months = int(period_match.group(1)) if period_match else 6

        now = datetime.now()

        lines = [f"## 📈 Trend Analysis — Last {months} Months\n"]

        # Revenue trend
        revenue_data = frappe.db.sql("""
            SELECT DATE_FORMAT(posting_date, '%%Y-%%m') as month,
                   COALESCE(SUM(grand_total), 0) as revenue,
                   COUNT(*) as invoices
            FROM `tabSales Invoice`
            WHERE posting_date >= DATE_SUB(NOW(), INTERVAL %s MONTH)
            AND docstatus = 1
            GROUP BY month ORDER BY month
        """, (months,), as_dict=True)

        if revenue_data:
            lines.append("### Revenue Trend")
            lines.append("| Month | Revenue | Invoices |")
            lines.append("|-------|---------|----------|")
            for r in revenue_data:
                lines.append(f"| {r['month']} | ${r['revenue']:,.2f} | {r['invoices']} |")

        # Production trend
        production_data = frappe.db.sql("""
            SELECT DATE_FORMAT(creation, '%%Y-%%m') as month,
                   COUNT(*) as work_orders,
                   COALESCE(SUM(produced_qty), 0) as produced
            FROM `tabWork Order`
            WHERE creation >= DATE_SUB(NOW(), INTERVAL %s MONTH)
            AND status = 'Completed'
            GROUP BY month ORDER BY month
        """, (months,), as_dict=True)

        if production_data:
            lines.append("\n### Production Trend")
            lines.append("| Month | Work Orders | Produced (Kg) |")
            lines.append("|-------|-------------|---------------|")
            for p in production_data:
                lines.append(f"| {p['month']} | {p['work_orders']} | {p['produced']:,.1f} |")

        # Quality trend (NCs)
        nc_data = frappe.db.sql("""
            SELECT DATE_FORMAT(creation, '%%Y-%%m') as month,
                   COUNT(*) as ncs
            FROM `tabNon Conformance`
            WHERE creation >= DATE_SUB(NOW(), INTERVAL %s MONTH)
            GROUP BY month ORDER BY month
        """, (months,), as_dict=True)

        if nc_data:
            lines.append("\n### Non-Conformance Trend")
            lines.append("| Month | NCs |")
            lines.append("|-------|-----|")
            for n in nc_data:
                lines.append(f"| {n['month']} | {n['ncs']} |")

        # Inspection trend
        insp_data = frappe.db.sql("""
            SELECT DATE_FORMAT(report_date, '%%Y-%%m') as month,
                   COUNT(*) as total,
                   SUM(CASE WHEN status = 'Accepted' THEN 1 ELSE 0 END) as accepted,
                   SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected
            FROM `tabQuality Inspection`
            WHERE report_date >= DATE_SUB(NOW(), INTERVAL %s MONTH)
            AND docstatus = 1
            GROUP BY month ORDER BY month
        """, (months,), as_dict=True)

        if insp_data:
            lines.append("\n### Inspection Trend")
            lines.append("| Month | Total | Accepted | Rejected | Pass Rate |")
            lines.append("|-------|-------|----------|----------|-----------|")
            for i in insp_data:
                rate = f"{(i['accepted'] / i['total'] * 100):.1f}%" if i["total"] > 0 else "N/A"
                lines.append(f"| {i['month']} | {i['total']} | {i['accepted']} | {i['rejected']} | {rate} |")

        if not revenue_data and not production_data and not nc_data and not insp_data:
            lines.append("No trend data available for the selected period.")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Scheduled Reports
    # ══════════════════════════════════════════════════════════════════

    def _report_daily(self) -> Dict:
        """Generate daily summary report"""
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        lines = [f"## 📋 Daily Report — {now.strftime('%A, %B %d, %Y')}\n"]

        # New Sales Orders
        new_so = frappe.db.sql("""
            SELECT name, customer_name, grand_total, currency
            FROM `tabSales Order`
            WHERE DATE(creation) = %s AND docstatus = 1
            ORDER BY grand_total DESC LIMIT 10
        """, (today_str,), as_dict=True)

        lines.append("### New Sales Orders")
        if new_so:
            site = frappe.local.site
            for so in new_so:
                lines.append(f"- [{so['name']}](https://{site}/app/sales-order/{so['name']}) — "
                             f"{so['customer_name']} — ${so['grand_total']:,.2f} {so.get('currency', '')}")
        else:
            lines.append("No new sales orders today.")

        # Completed Work Orders
        completed_wo = frappe.db.sql("""
            SELECT name, production_item, produced_qty
            FROM `tabWork Order`
            WHERE DATE(modified) = %s AND status = 'Completed'
            ORDER BY produced_qty DESC LIMIT 10
        """, (today_str,), as_dict=True)

        lines.append("\n### Completed Work Orders")
        if completed_wo:
            for wo in completed_wo:
                lines.append(f"- {wo['name']} — {wo.get('production_item', '')} — {wo.get('produced_qty', 0):,.1f} Kg")
        else:
            lines.append("No work orders completed today.")

        # Invoices Created
        new_inv = frappe.db.sql("""
            SELECT name, customer_name, grand_total, outstanding_amount
            FROM `tabSales Invoice`
            WHERE DATE(creation) = %s AND docstatus = 1
            ORDER BY grand_total DESC LIMIT 10
        """, (today_str,), as_dict=True)

        lines.append("\n### Invoices Created")
        if new_inv:
            site = frappe.local.site
            for inv in new_inv:
                lines.append(f"- [{inv['name']}](https://{site}/app/sales-invoice/{inv['name']}) — "
                             f"{inv['customer_name']} — ${inv['grand_total']:,.2f}")
        else:
            lines.append("No invoices created today.")

        # Payments Received
        new_pay = frappe.db.sql("""
            SELECT name, party_name, paid_amount, payment_type
            FROM `tabPayment Entry`
            WHERE DATE(creation) = %s AND docstatus = 1
            ORDER BY paid_amount DESC LIMIT 10
        """, (today_str,), as_dict=True)

        lines.append("\n### Payments Received")
        if new_pay:
            for p in new_pay:
                lines.append(f"- {p['name']} — {p.get('party_name', '')} — ${p.get('paid_amount', 0):,.2f}")
        else:
            lines.append("No payments received today.")

        # Quality Events
        new_nc = frappe.db.count("Non Conformance", {"creation": [">=", today_str]})
        new_insp = frappe.db.count("Quality Inspection", {"creation": [">=", today_str]})

        lines.append(f"\n### Quality")
        lines.append(f"- New NCs: {new_nc}")
        lines.append(f"- Inspections: {new_insp}")

        return {"success": True, "message": "\n".join(lines)}

    def _report_weekly(self) -> Dict:
        """Generate weekly summary report"""
        now = datetime.now()
        week_start = now - timedelta(days=now.weekday())
        week_start_str = week_start.strftime("%Y-%m-%d")

        lines = [f"## 📋 Weekly Report — Week of {week_start.strftime('%B %d, %Y')}\n"]

        # Weekly Sales
        weekly_sales = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as cnt
            FROM `tabSales Invoice`
            WHERE posting_date >= %s AND docstatus = 1
        """, (week_start_str,), as_dict=True)
        ws = weekly_sales[0] if weekly_sales else {"total": 0, "cnt": 0}

        # Weekly Production
        weekly_prod = frappe.db.sql("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(produced_qty), 0) as qty
            FROM `tabWork Order`
            WHERE modified >= %s AND status = 'Completed'
        """, (week_start_str,), as_dict=True)
        wp = weekly_prod[0] if weekly_prod else {"cnt": 0, "qty": 0}

        # Weekly Deliveries
        weekly_dn = frappe.db.sql("""
            SELECT COUNT(*) as cnt FROM `tabDelivery Note`
            WHERE posting_date >= %s AND docstatus = 1
        """, (week_start_str,), as_dict=True)
        dn = weekly_dn[0]["cnt"] if weekly_dn else 0

        # Weekly Quality
        weekly_nc = frappe.db.count("Non Conformance", {"creation": [">=", week_start_str]})
        weekly_insp = frappe.db.count("Quality Inspection", {"creation": [">=", week_start_str]})

        lines.append("### Summary")
        lines.append("| Category | Metric | Value |")
        lines.append("|----------|--------|-------|")
        lines.append(f"| 💰 Sales | Revenue | ${ws['total']:,.2f} ({ws['cnt']} invoices) |")
        lines.append(f"| 🏭 Production | Completed WOs | {wp['cnt']} ({wp['qty']:,.1f} Kg) |")
        lines.append(f"| 📦 Logistics | Deliveries | {dn} |")
        lines.append(f"| 📊 Quality | NCs / Inspections | {weekly_nc} / {weekly_insp} |")

        # Top customers this week
        top_customers = frappe.db.sql("""
            SELECT customer_name, SUM(grand_total) as total, COUNT(*) as cnt
            FROM `tabSales Invoice`
            WHERE posting_date >= %s AND docstatus = 1
            GROUP BY customer_name ORDER BY total DESC LIMIT 5
        """, (week_start_str,), as_dict=True)

        if top_customers:
            lines.append("\n### Top Customers This Week")
            lines.append("| Customer | Revenue | Invoices |")
            lines.append("|----------|---------|----------|")
            for c in top_customers:
                lines.append(f"| {c['customer_name']} | ${c['total']:,.2f} | {c['cnt']} |")

        return {"success": True, "message": "\n".join(lines)}

    def _report_monthly(self) -> Dict:
        """Generate monthly summary report"""
        now = datetime.now()
        month_start = now.replace(day=1)
        month_start_str = month_start.strftime("%Y-%m-%d")

        # Previous month for comparison
        prev_month_end = month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)

        lines = [f"## 📋 Monthly Report — {now.strftime('%B %Y')}\n"]

        # Current month revenue
        curr_rev = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as cnt
            FROM `tabSales Invoice`
            WHERE posting_date >= %s AND docstatus = 1
        """, (month_start_str,), as_dict=True)
        cr = curr_rev[0] if curr_rev else {"total": 0, "cnt": 0}

        # Previous month revenue
        prev_rev = frappe.db.sql("""
            SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as cnt
            FROM `tabSales Invoice`
            WHERE posting_date >= %s AND posting_date < %s AND docstatus = 1
        """, (prev_month_start.strftime("%Y-%m-%d"), month_start_str), as_dict=True)
        pr = prev_rev[0] if prev_rev else {"total": 0, "cnt": 0}

        # Revenue change
        if pr["total"] > 0:
            rev_change = ((cr["total"] - pr["total"]) / pr["total"]) * 100
            rev_arrow = "📈" if rev_change >= 0 else "📉"
            rev_change_str = f"{rev_arrow} {rev_change:+.1f}%"
        else:
            rev_change_str = "N/A (no prev month)"

        # Production comparison
        curr_prod = frappe.db.sql("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(produced_qty), 0) as qty
            FROM `tabWork Order`
            WHERE creation >= %s AND status = 'Completed'
        """, (month_start_str,), as_dict=True)
        cp = curr_prod[0] if curr_prod else {"cnt": 0, "qty": 0}

        prev_prod = frappe.db.sql("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(produced_qty), 0) as qty
            FROM `tabWork Order`
            WHERE creation >= %s AND creation < %s AND status = 'Completed'
        """, (prev_month_start.strftime("%Y-%m-%d"), month_start_str), as_dict=True)
        pp = prev_prod[0] if prev_prod else {"cnt": 0, "qty": 0}

        lines.append("### Month-over-Month Comparison")
        lines.append("| Metric | Current Month | Previous Month | Change |")
        lines.append("|--------|---------------|----------------|--------|")
        lines.append(f"| Revenue | ${cr['total']:,.2f} | ${pr['total']:,.2f} | {rev_change_str} |")
        lines.append(f"| Invoices | {cr['cnt']} | {pr['cnt']} | — |")
        lines.append(f"| WOs Completed | {cp['cnt']} | {pp['cnt']} | — |")
        lines.append(f"| Production (Kg) | {cp['qty']:,.1f} | {pp['qty']:,.1f} | — |")

        # Outstanding AR aging
        aging = frappe.db.sql("""
            SELECT
                SUM(CASE WHEN DATEDIFF(NOW(), due_date) <= 0 THEN outstanding_amount ELSE 0 END) as current_amt,
                SUM(CASE WHEN DATEDIFF(NOW(), due_date) BETWEEN 1 AND 30 THEN outstanding_amount ELSE 0 END) as d30,
                SUM(CASE WHEN DATEDIFF(NOW(), due_date) BETWEEN 31 AND 60 THEN outstanding_amount ELSE 0 END) as d60,
                SUM(CASE WHEN DATEDIFF(NOW(), due_date) BETWEEN 61 AND 90 THEN outstanding_amount ELSE 0 END) as d90,
                SUM(CASE WHEN DATEDIFF(NOW(), due_date) > 90 THEN outstanding_amount ELSE 0 END) as d90plus
            FROM `tabSales Invoice`
            WHERE outstanding_amount > 0 AND docstatus = 1
        """, as_dict=True)
        ag = aging[0] if aging else {}

        lines.append("\n### AR Aging")
        lines.append("| Bucket | Amount |")
        lines.append("|--------|--------|")
        lines.append(f"| Current (not due) | ${ag.get('current_amt', 0):,.2f} |")
        lines.append(f"| 1-30 days | ${ag.get('d30', 0):,.2f} |")
        lines.append(f"| 31-60 days | ${ag.get('d60', 0):,.2f} |")
        lines.append(f"| 61-90 days | ${ag.get('d90', 0):,.2f} |")
        lines.append(f"| 90+ days | ${ag.get('d90plus', 0):,.2f} |")

        return {"success": True, "message": "\n".join(lines)}

    # ══════════════════════════════════════════════════════════════════
    # Alert Rules Engine
    # ══════════════════════════════════════════════════════════════════

    # Default thresholds (stored in AI Memory when customized)
    _DEFAULT_THRESHOLDS = {
        "overdue_invoices": 0,       # alert if any overdue
        "overdue_wo": 0,             # alert if any overdue WO
        "nc_open_max": 5,            # alert if open NCs exceed this
        "capa_open_max": 3,          # alert if open CAPAs exceed this
        "ar_overdue_amount": 50000,  # alert if overdue AR exceeds this (USD)
        "low_stock_threshold": 100,  # alert if any FG item below this qty
        "inspection_reject_rate": 10, # alert if rejection rate exceeds this %
    }

    def _get_alert_thresholds(self) -> Dict:
        """Get alert thresholds (from AI Memory or defaults)"""
        try:
            memory = frappe.get_list(
                "AI Memory",
                filters={"key": "alert_thresholds"},
                fields=["value"],
                limit=1
            )
            if memory and memory[0].get("value"):
                return json.loads(memory[0]["value"])
        except Exception:
            pass
        return self._DEFAULT_THRESHOLDS.copy()

    def _alerts_status(self) -> Dict:
        """Show current alert status"""
        thresholds = self._get_alert_thresholds()
        alerts = self._run_alert_checks(thresholds)

        lines = ["## 🔔 Alert Status\n"]

        if alerts:
            lines.append(f"**{len(alerts)} active alert(s)**\n")
            for alert in alerts:
                lines.append(f"- {alert['icon']} **{alert['title']}**: {alert['detail']}")
        else:
            lines.append("✅ All clear — no active alerts.\n")

        lines.append("\n### Configured Thresholds")
        lines.append("| Rule | Threshold | Current |")
        lines.append("|------|-----------|---------|")

        for alert in self._get_alert_details(thresholds):
            lines.append(f"| {alert['name']} | {alert['threshold']} | {alert['current']} |")

        return {"success": True, "message": "\n".join(lines)}

    def _alerts_check(self) -> Dict:
        """Run alert checks and report findings"""
        thresholds = self._get_alert_thresholds()
        alerts = self._run_alert_checks(thresholds)

        lines = ["## 🔍 Alert Check Results\n"]

        if alerts:
            critical = [a for a in alerts if a["severity"] == "critical"]
            warning = [a for a in alerts if a["severity"] == "warning"]
            info = [a for a in alerts if a["severity"] == "info"]

            if critical:
                lines.append("### 🔴 Critical")
                for a in critical:
                    lines.append(f"- **{a['title']}**: {a['detail']}")

            if warning:
                lines.append("\n### 🟠 Warning")
                for a in warning:
                    lines.append(f"- **{a['title']}**: {a['detail']}")

            if info:
                lines.append("\n### 🟡 Info")
                for a in info:
                    lines.append(f"- **{a['title']}**: {a['detail']}")
        else:
            lines.append("✅ All checks passed — no alerts triggered.\n")

        return {"success": True, "message": "\n".join(lines)}

    def _alerts_configure(self) -> Dict:
        """Show alert configuration"""
        thresholds = self._get_alert_thresholds()

        lines = ["## ⚙️ Alert Configuration\n"]
        lines.append("Current thresholds (modify via `@ai set alert [rule] [value]`):\n")
        lines.append("| Rule | Current Value | Description |")
        lines.append("|------|---------------|-------------|")
        lines.append(f"| overdue_invoices | {thresholds.get('overdue_invoices', 0)} | Max overdue invoices before alert |")
        lines.append(f"| overdue_wo | {thresholds.get('overdue_wo', 0)} | Max overdue work orders before alert |")
        lines.append(f"| nc_open_max | {thresholds.get('nc_open_max', 5)} | Max open NCs before alert |")
        lines.append(f"| capa_open_max | {thresholds.get('capa_open_max', 3)} | Max open CAPAs before alert |")
        lines.append(f"| ar_overdue_amount | ${thresholds.get('ar_overdue_amount', 50000):,.0f} | Max overdue AR amount (USD) |")
        lines.append(f"| low_stock_threshold | {thresholds.get('low_stock_threshold', 100)} | Min FG stock level (Kg) |")
        lines.append(f"| inspection_reject_rate | {thresholds.get('inspection_reject_rate', 10)}% | Max inspection rejection rate |")

        return {"success": True, "message": "\n".join(lines)}

    def _run_alert_checks(self, thresholds: Dict) -> List[Dict]:
        """Run all alert rules and return triggered alerts"""
        now = datetime.now()
        alerts = []

        # 1. Overdue invoices
        overdue_inv = frappe.db.sql("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(outstanding_amount), 0) as total
            FROM `tabSales Invoice`
            WHERE outstanding_amount > 0 AND docstatus = 1 AND due_date < %s
        """, (now.strftime("%Y-%m-%d"),), as_dict=True)
        oi = overdue_inv[0] if overdue_inv else {"cnt": 0, "total": 0}

        if oi["cnt"] > thresholds.get("overdue_invoices", 0):
            alerts.append({
                "icon": "🔴", "severity": "critical",
                "title": "Overdue Invoices",
                "detail": f"{oi['cnt']} invoices overdue, ${oi['total']:,.2f} outstanding"
            })

        # 2. Overdue Work Orders
        wo_overdue = frappe.db.count("Work Order", {
            "status": ["in", ["Not Started", "In Process"]],
            "expected_delivery_date": ["<", now.strftime("%Y-%m-%d")]
        })
        if wo_overdue > thresholds.get("overdue_wo", 0):
            alerts.append({
                "icon": "🟠", "severity": "warning",
                "title": "Overdue Work Orders",
                "detail": f"{wo_overdue} work orders past expected delivery date"
            })

        # 3. Open NCs
        nc_open = frappe.db.count("Non Conformance", {"status": "Open"})
        if nc_open > thresholds.get("nc_open_max", 5):
            alerts.append({
                "icon": "🟡", "severity": "warning",
                "title": "Open Non-Conformances",
                "detail": f"{nc_open} open NCs (threshold: {thresholds.get('nc_open_max', 5)})"
            })

        # 4. Open CAPAs
        capa_open = frappe.db.count("Quality Action", {"status": "Open"})
        if capa_open > thresholds.get("capa_open_max", 3):
            alerts.append({
                "icon": "🟡", "severity": "warning",
                "title": "Open CAPAs",
                "detail": f"{capa_open} open CAPAs (threshold: {thresholds.get('capa_open_max', 3)})"
            })

        # 5. AR overdue amount
        if oi["total"] > thresholds.get("ar_overdue_amount", 50000):
            alerts.append({
                "icon": "🔴", "severity": "critical",
                "title": "AR Overdue Amount",
                "detail": f"${oi['total']:,.2f} overdue (threshold: ${thresholds.get('ar_overdue_amount', 50000):,.0f})"
            })

        # 6. Inspection rejection rate (last 30 days)
        month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        insp_data = frappe.db.sql("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected
            FROM `tabQuality Inspection`
            WHERE report_date >= %s AND docstatus = 1
        """, (month_ago,), as_dict=True)
        insp = insp_data[0] if insp_data else {"total": 0, "rejected": 0}

        if insp["total"] > 0:
            reject_rate = (insp["rejected"] / insp["total"]) * 100
            if reject_rate > thresholds.get("inspection_reject_rate", 10):
                alerts.append({
                    "icon": "🟠", "severity": "warning",
                    "title": "High Rejection Rate",
                    "detail": f"{reject_rate:.1f}% rejection rate (threshold: {thresholds.get('inspection_reject_rate', 10)}%)"
                })

        return alerts

    def _get_alert_details(self, thresholds: Dict) -> List[Dict]:
        """Get current values for all alert rules"""
        now = datetime.now()

        overdue_inv = frappe.db.count("Sales Invoice", {
            "outstanding_amount": [">", 0], "docstatus": 1,
            "due_date": ["<", now.strftime("%Y-%m-%d")]
        })
        wo_overdue = frappe.db.count("Work Order", {
            "status": ["in", ["Not Started", "In Process"]],
            "expected_delivery_date": ["<", now.strftime("%Y-%m-%d")]
        })
        nc_open = frappe.db.count("Non Conformance", {"status": "Open"})
        capa_open = frappe.db.count("Quality Action", {"status": "Open"})

        return [
            {"name": "Overdue Invoices", "threshold": str(thresholds.get("overdue_invoices", 0)), "current": str(overdue_inv)},
            {"name": "Overdue WOs", "threshold": str(thresholds.get("overdue_wo", 0)), "current": str(wo_overdue)},
            {"name": "Open NCs", "threshold": str(thresholds.get("nc_open_max", 5)), "current": str(nc_open)},
            {"name": "Open CAPAs", "threshold": str(thresholds.get("capa_open_max", 3)), "current": str(capa_open)},
            {"name": "AR Overdue ($)", "threshold": f"${thresholds.get('ar_overdue_amount', 50000):,.0f}", "current": "—"},
            {"name": "Reject Rate (%)", "threshold": f"{thresholds.get('inspection_reject_rate', 10)}%", "current": "—"},
        ]
