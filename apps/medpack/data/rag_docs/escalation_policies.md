# MedPack AI — Escalation Policies

**Document ID:** ESC-MASTER-001  
**Effective Date:** January 1, 2025  
**Classification:** Internal — Supply Chain Operations

---

## Escalation Tiers

### Tier 1 — Monitor (Low Risk)

**Trigger:** Supply coverage ratio is between 50% and 80% of the 24-hour forecasted demand.

**Actions:**

- MedPack AI flags the item as **Low risk**.
- No immediate action required.
- Warehouse team monitors during the next restock cycle.
- Automated reorder is triggered if stock falls below the reorder point.

**Owner:** Warehouse Lead  
**Response Time:** Next scheduled restock cycle

---

### Tier 2 — Act (Medium Risk)

**Trigger:** Supply coverage ratio is between 25% and 50% of the 24-hour forecasted demand.

**Actions:**

- MedPack AI flags the item as **Medium risk**.
- Warehouse team prioritizes this item in the packing queue.
- Check for internal transfer availability from other departments.
- Prepare a reorder request for the next business day if transfers are insufficient.

**Owner:** Warehouse Lead  
**Response Time:** Within 4 hours  
**Escalation if unresolved:** Proceed to Tier 3

---

### Tier 3 — Escalate (High Risk)

**Trigger:** Supply coverage ratio is between 10% and 25% of the 24-hour forecasted demand.

**Actions:**

- MedPack AI flags the item as **High risk**.
- Notify the Shift Supervisor immediately.
- Initiate internal transfers from all available departments.
- Place an emergency supplier order if supplier SLA supports same-day delivery.
- Identify substitute items using the MedPack AI substitution engine.
- Log the escalation event in the memory system.

**Owner:** Shift Supervisor  
**Response Time:** Within 1 hour  
**Escalation if unresolved:** Proceed to Tier 4

---

### Tier 4 — Command Center (Critical Risk)

**Trigger:** Supply coverage ratio is below 10% of the 24-hour forecasted demand, OR the item is classified as clinically critical (PPE, oxygen, catheters in ICU/ED).

**Actions:**

- MedPack AI flags the item as **Critical risk** and generates a Command Center Action Card.
- The Supply Chain Director is notified immediately.
- Emergency supplier order is placed (accept premium pricing if necessary).
- All available internal stock is transferred to the department in need.
- Substitute items are deployed if available and clinically appropriate.
- The Clinical Safety Agent generates a bedside-risk assessment.
- A post-event review is scheduled within 48 hours.

**Owner:** Supply Chain Director  
**Response Time:** Within 15 minutes  
**Backup:** Chief Nursing Officer

---

## Department-Specific Escalation Rules

### Emergency Department

- Any Critical or High-risk shortage in the ED triggers an automatic notification to the ED Medical Director in addition to the Supply Chain Director.
- ED shortages are prioritized above all other departments for internal transfers.

### ICU / NICU

- ICU and NICU shortages for ventilator circuits, IV kits, or monitoring leads trigger immediate Tier 4 escalation regardless of coverage ratio.
- Pediatric/neonatal supply shortages in the NICU escalate to the regional pediatric supply consortium.

### Operating Room

- Any shortage that may impact a scheduled surgery within the next 8 hours triggers Tier 4.
- The OR Charge Nurse must confirm substitute acceptability with the attending surgeon before deployment.

### Labor and Delivery

- Blood product supply shortages trigger a parallel notification to the Blood Bank in addition to normal escalation.

---

## Escalation Communication Channels

| Channel | Use Case |
|---|---|
| MedPack AI Dashboard Alert | All tiers — automated |
| Email notification | Tier 2 and above |
| Phone call / overhead page | Tier 3 and above |
| In-person huddle | Tier 4 |
| Incident report filing | Any event with patient safety impact |

---

## Post-Event Review

All Tier 3 and Tier 4 escalation events require a post-event review within **48 hours**, covering:

1. Root cause of the shortage
2. Effectiveness of the response
3. Whether MedPack AI predictions were accurate
4. Recommendations for PAR level adjustments
5. Supplier performance review
6. Process improvements for future events

Results are documented in the facility's supply chain improvement log and used to update MedPack AI forecasting parameters.
