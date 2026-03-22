# Month-End Pipeline Validation – Raven Workflow

This runbook describes how to use **Raven's pipeline validation** to check critical sales flows at month-end, focusing on Quotation → Sales Order → Delivery Note → Sales Invoice consistency and CFDI correctness.

## 1. Scope

Use this checklist for:
- High-value customers
- Large or complex Sales Orders
- Any pipeline where CFDI / payment terms are sensitive

## 2. Core Command

In the Raven channel:

```
@workflow validate <Quotation or Sales Order>
```

You can pass:
- Full quotation name: `SAL-QTN-2024-00753`
- Only the numeric part: `0753`
- Partial SO name: `SO-00752`

Raven will auto-resolve:
- `0753` → `SAL-QTN-2024-00753`
- `SO-00752` → `SO-00752-LEGOSAN AB`

And then validate: Quotation → Sales Order → Delivery Note → Sales Invoice

## 3. Month-End Checklist (per key customer)

For each key customer or SO range (for example, 0752–0960):

1. **List recent or critical quotations / sales orders**

   Use your existing reports or dashboards in ERPNext.

2. **For each selected pipeline, run:**

   ```
   @workflow validate 0753
   @workflow validate SAL-QTN-2024-00752
   @workflow validate SO-00763
   ```

3. **Review the validation output**

   Confirm:
   - Quotation status is "Ordered", not "Draft"
   - Sales Order is submitted and in the expected status
   - Delivery Note is submitted (if goods were shipped)
   - Sales Invoice exists and matches the expected total
   - CFDI use (e.g., PPD vs PUE), payment terms, and amounts align with policy

   Use the clickable document links to open Quotation, SO, DN, SI directly in ERPNext for adjustments.

4. **Resolve any issues reported**

   - Fix Quotation status if it is still Draft but should be Ordered
   - Correct CFDI fields or payment terms on the Sales Invoice when needed
   - Create missing Delivery Notes or Invoices where appropriate

## 4. Recommended "Must Validate" Set

As a minimum for month-end:

- All sales pipelines above a configurable value threshold (e.g., > USD 50,000)
- All pipelines for designated strategic customers
- Any pipeline flagged by finance for CFDI discrepancies in the prior month

## 6. Batch Validation (Finance Only)

For larger month-end audits, finance can run a batch validation that processes multiple IDs at once and generates a consolidated report.

### Run Batch Validation

```bash
cd ~/frappe-bench
bench --site <site> execute raven_ai_agent.cli.batch_pipeline_validation.run_batch_validation
```

By default, it validates IDs 0752-0760. You can customize via environment variables:

```bash
# With explicit IDs (comma-separated)
RAVEN_BATCH_IDS="0752,0753,SAL-QTN-2024-00763" bench --site <site> execute raven_ai_agent.cli.batch_pipeline_validation.run_batch_validation

# With numeric range
RAVEN_BATCH_RANGE="752-765" bench --site <site> execute raven_ai_agent.cli.batch_pipeline_validation.run_batch_validation
```

### Output Files

The command writes two files under `apps/raven_ai_agent/raven_ai_agent/transcripts/`:

- `batch_pipeline_<timestamp>.json` — Machine-readable JSON with all results
- `batch_pipeline_<timestamp>.md` — Human-readable Markdown report

The latest month-end batch report is also available in ERPNext under **Files → raven_reports/latest_batch.md** for each site, via the private files area.

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `RAVEN_BATCH_IDS` | Comma-separated list of IDs | `"0752,SAL-QTN-2024-00763"` |
| `RAVEN_BATCH_RANGE` | Numeric range (start-end) | `"752-765"` |

If neither is set, defaults to range 752-760.

### Evidence Attachment

Attach the Markdown report to your month-end close ticket as audit evidence:

```bash
# Find the latest report
ls -t ~/frappe-bench/apps/raven_ai_agent/raven_ai_agent/transcripts/batch_pipeline_*.md | head -1
```

---

## 5. Evidence for Closing

Optionally, capture the validation output for key pipelines:

- Copy Raven's `@workflow validate` results into your month-end close ticket
- Or run the golden transcript tool and attach the Markdown output when validating specific SOs

This ensures there is an auditable trail showing that critical pipelines were checked and any discrepancies were addressed before closing the month.

---

**Example Validation Output:**

```
⚠️ Pipeline Validation: SAL-QTN-2024-00753

📋 QTN: SAL-QTN-2024-00753 | Draft | USD 187,200.00
📦 SO: SO-00753-GREENTECH SA | Status: Completed | Terms: T/T In Advance
🚚 DN: MAT-DN-2026-00003 | Submitted: ✅
🧾 SI: ACC-SINV-2026-00004 | Status: Overdue | USD 187,200.00

🇲🇽 CFDI: PUE (expected: PPD)

Issues (2):
⚠️ QTN SAL-QTN-2024-00753 status is 'Draft', expected 'Ordered'
⚠️ CFDI mismatch: SI has PUE, expected PPD
```

---

## Troubleshooting

### Quotation Not Found
- Check the quotation number format: `SAL-QTN-YYYY-NNNNN`
- Try using just the numeric part: `0753`

### Status Issues
- QTN must be "Ordered" (not "Draft" or "Lost")
- SO must be submitted (docstatus = 1)

### CFDI Mismatch
- PPD (Pago en Una Sola Exhibicion) vs PUE (Pago en Unidades)
- Check the payment terms in the Quotation
- The system uses customer history to determine expected CFDI type
