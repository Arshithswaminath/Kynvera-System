# Chargeable vs Non-Chargeable — how assignments work

This document explains how the **MMR (Report Generation)** module decides whether each work order is **Chargeable** or **Non-Chargeable** for reporting. The resolved value is what you see in the **Space** column on the dashboard and in Excel/email summaries (all use the same logic).

| Canonical value | Meaning in KPIs, charts, and reports |
|-----------------|--------------------------------------|
| **Chargeable** | Counted as chargeable |
| **Non-Chargeable** | Counted as non-chargeable |

**Code:** `module_mmr/mmr_service.py` — `_resolve_chargeable()` and helpers (`_text_indicates_roof_top`, `_baseunit_is_non_chargeable_cafm_labels`, `_normalise_space`; apartment pattern `_APT_NO_WITH_NUMBER_RE`).

---

## 1. Inputs (columns used)

The resolver reads these CAFM / Excel fields (empty cells are treated as blank strings):

| Column | Role |
|--------|------|
| **Service Group** | Service type (drives facade, elevator, Garden AC rules). |
| **Client** | Combined with Contract for “office default” and Garden City checks. |
| **Contract** | Same as Client for those checks. |
| **BaseUnit** | Location label from CAFM; drives most rules when it has text. |
| **Space** | Original Excel billing flag; used only when BaseUnit is empty and the client is not in the office-default list (see §6). |
| **Work Description** | Free text; scanned for **roof top** / **rooftop** patterns (§3). |
| **Specific Area** | Optional CAFM column; same roof-top scan as Work Description (§3). |

---

## 2. Evaluation order (first match wins)

Rules run **top to bottom**. As soon as one rule applies, the result is fixed and **no later rule** is used for that row.

| Step | Rule (summary) | If it applies → |
|------|------------------|-----------------|
| 1 | Service Group contains **facade cleaning** | Non-Chargeable |
| 2 | Service Group is **elevator** / **elevater** (not “elevation”) | Non-Chargeable |
| 3 | **BaseUnit**, **Work Description**, or **Specific Area** matches roof top / rooftop (§3) | Non-Chargeable |
| 4 | Client or Contract contains **garden** *and* Service Group looks like **AC/HVAC** | Non-Chargeable |
| 5 | **BaseUnit** is non-empty → **Apt No + number** (§4.1) | Chargeable |
| 6 | **BaseUnit** is non-empty → CAFM labels or **floor** (§4.2) | Non-Chargeable or Chargeable |
| 7 | **BaseUnit** empty → Askaan / Ajman Holding / Injaaz (§5) | Chargeable |
| 8 | **BaseUnit** empty → else use Excel **Space** with typo mapping (§6) | Chargeable or Non-Chargeable |

---

## 3. Roof top / rooftop (any of three fields)

After facade and elevator rules, the system scans **BaseUnit**, **Work Description**, and **Specific Area** together. If the combined text matches the roof pattern, the row is **Non-Chargeable** (even if Excel Space said Chargeable or BaseUnit is a generic building name).

| Detection | Examples that match |
|-----------|---------------------|
| Regex `roof` + optional spaces + `t` + one or more `o` + `p` (case-insensitive) | `roof top`, `roof toop`, `rooftop`, `Roof Top` |

**Typical use:** Specific Area = “Roof Top”, or description mentions “roof toop” / “roof top”, or BaseUnit text includes the same pattern.

**Does not match:** unrelated phrases that do not contain that pattern (e.g. a building name without “roof/top” wording).

---

## 4. BaseUnit has text (after steps 1–4)

When **BaseUnit** is not empty, rules below run **in order** (§4.1 first).

### 4.1 Chargeable — “Apt No” + apartment number

If BaseUnit matches **Apt No** followed by at least one digit (flexible spacing), the row is **Chargeable**. This is evaluated **before** reception / outside / **floor** rules, so apartment labels stay billable even if the same cell also mentions e.g. a floor elsewhere.

| Pattern (case-insensitive regex) | Examples |
|----------------------------------|----------|
| `apt` + optional spaces + `no` + optional spaces + one or more digits | `Apt No 911`, `apt no 12`, `AptNo 305` |

**Does not match:** `Apt No` with no digits, or text that does not contain this pattern.

### 4.2 Non-Chargeable — CAFM-style labels or “floor”

