# MedPack AI — Standard Operating Procedures (SOPs)

**Document ID:** SOP-MASTER-001  
**Effective Date:** January 1, 2025  
**Classification:** Internal — Supply Chain Operations

---

## SOP-101: IV Kit Shortage — Emergency Department

**Trigger:** IV Kit stock in the Emergency Department falls below 20% of the 24-hour forecasted demand.

**Actions:**

1. Check the FAISS-indexed inventory for usable IV Kits across all departments.
2. If usable stock exists in another department (e.g., Med-Surg), initiate an internal transfer via the Transfer Optimizer.
3. Substitute with Pediatric IV Kits for patients under 40 kg if standard IV Kits are unavailable.
4. For critical patients, Central Line Kits may be used as a last resort.
5. **Do not use expired IV Kits under any circumstances**, even if they appear in the inventory system.
6. Escalate to the Shift Supervisor within 30 minutes if stock cannot be replenished.

**Owner:** ED Charge Nurse  
**Escalation Contact:** Supply Chain Manager on Duty

---

## SOP-102: IV Kit Shortage — ICU

**Trigger:** IV Kit stock in the ICU falls below PAR level (minimum 15 units).

**Actions:**

1. Halt allocation of IV Kits to elective procedures.
2. Contact Central Supply for emergency redistribution from the warehouse.
3. If warehouse stock is also low, initiate an emergency supplier order (see SLA-001).
4. Log the shortage event in the MedPack AI memory system for trend analysis.

**Owner:** ICU Charge Nurse  
**Escalation Window:** 15 minutes

---

## SOP-201: Surgical Mask Shortage — Operating Room

**Trigger:** Level 3 Surgical Mask stock in the OR falls below 50 units.

**Actions:**

1. Switch to N95 Respirators for all surgical procedures.
2. **Level 1 masks are not permitted in the Operating Room** under any circumstances.
3. Contact the warehouse to prioritize Surgical Mask restocking for the OR.
4. If N95 stock is also low, contact Infection Control for guidance.

**Owner:** OR Charge Nurse  
**Escalation Contact:** Infection Control Officer

---

## SOP-301: Saline Flush Shortage

**Trigger:** Pre-filled 10 mL saline flush stock falls below 100 units hospital-wide.

**Actions:**

1. Nurses may manually draw 10 mL from a 1L normal saline bag using a sterile syringe.
2. This workaround requires a licensed RN and adds approximately 2 minutes per flush.
3. Prioritize pre-filled flush allocation to the ICU and ED.
4. Notify the pharmacy for bulk saline bag availability.

**Owner:** Unit Charge Nurse  
**Note:** Manual drawing increases infection risk slightly. Limit to 48-hour maximum.

---

## SOP-401: Wound Care Pack Shortage — Labor and Delivery

**Trigger:** Wound Care Pack stock in L&D falls below 5 units.

**Actions:**

1. For non-hemorrhagic cases, substitute with basic gauze and surgical tape.
2. For hemorrhagic cases, maintain full Wound Care Packs — escalate immediately if unavailable.
3. Request emergency transfer from the ED or Med-Surg wound care inventory.

**Owner:** L&D Charge Nurse

---

## SOP-501: General Escalation Policy

**Trigger:** Any supply item drops below 20% of the 24-hour forecasted demand.

**Actions:**

1. The MedPack AI system automatically flags the item as **Critical** or **High** risk.
2. A mandatory Command Center Escalation notification is generated.
3. The Shift Supervisor must acknowledge within 30 minutes.
4. If no acknowledgment, escalate to the Supply Chain Director.
5. All escalation events are logged in `supply_memory_events.jsonl` for audit.

**No exceptions.**

**Owner:** Shift Supervisor  
**Backup:** Supply Chain Director

---

## SOP-601: Catheter Recall Response

**Trigger:** FDA recall notice received for any catheter product.

**Actions:**

1. Immediately quarantine all affected stock (match lot numbers against recall bulletin).
2. Update the MedPack AI inventory state to mark affected units as `recalled`.
3. For Foley Catheters, substitute with straight catheters if continuous drainage is not strictly required.
4. Notify all departments that use catheters.
5. Contact the supplier for replacement stock and credit.

**Owner:** Materials Management  
**Regulatory Contact:** Risk Management / Quality Assurance

---

## SOP-701: Oxygen Tubing Compatibility

**Standard 7 ft oxygen tubing** is compatible with:
- Wall O2 flowmeters
- Portable oxygen tanks
- Standard nasal cannulas

**For high-flow nasal cannula (HFNC):**
- Only use specialized heated tubing (Item #HF-992).
- Standard tubing connected to HFNC devices may cause condensation and flow inconsistencies.

**Owner:** Respiratory Therapy

---

## SOP-801: Ventilator Circuit Shortage — NICU

**Trigger:** Pediatric ventilator circuit stock in the NICU falls below 3 units.

**Actions:**

1. **Adult ventilator circuits cannot be adapted for pediatric use.** Do not attempt modifications.
2. Initiate a hospital-to-hospital transfer request for pediatric circuits.
3. Contact the regional pediatric supply consortium if available.
4. Escalate to the NICU Medical Director immediately.

**Owner:** NICU Charge Nurse  
**Escalation Window:** Immediate

---

## SOP-901: PPE Shortage During Infectious Disease Surge

**Trigger:** N95 Respirator or Isolation Gown stock falls below 24-hour forecasted demand during an active infectious disease surge.

**Actions:**

1. Activate extended-use protocols: healthcare workers may reuse N95s for the same patient cohort during a single shift.
2. Prioritize PPE allocation: ICU > ED > Isolation Units > General Wards.
3. Initiate emergency supplier order (see SLA-001 for Medline 4-hour emergency delivery).
4. Contact Infection Prevention for decontamination/reprocessing guidance if stock is critically low.
5. Log surge event in MedPack AI for retrospective analysis.

**Owner:** Infection Control Officer  
**Escalation Contact:** Chief Nursing Officer
