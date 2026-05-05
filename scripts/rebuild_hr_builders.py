"""
Replaces all _build_* functions (commencement → contract_renewal) in
hr_pdf_builder.py with new single-table implementations that mirror the
HR Documents - Main Word documents exactly (same approach as _build_leave).
"""
import re, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

TARGET = os.path.join(os.path.dirname(__file__), '..', 'module_hr', 'hr_pdf_builder.py')

# ──────────────────────────────────────────────────────────────────────────────
NEW_BUILDERS = r'''
# ─── shared per-form helpers ────────────────────────────────────────────────
_C_SEC_BG = colors.HexColor("#f0f0f0")


def _fstyles():
    """Return (LBL, VAL, SEC, SML, ITL) paragraph styles for form tables."""
    LBL = ParagraphStyle("fLBL", fontSize=9,   fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=12)
    VAL = ParagraphStyle("fVAL", fontSize=9,   fontName="Helvetica",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=12)
    SEC = ParagraphStyle("fSEC", fontSize=9,   fontName="Helvetica-Bold",
                         textColor=C_BLACK, alignment=TA_CENTER, leading=13)
    SML = ParagraphStyle("fSML", fontSize=7.5, fontName="Helvetica",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=10)
    ITL = ParagraphStyle("fITL", fontSize=8.5, fontName="Helvetica-Oblique",
                         textColor=C_BLACK, alignment=TA_LEFT,   leading=11)
    return LBL, VAL, SEC, SML, ITL


def _flv(label, val):
    """'Label: value' paragraph."""
    _, VAL, _, _, _ = _fstyles()
    v = str(val) if val not in (None, "", "-") else ""
    return Paragraph(f"<b>{label}:</b>  {v}", VAL)


def _fsec(text, left=False):
    """Section-header paragraph (centred by default)."""
    align = TA_LEFT if left else TA_CENTER
    s = ParagraphStyle("_fsecX", fontSize=9, fontName="Helvetica-Bold",
                       textColor=C_BLACK, alignment=align, leading=13)
    return Paragraph(f"<b>{text}</b>", s)


def _fchk(val, label, compare=None):
    """[ ] / [✓] checkbox paragraph."""
    _, VAL, _, _, _ = _fstyles()
    if compare is not None:
        checked = str(val or "").strip().lower() == compare.lower()
    else:
        checked = bool(val) and str(val).strip().lower() not in ("", "no", "false", "0")
    box = "[&#10003;]" if checked else "[ ]"
    return Paragraph(f"{box}  {label}", VAL)


def _fsig(label, img_data):
    """Compact inline signature cell (label left, image right)."""
    LBL, _, _, _, _ = _fstyles()
    img = _sig_to_image(img_data, w_mm=36, h_mm=13)
    lbl = Paragraph(f"<b>{label}:</b>", LBL)
    if img:
        inner = Table([[lbl, img]], colWidths=[40 * mm, 34 * mm], rowHeights=[10])
        inner.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return inner
    return lbl


def _ftable(rows, cws, spans=(), secs=(), sigs=(), extra=()):
    """
    Build a consistently styled single form table.
    spans  – row indices to span full width
    secs   – row indices that are section headers (shaded, bold border below)
    sigs   – row indices that need extra padding (signature rows)
    extra  – additional TableStyle commands
    """
    t = Table(rows, colWidths=cws)
    ncols = len(cws)
    style = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.3, C_LIGHT),
    ]
    for ri in spans:
        style.append(("SPAN", (0, ri), (-1, ri)))
    for ri in secs:
        style.append(("BACKGROUND", (0, ri), (-1, ri), _C_SEC_BG))
        style.append(("LINEBELOW",  (0, ri), (-1, ri), 0.5, C_BLACK))
        style.append(("ALIGN",      (0, ri), (-1, ri), "CENTER"))
    for ri in sigs:
        style.append(("TOPPADDING",    (0, ri), (-1, ri), 8))
        style.append(("BOTTOMPADDING", (0, ri), (-1, ri), 8))
    style.extend(extra)
    t.setStyle(TableStyle(style))
    return t


# ─────────────────────────────────────────────────────────────────────────────
#  COMMENCEMENT FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_commencement(story, fd, styles):
    """Commencement Form — mirrors HR Documents - Main reference."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, ITL = _fstyles()

    inst = Paragraph(
        "To complete the administrative aspect of your Employment please complete this form within "
        "5 days of joining and fax it back to AH or email it to joana@ajmanholding.ae",
        ITL,
    )

    rows = [
        [inst, ""],                                                          # r0 instruction
        [_fsec("Personal Details:"), ""],                                    # r1
        [_flv("Name",         _fd(fd, "employee_name")), ""],                # r2
        [_flv("Position",     _fd(fd, "position")),
         _flv("Contacts",     _fd(fd, "contacts"))],                         # r3
        [_flv("Department",   _fd(fd, "department")),
         _flv("Organization", _fd(fd, "organization", "INJAAZ LLC"))],       # r4
        [_flv("Date of Joining", _fmt(fd.get("date_of_joining"))), ""],      # r5
        [_fsec("Bank Account Details:"), ""],                                # r6
        [_flv("Bank Name", _fd(fd, "bank_name")), ""],                       # r7
        [_flv("Branch",    _fd(fd, "bank_branch")),
         _flv("Account Number", _fd(fd, "account_number"))],                 # r8
        [_fsig("Employee's Signature", fd.get("employee_signature")),
         _flv("Date", _fmt(fd.get("employee_sign_date")))],                  # r9 sig
        [_fsec("Reporting To:"), ""],                                        # r10
        [_flv("Name", _fd(fd, "reporting_to_name")), ""],                    # r11
        [_flv("Designation / Title", _fd(fd, "reporting_to_designation")),
         _flv("Contact No",          _fd(fd, "reporting_to_contact"))],      # r12
        [_fsig("Signature", fd.get("reporting_to_signature")),
         _flv("Date", _fmt(fd.get("reporting_sign_date")))],                 # r13 sig
    ]

    t = _ftable(rows, [L, R],
                spans=(0, 1, 2, 5, 6, 7, 10, 11),
                secs=(1, 6, 10),
                sigs=(9, 13))

    story.append(_header_table("Commencement Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)
    story.append(Spacer(1, 6))

    note = Paragraph(
        "If you need assistance with Salary letter required to open new bank account, please "
        "forward an email to HR Department at joana@ajmanholding.ae",
        ParagraphStyle("cNote", fontSize=8, fontName="Helvetica-Oblique",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11),
    )
    nt = Table([[note]], colWidths=[CW])
    nt.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(nt)


# ─────────────────────────────────────────────────────────────────────────────
#  DUTY RESUMPTION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_duty_resumption(story, fd, styles):
    """Resumption of Duty Form — mirrors Word document."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, _ = _fstyles()

    rows = [
        [_fsec("Requester:"), ""],                                           # r0
        [_flv("Employee Name", _fd(fd, "employee_name")),
         _flv("Employee ID",   _fd(fd, "employee_id"))],                     # r1
        [_flv("Job Title",     _fd(fd, "job_title")),
         _flv("Company",       _fd(fd, "company", "INJAAZ LLC"))],           # r2
        [_fsec("Leave Information:"), ""],                                   # r3
        [_flv("Leave Started",  _fmt(fd.get("leave_started"))),
         _flv("Leave Ended",    _fmt(fd.get("leave_ended")))],               # r4
        [_flv("Planned Resumption Date",
              _fmt(fd.get("planned_resumption_date"))), ""],                 # r5
        [_flv("Actual Resumption Date",
              _fmt(fd.get("actual_resumption_date"))), ""],                  # r6
        [_flv("Note",          _fd(fd, "note")), ""],                        # r7
        [_fsig("Employee Signature", fd.get("employee_signature")),
         _flv("Date", _fmt(fd.get("sign_date")))],                           # r8 sig
        [_fsec("Line Manager Remarks:"), ""],                                # r9
        [Paragraph(_fd(fd, "line_manager_remarks"), VAL), ""],               # r10
        [_fsig("Approved by Line Manager", fd.get("gm_signature")),
         _flv("Date", "")],                                                  # r11 sig
        [_fsig("HR Signature", fd.get("hr_signature")),
         _flv("Date", "")],                                                  # r12 sig
    ]

    t = _ftable(rows, [L, R],
                spans=(0, 3, 5, 6, 7, 9, 10),
                secs=(0, 3, 9),
                sigs=(8, 11, 12))

    story.append(_header_table("Resumption of Duty Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────────────
#  PASSPORT RELEASE / SUBMISSION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_passport_release(story, fd, styles):
    """Passport Release/Submission Form — two sections matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, ITL = _fstyles()

    ft = _fd(fd, "passport_form_type", "Release").replace("_", " ").title()
    purpose = _fd(fd, "purpose_of_release")

    # ── Section 1: Release ──────────────────────────────────────────────
    rows1 = [
        [_fsec(f"Passport {ft} Form"), ""],                                  # r0 title
        [_flv("Employee Name", _fd(fd, "employee_name")),
         _flv("Employee ID",   _fd(fd, "employee_id"))],                     # r1
        [_flv("Job Title",     _fd(fd, "job_title")),
         _flv("Project",       _fd(fd, "project"))],                         # r2
        [_flv("Date", _fmt(fd.get("form_date"))), ""],                       # r3
        [_fsec("Purpose of Release:"), ""],                                  # r4
        [Paragraph(purpose, VAL), ""],                                       # r5
        [_flv("Release Date", _fmt(fd.get("release_date"))), ""],            # r6
        [_fsig("Employee Signature", fd.get("employee_signature")), ""],     # r7 sig
        [_fsec("Note"), ""],                                                 # r8
        [Paragraph(
            "If an employee submits their passport to management for safekeeping, "
            "they should provide a dated signature of consent during duty resumption "
            "in the submission part of the same form of requisition.<br/>"
            "Management will not accept any passport for safekeeping without a signed "
            "consent from the employee.<br/>"
            "All passports will be released two days before the requested date, and "
            "immediately in emergency cases.",
            ITL), ""],                                                       # r9
        [_fsig("Approved by Line Manager", fd.get("gm_signature")),
         _flv("Date", "")],                                                  # r10 sig
        [_fsig("HR Signature", fd.get("hr_signature")),
         _flv("Date", "")],                                                  # r11 sig
    ]

    t1 = _ftable(rows1, [L, R],
                 spans=(0, 3, 4, 5, 6, 7, 8, 9),
                 secs=(0, 4, 8),
                 sigs=(7, 10, 11))

    story.append(_header_table("Passport Release / Submission Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t1)

    # ── Section 2: Safekeeping Requisition ──────────────────────────────
    story.append(Spacer(1, 8))
    rows2 = [
        [_fsec("Requisition for Safekeeping"), ""],                          # r0
        [_flv("Employee Name", _fd(fd, "employee_name")),
         _flv("Employee ID",   _fd(fd, "employee_id"))],                     # r1
        [_flv("Job Title",     _fd(fd, "job_title")),
         _flv("Date",          _fmt(fd.get("form_date")))],                  # r2
        [_fsig("Approved by Line Manager", fd.get("gm_signature")),
         _flv("Date", "")],                                                  # r3 sig
        [_fsig("HR Signature", fd.get("hr_signature")),
         _flv("Date", "")],                                                  # r4 sig
    ]

    t2 = _ftable(rows2, [L, R],
                 spans=(0,),
                 secs=(0,),
                 sigs=(3, 4))
    story.append(t2)

    # DOC NO footer row
    story.append(Spacer(1, 6))
    doc_row = Table(
        [[Paragraph("<b>DOC NO:</b> HR-FRM-003", ParagraphStyle("dr", fontSize=7.5, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=10)),
          Paragraph("<b>DATE:</b> 09/05/2025",   ParagraphStyle("dr2", fontSize=7.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=10)),
          Paragraph("<b>ISSUE:</b> 01",           ParagraphStyle("dr3", fontSize=7.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=10)),
          Paragraph("<b>REVISION:</b> 02",        ParagraphStyle("dr4", fontSize=7.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_RIGHT, leading=10))]],
        colWidths=[CW * 0.30, CW * 0.25, CW * 0.20, CW * 0.25],
    )
    doc_row.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(doc_row)


# ─────────────────────────────────────────────────────────────────────────────
#  VISA RENEWAL FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_visa_renewal(story, fd, styles):
    """Visa Renewal Form — letter-format matching Word document."""
    CW = CONTENT_W
    _, VAL, _, _, ITL = _fstyles()

    name       = _fd(fd, "employee_name")
    emp_id     = _fd(fd, "employee_id")
    employer   = _fd(fd, "employer", "INJAAZ LLC")
    position   = _fd(fd, "position")
    years      = _fd(fd, "years_completed")
    form_date  = _fmt(fd.get("form_date"))
    decision   = (fd.get("decision") or "").strip().lower()

    rows = [
        [_flv("Date", form_date)],                                          # r0
        [Paragraph("", VAL)],                                               # r1 blank
        [Paragraph("<b>To: HR Department,</b>", VAL)],                      # r2
        [Paragraph("", VAL)],                                               # r3 blank
        [Paragraph(
            f"I, <b>{name}</b> with ID number <b>{emp_id}</b> employed by "
            f"<b>{employer}</b>", VAL)],                                     # r4
        [Paragraph("", VAL)],                                               # r5 blank
        [Paragraph(
            f"in the position <b>{position}</b> have completed "
            f"<b>{years}</b> years.", VAL)],                                 # r6
        [Paragraph("I would like to confirm my decision to,", VAL)],        # r7
        [Paragraph("", VAL)],                                               # r8 blank
        [_fchk(decision == "continue", "1.  Continue by employment with the company for the next 2 years and willing to have my visa renewed.")],  # r9
        [Paragraph("", VAL)],                                               # r10 blank
        [_fchk(decision == "discontinue" or decision == "cancel",
               "2.  Discontinue my service and require visa cancellation.")], # r11
        [Paragraph("", VAL)],                                               # r12 blank
        [Paragraph(
            "<i>Note: In case I do not continue my service, I will be liable "
            "to cover any additional charges covered by the company.</i>",
            ITL)],                                                           # r13
        [Paragraph("", VAL)],                                               # r14 blank
        [_fsig("Signature of Employee", fd.get("employee_signature"))],     # r15 sig
        [Paragraph("", VAL)],                                               # r16 blank
        [Paragraph("<b>INJAAZ LLC</b>", VAL)],                              # r17
    ]

    t = Table(rows, colWidths=[CW])
    t.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("TOPPADDING",    (0, 15), (-1, 15), 8),
        ("BOTTOMPADDING", (0, 15), (-1, 15), 8),
    ]))

    story.append(_header_table("Visa Renewal Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────────────
#  STATION CLEARANCE FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_station_clearance(story, fd, styles):
    """Station Clearance Form — 4-column checklist matching Word doc."""
    CW = CONTENT_W
    C0, C1, C2, C3 = CW*0.24, CW*0.47, CW*0.15, CW*0.14
    _, VAL, _, SML, _ = _fstyles()

    dep_map = {"transfer": "Transfer", "resignation": "Resignation",
               "termination": "Termination", "end_of_contract": "End of Contract"}
    tdep = dep_map.get(_fd(fd, "type_of_departure"), _fd(fd, "type_of_departure"))

    def row(section, item, chk_val, date_val=""):
        tick = "[&#10003;]" if chk_val else "[ ]"
        return [
            Paragraph(f"<b>{section}</b>", SML) if section else "",
            Paragraph(f"{tick}  {item}", VAL),
            Paragraph(_fmt(date_val) if date_val else "", SML),
            Paragraph("", SML),
        ]

    info_rows = [
        [_flv("Employee Name",  _fd(fd, "employee_name")),
         _flv("Employee ID",    _fd(fd, "employee_id")), "", ""],             # r0
        [_flv("Employment Date",_fmt(fd.get("employment_date"))),
         _flv("Position",       _fd(fd, "position")), "", ""],                # r1
        [_flv("Department",     _fd(fd, "department")),
         _flv("Section",        _fd(fd, "section")), "", ""],                 # r2
        [_flv("Type of Departure", tdep),
         _flv("Last Working Date", _fmt(fd.get("last_working_date"))), "", ""],# r3
    ]

    hdr = [
        [_fsec("EMPLOYEE'S DEPARTMENT / SECTION"),
         _fsec("EMPLOYEE'S DEPARTMENT / SECTION"),
         _fsec("DATE"), _fsec("SIGNATURE")],                                  # r4
    ]

    dept_rows = [
        row("", "Has completed / handed over all tasks on hand",
            fd.get("tasks_handed_over")),
        row("", "Has handed over all original working documents",
            fd.get("documents_handed_over")),
        row("", "Has handed over all normal & Electronic files",
            fd.get("files_handed_over")),
        row("", "Keys Returned",      fd.get("keys_returned")),
        row("", "Toolbox Returned",   fd.get("toolbox_returned")),
        row("", "Access card",        fd.get("access_card_returned")),
        row("", f"Others: {_fd(fd, 'dept_others', '')}",
            False),
    ]

    it_hdr  = [[_fsec("INFORMATION TECHNOLOGY DEPARTMENT"), _fsec("INFORMATION TECHNOLOGY DEPARTMENT"), _fsec("DATE"), _fsec("SIGNATURE")]]
    it_rows = [
        row("", "E-mail Account Cancelled",          fd.get("email_cancelled")),
        row("", "Has returned all software / hardware materials",
            fd.get("software_hardware_returned")),
        row("", "Laptop Returned",                   fd.get("laptop_returned")),
        row("", f"Others: {_fd(fd, 'it_others', '')}",  False),
    ]

    hr_hdr  = [[_fsec("HUMAN RESOURCES & ADMINISTRATION"), _fsec("HUMAN RESOURCES & ADMINISTRATION"), _fsec("DATE"), _fsec("SIGNATURE")]]
    hr_rows = [
        row("", "Employee file Shifted to Exit folder",      fd.get("file_shifted")),
        row("", "Payment of outstanding dues (Salary)",      fd.get("dues_paid")),
        row("", "Medical Card Returned",                     fd.get("medical_card_returned")),
        row("", f"Others: {_fd(fd, 'hr_others', '')}",       False),
    ]

    fin_hdr  = [[_fsec("FINANCE DEPARTMENT"), _fsec("FINANCE DEPARTMENT"), _fsec("DATE"), _fsec("SIGNATURE")]]
    fin_rows = [
        row("", "EOS Benefits Transfer",                     fd.get("eos_transfer")),
        row("", f"Others: {_fd(fd, 'finance_others', '')}",  False),
    ]

    remarks_row = [[
        Paragraph(f"<b>Remarks:</b>  {_fd(fd, 'remarks')}", VAL),
        "", "", "",
    ]]

    sig_row = [[
        _fsig("Employee Signature", fd.get("employee_signature")),
        "",
        _fsig("Human Resources Manager", fd.get("hr_signature")),
        "",
    ]]

    all_rows = info_rows + hdr + dept_rows + it_hdr + it_rows + hr_hdr + hr_rows + fin_hdr + fin_rows + remarks_row + sig_row

    t = Table(all_rows, colWidths=[C0, C1, C2, C3])

    n_info = len(info_rows)      # 4
    n_hdr  = 1                   # 1  (r4)
    n_dept = len(dept_rows)      # 7  (r5-r11)
    n_ithdr= 1                   # 1  (r12)
    n_it   = len(it_rows)        # 4  (r13-r16)
    n_hrhdr= 1                   # 1  (r17)
    n_hr   = len(hr_rows)        # 4  (r18-r21)
    n_fhdr = 1                   # 1  (r22)
    n_fin  = len(fin_rows)       # 2  (r23-r24)
    # remarks r25, sig r26

    r_ithdr  = n_info + n_hdr + n_dept
    r_hrhdr  = r_ithdr + n_ithdr + n_it
    r_fhdr   = r_hrhdr + n_hrhdr + n_hr
    r_remarks= r_fhdr  + n_fhdr  + n_fin
    r_sig    = r_remarks + 1

    sec_rows = [n_info, r_ithdr, r_hrhdr, r_fhdr]

    style = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (-2, -1), 0.3, C_LIGHT),
        # info rows: first 2 cols merged (col0+col1 for name/id pair)
        ("SPAN",  (0, 0), (1, 0)),
        ("SPAN",  (0, 1), (1, 1)),
        ("SPAN",  (0, 2), (1, 2)),
        ("SPAN",  (0, 3), (1, 3)),
        # section header rows: span col0+col1, keep date+sig separate
        ("SPAN",  (0, n_info),   (1, n_info)),
        ("SPAN",  (0, r_ithdr),  (1, r_ithdr)),
        ("SPAN",  (0, r_hrhdr),  (1, r_hrhdr)),
        ("SPAN",  (0, r_fhdr),   (1, r_fhdr)),
        # remarks spans all 4
        ("SPAN",  (0, r_remarks), (-1, r_remarks)),
        # sig row: employee spans col0+col1, HR spans col2+col3
        ("SPAN",  (0, r_sig), (1, r_sig)),
        ("SPAN",  (2, r_sig), (3, r_sig)),
        # sig row padding
        ("TOPPADDING",    (0, r_sig), (-1, r_sig), 8),
        ("BOTTOMPADDING", (0, r_sig), (-1, r_sig), 8),
    ]
    for ri in sec_rows:
        style.extend([
            ("BACKGROUND", (0, ri), (-1, ri), _C_SEC_BG),
            ("LINEBELOW",  (0, ri), (-1, ri), 0.5, C_BLACK),
            ("ALIGN",      (0, ri), (-1, ri), "CENTER"),
        ])

    t.setStyle(TableStyle(style))

    story.append(_header_table("Station Clearance Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))

    intro = Paragraph(
        "The following departments must ensure that all exit formalities have been "
        "conducted for transferring employees.",
        ParagraphStyle("scI", fontSize=8.5, fontName="Helvetica-Oblique",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11),
    )
    story.append(intro)
    story.append(Spacer(1, 4))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────────────
#  GRIEVANCE / DISCIPLINARY ACTION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_grievance(story, fd, styles):
    """Employee Grievance/Disciplinary Action Form — mirrors Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, _, ITL = _fstyles()

    desc  = _fd(fd, "complaint_description") or _fd(fd, "complaint")
    wits  = _fd(fd, "witnesses")
    who   = _fd(fd, "who_informed")
    att   = _fd(fd, "attachment")
    loc   = _fd(fd, "issue_location", "").replace("_", " ").title()
    s2v   = _fd(fd, "statement_2nd_party")
    hrv   = _fd(fd, "hr_statement_verified")
    hrf   = _fd(fd, "hr_first_recurring")
    hra   = _fd(fd, "hr_remarks")
    gma   = _fd(fd, "gm_remarks")

    rows = [
        # ── Purpose ────────────────────────────────────────────────────
        [Paragraph(
            "The purpose of the Grievance/Disciplinary form is to establish a method whereby "
            "grievances and disciplinary issues of employees will be resolved fairly and effectively. "
            "The filing of a grievance and disciplinary issues will in no way prejudice the status of "
            "the employee. This form remains confidential with Line Manager / Human Resource department.",
            ITL), ""],                                                        # r0
        # ── Part A: 1st Party ──────────────────────────────────────────
        [_fsec("1st Party:  Complainant Information — Part A"), ""],          # r1
        [_flv("Employee Name",    _fd(fd, "complainant_name")),
         _flv("Employee ID #",    _fd(fd, "complainant_id"))],                # r2
        [_flv("Designation",      _fd(fd, "complainant_designation")),
         _flv("Date of Incident", _fmt(fd.get("date_of_incident")))],         # r3
        [_flv("Shift / Time",     _fd(fd, "shift_time")),
         _flv("Employee Contact #", _fd(fd, "complainant_contact"))],         # r4
        [_flv("Issue happened at", loc), ""],                                 # r5
        # ── Part B: 2nd Party ──────────────────────────────────────────
        [_fsec("2nd Party — Part B"), ""],                                    # r6
        [Paragraph(
            "<i>Note: use new form if complaint is for more than 1 employee.</i>",
            ITL), ""],                                                        # r7
        [_flv("Employee Name",    _fd(fd, "second_party_name")),
         _flv("Staff ID",         _fd(fd, "second_party_id"))],               # r8
        [_flv("Department",       _fd(fd, "second_party_department")),
         _flv("Place of Incident",_fd(fd, "place_of_incident"))],             # r9
        [_flv("Shift / Time",     _fd(fd, "second_party_shift")),
         _flv("Employee Contact #",_fd(fd, "second_party_contact"))],         # r10
        # ── Part C: Complaint ──────────────────────────────────────────
        [_fsec("What is the complaint/issue? — Part C"), ""],                 # r11
        [Paragraph(desc, VAL), ""],                                           # r12
        # ── Witnesses / Attachment ─────────────────────────────────────
        [_flv("Witnesses", wits),
         _flv("Attachment", att)],                                            # r13
        [_flv("Who was informed", who), ""],                                  # r14
        # ── Acknowledgement (1st party) ────────────────────────────────
        [_fsec("Acknowledgement and Signature"), ""],                         # r15
        [Paragraph(
            "I have written and signed this grievance/disciplinary action form.",
            VAL), ""],                                                        # r16
        [_fsig("Signature of Complainant (1st Party)",
               fd.get("complainant_signature")), ""],                         # r17 sig
        # ── For HOD / Engineer use ─────────────────────────────────────
        [_fsec("For Engineer, QHSE & Head of Department (HOD) Use"), ""],     # r18
        [_flv("Statement of 2nd party taken & attached?", s2v), ""],          # r19
        [Paragraph(
            _fd(fd, "hod_actions") or
            "Actions / recommendations taken to resolve the issue:", VAL), ""],# r20
        # ── 2nd party consent ──────────────────────────────────────────
        [_fsec("Employee Acknowledgement / Consent (2nd Party)"), ""],        # r21
        [Paragraph(
            "I have read & agreed and signed on this form as per the actions taken "
            "or recommended by my engineer, QHSE or HOD.", VAL), ""],         # r22
        [_fsig("Employee Signature (2nd Party)",
               fd.get("second_party_signature")), ""],                        # r23 sig
        # ── For HR use ─────────────────────────────────────────────────
        [_fsec("For HR Use Only"), ""],                                       # r24
        [_flv("Statement verified",  hrv),
         _flv("1st / Recurring",     hrf)],                                   # r25
        [Paragraph(f"<b>HR Remarks:</b>  {hra}", VAL), ""],                  # r26
        [_fsig("HR Signature", fd.get("hr_signature")), ""],                  # r27 sig
        # ── For GM use ─────────────────────────────────────────────────
        [_fsec("For General Manager Use Only"), ""],                          # r28
        [Paragraph(f"<b>GM Remarks:</b>  {gma}", VAL), ""],                  # r29
        [_fsig("GM Signature", fd.get("gm_signature")), ""],                  # r30 sig
    ]

    t = _ftable(rows, [L, R],
                spans=(0, 1, 5, 6, 7, 11, 12, 14, 15, 16, 17,
                       18, 19, 20, 21, 22, 23, 24, 26, 27, 28, 29, 30),
                secs=(1, 6, 11, 15, 18, 21, 24, 28),
                sigs=(17, 23, 27, 30),
                extra=[("MINROWHEIGHT", (0, 12), (-1, 12), 40),
                       ("MINROWHEIGHT", (0, 20), (-1, 20), 40),
                       ("MINROWHEIGHT", (0, 26), (-1, 26), 30),
                       ("MINROWHEIGHT", (0, 29), (-1, 29), 30)])

    story.append(_header_table("Employee Grievance / Disciplinary Action Form",
                               styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t)


# ─────────────────────────────────────────────────────────────────────────────
#  INTERVIEW ASSESSMENT FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_interview_assessment(story, fd, styles):
    """Interview Assessment Form — rating table matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, ITL = _fstyles()

    RATING_MAP = {"outstanding": "Outstanding", "v_good": "V. Good",
                  "good": "Good", "fair": "Fair", "low": "Low"}

    def tick(val, target):
        return "[&#10003;]" if RATING_MAP.get(str(val or "").strip().lower()) == target else "[ ]"

    def gender_cell():
        g = str(fd.get("gender") or "").strip().upper()
        f_box = "[&#10003;] F" if g == "F" else "[ ] F"
        m_box = "[&#10003;] M" if g == "M" else "[ ] M"
        _, VAL, _, _, _ = _fstyles()
        return Paragraph(f"<b>Gender:</b>  {f_box}    {m_box}", VAL)

    # ── Candidate info ───────────────────────────────────────────────
    info_rows = [
        [_flv("Candidate Name",       _fd(fd, "candidate_name")),
         _flv("Position Title",        _fd(fd, "position_title"))],
        [_flv("Academic Qualification",_fd(fd, "academic_qualification")),
         _flv("Age",                   _fd(fd, "age"))],
        [_flv("Marital Status",        _fd(fd, "marital_status")),
         _flv("No. of Dependents",     _fd(fd, "dependents"))],
        [_flv("Nationality",           _fd(fd, "nationality")),
         gender_cell()],
        [_flv("Current Job Title",     _fd(fd, "current_job_title")),
         _flv("Years of Experience",   _fd(fd, "years_experience"))],
        [_flv("Current Salary",        _fd(fd, "current_salary")),
         _flv("Expected Salary",       _fd(fd, "expected_salary"))],
        [_flv("Interview Date",        _fmt(fd.get("interview_date"))),
         _flv("Interview By",          _fd(fd, "interview_by"))],
    ]

    t_info = _ftable(info_rows, [L, R])
    story.append(_header_table("Interview Assessment Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Note ────────────────────────────────────────────────────────
    note = Paragraph(
        "<i>Note: The Interviewer shall indicate the rating by ticking the appropriate column.</i>",
        ITL)
    story.append(note)
    story.append(Spacer(1, 4))

    # ── Rating table ─────────────────────────────────────────────────
    FACTORS = [
        ("Turn-out & Appearance",
         "The Turn-out and appearance are appropriate to the position",
         "rating_turnout"),
        ("Confidence",
         "Demonstrates professional competence and self-confidence",
         "rating_confidence"),
        ("Mental Alertness",
         "Comprehends and coherently responds to questions",
         "rating_mental_alertness"),
        ("Maturity & Emotional Stability",
         "Demonstrates composure and balanced behaviour when under pressure "
         "or responding to difficult/critical queries.",
         "rating_maturity"),
        ("Communication Skills",
         "Good listener, Expresses own thoughts and opinions clearly and to "
         "the point? Fluent in conversational English.",
         "rating_communication"),
        ("Technical Knowledge",
         "Candidate awareness of his own duties and responsibilities as per "
         "experience gained",
         "rating_technical"),
        ("Relevant Training",
         "Has professional/technical training relevant to the job requirements",
         "rating_training"),
        ("Relevant Experience",
         "Previous work experience meets with job requirement",
         "rating_experience"),
        ("Overall Rating",
         "The candidate's overall suitability for the position",
         "rating_overall"),
    ]

    CW_F = CW * 0.22
    CW_I = CW * 0.38
    CW_R = CW * 0.08

    hdr = [[
        Paragraph("<b>FACTOR</b>", ParagraphStyle("rh", fontSize=8.5, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=11)),
        Paragraph("<b>DEMONSTRABLE INDICATORS</b>", ParagraphStyle("rh2", fontSize=8.5, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=11)),
        Paragraph("<b>Outstanding</b>", SML),
        Paragraph("<b>V. Good</b>", SML),
        Paragraph("<b>Good</b>", SML),
        Paragraph("<b>Fair</b>", SML),
        Paragraph("<b>Low</b>", SML),
    ]]

    rating_rows = []
    for factor, indicator, key in FACTORS:
        val = fd.get(key)
        rating_rows.append([
            Paragraph(factor, VAL),
            Paragraph(indicator, ParagraphStyle("rI", fontSize=8.5, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
            Paragraph(tick(val, "Outstanding"), SML),
            Paragraph(tick(val, "V. Good"),     SML),
            Paragraph(tick(val, "Good"),         SML),
            Paragraph(tick(val, "Fair"),         SML),
            Paragraph(tick(val, "Low"),          SML),
        ])

    all_rating = hdr + rating_rows
    t_rate = Table(all_rating, colWidths=[CW_F, CW_I, CW_R, CW_R, CW_R, CW_R, CW_R])
    t_rate.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (2, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
    ]))
    story.append(t_rate)
    story.append(Spacer(1, 6))

    # ── Comments / Eligibility ───────────────────────────────────────
    comment_rows = [
        [_fsec("Overall Assessment / Comments"), ""],
        [Paragraph(
            f"<b>Professional</b> (e.g. academic qualification, technical training and experience):<br/>"
            f"{_fd(fd, 'assessment_professional') or _fd(fd, 'overall_assessment')}", VAL), ""],
        [Paragraph(
            f"<b>Personality</b> (e.g. behaviour, attitude and presentation):<br/>"
            f"{_fd(fd, 'assessment_personality')}", VAL), ""],
        [_flv("Eligibility for Employment",
              _fd(fd, "eligibility")),
         _flv("Job Recommended for",
              _fd(fd, "job_recommended_for"))],
        [_flv("Interviewer's Name",
              _fd(fd, "interviewer_name", _fd(fd, "interview_by"))),
         _flv("Title", _fd(fd, "interviewer_title"))],
        [_fsig("Interviewer Signature",
               fd.get("interviewer_signature")),
         ""],
    ]
    t_cmt = _ftable(comment_rows, [L, R],
                    spans=(0, 1, 2, 5),
                    secs=(0,),
                    sigs=(5,),
                    extra=[("MINROWHEIGHT", (0, 1), (-1, 1), 40),
                           ("MINROWHEIGHT", (0, 2), (-1, 2), 40)])
    story.append(t_cmt)


# ─────────────────────────────────────────────────────────────────────────────
#  STAFF APPRAISAL FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_staff_appraisal(story, fd, styles):
    """Staff Appraisal Form — weighted rating table matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, _ = _fstyles()

    # ── Employee info ────────────────────────────────────────────────
    info_rows = [
        [_flv("Name",            _fd(fd, "employee_name")),
         _flv("Employee ID",     _fd(fd, "employee_id"))],
        [_flv("Department",      _fd(fd, "department")),
         _flv("Position",        _fd(fd, "position"))],
        [_flv("Appraisal Period",_fd(fd, "appraisal_period")),
         _flv("Reviewer",        _fd(fd, "reviewer"))],
    ]
    t_info = _ftable(info_rows, [L, R])
    story.append(_header_table("Staff Appraisal Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Performance criteria table ───────────────────────────────────
    CRITERIA = [
        ("Punctuality",             "15%", "rating_punctuality",
         "Regularity in attendance and adherence to schedules."),
        ("Job Knowledge and Expertise","15%","rating_job_knowledge",
         "Understanding of job responsibilities, skills, and processes."),
        ("Quality of Work",         "15%", "rating_quality",
         "Accuracy, attention to detail, and meeting quality standards."),
        ("Productivity",            "15%", "rating_productivity",
         "Efficiency, meeting deadlines, and handling workload."),
        ("Communication Skills",    "10%", "rating_communication",
         "Effectiveness in written and verbal communication."),
        ("Teamwork and Collaboration","10%","rating_teamwork",
         "Willingness to work with others and contribute to a team environment."),
        ("Problem-Solving & Initiative","10%","rating_problem_solving",
         "Root Cause Analytic, Ability to handle challenges and suggest improvements."),
        ("Adaptability",            "5%",  "rating_adaptability",
         "Flexibility in dealing with changes and new responsibilities."),
        ("Leadership (if applicable)","5%","rating_leadership",
         "Ability to lead, motivate, and manage a team effectively."),
    ]

    CW_C = CW * 0.30
    CW_W = CW * 0.12
    CW_R = CW * 0.10
    CW_M = CW * 0.48

    hdr = [[
        Paragraph("<b>Performance Criterion</b>", ParagraphStyle("sah", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Weightage (%)</b>",         ParagraphStyle("sah2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Rating (1–5)</b>",           ParagraphStyle("sah3", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Comments</b>",               ParagraphStyle("sah4", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]
    criteria_rows = []
    for criterion, wt, key, comment_desc in CRITERIA:
        criteria_rows.append([
            Paragraph(criterion, VAL),
            Paragraph(wt, ParagraphStyle("saw", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph(_fd(fd, key), ParagraphStyle("sar", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph(fd.get(key.replace("rating_", "comments_")) or comment_desc,
                      ParagraphStyle("sacd", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
        ])

    total_score = _fd(fd, "total_score")
    total_row = [[
        Paragraph("<b>Total Score:</b>", VAL),
        Paragraph("100%", ParagraphStyle("sat", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph(f"<b>{total_score}</b> / 5", ParagraphStyle("tat2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Rating:</b>  1 Unsatisfactory   2 Conditional   3 Satisfactory   4 Excellent   5 Outstanding",
                  ParagraphStyle("saleg", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
    ]]

    all_rows = hdr + criteria_rows + total_row
    t_crit = Table(all_rows, colWidths=[CW_C, CW_W, CW_R, CW_M])
    t_crit.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
        ("BACKGROUND",    (0, -1),(-1, -1), _C_SEC_BG),
        ("LINEABOVE",     (0, -1),(-1, -1), 0.5, C_BLACK),
    ]))
    story.append(t_crit)
    story.append(Spacer(1, 6))

    # ── Narrative + signatures ───────────────────────────────────────
    narrative_fields = [
        ("Employee Strengths and Achievements",
         _fd(fd, "employee_strengths")),
        ("Areas for Improvement",
         _fd(fd, "areas_for_improvement")),
        ("Development Goals",
         _fd(fd, "development_goals")),
        ("Employee's Feedback (Optional)",
         _fd(fd, "employee_feedback")),
        ("Appraiser's Comments",
         _fd(fd, "appraiser_comments")),
    ]
    narrative_rows = []
    for label, val in narrative_fields:
        narrative_rows.append([_fsec(label, left=True), ""])
        narrative_rows.append([Paragraph(val, VAL), ""])

    sig_rows_idx = []
    sig_r_start = len(narrative_rows)
    narrative_rows.append([
        _fsig("Employee Signature", fd.get("employee_signature")),
        _fsig("Appraiser Signature", fd.get("hr_signature")),
    ])
    sig_rows_idx.append(sig_r_start)

    span_idx = [i for i in range(0, len(narrative_rows) - 1, 2)]
    content_idx = [i for i in range(1, len(narrative_rows) - 1, 2)]
    sec_idx = span_idx

    t_narr = _ftable(narrative_rows, [L, R],
                     spans=span_idx + content_idx,
                     secs=sec_idx,
                     sigs=sig_rows_idx,
                     extra=[("MINROWHEIGHT", (0, i), (-1, i), 35)
                             for i in content_idx])
    story.append(t_narr)


# ─────────────────────────────────────────────────────────────────────────────
#  PERFORMANCE EVALUATION FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_performance_evaluation(story, fd, styles):
    """Employee Performance Evaluation Form — 10-parameter table matching Word doc."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, ITL = _fstyles()

    # ── Employee info ────────────────────────────────────────────────
    info_rows = [
        [_flv("Employee Name",    _fd(fd, "employee_name")),
         _flv("Date of Evaluation",_fmt(fd.get("date_of_evaluation")))],
        [_flv("Employee ID No",   _fd(fd, "employee_id")),
         _flv("Date of Joining",  _fmt(fd.get("date_of_joining")))],
        [_flv("Department / Section", _fd(fd, "department")),
         _flv("Designation",      _fd(fd, "designation"))],
        [_flv("Evaluation Done By",   _fd(fd, "evaluation_done_by")), ""],
    ]
    t_info = _ftable(info_rows, [L, R], spans=(3,))

    story.append(_header_table("Employee Performance Evaluation Form", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Rating legend ────────────────────────────────────────────────
    story.append(Paragraph(
        "<b>To be filled by Supervisor / HOD / Manager:</b>&nbsp;&nbsp;&nbsp;"
        "<b>To be filled by the Performance Evaluator:</b>",
        ParagraphStyle("peNote", fontSize=8.5, fontName="Helvetica-Bold",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11)))
    story.append(Spacer(1, 3))

    leg_left  = ("Outstanding 10 &nbsp; Excellent 8 &nbsp; Satisfactory 7 &nbsp; "
                 "Conditional 5 &nbsp; Unsatisfactory 4 or less")
    leg_right = ("90 &amp; above = Outstanding &nbsp; 80-89 = Excellent &nbsp; "
                 "70-79 = Satisfactory &nbsp; 50-69 = Conditional &nbsp; "
                 "00-49 = Unsatisfactory")
    leg_t = Table([[
        Paragraph(f"<b>RATING:</b><br/>{leg_left}", ParagraphStyle("ll", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
        Paragraph(f"<b>PERFORMANCE RATING:</b><br/>{leg_right}", ParagraphStyle("lr", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
    ]], colWidths=[L, R])
    leg_t.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (0, -1),  0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND",    (0, 0), (-1, -1), _C_SEC_BG),
    ]))
    story.append(leg_t)
    story.append(Spacer(1, 5))

    # ── Evaluation table ─────────────────────────────────────────────
    PARAMS = [
        ("01", "Communication.",
         "Internal/external communications with staff, client, contractors, "
         "supplier, etc on timely manners", "score_01"),
        ("02", "Achievements.",
         "Departmental achievements for better approach and company image",
         "score_02"),
        ("03", "Creativity and innovation.",
         "Reactiveness & productivity", "score_03"),
        ("04", "Collaboration and teamwork.",        "", "score_04"),
        ("05", "Problem-solving & reliability.",     "", "score_05"),
        ("06", "Quality and accuracy of work.",      "", "score_06"),
        ("07", "Attendance, punctuality.",            "", "score_07"),
        ("08", "Ability to accomplish goals and meet the deadlines.", "", "score_08"),
        ("09", "Intelligence:",
         "Analytic ability, mental alertness & general awareness", "score_09"),
        ("10", "Policy & HSE compliance:",
         "Awareness and complying with company policies and procedures as per "
         "HSE department", "score_10"),
    ]

    CW_SN = CW * 0.07
    CW_PM = CW * 0.71
    CW_SC = CW * 0.22

    eval_hdr = [[
        Paragraph("<b>SN</b>", ParagraphStyle("eh", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Evaluation Parameters</b>", ParagraphStyle("eh2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>SCORE</b>", ParagraphStyle("eh3", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]
    eval_rows = []
    for sn, title, desc, key in PARAMS:
        txt = f"<b>{title}</b>"
        if desc:
            txt += f"<br/><font size='8'>{desc}</font>"
        eval_rows.append([
            Paragraph(sn, ParagraphStyle("esn", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph(txt, VAL),
            Paragraph(_fd(fd, key), ParagraphStyle("esc", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        ])

    total_score = _fd(fd, "overall_score")
    overall_row = [[
        Paragraph("<b>OVERALL SCORE:</b>", ParagraphStyle("eos", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=12)),
        Paragraph("", VAL),
        Paragraph(f"<b>{total_score}</b>", ParagraphStyle("eos2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]

    t_eval = Table(eval_hdr + eval_rows + overall_row, colWidths=[CW_SN, CW_PM, CW_SC])
    extra_style_eval = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
        ("ALIGN",         (2, 0), (2, -1),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
        ("BACKGROUND",    (0, -1),(-1, -1), _C_SEC_BG),
        ("LINEABOVE",     (0, -1),(-1, -1), 0.5, C_BLACK),
        ("SPAN",          (0, -1),(1, -1)),
    ]
    t_eval.setStyle(TableStyle(extra_style_eval))
    story.append(t_eval)
    story.append(Spacer(1, 6))

    # ── Evaluation details + signatures ──────────────────────────────
    eval_name = _fd(fd, "evaluator_name")
    eval_desig = _fd(fd, "evaluator_designation")
    obs         = _fd(fd, "evaluator_observation")
    concern     = _fd(fd, "area_of_concern")
    training    = _fd(fd, "training_required")
    emp_cmt     = _fd(fd, "employee_comments")
    incharge    = _fd(fd, "concern_incharge_name")
    inch_cmt    = _fd(fd, "incharge_comments")
    gm_rem      = _fd(fd, "gm_remarks")
    hr_rem      = _fd(fd, "hr_remarks")

    detail_rows = [
        [_fsec("Evaluation Details"), ""],                                   # r0
        [_flv("Evaluator Name", eval_name),
         _flv("Designation",    eval_desig)],                                # r1
        [_flv("Evaluator Observation / Suggestion / Remarks", obs), ""],    # r2
        [_flv("Area of Concern / Weakness", concern), ""],                  # r3
        [_flv("Employee Training Required", training), ""],                  # r4
        [_flv("Employee Comments", emp_cmt), ""],                            # r5
        [_fsig("Employee Signature",  fd.get("employee_signature")),
         _fsig("Evaluator Signature", fd.get("evaluator_signature"))],       # r6 sigs
        [_fsec("For In-charge / Engineer / Manager"), ""],                   # r7
        [_flv("In-charge Name", incharge), ""],                              # r8
        [_flv("Comments & Recommendations", inch_cmt), ""],                  # r9
        [_fsec("For General Manager"), ""],                                  # r10
        [_flv("GM Remarks / Comments", gm_rem), ""],                         # r11
        [_fsec("For HR — Use Only"), ""],                                    # r12
        [_flv("HR Remarks / Comments", hr_rem), ""],                         # r13
        [_fsig("HR Signature", fd.get("hr_signature")),
         _fsig("GM Signature", fd.get("gm_signature"))],                     # r14 sigs
    ]

    t_det = _ftable(detail_rows, [L, R],
                    spans=(0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13),
                    secs=(0, 7, 10, 12),
                    sigs=(6, 14),
                    extra=[("MINROWHEIGHT", (0, 2), (-1, 2), 35),
                           ("MINROWHEIGHT", (0, 5), (-1, 5), 35),
                           ("MINROWHEIGHT", (0, 9), (-1, 9), 35),
                           ("MINROWHEIGHT", (0, 11),(-1, 11), 35),
                           ("MINROWHEIGHT", (0, 13),(-1, 13), 35)])
    story.append(t_det)


# ─────────────────────────────────────────────────────────────────────────────
#  CONTRACT RENEWAL ASSESSMENT FORM
# ─────────────────────────────────────────────────────────────────────────────
def _build_contract_renewal(story, fd, styles):
    """Employee Contract Renewal Assessment — mirrors Word doc exactly."""
    CW = CONTENT_W
    L, R = CW * 0.50, CW * 0.50
    _, VAL, _, SML, _ = _fstyles()

    # ── Employee info ────────────────────────────────────────────────
    info_rows = [
        [_flv("Employee Name",    _fd(fd, "employee_name")),
         _flv("Date of Evaluation",
              _fmt(fd.get("date_of_evaluation")) or _fmt(fd.get("today_date")))],
        [_flv("Employee ID",      _fd(fd, "employee_id")),
         _flv("Date of Joining",  _fmt(fd.get("date_of_joining")))],
        [_flv("Department / Section", _fd(fd, "department")),
         _flv("Contract End Date",    _fmt(fd.get("contract_end_date")))],
        [_flv("Evaluation By",    _fd(fd, "evaluation_by") or _fd(fd, "evaluator_name")),
         _flv("Designation",      _fd(fd, "designation"))],
    ]
    t_info = _ftable(info_rows, [L, R])

    story.append(_header_table("Employee Contract Renewal Assessment", styles, show_bottom_line=False))
    story.append(Spacer(1, 4))

    note_p = Paragraph(
        "<b>To be filled by supervisor:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "<b>To be filled by the Performance Evaluator:</b>",
        ParagraphStyle("crNote", fontSize=8.5, fontName="Helvetica-Bold",
                       textColor=C_BLACK, alignment=TA_LEFT, leading=11))
    story.append(note_p)
    story.append(Spacer(1, 3))
    story.append(t_info)
    story.append(Spacer(1, 6))

    # ── Score/decision legend ────────────────────────────────────────
    leg_l  = "Outstanding 5 &nbsp; Excellent 4 &nbsp; Satisfactory 3 &nbsp; Conditional 2 &nbsp; Unsatisfactory 1"
    leg_r  = "3 &amp; above → Renew Contract &nbsp; | &nbsp; 2–&gt;3 → Renew/Extend with Conditions &nbsp; | &nbsp; 2&lt; → Terminate"
    leg_t  = Table([[
        Paragraph(f"<b>SCORE AND PERFORMANCE RATING:</b><br/>{leg_l}",
                  ParagraphStyle("crll", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
        Paragraph(f"<b>DECISION BASED ON THE EVALUATION:</b><br/>{leg_r}",
                  ParagraphStyle("crlr", fontSize=8, fontName="Helvetica", textColor=C_BLACK, alignment=TA_LEFT, leading=11)),
    ]], colWidths=[L, R])
    leg_t.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("LINEAFTER",     (0, 0), (0, -1),  0.3, C_LIGHT),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND",    (0, 0), (-1, -1), _C_SEC_BG),
    ]))
    story.append(leg_t)
    story.append(Spacer(1, 5))

    # ── Main evaluation table ────────────────────────────────────────
    SECTIONS = [
        ("01", "Job Performance", [
            ("01A", "a", "Completes assigned tasks efficiently and accurately."),
            ("01B", "b", "Demonstrates a strong understanding of job responsibilities."),
            ("01C", "c", "Meets deadlines consistently."),
            ("01D", "d", "Produces work of high quality."),
            ("01E", "e", "Takes initiative to improve work processes."),
        ]),
        ("02", "Work Attitude and Behaviour", [
            ("02A", "a", "Shows a positive attitude towards work and colleagues."),
            ("02B", "b", "Accepts feedback constructively and strives for improvement."),
            ("02C", "c", "Maintains professionalism in all interactions."),
            ("02D", "d", "Demonstrates adaptability to changing situations or challenges."),
            ("02E", "e", "Upholds company policies and values."),
        ]),
        ("03", "Communication and Teamwork", [
            ("03A", "a", "Communicates clearly and effectively with team members."),
            ("03B", "b", "Works collaboratively and contributes to team goals."),
            ("03C", "c", "Resolves conflicts or issues amicably."),
            ("03D", "d", "Demonstrates good listening skills."),
            ("03E", "e", "Keeps supervisors and colleagues informed of work progress."),
        ]),
        ("04", "Attendance and Punctuality", [
            ("04A", "a", "Arrives on time and prepared for work."),
            ("04B", "b", "Maintains consistent attendance."),
            ("04C", "c", "Provides notice and valid reasons for absences."),
        ]),
    ]

    CW_SN = CW * 0.07
    CW_SB = CW * 0.07
    CW_PM = CW * 0.72
    CW_SC = CW * 0.14

    CR_hdr = [[
        Paragraph("<b>SN</b>", SML),
        Paragraph("", SML),
        Paragraph("<b>Evaluation Parameters</b>", ParagraphStyle("creh", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
        Paragraph("<b>Rating</b>", ParagraphStyle("creh2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
    ]]

    CR_rows = []
    for sn, sec_title, items in SECTIONS:
        # Section header row
        CR_rows.append([
            Paragraph(f"<b>{sn}</b>", ParagraphStyle("crsn", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            Paragraph("", SML),
            Paragraph(f"<b>{sec_title}</b>", ParagraphStyle("crst", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=12)),
            Paragraph("", SML),
        ])
        # Sub-items
        for code, suffix, desc in items:
            key = f"rating_{sn.lower()}{suffix}"
            CR_rows.append([
                Paragraph(sn,    SML),
                Paragraph(suffix.upper(), SML),
                Paragraph(desc,  VAL),
                Paragraph(_fd(fd, key), ParagraphStyle("crsc", fontSize=9, fontName="Helvetica", textColor=C_BLACK, alignment=TA_CENTER, leading=12)),
            ])

    # Overall Evaluation
    strength  = _fd(fd, "strength")
    improve   = _fd(fd, "areas_for_improvement")
    overall   = _fd(fd, "overall_score") or _fd(fd, "overall_rating")
    CR_rows += [
        [Paragraph("<b>05</b>", SML), Paragraph("", SML),
         Paragraph("<b>Overall Evaluation</b>", ParagraphStyle("crOE", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_LEFT, leading=12)),
         Paragraph("", SML)],
        [Paragraph("05", SML), Paragraph("", SML),
         Paragraph(f"<b>Strength:</b>  {strength}", VAL),
         Paragraph("", SML)],
        [Paragraph("05", SML), Paragraph("", SML),
         Paragraph(f"<b>Areas for Improvement:</b>  {improve}", VAL),
         Paragraph("", SML)],
        [Paragraph("<b>OVERALL SCORE:</b>", VAL),
         Paragraph("", SML),
         Paragraph("", SML),
         Paragraph(f"<b>{overall}</b>",
                   ParagraphStyle("cros2", fontSize=9, fontName="Helvetica-Bold", textColor=C_BLACK, alignment=TA_CENTER, leading=12))],
    ]

    # Section header row indices in CR_rows (0-based, after hdr)
    # We'll figure out which rows are section headers dynamically
    all_cr = CR_hdr + CR_rows
    n_hdr  = 1
    sec_hdr_rows = [n_hdr]  # first section (01) header
    ri = n_hdr
    for _, _, items in SECTIONS:
        sec_hdr_rows.append(ri)
        ri += 1 + len(items)
    # overall (05) header
    sec_hdr_rows.append(ri)

    # Calculate overall sub-rows indices for spanning col2+col3
    # Strength / improvement rows need col1+col2+col3 span
    strength_row_idx  = ri + 1
    improve_row_idx   = ri + 2
    overall_score_idx = ri + 3

    t_cr = Table(all_cr, colWidths=[CW_SN, CW_SB, CW_PM, CW_SC])
    cr_style = [
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
        ("ALIGN",         (1, 0), (1, -1),  "CENTER"),
        ("ALIGN",         (3, 0), (3, -1),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX",           (0, 0), (-1, -1), 0.5, C_BLACK),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, C_LIGHT),
        ("BACKGROUND",    (0, 0), (-1, 0),  _C_SEC_BG),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.5, C_BLACK),
        # Strength and improvement rows: span col1+col2+col3
        ("SPAN",          (1, strength_row_idx),  (3, strength_row_idx)),
        ("SPAN",          (1, improve_row_idx),   (3, improve_row_idx)),
        # Overall score row: span col0+col1+col2
        ("SPAN",          (0, overall_score_idx), (2, overall_score_idx)),
        # Section header: span col1+col2 (leave rating col separate)
        ("BACKGROUND",    (0, overall_score_idx), (-1, overall_score_idx), _C_SEC_BG),
        ("LINEABOVE",     (0, overall_score_idx), (-1, overall_score_idx), 0.5, C_BLACK),
        ("MINROWHEIGHT",  (0, strength_row_idx), (-1, strength_row_idx), 28),
        ("MINROWHEIGHT",  (0, improve_row_idx),  (-1, improve_row_idx),  28),
    ]
    for ri_s in sec_hdr_rows:
        cr_style.extend([
            ("BACKGROUND", (0, ri_s), (-1, ri_s), _C_SEC_BG),
            ("LINEBELOW",  (0, ri_s), (-1, ri_s), 0.5, C_BLACK),
            ("SPAN",       (1, ri_s), (2, ri_s)),
        ])

    t_cr.setStyle(TableStyle(cr_style))
    story.append(t_cr)
    story.append(Spacer(1, 5))

    # ── Recommendation + signature ───────────────────────────────────
    decision = (fd.get("decision") or "").strip().lower()
    rec_rows = [
        [_fsec("Evaluator's Recommendation"), ""],
        [_fchk(decision == "renew",
               "3 & above    —    Renew Contract"), ""],
        [_fchk(decision in ("renew_conditions", "conditional"),
               "2 – >3    —    Renew or extend Contract with Conditions"), ""],
        [_fchk(decision == "terminate",
               "2<    —    Terminate Contract"), ""],
        [_fsig("Evaluator's Signature", fd.get("evaluator_signature")),
         _flv("Date", _fmt(fd.get("date_of_evaluation")))],
    ]
    t_rec = _ftable(rec_rows, [L, R],
                    spans=(0, 1, 2, 3),
                    secs=(0,),
                    sigs=(4,))
    story.append(t_rec)

'''

# ──────────────────────────────────────────────────────────────────────────────
def main():
    with open(TARGET, 'r', encoding='utf-8') as f:
        source = f.read()

    # Find the block from `def _build_commencement` to just before `_BUILDERS = {`
    pattern = r'(def _build_commencement\(.*?)(_BUILDERS\s*=\s*\{)'
    m = re.search(pattern, source, re.DOTALL)
    if not m:
        print("ERROR: Could not find target region in hr_pdf_builder.py")
        sys.exit(1)

    new_source = source[:m.start(1)] + NEW_BUILDERS.lstrip('\n') + '\n\n' + source[m.start(2):]

    with open(TARGET, 'w', encoding='utf-8') as f:
        f.write(new_source)
    print(f"Replaced builders in {TARGET}")


if __name__ == '__main__':
    main()
