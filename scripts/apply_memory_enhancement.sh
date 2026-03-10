#!/bin/bash
# Apply Memory Enhancement DocType changes
# Run on your ERPNext bench server

cd /home/frappe/frappe-bench || exit 1

echo "=========================================="
echo "Applying Memory Enhancement Changes"
echo "=========================================="

# 1. Pull latest changes
echo "[1/4] Pulling latest raven_ai_agent..."
cd /home/frappe/frappe-bench/sites/apps/raven_ai_agent || (
    bench get-app https://github.com/rogerboy38/raven_ai_agent --branch main
)
cd /home/frappe/frappe-bench/sites/apps/raven_ai_agent && git pull origin main

# 2. Migrate the site
echo "[2/4] Running bench migrate..."
bench --site erp.sysmayal2.cloud migrate

# 3. Sync the DocType
echo "[3/4] Syncing AI Memory DocType..."
bench --site erp.sysmayal2.cloud migrate

# Or force sync via:
# bench --site erp.sysmayal2.cloud install-app raven_ai_agent

# 4. Verify
echo "[4/4] Verifying fields..."
curl -s -u "46f1208a5275572:7ccbed0c82eaf00" \
    "https://erp.sysmayal2.cloud/api/metadata/doctype/AI%20Memory" | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
fields = [f.get('fieldname') for f in data.get('fields', [])]
tests = ['importance_score', 'entities', 'topics', 'consolidated', 'consolidation_refs']
for t in tests:
    status = '✅' if t in fields else '❌'
    print(f'{status} {t}')
"

echo "=========================================="
echo "Done! Fields should now be available."
echo "=========================================="
