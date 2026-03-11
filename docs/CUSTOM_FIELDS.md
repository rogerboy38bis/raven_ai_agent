# Custom Fields for Sales Order - PO Extraction

## Best Practice Order:
1. ✅ DocType (fixtures in app) - defined below
2. ⚠️ Fixtures - will export after creating custom field
3. Database - auto-created on app install

---

## Approach for Frappe Cloud:
1. Create Custom Field DocType in app
2. Define fields in fixtures  
3. App install auto-adds fields

---

## Alternative (Simpler for now):
Use `create_custom_fields()` function in hooks.py

This is cleaner for deployment without bench access.
