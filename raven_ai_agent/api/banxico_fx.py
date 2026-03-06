"""
Banxico FIX Exchange Rate Utility for ERPNext

Provides the official Banco de México FIX (SF43718) exchange rate for CFDI
invoicing and payment processing.

SAT/Banxico Rule:
  - CFDI Anexo 20: TipoCambio must be the FIX rate
  - FIX is determined at noon by Banxico, published in DOF next business day
  - For an invoice on date T: use FIX from T-1 (previous business day)
  - For a payment on date T: use FIX from T-1 (previous business day)
  - Difference between invoice rate and payment rate → Exchange Gain/Loss

Data Source: Banxico SIE API
  Serie: SF43718 (Tipo de cambio FIX - Fecha de determinación)
  URL: https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF43718/datos/{start}/{end}
  Token: Required (64-char alphanumeric from https://www.banxico.org.mx/SieAPIRest/service/v1/)

Author: raven_ai_agent
"""
import frappe
import requests
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple


# Banxico SIE API configuration
BANXICO_SERIE_FIX = "SF43718"
BANXICO_API_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{serie}/datos/{start}/{end}"

# Cache key for site-level rate cache (avoids repeated API calls)
CACHE_KEY_PREFIX = "banxico_fix_rate_"


def _get_banxico_token() -> Optional[str]:
    """Get Banxico API token from site_config or Company settings.
    
    Looks for token in this order:
    1. frappe.conf.banxico_token (site_config.json)
    2. Company.custom_banxico_token (custom field if exists)
    3. None (caller must handle)
    """
    # Try site config first
    token = getattr(frappe.conf, 'banxico_token', None)
    if token:
        return token
    
    # Try company custom field
    try:
        companies = frappe.get_all('Company', filters={'is_group': 0}, limit=1)
        if companies:
            token = frappe.db.get_value('Company', companies[0].name, 'custom_banxico_token')
            if token:
                return token
    except Exception:
        pass
    
    return None


def get_fix_rates_from_banxico(start_date: str, end_date: str, token: str = None) -> Dict[str, float]:
    """Fetch FIX exchange rates from Banxico SIE API for a date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        token: Banxico API token (optional, will try to auto-detect)
    
    Returns:
        Dict mapping YYYY-MM-DD dates to FIX rates (MXN per USD)
        Only includes business days where FIX was determined.
    
    Raises:
        ValueError: If no token available
        requests.RequestException: If API call fails
    """
    if not token:
        token = _get_banxico_token()
    if not token:
        frappe.throw(
            "Banxico API token not configured. "
            "Set 'banxico_token' in site_config.json or add custom_banxico_token to Company."
        )
    
    url = BANXICO_API_URL.format(
        serie=BANXICO_SERIE_FIX,
        start=start_date,
        end=end_date
    )
    
    headers = {
        "Accept": "application/json",
        "Bmx-Token": token,
        "Accept-Encoding": "gzip"
    }
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    
    # Check for API errors
    if "error" in data:
        frappe.throw(f"Banxico API error: {data['error'].get('mensaje', 'Unknown error')}")
    
    rates = {}
    series_data = data.get("bmx", {}).get("series", [])
    if not series_data:
        return rates
    
    for entry in series_data[0].get("datos", []):
        dato = entry.get("dato", "N/E")
        if dato == "N/E":
            continue  # No data (weekend/holiday)
        
        # Convert DD/MM/YYYY to YYYY-MM-DD
        fecha = entry["fecha"]
        parts = fecha.split("/")
        iso_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        
        try:
            rates[iso_date] = float(dato)
        except (ValueError, TypeError):
            continue
    
    return rates


def get_fix_t_minus_1(target_date: str, token: str = None) -> Tuple[Optional[float], Optional[str]]:
    """Get the FIX rate for T-1 (previous business day) relative to target_date.
    
    This is THE rate to use for CFDI invoicing per SAT/Banxico rules.
    
    If T-1 is a weekend or Mexican bank holiday, walks back up to 10 days
    to find the last available FIX rate.
    
    Args:
        target_date: The invoice/payment posting_date in YYYY-MM-DD format
        token: Banxico API token (optional)
    
    Returns:
        Tuple of (rate, rate_date) or (None, None) if not found
        - rate: float, MXN per 1 USD
        - rate_date: str, YYYY-MM-DD of the FIX determination date
    """
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    
    # Fetch rates for a window of 15 days before target date
    start_dt = dt - timedelta(days=15)
    end_dt = dt - timedelta(days=1)  # T-1 at most
    
    rates = get_fix_rates_from_banxico(
        start_dt.strftime("%Y-%m-%d"),
        end_dt.strftime("%Y-%m-%d"),
        token=token
    )
    
    if not rates:
        return None, None
    
    # Walk backwards from T-1 to find the most recent business day with a rate
    for days_back in range(1, 15):
        check_date = (dt - timedelta(days=days_back)).strftime("%Y-%m-%d")
        if check_date in rates:
            return rates[check_date], check_date
    
    return None, None


