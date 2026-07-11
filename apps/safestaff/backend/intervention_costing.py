import os
import json

def load_intervention_cost_catalog():
    """Loads the intervention cost catalog JSON config file."""
    catalog_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database", "intervention_cost_catalog.json")
    try:
        if os.path.exists(catalog_path):
            with open(catalog_path, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading intervention cost catalog: {e}")
    return {"interventions": {}}

def calculate_single_intervention_cost(action_id, quantity=1, hours=None):
    """Calculates estimated costing details for a single intervention based on catalog configuration."""
    catalog = load_intervention_cost_catalog()
    interventions = catalog.get("interventions", {})
    
    if action_id not in interventions:
        return {
            "action_id": action_id,
            "name": action_id.replace("_", " ").title(),
            "quantity": quantity,
            "hours": hours,
            "cost_status": "unknown",
            "estimated_cost": 0.0,
            "cost_formula": "N/A",
            "cost_assumption_source": "N/A",
            "cost_note": f"Action ID '{action_id}' not found in cost catalog."
        }
        
    config = interventions[action_id]
    name = config.get("name", action_id.replace("_", " ").title())
    formula_type = config.get("type", "fixed")
    source = config.get("cost_assumption_source", "Generic Cost Model")
    note = config.get("cost_note", "")
    
    default_hours = config.get("default_hours", 12.0)
    calc_hours = hours if hours is not None else default_hours
    
    if formula_type == "hourly":
        rate = config.get("hourly_rate", 0.0)
        cost = rate * calc_hours * quantity
        formula = f"${rate:.2f}/hr * {calc_hours}h * {quantity} qty"
    elif formula_type == "fixed_plus_hourly":
        fixed = config.get("fixed_cost", 0.0)
        rate = config.get("hourly_rate", 0.0)
        cost = (fixed + (rate * calc_hours)) * quantity
        formula = f"(${fixed:.2f} + (${rate:.2f}/hr * {calc_hours}h)) * {quantity} qty"
    else:  # fixed
        fixed = config.get("fixed_cost", 0.0)
        cost = fixed * quantity
        formula = f"${fixed:.2f} * {quantity} qty"
        
    return {
        "action_id": action_id,
        "name": name,
        "quantity": quantity,
        "hours": calc_hours if formula_type in ["hourly", "fixed_plus_hourly"] else None,
        "cost_status": "estimated",
        "estimated_cost": float(cost),
        "cost_formula": formula,
        "cost_assumption_source": source,
        "cost_note": note
    }

def attach_costs_to_interventions(interventions):
    """Enriches an intervention list by attaching detailed costing information to each item."""
    costed = []
    for item in interventions:
        if not isinstance(item, dict):
            costed.append(item)
            continue
            
        action_id = item.get("action_id")
        if not action_id:
            costed.append(item)
            continue
            
        qty = item.get("quantity", 1)
        hrs = item.get("hours")
        
        cost_details = calculate_single_intervention_cost(action_id, quantity=qty, hours=hrs)
        
        merged = dict(item)
        merged.update({
            "name": cost_details["name"],
            "quantity": cost_details["quantity"],
            "cost_status": cost_details["cost_status"],
            "estimated_cost": cost_details["estimated_cost"],
            "cost_formula": cost_details["cost_formula"],
            "cost_assumption_source": cost_details["cost_assumption_source"],
            "cost_note": cost_details["cost_note"]
        })
        if cost_details["hours"] is not None:
            merged["hours"] = cost_details["hours"]
            
        costed.append(merged)
    return costed
