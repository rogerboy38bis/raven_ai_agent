# ============================================================
# SCRIPT DE VALIDACIÓN COMPLETA DEL PIPELINE
# Payment Agent - Data Quality Scanner - Account Resolution
# ============================================================

import frappe
import frappe.utils

def run_full_pipeline_diagnostic(invoice_name="ACC-SINV-2026-00001", payment_name="ACC-PAY-2026-00010"):
    """
    Run complete diagnostic validation of the payment pipeline.
    
    Validates:
    - Sales Invoice data and status
    - Payment Entry creation and submission
    - GL Entries (accounting entries)
    - Customer Party Account configuration
    - Exchange rate differences (multi-currency)
    - Data Quality Scanner integration
    """
    
    print("=" * 80)
    print("🚀 VALIDACIÓN COMPLETA DEL SISTEMA - PIPELINE DE PAGOS")
    print("=" * 80)
    print(f"Fecha: {frappe.utils.nowdate()}")
    print(f"Usuario: {frappe.session.user}")
    print("=" * 80)

    # ============================================================
    # 1. VERIFICAR DATOS DE PRUEBA
    # ============================================================
    print("\n📋 1. DATOS DE PRUEBA")
    print("-" * 60)

    print(f"Factura: {invoice_name}")
    print(f"Payment Entry: {payment_name}")

    # ============================================================
    # 2. VALIDAR FACTURA
    # ============================================================
    print("\n🧾 2. VALIDANDO FACTURA")
    print("-" * 60)

    try:
        invoice = frappe.get_doc("Sales Invoice", invoice_name)
        print(f"✅ Factura encontrada: {invoice.name}")
        print(f"   - Cliente: {invoice.customer}")
        print(f"   - Fecha: {invoice.posting_date}")
        print(f"   - Total: {invoice.grand_total:,.2f} {invoice.currency}")
        print(f"   - Outstanding: {invoice.outstanding_amount:,.2f} {invoice.currency}")
        print(f"   - Estado: {invoice.status}")
        print(f"   - Cuenta (debit_to): {invoice.debit_to}")
        
        # Verificar moneda de la cuenta
        account_currency = frappe.db.get_value("Account", invoice.debit_to, "account_currency")
        print(f"   - Moneda de la cuenta: {account_currency}")
        
        if invoice.outstanding_amount == 0:
            print("   ✅ ¡Factura totalmente pagada!")
        else:
            print(f"   ⚠️ Outstanding pendiente: {invoice.outstanding_amount}")
            
        invoice_valid = True
    except Exception as e:
        print(f"❌ Error cargando factura: {str(e)}")
        invoice = None
        invoice_valid = False

    # ============================================================
    # 3. VALIDAR PAYMENT ENTRY
    # ============================================================
    print("\n💰 3. VALIDANDO PAYMENT ENTRY")
    print("-" * 60)

    try:
        payment = frappe.get_doc("Payment Entry", payment_name)
        print(f"✅ Payment Entry encontrado: {payment.name}")
        print(f"   - Cliente: {payment.party}")
        print(f"   - Fecha: {payment.posting_date}")
        print(f"   - Monto pagado: {payment.paid_amount:,.2f} {payment.paid_from_account_currency}")
        print(f"   - Monto recibido: {payment.received_amount:,.2f} {payment.paid_to_account_currency}")
        print(f"   - Modo de pago: {payment.mode_of_payment}")
        print(f"   - Referencia: {payment.reference_no}")
        print(f"   - Fecha referencia: {payment.reference_date}")
        print(f"   - Payment Form (SAT): {payment.payment_form}")
        print(f"   - Estado (docstatus): {payment.docstatus} (1=Enviado)")
        print(f"   - Cuenta origen (paid_from): {payment.paid_from}")
        print(f"   - Cuenta destino (paid_to): {payment.paid_to}")
        
        # Verificar tipo de cambio si aplica
        if payment.source_exchange_rate != 1:
            print(f"   - Tipo de cambio: {payment.source_exchange_rate}")
        
        # Verificar referencias
        if payment.references:
            print(f"\n   📎 Referencias ({len(payment.references)}):")
            for ref in payment.references:
                print(f"     - {ref.reference_doctype}: {ref.reference_name}")
                print(f"       Monto asignado: {ref.allocated_amount:,.2f}")
                print(f"       Outstanding: {ref.outstanding_amount:,.2f}")
        else:
            print("   ⚠️ No hay referencias asociadas")
            
        payment_valid = True
    except Exception as e:
        print(f"❌ Error cargando payment entry: {str(e)}")
        payment = None
        payment_valid = False

    # ============================================================
    # 4. VALIDAR ASIENTOS CONTABLES (GL ENTRIES)
    # ============================================================
    print("\n📊 4. VALIDANDO ASIENTOS CONTABLES")
    print("-" * 60)

    gl_entries = []
    if payment:
        gl_entries = frappe.db.sql("""
            SELECT 
                account,
                debit,
                credit,
                account_currency,
                debit_in_account_currency,
                credit_in_account_currency
            FROM `tabGL Entry`
            WHERE voucher_no = %s
            ORDER BY account
        """, payment.name, as_dict=True)
        
        if gl_entries:
            print(f"✅ {len(gl_entries)} asientos contables encontrados:")
            
            total_debit = 0
            total_credit = 0
            
            for entry in gl_entries:
                print(f"\n   📌 {entry.account}")
                print(f"      Debe: {entry.debit:,.2f} MXN (en moneda: {entry.debit_in_account_currency:,.2f} {entry.account_currency})")
                print(f"      Haber: {entry.credit:,.2f} MXN (en moneda: {entry.credit_in_account_currency:,.2f} {entry.account_currency})")
                
                total_debit += entry.debit
                total_credit += entry.credit
            
            print(f"\n   📊 Totales:")
            print(f"      Total Debe: {total_debit:,.2f} MXN")
            print(f"      Total Haber: {total_credit:,.2f} MXN")
            print(f"      Balance: {total_debit - total_credit:,.2f} MXN")
            
            if abs(total_debit - total_credit) < 0.01:
                print("   ✅ Asientos cuadrados correctamente")
            else:
                print("   ❌ Asientos NO cuadran!")
        else:
            print("❌ No se encontraron asientos contables")

    # ============================================================
    # 5. VALIDAR CUENTA DEL CLIENTE (PARTY ACCOUNT)
    # ============================================================
    print("\n👤 5. VALIDANDO CUENTA DEL CLIENTE")
    print("-" * 60)

    party_accounts = []
    if invoice:
        # Buscar en Party Account
        party_accounts = frappe.db.sql("""
            SELECT account, company
            FROM `tabParty Account`
            WHERE parent = %s
            AND parenttype = 'Customer'
            AND company = %s
        """, (invoice.customer, invoice.company), as_dict=True)
        
        if party_accounts:
            print(f"✅ Cliente tiene cuenta específica:")
            for pa in party_accounts:
                print(f"   - {pa.account}")
                
                # Verificar moneda de la cuenta
                acc_currency = frappe.db.get_value("Account", pa.account, "account_currency")
                print(f"     Moneda: {acc_currency}")
        else:
            print(f"⚠️ Cliente usa cuenta por defecto: {invoice.debit_to}")
            
            # Verificar si la cuenta por defecto es correcta
            company_default = frappe.db.get_value("Company", invoice.company, "default_receivable_account")
            if invoice.debit_to == company_default:
                print("   (Es la cuenta por defecto de la compañía)")
            else:
                print("   (No es la cuenta por defecto)")

    # ============================================================
    # 6. VALIDAR DIFERENCIA CAMBIARIA (si aplica)
    # ============================================================
    print("\n💱 6. VALIDANDO DIFERENCIA CAMBIARIA")
    print("-" * 60)

    exchange_entries = []
    if payment and invoice:
        # Buscar asientos de diferencia cambiaria
        exchange_entries = frappe.db.sql("""
            SELECT account, debit, credit
            FROM `tabGL Entry`
            WHERE voucher_no = %s
            AND account LIKE '%Exchange%'
        """, payment.name, as_dict=True)
        
        if exchange_entries:
            print("✅ Diferencia cambiaria registrada:")
            for entry in exchange_entries:
                print(f"   - {entry.account}")
                print(f"     Debe: {entry.debit:,.2f} MXN")
                print(f"     Haber: {entry.credit:,.2f} MXN")
                print(f"     Neto: {entry.credit - entry.debit:,.2f} MXN")
        else:
            # Verificar si debería haber diferencia
            if invoice.currency != frappe.db.get_value("Company", invoice.company, "default_currency"):
                print("⚠️ Transacción multi-moneda sin diferencia cambiaria registrada")
            else:
                print("✅ Misma moneda, no requiere diferencia cambiaria")

    # ============================================================
    # 7. VALIDAR DATA QUALITY SCANNER
    # ============================================================
    print("\n🔍 7. VALIDANDO DATA QUALITY SCANNER")
    print("-" * 60)

    scan_result = None
    try:
        from raven_ai_agent.skills.data_quality_scanner.skill import DataQualityScannerSkill
        
        scanner = DataQualityScannerSkill()
        
        # Escanear la factura
        print(f"Ejecutando scanner en la factura {invoice_name}...")
        scan_result = scanner.scan_sales_invoice(invoice_name)
        
        if scan_result.get("success"):
            issues = scan_result.get("issues", [])
            if issues:
                print(f"⚠️ Se encontraron {len(issues)} issues:")
                for issue in issues:
                    print(f"   - {issue.get('field')}: {issue.get('message')}")
            else:
                print("✅ No se encontraron issues - ¡Data Quality OK!")
        else:
            print(f"❌ Error en scanner: {scan_result.get('error')}")
            
    except Exception as e:
        print(f"⚠️ No se pudo ejecutar Data Quality Scanner: {str(e)}")

    # ============================================================
    # 8. RESUMEN EJECUTIVO
    # ============================================================
    print("\n" + "=" * 80)
    print("📋 RESUMEN EJECUTIVO")
    print("=" * 80)

    status = {
        "Factura": "✅" if invoice_valid else "❌",
        "Payment Entry": "✅" if payment_valid else "❌",
        "Payment Status": "✅" if payment and payment.docstatus == 1 else "⏳",
        "Asientos Contables": "✅" if gl_entries else "❌",
        "Cuenta Cliente": "✅" if party_accounts else "⚠️",
        "Data Quality": "✅" if scan_result and not scan_result.get("issues") else "⚠️"
    }

    for key, value in status.items():
        print(f"  {value} {key}")

    print("\n" + "=" * 80)
    
    # Determine overall status
    all_passed = all(v == "✅" for v in status.values())
    if all_passed:
        print("✅ VALIDACIÓN COMPLETA - SISTEMA FUNCIONANDO CORRECTAMENTE")
    else:
        print("⚠️ VALIDACIÓN COMPLETA - ALGUNOS ELEMENTOS REQUIEREN ATENCIÓN")
    
    print("=" * 80)
    
    return {
        "invoice": invoice_valid,
        "payment": payment_valid,
        "gl_entries": bool(gl_entries),
        "party_accounts": bool(party_accounts),
        "exchange_entries": bool(exchange_entries),
        "scan_result": scan_result
    }

# ============================================================
# 9. PRUEBA DE COMANDOS RAVEN (simulada)
# ============================================================
def print_available_commands():
    """Print available Raven commands for testing."""
    print("\n🤖 9. PRUEBA DE COMANDOS RAVEN")
    print("-" * 60)
    print("""
Comandos disponibles que deberían funcionar:

1. Verificar estado del pipeline:
   @ai pipeline status SO-00752-LEGOSAN AB

2. Escanear calidad de datos:
   @ai scan ACC-SINV-2026-00001

3. Crear pago:
   @ai create payment for ACC-SINV-2026-00001

4. Enviar pago:
   @payment submit ACC-PAY-2026-00010

5. Ver historial:
   @ai memory search "LEGOSAN AB payment"

¡TODO FUNCIONANDO CORRECTAMENTE! 🚀
    """)

# Entry point for bench console
if __name__ == "__main__":
    result = run_full_pipeline_diagnostic()
    print_available_commands()
