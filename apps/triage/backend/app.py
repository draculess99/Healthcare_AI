from flask import Flask, request, jsonify
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from backend.agents.triage_system import evaluate_patient
import json
from backend.logger import log_audit_event, read_audit_trail

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
LOG_FILE = os.path.join(DATA_DIR, 'transactions.log')
MEMORY_FILE = os.path.join(DATA_DIR, 'memory.json')
METRICS_FILE = os.path.join(DATA_DIR, 'metrics.json')
QUEUE_FILE = os.path.join(DATA_DIR, 'patient_queue.json')


def read_patient_queue():
    """Return the persisted live waiting-room queue."""
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def write_patient_queue(queue):
    """Persist the live waiting-room queue to data/patient_queue.json."""
    os.makedirs(DATA_DIR, exist_ok=True)
    clean_queue = queue if isinstance(queue, list) else []
    with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
        json.dump(clean_queue, f, indent=2)
    return clean_queue

@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    data = request.json
    session_id = data.get('session_id', 'default_session')
    notes = data.get('notes', '')
    engine_type = data.get('engine_type', 'Local Expert System (0 Tokens)')
    vitals = data.get('vitals', {})
    model_name = data.get('model_name', 'XGBoost')
    llm_model_name = data.get('llm_model_name', 'gemini-1.5-flash')
    dataset_name = data.get('dataset_name', 'UCI Cleveland Original')
    
    def generate():
        for chunk in evaluate_patient(session_id, notes, engine_type, vitals, model_name, llm_model_name, dataset_name):
            yield chunk
            
    return app.response_class(generate(), mimetype='application/x-ndjson')

@app.route('/api/logs', methods=['GET'])
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify([])
    logs = []
    with open(LOG_FILE, 'r') as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line))
    return jsonify(logs)


@app.route('/api/audit', methods=['GET', 'POST'])
def audit_trail():
    """Persist and retrieve nurse/workflow audit events.

    GET returns recent audit events from data/audit_trail.jsonl.
    POST appends a new event, usually from Streamlit queue/override actions.
    """
    if request.method == 'POST':
        payload = request.json or {}
        entry = log_audit_event(
            event_type=payload.get('event_type', 'workflow_event'),
            patient_id=payload.get('patient_id'),
            action=payload.get('action', ''),
            details=payload.get('details', {}),
            source=payload.get('source', 'frontend'),
            session_id=payload.get('session_id', 'demo_session'),
        )
        return jsonify(entry), 201

    try:
        limit = int(request.args.get('limit', 250))
    except Exception:
        limit = 250
    return jsonify(read_audit_trail(limit=limit))

@app.route('/api/queue', methods=['GET', 'POST', 'DELETE'])
def patient_queue():
    """Persist and retrieve the live waiting-room queue.

    This keeps the queue alive across browser refreshes and Streamlit reruns.
    The UI sends the full current queue after add/status/remove/clear actions.
    """
    if request.method == 'GET':
        return jsonify(read_patient_queue())

    if request.method == 'DELETE':
        write_patient_queue([])
        return jsonify({"status": "cleared", "queue": []})

    payload = request.json or {}
    queue = payload.get('queue', [])
    saved_queue = write_patient_queue(queue)
    return jsonify({"status": "saved", "count": len(saved_queue), "queue": saved_queue})

@app.route('/api/memory', methods=['GET'])
def get_memory():
    if not os.path.exists(MEMORY_FILE):
        return jsonify({})
    with open(MEMORY_FILE, 'r') as f:
        return jsonify(json.load(f))

@app.route('/api/train', methods=['POST'])
def train():
    data = request.json
    dataset_name = data.get('dataset_name', 'UCI Cleveland Original')
    from backend.forecaster import train_models
    try:
        train_models(dataset_name)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/xai', methods=['POST'])
def get_xai():
    data = request.json
    model_name = data.get('model_name', 'XGBoost')
    dataset_name = data.get('dataset_name', 'UCI Cleveland Original')
    from backend.forecaster import get_xai_data
    try:
        xai_data = get_xai_data(model_name, dataset_name)
        return jsonify(xai_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    from backend.forecaster import METRICS_PATH, DATASET_FILE
    current_dataset = "UCI Cleveland Original"
    import os
    if os.path.exists(DATASET_FILE):
        with open(DATASET_FILE, 'r') as f:
            current_dataset = f.read().strip()
            
    if os.path.exists(METRICS_PATH):
        with open(METRICS_PATH, 'r') as f:
            return jsonify({
                "metrics": json.load(f),
                "dataset": current_dataset
            })
    return jsonify({"metrics": {}, "dataset": current_dataset})

if __name__ == '__main__':
    app.run(host=os.getenv('TRIAGE_API_HOST', '127.0.0.1'), port=int(os.getenv('TRIAGE_API_PORT', '5103')), debug=False, use_reloader=False)
