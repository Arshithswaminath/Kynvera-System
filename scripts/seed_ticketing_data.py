"""Seed dummy data for ticketing: Projects, Location hierarchy, Title Templates.

Usage (from project root):
  python scripts/seed_ticketing_data.py

Callable from app startup via seed_ticketing_data() inside an app context.
"""
from app.models import (
    db, TicketProject, TicketProperty, TicketZone,
    TicketSubZone, TicketBaseUnit, TicketTitleTemplate,
)


def seed_ticketing_data():
    """Idempotent get-or-create for projects, locations, and title templates."""
    # ── Clear existing (optional reset) ──────────────────────────────────
    if TicketProject.query.count() == 0 and TicketTitleTemplate.query.count() == 0:
        print("Database is empty — seeding fresh data…")
    else:
        print("Some data already exists. Adding/merging only new entries…")

    # ── Helper: get or create ─────────────────────────────────────────────
    def goc_project(name, client=None, desc=None):
        p = TicketProject.query.filter_by(name=name).first()
        if not p:
            p = TicketProject(name=name, client_name=client, description=desc)
            db.session.add(p)
            db.session.flush()
        return p

    def goc_property(name, project_id):
        p = TicketProperty.query.filter_by(name=name, project_id=project_id).first()
        if not p:
            p = TicketProperty(name=name, project_id=project_id)
            db.session.add(p)
            db.session.flush()
        return p

    def goc_zone(name, property_id):
        z = TicketZone.query.filter_by(name=name, property_id=property_id).first()
        if not z:
            z = TicketZone(name=name, property_id=property_id)
            db.session.add(z)
            db.session.flush()
        return z

    def goc_sub_zone(name, zone_id):
        s = TicketSubZone.query.filter_by(name=name, zone_id=zone_id).first()
        if not s:
            s = TicketSubZone(name=name, zone_id=zone_id)
            db.session.add(s)
            db.session.flush()
        return s

    def goc_unit(name, sub_zone_id):
        u = TicketBaseUnit.query.filter_by(name=name, sub_zone_id=sub_zone_id).first()
        if not u:
            u = TicketBaseUnit(name=name, sub_zone_id=sub_zone_id)
            db.session.add(u)
        return u

    def goc_title(title, sg=None, cat=None, ft=None, desc_tmpl=None):
        t = TicketTitleTemplate.query.filter_by(title=title).first()
        if not t:
            t = TicketTitleTemplate(
                title=title, service_group=sg, category=cat,
                fault_type=ft, description_template=desc_tmpl,
            )
            db.session.add(t)
        return t

    # ════════════════════════════════════════════════════════════════════════
    # PROJECTS + LOCATION HIERARCHY
    # ════════════════════════════════════════════════════════════════════════

    # ── Project 1: Marina Towers ─────────────────────────────────────────
    p1 = goc_project("Marina Towers", "Al Futtaim Group", "Mixed-use residential & retail complex")

    prop_ta = goc_property("Tower A", p1.id)
    for zone_name, sub_zones in {
        "Basement Levels": {
            "B1 – Parking": ["P1-01", "P1-02", "P1-03", "P1-04", "P1-05"],
            "B2 – Parking": ["P2-01", "P2-02", "P2-03"],
            "B1 – Utility": ["Electrical Room", "Water Tank Room", "Generator Room"],
        },
        "Podium (Ground – 4F)": {
            "Ground Floor": ["Lobby", "Reception", "Retail Unit 01", "Retail Unit 02", "Security Room"],
            "Level 1": ["Gym & Spa", "Swimming Pool", "Kids Play Area"],
            "Level 2 – 4 (Offices)": ["Office 201", "Office 202", "Office 301", "Office 302", "Office 401"],
        },
        "Residential Floors (5F – 30F)": {
            "Low Zone (5F – 15F)": ["Apt 501", "Apt 502", "Apt 503", "Apt 601", "Apt 602", "Apt 701", "Apt 1001", "Apt 1501"],
            "Mid Zone (16F – 25F)": ["Apt 1601", "Apt 1602", "Apt 1701", "Apt 2001", "Apt 2501"],
            "High Zone (26F – 30F)": ["Apt 2601", "Apt 2701", "Apt 2801", "Apt 2901", "Penthouse 3001"],
        },
        "Roof & Plant": {
            "Roof Level": ["Cooling Tower Area", "Solar Panel Zone", "Lift Machine Room"],
        },
    }.items():
        zone = goc_zone(zone_name, prop_ta.id)
        for sz_name, units in sub_zones.items():
            sz = goc_sub_zone(sz_name, zone.id)
            for u in units:
                goc_unit(u, sz.id)

    prop_tb = goc_property("Tower B", p1.id)
    for zone_name, sub_zones in {
        "Basement": {
            "B1 – Parking": ["P1-10", "P1-11", "P1-12"],
            "B1 – Services": ["Pump Room", "Fire Control Room"],
        },
        "Residential Floors": {
            "Low Zone (1F – 10F)": ["Apt 101", "Apt 102", "Apt 201", "Apt 301", "Apt 1001"],
            "High Zone (11F – 20F)": ["Apt 1101", "Apt 1501", "Apt 2001"],
        },
    }.items():
        zone = goc_zone(zone_name, prop_tb.id)
        for sz_name, units in sub_zones.items():
            sz = goc_sub_zone(sz_name, zone.id)
            for u in units:
                goc_unit(u, sz.id)

    prop_retail = goc_property("Retail Podium", p1.id)
    zone_gf = goc_zone("Ground Level", prop_retail.id)
    for sz_n, units in {
        "Wing A": ["Shop A-01", "Shop A-02", "Shop A-03", "Food Court A"],
        "Wing B": ["Shop B-01", "Shop B-02", "Pharmacy", "ATM Corner"],
        "Back of House": ["Loading Bay", "Waste Room", "Staff Canteen"],
    }.items():
        sz = goc_sub_zone(sz_n, zone_gf.id)
        for u in units:
            goc_unit(u, sz.id)

    # ── Project 2: Green Valley Villas ───────────────────────────────────
    p2 = goc_project("Green Valley Villas", "Emaar Properties", "Gated villa community, 120 units")

    prop_phA = goc_property("Phase A", p2.id)
    for zone_n, sub_zones in {
        "Block 1 (Villas 1–20)": {
            "Interior": ["Villa 1", "Villa 2", "Villa 3", "Villa 4", "Villa 5", "Villa 10", "Villa 15", "Villa 20"],
            "Exterior / Garden": ["Villa 1 Garden", "Villa 5 Garden", "Villa 10 Garden"],
        },
        "Block 2 (Villas 21–40)": {
            "Interior": ["Villa 21", "Villa 22", "Villa 25", "Villa 30", "Villa 40"],
            "Exterior / Garden": ["Villa 21 Garden", "Villa 30 Garden"],
        },
        "Community Facilities": {
            "Recreation": ["Clubhouse", "Swimming Pool", "Tennis Court", "Kids Play Area"],
            "Infrastructure": ["Main Entrance Gate", "Guard House", "Pump Station"],
        },
    }.items():
        zone = goc_zone(zone_n, prop_phA.id)
        for sz_n, units in sub_zones.items():
            sz = goc_sub_zone(sz_n, zone.id)
            for u in units:
                goc_unit(u, sz.id)

    # ── Project 3: Injaaz HQ ─────────────────────────────────────────────
    p3 = goc_project("Injaaz HQ Office", "Injaaz FM", "Company headquarters building")

    prop_hq = goc_property("HQ Building", p3.id)
    for zone_n, sub_zones in {
        "Ground Floor": {
            "Public Areas": ["Main Lobby", "Reception", "Waiting Area", "Security Desk"],
            "Services": ["Server Room", "Electrical Room", "Storage"],
        },
        "First Floor": {
            "Operations": ["Operations Hub", "Control Room", "Team Workstations"],
            "Meeting Rooms": ["Conf Room A", "Conf Room B", "Boardroom"],
        },
        "Second Floor": {
            "Management": ["CEO Office", "CFO Office", "HR Department", "Finance Department"],
            "Support": ["Pantry", "Prayer Room", "Archive Room"],
        },
        "Rooftop": {
            "Plant Room": ["AC Chillers", "Cooling Tower", "Pump Room"],
        },
    }.items():
        zone = goc_zone(zone_n, prop_hq.id)
        for sz_n, units in sub_zones.items():
            sz = goc_sub_zone(sz_n, zone.id)
            for u in units:
                goc_unit(u, sz.id)

    # ════════════════════════════════════════════════════════════════════════
    # TITLE TEMPLATES
    # ════════════════════════════════════════════════════════════════════════

    hvac_templates = [
        ("AC Unit Not Cooling — Inspection Required", "HVAC & MEP", "FCU", "Breakdown",
         "AC unit reported not cooling to the required temperature.\n\nScope of work:\n- Inspect FCU filters and coils\n- Check refrigerant levels and pressure\n- Verify thermostat and controls operation\n- Clean/service unit as required\n- Document findings and corrective action taken"),

        ("AC Water Leak — Emergency Repair", "HVAC & MEP", "FCU", "Emergency",
         "Water leakage reported from AC unit.\n\nScope of work:\n- Locate and identify source of water leak\n- Clear condensate drain line blockage\n- Check drain pan and insulation condition\n- Repair or replace faulty components\n- Test operation after repair"),

        ("Chiller Fault — Immediate Attention", "HVAC & MEP", "Chiller", "Breakdown",
         "Central chiller unit reported faulty.\n\nScope of work:\n- Run diagnostic check on chiller controls\n- Inspect compressor, condenser, and evaporator\n- Check refrigerant levels and pressures\n- Log all fault codes and alarms\n- Carry out corrective maintenance or escalate if major fault"),

        ("HVAC Scheduled Preventive Maintenance", "HVAC & MEP", "AHU", "Preventive Maintenance",
         "Routine preventive maintenance for HVAC system.\n\nScope of work:\n- Clean and replace air filters\n- Check belt tensions and motor performance\n- Lubricate all moving parts\n- Inspect controls, sensors, and thermostats\n- Verify air flow and temperature set points\n- Update maintenance log"),

        ("Ductwork Noise / Vibration Issue", "HVAC & MEP", "Ductwork", "Complaint",
         "Excessive noise or vibration reported from ductwork.\n\nScope of work:\n- Inspect duct connections and supports\n- Check for loose panels or damper issues\n- Balance airflow if required\n- Apply vibration dampening where needed"),
    ]

    elec_templates = [
        ("Power Outage — Area Affected", "Electrical", "Power Outage", "Emergency",
         "Power outage reported in the specified area.\n\nScope of work:\n- Identify tripped breakers or blown fuses\n- Inspect distribution board for faults\n- Check for short circuits or overloads\n- Restore power safely and test all circuits\n- Document root cause and preventive measures"),

        ("Lighting Fixture Fault — Replacement", "Electrical", "Lighting", "Corrective Maintenance",
         "Lighting fixture reported faulty or not working.\n\nScope of work:\n- Identify faulty fixture(s)\n- Replace lamp/bulb or entire fitting as required\n- Check wiring connections and earthing\n- Test operation after replacement"),

        ("Electrical Panel Inspection", "Electrical", "Panels", "Inspection",
         "Routine inspection of electrical distribution panel.\n\nScope of work:\n- Visual inspection of all MCBs and connections\n- Check for signs of overheating, corrosion, or damage\n- Tighten all cable terminations\n- Test RCDs and safety devices\n- Update inspection record"),

        ("Generator Startup / Test Run", "Electrical", "Generator", "Preventive Maintenance",
         "Scheduled generator test run and inspection.\n\nScope of work:\n- Start generator and run under load for 30 minutes\n- Check fuel level, oil level, and coolant\n- Inspect battery and charging system\n- Record running hours and performance readings\n- Resolve any faults observed during test"),
    ]

    plumbing_templates = [
        ("Water Leak — Urgent Repair", "Plumbing", "Leak", "Emergency",
         "Water leak reported. Urgent action required.\n\nScope of work:\n- Isolate water supply to affected area\n- Identify and locate leak source\n- Repair or replace faulty pipe / fitting\n- Test for leaks after repair\n- Inspect surrounding area for water damage"),

        ("Blocked Drain / Sewage Backup", "Plumbing", "Blockage", "Corrective Maintenance",
         "Drain blockage or sewage backup reported.\n\nScope of work:\n- Identify blocked drain location\n- Use appropriate clearing method (plunger, snake, CCTV if needed)\n- Clear blockage and flush drain\n- Inspect for root cause (grease, debris, structural issue)\n- Advise occupant on prevention"),

        ("Low Water Pressure Complaint", "Plumbing", "Water Pressure", "Complaint",
         "Low water pressure reported in the specified unit/area.\n\nScope of work:\n- Check pressure at incoming supply\n- Inspect and clean pressure regulator valve\n- Check for partial blockages in pipework\n- Inspect pump performance if applicable\n- Document readings and corrective action"),

        ("Sanitary Fixture Replacement", "Plumbing", "Fixtures", "Installation",
         "Sanitary fixture repair or replacement required.\n\nScope of work:\n- Remove existing faulty fixture\n- Install new fixture and connect to supply and waste\n- Test for leaks and proper operation\n- Seal and finish to required standard"),
    ]

    civil_templates = [
        ("Wall / Ceiling Crack — Assessment", "Civil Works", "Walls", "Inspection",
         "Crack reported in wall or ceiling. Assessment required.\n\nScope of work:\n- Inspect crack dimensions and pattern\n- Determine if structural or non-structural\n- Mark crack for monitoring if minor\n- Carry out repair: fill, grout, plaster, and paint finish\n- Escalate to structural engineer if major concern"),

        ("Floor Tile Damage — Repair", "Civil Works", "Flooring", "Corrective Maintenance",
         "Damaged or loose floor tiles reported.\n\nScope of work:\n- Remove damaged tiles carefully\n- Prepare substrate surface\n- Install replacement tiles with appropriate adhesive\n- Grout and seal joints\n- Match finish to existing floor as closely as possible"),

        ("Door / Window Not Closing Properly", "Civil Works", "Doors & Windows", "Complaint",
         "Door or window reported not closing, sticking, or damaged.\n\nScope of work:\n- Inspect hinges, frame alignment, and hardware\n- Adjust or replace hinges/closers as required\n- Re-align door/window frame if needed\n- Repair or replace lock mechanisms\n- Test operation after repair"),

        ("Painting & Touch-Up Works", "Civil Works", "Walls", "Corrective Maintenance",
         "Painting or touch-up work required.\n\nScope of work:\n- Prepare surface (clean, sand, fill cracks)\n- Apply primer coat where needed\n- Apply finish paint to match existing\n- Protect surrounding areas during work\n- Inspect and touch up after drying"),
    ]

    cleaning_templates = [
        ("Deep Clean Required — Post-Construction", "Cleaning Services", "Deep Clean", "Corrective Maintenance",
         "Post-construction deep clean required for the specified area.\n\nScope of work:\n- Remove all construction debris and waste\n- Deep clean all floors, walls, and surfaces\n- Clean all fixtures, fittings, and glass\n- Clean and sanitise wet areas\n- Final inspection and sign-off"),

        ("Pest Control — Urgent Treatment", "Cleaning Services", "Pest Control", "Emergency",
         "Pest infestation reported. Urgent treatment required.\n\nScope of work:\n- Identify pest type and infestation extent\n- Apply appropriate treatment (gel, spray, fumigation)\n- Seal entry points where identified\n- Leave monitoring bait stations if required\n- Provide follow-up schedule"),

        ("Routine Cleaning Not Done — Complaint", "Cleaning Services", "Routine Clean", "Complaint",
         "Complaint received: routine cleaning service not carried out as scheduled.\n\nScope of work:\n- Carry out missed cleaning service immediately\n- Verify cleaning schedule compliance\n- Document reason for missed service\n- Implement corrective measure to prevent recurrence"),
    ]

    general_templates = [
        ("General Maintenance Request", None, None, None,
         "General maintenance work order.\n\nScope of work:\n- Inspect and assess reported issue\n- Carry out required maintenance or repair\n- Source materials if needed\n- Test and verify completion\n- Document work performed and materials used"),

        ("Urgent Emergency — Immediate Response Required", None, None, "Emergency",
         "URGENT: Emergency maintenance required. Immediate response needed.\n\nScope of work:\n- Respond immediately to site\n- Assess situation and take immediate corrective action\n- Make area safe and isolate hazard if required\n- Carry out permanent repair or temporary fix\n- Report findings and recommend follow-up works"),

        ("Scheduled Preventive Maintenance Visit", None, None, "Preventive Maintenance",
         "Scheduled preventive maintenance visit as per PPM plan.\n\nScope of work:\n- Carry out all items listed on the PPM checklist\n- Inspect equipment and systems for signs of wear\n- Lubricate, clean, and adjust as required\n- Record readings and observations\n- Report any defects found for corrective action"),

        ("Site Inspection & Condition Report", None, None, "Inspection",
         "Site inspection visit to assess overall condition.\n\nScope of work:\n- Walk through assigned areas and inspect all systems\n- Photograph any defects or areas of concern\n- Record condition ratings for each area\n- Prepare and submit condition report\n- Prioritise findings for action"),
    ]

    all_templates = hvac_templates + elec_templates + plumbing_templates + civil_templates + cleaning_templates + general_templates
    for args in all_templates:
        goc_title(*args)

    db.session.commit()
    print(f"\n✓ Seeded successfully!")
    print(f"  Projects:          {TicketProject.query.count()}")
    print(f"  Properties:        {TicketProperty.query.count()}")
    print(f"  Zones:             {TicketZone.query.count()}")
    print(f"  Sub-zones:         {TicketSubZone.query.count()}")
    print(f"  Base units:        {TicketBaseUnit.query.count()}")
    print(f"  Title templates:   {TicketTitleTemplate.query.count()}")


def main():
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from Injaaz import create_app
    app = create_app()
    with app.app_context():
        seed_ticketing_data()


if __name__ == '__main__':
    main()