If §4.1 did not apply, BaseUnit is compared **case-insensitively**:

| Condition on BaseUnit | Result |
|-----------------------|--------|
| Contains **reception** | Non-Chargeable |
| Contains **outside** or **out side** | Non-Chargeable |
| Contains both **exit** and **entry** | Non-Chargeable |
| Contains **exit/** or **exit /** | Non-Chargeable |
| Contains **floor** | Non-Chargeable |

### 4.3 Otherwise — any other non-empty BaseUnit

| Result |
|--------|
| **Chargeable** |

Applies to **all** clients (including Askaan, Ajman Holding, Injaaz) when BaseUnit is non-empty and does not match §4.2.

**Examples (Chargeable):** `Lobby`, `Lift Area`, `GYM Equipment`, numeric-only labels (no `floor` in the label). (Apartment numbers are handled in §4.1.)

---

## 5. BaseUnit empty — default Chargeable for named office clients

| Condition | Result |
|-----------|--------|
| **Client** or **Contract** (combined, lowercased) contains **askaan**, **ajman holding**, or **injaaz** | **Chargeable** |

Used when CAFM leaves BaseUnit blank for those sites.

---

## 6. BaseUnit empty — everyone else: use Excel **Space**

If §5 does not apply:

1. Read the workbook **Space** cell.
2. Normalise known typos (table below).
3. If the normalised value is **Chargeable** or **Non-Chargeable**, use it.
4. If missing, unknown, or anything else → **Non-Chargeable**.

### Excel Space typo normalisation

| Raw value (examples, case-insensitive) | Mapped to |
|----------------------------------------|-----------|
| `chargeable`, `chargebale` | Chargeable |
| `non-chargeable`, `non-chargebale`, `non chargeable`, `non chargebale` | Non-Chargeable |

Any other text is **not** treated as a trusted billing flag unless it resolves to one of the two rows above.

---

## 7. Global rules detail (steps 1–2 and 4)

### 7.1 Facade Cleaning — Non-Chargeable

| Condition | Result |
|-----------|--------|
| **Service Group** (lowercased) contains `facade cleaning` | Non-Chargeable |

### 7.2 Elevator works — Non-Chargeable

| Condition | Result |
|-----------|--------|
| **Service Group** matches regex `elevat(or|er)` (case-insensitive) | Non-Chargeable |

**Matched:** “Elevator system”, CAFM typo “Elevater system”.  
**Not matched:** “elevation” (civil / unrelated).

### 7.3 Garden City — AC/HVAC only — Non-Chargeable

| Condition | Result |
|-----------|--------|
| **Client** or **Contract** contains `garden` **and** **Service Group** contains one of: `hvac`, `ac`, `air conditioning`, `airconditioning` | Non-Chargeable |

Other Garden City service groups are **not** forced non-chargeable by this rule alone.

---

## 8. Where this logic runs

The same resolution is applied when:

| Context |
|---------|
| Uploading a CAFM Excel file to the MMR dashboard |
| Opening a saved report from the report folder |
| Building the **Space** column in generated Excel reports |
| Chargeable summaries in scheduled / manual emails |
| Dashboard KPIs and charts that use resolved chargeable totals |

---

## 9. One-page quick reference

| Situation | Typical result |
|-----------|----------------|
| Facade Cleaning (service group) | Non-Chargeable |
| Elevator / Elevater (service group) | Non-Chargeable |
| Roof top / rooftop in BaseUnit, Work Description, or Specific Area | Non-Chargeable |
| Garden + AC/HVAC-type service group | Non-Chargeable |
| BaseUnit matches **Apt No** + number (§4.1) | Chargeable |
| BaseUnit = reception / outside / out side / exit+entry / exit/ / contains **floor** (and §4.1 did not apply) | Non-Chargeable |
| BaseUnit = anything else (non-empty), and steps 1–4 did not fire | Chargeable |
| BaseUnit empty + Askaan / Ajman Holding / Injaaz | Chargeable |
| BaseUnit empty + other client + Excel Space chargeable (after typo fix) | Chargeable |
| BaseUnit empty + other client + Excel Space non-chargeable or blank / unknown | Non-Chargeable |

---

## 10. Maintenance

When business rules change, update **`_resolve_chargeable`** (and related helpers) in **`mmr_service.py`**, then align this document so they stay in sync.
