import json
import os
import threading
import datetime
from typing import Dict, List, Any, Optional

DB_FILE_PATH = os.path.join(os.path.dirname(__file__), "db.json")
lock = threading.Lock()

class JSONDatabase:
    def __init__(self, filepath: str = DB_FILE_PATH):
        self.filepath = filepath
        self._ensure_db_exists()

    def _empty_db_structure(self) -> Dict[str, Any]:
        return {
            "nurses": [],
            "schedule": [],
            "memory": {},
            "logs": [],
            "audit_logs": []
        }

    def _needs_demo_seed(self, data: Dict[str, Any]) -> bool:
        """Return True when the demo nurse registry and shift schedule are missing.

        Railway can start with no db.json, or with a db.json that has empty
        nurses/schedule arrays. The UI tables are read from GET /api/nurses and
        GET /api/schedule, so an empty database makes the tables disappear.
        """
        nurses = data.get("nurses") or []
        schedule = data.get("schedule") or []
        return len(nurses) == 0 and len(schedule) == 0

    def _ensure_db_exists(self):
        # If the database file is missing, seed it with the demo data immediately
        # instead of creating empty nurses/schedule arrays.
        if not os.path.exists(self.filepath):
            self.reset_db()
            return

        data = self._read_raw()

        # If Railway or a prior run left an empty db.json, reseed the demo data.
        if self._needs_demo_seed(data):
            self.reset_db()
            return

        # Preserve populated databases, but make sure expected top-level keys exist.
        changed = False
        for key, default_value in self._empty_db_structure().items():
            if key not in data:
                data[key] = default_value
                changed = True
        if changed:
            self._write_raw(data)

    def ensure_demo_data(self) -> bool:
        """Ensure GET /api/nurses and GET /api/schedule never return blank demo tables.

        This is intentionally safe: it only seeds when BOTH nurses and schedule
        are empty. It does not overwrite a populated database.
        """
        data = self._read_raw()
        if self._needs_demo_seed(data):
            return self.reset_db()
        return True

    def _read_raw(self) -> Dict[str, Any]:
        with lock:
            try:
                with open(self.filepath, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading JSON database: {e}")
                return {"nurses": [], "schedule": [], "memory": {}, "logs": []}

    def _write_raw(self, data: Dict[str, Any]) -> bool:
        with lock:
            try:
                with open(self.filepath, "w") as f:
                    json.dump(data, f, indent=2)
                return True
            except Exception as e:
                print(f"Error writing to JSON database: {e}")
                return False

    def get_nurses(self) -> List[Dict[str, Any]]:
        self.ensure_demo_data()
        return self._read_raw().get("nurses", [])

    def get_nurse_by_id(self, nurse_id: str) -> Optional[Dict[str, Any]]:
        nurses = self.get_nurses()
        for nurse in nurses:
            if nurse["id"] == nurse_id:
                return nurse
        return None

    def update_nurse_hours(self, nurse_id: str, additional_hours: int) -> bool:
        data = self._read_raw()
        for nurse in data.get("nurses", []):
            if nurse["id"] == nurse_id:
                nurse["weekly_hours"] = nurse.get("weekly_hours", 0) + additional_hours
                return self._write_raw(data)
        return False

    def add_nurse(self, nurse: Dict[str, Any]) -> bool:
        data = self._read_raw()
        if "nurses" not in data:
            data["nurses"] = []
        data["nurses"].append(nurse)
        return self._write_raw(data)


    def get_schedule(self) -> List[Dict[str, Any]]:
        self.ensure_demo_data()
        return self._read_raw().get("schedule", [])

    def add_schedule_shift(self, shift: Dict[str, Any]) -> bool:
        data = self._read_raw()
        if "schedule" not in data:
            data["schedule"] = []
        data["schedule"].append(shift)
        return self._write_raw(data)

    def update_shift_status(self, shift_id: str, status: str, assigned_nurses: List[str]) -> bool:
        data = self._read_raw()
        for shift in data.get("schedule", []):
            if shift["id"] == shift_id:
                shift["status"] = status
                shift["assigned_nurses"] = assigned_nurses
                return self._write_raw(data)
        return False

    def get_logs(self) -> List[Dict[str, Any]]:
        return self._read_raw().get("logs", [])

    def add_log(self, log_entry: Dict[str, Any]) -> bool:
        data = self._read_raw()
        if "logs" not in data:
            data["logs"] = []
        data["logs"].append(log_entry)
        return self._write_raw(data)

    def update_log_status(self, log_id: str, status: str) -> bool:
        data = self._read_raw()
        for log in data.get("logs", []):
            if log["id"] == log_id:
                log["status"] = status
                return self._write_raw(data)
        return False

    def get_audit_logs(self) -> List[Dict[str, Any]]:
        return self._read_raw().get("audit_logs", [])

    def add_audit_log(self, audit_entry: Dict[str, Any]) -> bool:
        data = self._read_raw()
        if "audit_logs" not in data:
            data["audit_logs"] = []
        data["audit_logs"].append(audit_entry)
        return self._write_raw(data)

    def get_memory(self) -> Dict[str, Any]:
        return self._read_raw().get("memory", {})

    def update_memory(self, key: str, value: Any) -> bool:
        data = self._read_raw()
        if "memory" not in data:
            data["memory"] = {}
        data["memory"][key] = value
        return self._write_raw(data)

    def reset_db(self) -> bool:
        today = datetime.date.today()
        tomorrow = today + datetime.timedelta(days=1)
        default_data = {
            "nurses": [
                {
                    "id": "NURSE_001",
                    "name": "Sarah Jenkins",
                    "certifications": ["Emergency", "ICU"],
                    "weekly_hours": 36,
                    "base_rate": 55.0,
                    "circadian_preference": "Night",
                    "distance_miles": 5,
                    "phone": "+1-555-0192"
                },
                {
                    "id": "NURSE_002",
                    "name": "David Miller",
                    "certifications": ["Emergency"],
                    "weekly_hours": 44,
                    "base_rate": 48.0,
                    "circadian_preference": "Morning",
                    "distance_miles": 12,
                    "phone": "+1-555-0183"
                },
                {
                    "id": "NURSE_003",
                    "name": "Elena Rostova",
                    "certifications": ["ICU", "Pediatrics"],
                    "weekly_hours": 24,
                    "base_rate": 58.0,
                    "circadian_preference": "Flexible",
                    "distance_miles": 8,
                    "phone": "+1-555-0174"
                },
                {
                    "id": "NURSE_004",
                    "name": "Marcus Vance",
                    "certifications": ["Emergency", "Pediatrics"],
                    "weekly_hours": 48,
                    "base_rate": 52.0,
                    "circadian_preference": "Morning",
                    "distance_miles": 22,
                    "phone": "+1-555-0165"
                },
                {
                    "id": "NURSE_005",
                    "name": "Jessica Taylor",
                    "certifications": ["Emergency"],
                    "weekly_hours": 8,
                    "base_rate": 47.0,
                    "circadian_preference": "Flexible",
                    "distance_miles": 3,
                    "phone": "+1-555-0156"
                },
                {
                    "id": "NURSE_006",
                    "name": "Chloe Vance",
                    "certifications": ["Emergency", "ICU"],
                    "weekly_hours": 52,
                    "base_rate": 56.0,
                    "circadian_preference": "Night",
                    "distance_miles": 15,
                    "phone": "+1-555-0147"
                },
                {
                    "id": "NURSE_007",
                    "name": "Arjun Patel",
                    "certifications": ["Pediatrics"],
                    "weekly_hours": 40,
                    "base_rate": 50.0,
                    "circadian_preference": "Morning",
                    "distance_miles": 9,
                    "phone": "+1-555-0138"
                },
                {
                    "id": "NURSE_008",
                    "name": "Emily Watson",
                    "certifications": ["Emergency"],
                    "weekly_hours": 32,
                    "base_rate": 49.0,
                    "circadian_preference": "Flexible",
                    "distance_miles": 6,
                    "phone": "+1-555-0129"
                },
                {
                    "id": "NURSE_009",
                    "name": "Daniel Kim",
                    "certifications": ["ICU"],
                    "weekly_hours": 40,
                    "base_rate": 54.0,
                    "circadian_preference": "Night",
                    "distance_miles": 14,
                    "phone": "+1-555-0110"
                },
                {
                    "id": "NURSE_010",
                    "name": "Sofia Al-Mansoor",
                    "certifications": ["Emergency", "Pediatrics"],
                    "weekly_hours": 20,
                    "base_rate": 57.0,
                    "circadian_preference": "Morning",
                    "distance_miles": 10,
                    "phone": "+1-555-0101"
                },
                {
                    "id": "NURSE_011",
                    "name": "Liam O'Connor",
                    "certifications": ["Emergency", "ICU"],
                    "weekly_hours": 36,
                    "base_rate": 53.0,
                    "circadian_preference": "Flexible",
                    "distance_miles": 18,
                    "phone": "+1-555-0099"
                },
                {
                    "id": "NURSE_012",
                    "name": "Grace Hopper",
                    "certifications": ["ICU", "Pediatrics"],
                    "weekly_hours": 40,
                    "base_rate": 60.0,
                    "circadian_preference": "Flexible",
                    "distance_miles": 4,
                    "phone": "+1-555-0088"
                },
                {
                    "id": "NURSE_013",
                    "name": "Oliver Smith",
                    "certifications": ["ICU"],
                    "weekly_hours": 40,
                    "base_rate": 55.0,
                    "circadian_preference": "Night",
                    "distance_miles": 11,
                    "phone": "+1-555-0077"
                },
                {
                    "id": "NURSE_014",
                    "name": "Emma Johnson",
                    "certifications": ["Emergency"],
                    "weekly_hours": 36,
                    "base_rate": 50.0,
                    "circadian_preference": "Morning",
                    "distance_miles": 7,
                    "phone": "+1-555-0066"
                },
                {
                    "id": "NURSE_015",
                    "name": "Lucas Miller",
                    "certifications": ["Emergency", "ICU"],
                    "weekly_hours": 48,
                    "base_rate": 56.0,
                    "circadian_preference": "Flexible",
                    "distance_miles": 15,
                    "phone": "+1-555-0055"
                },
                {
                    "id": "NURSE_016",
                    "name": "Mia Brown",
                    "certifications": ["Pediatrics"],
                    "weekly_hours": 24,
                    "base_rate": 48.0,
                    "circadian_preference": "Morning",
                    "distance_miles": 9,
                    "phone": "+1-555-0044"
                },
                {
                    "id": "NURSE_017",
                    "name": "Ethan Garcia",
                    "certifications": ["ICU", "Pediatrics"],
                    "weekly_hours": 32,
                    "base_rate": 58.0,
                    "circadian_preference": "Night",
                    "distance_miles": 13,
                    "phone": "+1-555-0033"
                },
                {
                    "id": "NURSE_018",
                    "name": "Isabella Davis",
                    "certifications": ["Emergency", "Pediatrics"],
                    "weekly_hours": 40,
                    "base_rate": 52.0,
                    "circadian_preference": "Flexible",
                    "distance_miles": 5,
                    "phone": "+1-555-0022"
                }
            ],
            "schedule": [
                {
                    "id": "SHIFT_001",
                    "date": today.isoformat(),
                    "shift_type": "Morning",
                    "department": "Emergency",
                    "assigned_nurses": ["NURSE_002", "NURSE_004", "NURSE_007"],
                    "acuity_level": 3,
                    "predicted_wait_time": 42.5,
                    "status": "Staffed"
                },
                {
                    "id": "SHIFT_002",
                    "date": today.isoformat(),
                    "shift_type": "Night",
                    "department": "Emergency",
                    "assigned_nurses": ["NURSE_001", "NURSE_006"],
                    "acuity_level": 4,
                    "predicted_wait_time": 58.0,
                    "status": "Staffed"
                },
                {
                    "id": "SHIFT_003",
                    "date": tomorrow.isoformat(),
                    "shift_type": "Morning",
                    "department": "Emergency",
                    "assigned_nurses": ["NURSE_002", "NURSE_005"],
                    "acuity_level": 3,
                    "predicted_wait_time": 55.0,
                    "status": "Staffed"
                }
            ],
            "memory": {
                "nurse_refusal_count": {
                    "NURSE_002": 1
                },
                "incentive_bonus_threshold": 45.0
            },
            "logs": [],
            "audit_logs": []
        }
        return self._write_raw(default_data)

if __name__ == "__main__":
    db = JSONDatabase()
    print("Database loaded. Number of nurses:", len(db.get_nurses()))