def get_fix_for_invoice(posting_date: str, token: str = None) -> Tuple[Optional[float], Optional[str]]:
    """Get the correct FIX exchange rate for a Sales Invoice.
    
    Rule: Use FIX(T-1) where T = posting_date.
    This is the rate published in DOF on the invoice date.
    
    Args:
        posting_date: Invoice posting_date in YYYY-MM-DD
        token: Banxico API token
    
    Returns:
        Tuple of (rate, rate_date)
    """
    return get_fix_t_minus_1(posting_date, token=token)


def get_fix_for_payment(posting_date: str, token: str = None) -> Tuple[Optional[float], Optional[str]]:
    """Get the correct FIX exchange rate for a Payment Entry.
    
    Rule: Use FIX(T-1) where T = payment posting_date.
    The difference between invoice rate and payment rate goes to
    Exchange Gain/Loss account (ganancia/pérdida cambiaria).
    
    Args:
        posting_date: Payment posting_date in YYYY-MM-DD
        token: Banxico API token
    
    Returns:
        Tuple of (rate, rate_date)
    """
    return get_fix_t_minus_1(posting_date, token=token)


def populate_currency_exchange(start_date: str, end_date: str,
                                token: str = None, dry_run: bool = False) -> Dict:
    """Bulk-load Banxico FIX rates into ERPNext's Currency Exchange table.
    
    This pre-populates the exchange rate table so ERPNext auto-picks the
    correct rate when invoices/payments are created for historical dates.
    
    Args:
        start_date: Start date YYYY-MM-DD (e.g., "2024-01-01")
        end_date: End date YYYY-MM-DD (e.g., "2024-12-31")
        token: Banxico API token
        dry_run: If True, only returns what would be created without saving
    
    Returns:
        Dict with created, skipped, errors counts and details
    """
    rates = get_fix_rates_from_banxico(start_date, end_date, token=token)
    
    result = {
        "total_rates": len(rates),
        "created": 0,
        "skipped": 0,
        "errors": 0,
        "details": []
    }
    
    for date_str, rate in sorted(rates.items()):
        # Check if Currency Exchange entry already exists for this date
        existing = frappe.db.exists("Currency Exchange", {
            "date": date_str,
            "from_currency": "USD",
            "to_currency": "MXN"
        })
        
        if existing:
            result["skipped"] += 1
            result["details"].append({
                "date": date_str, "rate": rate, "action": "skipped",
                "reason": f"Already exists: {existing}"
            })
            continue
        
        if dry_run:
            result["details"].append({
                "date": date_str, "rate": rate, "action": "would_create"
            })
            result["created"] += 1
            continue
        
        try:
            ce = frappe.get_doc({
                "doctype": "Currency Exchange",
                "date": date_str,
                "from_currency": "USD",
                "to_currency": "MXN",
                "exchange_rate": rate,
                "for_buying": 1,
                "for_selling": 1
            })
            ce.insert(ignore_permissions=True)
            result["created"] += 1
            result["details"].append({
                "date": date_str, "rate": rate, "action": "created",
                "name": ce.name
            })
        except Exception as e:
            result["errors"] += 1
            result["details"].append({
                "date": date_str, "rate": rate, "action": "error",
                "error": str(e)
            })
    
    if not dry_run:
        frappe.db.commit()
    
    return result


def calculate_exchange_gain_loss(
    invoice_rate: float,
    payment_rate: float,
    usd_amount: float
) -> Dict:
    """Calculate exchange gain or loss between invoice and payment dates.
    
    Mexican accounting rule:
      Invoice: USD 10,000 × TC 17.26 = MXN 172,600 (receivable)
      Payment: USD 10,000 × TC 17.60 = MXN 176,000 (received)
      Gain: MXN 3,400 → "Utilidad cambiaria" (income)
      
      If payment rate < invoice rate → Loss → "Pérdida cambiaria" (expense)
    
    Args:
        invoice_rate: conversion_rate at invoice time (MXN per USD)
        payment_rate: conversion_rate at payment time (MXN per USD)
        usd_amount: Amount in USD being paid
    
    Returns:
        Dict with gain/loss details:
        - invoice_mxn: MXN amount at invoice rate
        - payment_mxn: MXN amount at payment rate
        - difference_mxn: Absolute difference
        - is_gain: True if gain, False if loss
        - type: "gain" or "loss"
        - type_es: "Utilidad cambiaria" or "Pérdida cambiaria"
    """
    invoice_mxn = usd_amount * invoice_rate
    payment_mxn = usd_amount * payment_rate
    difference = payment_mxn - invoice_mxn
    
    return {
        "invoice_rate": invoice_rate,
        "payment_rate": payment_rate,
        "usd_amount": usd_amount,
        "invoice_mxn": round(invoice_mxn, 2),
        "payment_mxn": round(payment_mxn, 2),
        "difference_mxn": round(abs(difference), 2),
        "is_gain": difference > 0,
        "type": "gain" if difference > 0 else "loss",
        "type_es": "Utilidad cambiaria" if difference > 0 else "Pérdida cambiaria"
    }
