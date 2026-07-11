import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.rag_manager import rag_manager

res = rag_manager.query_rag("IV Start Kit in Emergency Department", n_results=2)
print("=== RAG RESULT ===")
print(res)
print("==================")
