import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
MEMORY_FILE = os.path.join(DATA_DIR, 'memory.json')

def get_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, 'r') as f:
        return json.load(f)

def save_memory(mem_data):
    with open(MEMORY_FILE, 'w') as f:
        json.dump(mem_data, f, indent=4)

def add_message(session_id, role, content):
    mem = get_memory()
    if session_id not in mem:
        mem[session_id] = []
    mem[session_id].append({"role": role, "content": content})
    save_memory(mem)
    return mem[session_id]

def get_messages(session_id):
    mem = get_memory()
    return mem.get(session_id, [])
