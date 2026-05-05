# HR DOCX Templates – Filling Shared Documents from UI Data

This document explains how the HR module **takes details from the UI** (e.g. Commencement Form) and **enters them into your shared HR document files** (e.g. `HR Documents/Commencement Form - INJAAZ.DOCX`).

## Flow

1. **User fills the form in the UI** – e.g. Commencement Form in the web app (name, position, bank details, signatures, etc.).
2. **Submit** – Data is saved and sent for HR/GM approval.
3. **Download DOCX** – HR or GM use **Download DOCX**; the app fills your shared Word template with that data and sends the filled document.

The template used is **your shared file** in `HR Documents/` (e.g. `Commencement Form - INJAAZ.DOCX`). The app fills in the fields you mark with placeholders (see below).

## Template Location

- **Preferred:** `HR Documents/` (e.g. `HR Documents/Commencement Form - INJAAZ.DOCX`) – your shared document.
- **Fallback:** `HR Documents/templates/` – e.g. if you run `python scripts/create_hr_docx_templates.py` to generate a minimal template.

So **put your Commencement Form - INJAAZ.DOCX in the HR Documents folder** and add the placeholders below; that file will be used when users download the filled document.

## Adding Placeholders to Your Shared Commencement Form

Open **Commencement Form - INJAAZ.DOCX** in Word. Where you want the app to insert UI data, type the **exact** placeholder (including double curly braces). The app will replace them with the values from the form.

Use this syntax: `{{ variable_name }}` (no spaces inside the braces).

### Commencement Form – Placeholders to Add

| What you want in the document | Placeholder to type in the DOCX |
|-------------------------------|----------------------------------|
| Employee name                 | `{{ employee_name }}` |
| Position                      | `{{ position }}` |
| Contacts                      | `{{ contacts }}` |
| Department                    | `{{ department }}` |
| Organization                  | `{{ organization }}` |
| Date of joining               | `{{ date_of_joining }}` |
| Bank name                     | `{{ bank_name }}` |
| Branch                        | `{{ bank_branch }}` |
| Account number                | `{{ account_number }}` |
| Employee signature (image)    | `{{ employee_signature }}` |
| Employee sign date            | `{{ employee_sign_date }}` |
| Reporting to – name           | `{{ reporting_to_name }}` |
| Reporting to – designation    | `{{ reporting_to_designation }}` |
| Reporting to – contact        | `{{ reporting_to_contact }}` |
| Reporting to – signature      | `{{ reporting_to_signature }}` |
| Reporting to – sign date      | `{{ reporting_sign_date }}` |

**Example in Word:**  
If the form has a line “Name: ____________”, replace the blank with:  
`Name: {{ employee_name }}`

For signature areas, put `{{ employee_signature }}` and `{{ reporting_to_signature }}` where the signatures should appear; the app will insert the images from the UI.

## Summary

- **UI:** User enters details in the Commencement Form in the app.  
- **Your document:** Keep `HR Documents/Commencement Form - INJAAZ.DOCX` and add the placeholders above where you want those details.  
- **Download:** When HR/GM click “Download DOCX”, the app fills this document with the submitted form data.
