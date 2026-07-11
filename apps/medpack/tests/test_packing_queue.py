from backend.packing_queue import build_packing_queue


def test_packing_queue_returns_ranked_records():
    inventory_records = [
        {
            "item_name": "Oxygen Mask",
            "department": "ICU",
            "item_category": "Respiratory",
            "current_stock": 2,
            "patient_volume": 40,
            "acuity_level": 4.0,
            "procedure_count": 12,
            "recent_usage_rate": 15.0,
            "supplier_delay_days": 5.0,
            "day_of_week": 1,
            "hour": 14,
            "season": "Winter",
            "reorder_point": 20,
            "supplier_reliability_score": 0.8,
            "pack_time_minutes": 4.0,
            "clinical_criticality": 4,
        },
        {
            "item_name": "Sterile Gauze",
            "department": "Outpatient Clinic",
            "item_category": "Wound Care",
            "current_stock": 100,
            "patient_volume": 5,
            "acuity_level": 1.0,
            "procedure_count": 1,
            "recent_usage_rate": 2.0,
            "supplier_delay_days": 1.0,
            "day_of_week": 1,
            "hour": 14,
            "season": "Winter",
            "reorder_point": 20,
            "supplier_reliability_score": 0.95,
            "pack_time_minutes": 2.0,
            "clinical_criticality": 2,
        },
    ]

    queue = build_packing_queue(inventory_records, limit=2, max_records=2)

    assert len(queue) == 2
    assert queue[0]["priority_score"] >= queue[1]["priority_score"] or queue[0]["risk_level"] in ["Critical", "High"]
    assert "recommended_pack_quantity" in queue[0]
    assert "recommended_action" in queue[0]


def test_packing_queue_changes_when_sidebar_scenario_changes():
    inventory_records = [
        {
            "item_name": "Oxygen Mask",
            "department": "ICU",
            "item_category": "Respiratory",
            "current_stock": 30,
            "patient_volume": 12,
            "acuity_level": 2.0,
            "procedure_count": 3,
            "recent_usage_rate": 5.0,
            "supplier_delay_days": 1.0,
            "day_of_week": 1,
            "hour": 10,
            "season": "Summer",
            "reorder_point": 20,
            "supplier_reliability_score": 0.9,
            "pack_time_minutes": 4.0,
            "clinical_criticality": 4,
        },
        {
            "item_name": "Patient Monitoring Leads",
            "department": "ICU",
            "item_category": "Monitoring",
            "current_stock": 30,
            "patient_volume": 12,
            "acuity_level": 2.0,
            "procedure_count": 3,
            "recent_usage_rate": 5.0,
            "supplier_delay_days": 1.0,
            "day_of_week": 1,
            "hour": 10,
            "season": "Summer",
            "reorder_point": 20,
            "supplier_reliability_score": 0.9,
            "pack_time_minutes": 4.0,
            "clinical_criticality": 4,
        },
    ]

    calm = build_packing_queue(inventory_records, limit=2, max_records=2, scenario={
        "department": "ICU",
        "patient_volume": 8,
        "acuity_level": 1.2,
        "procedure_count": 1,
        "recent_usage_rate": 2.0,
        "supplier_delay_days": 0.5,
        "season": "Summer",
        "hour": 10,
        "day_of_week": 1,
        "current_stock": 80,
    })
    surge = build_packing_queue(inventory_records, limit=2, max_records=2, scenario={
        "department": "ICU",
        "patient_volume": 90,
        "acuity_level": 4.0,
        "procedure_count": 35,
        "recent_usage_rate": 35.0,
        "supplier_delay_days": 8.0,
        "season": "Winter",
        "hour": 22,
        "day_of_week": 6,
        "current_stock": 5,
    })

    assert surge[0]["priority_score"] != calm[0]["priority_score"]
    assert surge[0]["recommended_pack_quantity"] != calm[0]["recommended_pack_quantity"]
    assert surge[0]["scenario_pressure_score"] != calm[0]["scenario_pressure_score"]
