import os
import json
from backend.packing_queue import build_packing_queue
from backend.data_loader import generate_inventory_state
from backend.traceability import ensure_traceability_fields

print("Loading inventory...")
records = ensure_traceability_fields()
if not records:
    generate_inventory_state()
    records = ensure_traceability_fields()

print("Building packing queue...")
try:
    queue = build_packing_queue(records, limit=5, max_records=50)
    print("Success!", len(queue))
except Exception as e:
    import traceback
    traceback.print_exc()
