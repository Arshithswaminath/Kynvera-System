"""Seed synthetic, high-volume data for local load/stress testing.

Unlike scripts/seed_ticketing_data.py (curated demo data, a handful of rows
per table so the UI has something believable to show), this script exists
purely to generate VOLUME: hundreds of users, a location hierarchy an order
of magnitude bigger than the demo seed, and thousands of tickets spread
across every real status/priority — so list/filter/pagination/export
endpoints face genuine pressure under Locust.

Usage (from project root, venv active):

    python scripts/seed_load_test_data.py
    python scripts/seed_load_test_data.py --users 500 --tickets 8000

Or import and call from within an app context (same convention as
scripts/seed_ticketing_data.py::seed_ticketing_data()):

    from scripts.seed_load_test_data import seed_load_test_data
    with app.app_context():
        seed_load_test_data()

Scale knobs (env vars, all optional — CLI flags of the same name override):
    LOADTEST_USERS               total User rows to ensure exist   (default 200)
    LOADTEST_TICKETS             total Ticket rows to ensure exist (default 3000)
    LOADTEST_PROJECTS            TicketProject rows                (default 8)
    LOADTEST_PROPERTIES_PER_PROJECT   TicketProperty rows/project  (default 6)
    LOADTEST_ZONES_PER_PROPERTY       TicketZone rows/property     (default 5)
    LOADTEST_SUBZONES_PER_ZONE        TicketSubZone rows/zone      (default 4)
    LOADTEST_UNITS_PER_SUBZONE        TicketBaseUnit rows/subzone  (default 5)
    LOADTEST_PASSWORD            shared password for every seeded user
                                  (default "LoadTest#2024" — used by loadtest/locustfile.py)

At the defaults above the location hierarchy alone is ~48 properties /
~240 zones / ~960 sub-zones / ~4,800 base units — noticeably heavier than
seed_ticketing_data.py's ~5 properties / ~15 zones / ~35 sub-zones / ~140
units, on purpose.

DATABASE TARGET — read this before running
--------------------------------------------
This script must run against a real file-based database (SQLite file or
Postgres), never `sqlite:///:memory:` (that's tests/conftest.py's in-memory
DB for pytest — this script deliberately does not touch that).

It will NOT default to the real dev database (`injaaz.db` at the repo root,
or `instance/injaaz.db`). If DATABASE_URL is not set in the environment, it
defaults to a clearly-separate file: `instance/loadtest.db` (the `instance/`
directory is created if missing). To target something else, set DATABASE_URL
explicitly and this script will use exactly that:

    DATABASE_URL=sqlite:////absolute/path/to/instance/loadtest.db \\
        python scripts/seed_load_test_data.py

    DATABASE_URL=postgresql://user:pass@localhost/injaaz_loadtest \\
        python scripts/seed_load_test_data.py

As a safety net, if DATABASE_URL resolves to a SQLite path literally named
`injaaz.db` (the real dev DB, wherever it lives), the script refuses to run
unless LOADTEST_ALLOW_UNSAFE_DB=true is also set. `sqlite:///:memory:` is
always refused, no override.

Idempotency
-----------
Safe to re-run. Users are get-or-create by username (deterministic
`loadtest_<role>_<n>` names), so re-running with the same LOADTEST_USERS
just no-ops; raising it adds the delta. The location hierarchy is "topped
up" per parent (count existing children, create only the shortfall) rather
than a per-row get-or-create like seed_ticketing_data.py's goc_* helpers —
at thousands of rows a per-row existence check is unnecessary overhead, and
the task doesn't call for perfect idempotency here, just "won't error or
explode on a second run". Tickets are topped up the same way, counted by
their `project` field pointing at a LoadTest-prefixed project.
"""
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone


# ---------------------------------------------------------------------------
# Database target safety net — must happen BEFORE `import config` / `from
# Injaaz import create_app`, since config.py reads DATABASE_URL from the
# environment at import time.
# ---------------------------------------------------------------------------

def _default_loadtest_db_url() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    instance_dir = os.path.join(base_dir, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    return f"sqlite:///{os.path.join(instance_dir, 'loadtest.db')}"


def _guard_database_url():
    """Refuse to run against the pytest in-memory DB or the real dev DB."""
    url = os.environ.get('DATABASE_URL')
    if not url:
        url = _default_loadtest_db_url()
        os.environ['DATABASE_URL'] = url
        print(f"DATABASE_URL not set — defaulting to {url}")

    if 'sqlite' in url.lower() and ':memory:' in url.lower():
        raise RuntimeError(
            "Refusing to run against sqlite:///:memory: — that's reserved for "
            "tests/conftest.py's pytest fixtures. Point DATABASE_URL at a real "
            "file-based SQLite path or a Postgres URL."
        )

    if 'sqlite' in url.lower():
        db_path = url.split('sqlite:///', 1)[-1].split('?', 1)[0]
        if os.path.basename(db_path) == 'injaaz.db' and os.environ.get('LOADTEST_ALLOW_UNSAFE_DB', '').lower() not in ('1', 'true', 'yes'):
            raise RuntimeError(
                f"Refusing to run against {db_path!r} — that looks like the real dev "
                "database. Point DATABASE_URL at a dedicated load-test DB (e.g. "
                "instance/loadtest.db), or set LOADTEST_ALLOW_UNSAFE_DB=true to override."
            )
    return url


_guard_database_url()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    'Ahmed', 'Fatima', 'Mohammed', 'Aisha', 'Omar', 'Layla', 'Khalid', 'Noor',
    'Yousef', 'Mariam', 'Hassan', 'Sara', 'Ali', 'Huda', 'Rashid', 'Amina',
    'Tariq', 'Zainab', 'Faisal', 'Reem', 'Samuel', 'Priya', 'David', 'Elena',
    'James', 'Maria', 'John', 'Anjali', 'Robert', 'Chen',
]
LAST_NAMES = [
    'Al Mansoori', 'Al Suwaidi', 'Khan', 'Rahman', 'Hussain', 'Al Falasi',
    'Sharma', 'Fernandes', 'Silva', 'Santos', 'Smith', 'Johnson', 'Wilson',
    'Rodriguez', 'Nguyen', 'Kumar', 'Patel', 'Reyes', 'Cruz', 'Abdullah',
]

# (service_group, category, fault_type) combos, mirrors the flavour of
# scripts/seed_ticketing_data.py's title templates but kept lightweight —
# this script is about volume, not curated narrative content.
SERVICE_COMBOS = [
    ('HVAC & MEP', 'FCU', 'Breakdown'),
    ('HVAC & MEP', 'FCU', 'Emergency'),
    ('HVAC & MEP', 'Chiller', 'Breakdown'),
    ('HVAC & MEP', 'AHU', 'Preventive Maintenance'),
    ('HVAC & MEP', 'Ductwork', 'Complaint'),
    ('Electrical', 'Power Outage', 'Emergency'),
    ('Electrical', 'Lighting', 'Corrective Maintenance'),
    ('Electrical', 'Panels', 'Inspection'),
    ('Electrical', 'Generator', 'Preventive Maintenance'),
    ('Plumbing', 'Leak', 'Emergency'),
    ('Plumbing', 'Blockage', 'Corrective Maintenance'),
    ('Plumbing', 'Water Pressure', 'Complaint'),
    ('Plumbing', 'Fixtures', 'Installation'),
    ('Civil Works', 'Walls', 'Inspection'),
    ('Civil Works', 'Flooring', 'Corrective Maintenance'),
    ('Civil Works', 'Doors & Windows', 'Complaint'),
    ('Cleaning Services', 'Deep Clean', 'Corrective Maintenance'),
    ('Cleaning Services', 'Pest Control', 'Emergency'),
    ('Cleaning Services', 'Routine Clean', 'Complaint'),
]

PRIORITIES = ['low', 'medium', 'high', 'critical']
PRIORITY_WEIGHTS = [30, 40, 20, 10]

# v2 canonical statuses (module_ticketing/routes.py::_STATUS_LABELS) — weighted
# to look like a real pipeline: most tickets mid-flow or closed, a modest tail
# of on_hold/cancelled.
STATUSES = [
    'open', 'assigned', 'site_attended', 'work_started', 'work_completed',
    'verification', 'provider_closed', 'on_hold', 'cancelled', 'closed',
]
STATUS_WEIGHTS = [12, 15, 10, 13, 8, 6, 5, 6, 5, 20]

# Statuses at/after technician assignment — these get technician_id/assigned_to_id set.
_ASSIGNED_OR_LATER = frozenset({
    'assigned', 'site_attended', 'work_started', 'work_completed',
    'verification', 'provider_closed', 'on_hold', 'closed',
})
_RESOLVED_TS_STATUSES = frozenset({'work_completed', 'verification', 'provider_closed', 'closed'})


def _env_int(name, default):
    val = os.environ.get(name)
    if val is None or val == '':
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _weighted_choice(options, weights):
    return random.choices(options, weights=weights, k=1)[0]


def _random_name(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _random_past_datetime(rng, days_back=120):
    """Naive UTC datetime somewhere in the last `days_back` days (models use naive-UTC columns)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = timedelta(
        days=rng.randint(0, days_back),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
    )
    return now - delta


def _gen_ticket_id(used: set) -> str:
    """Match module_ticketing/routes.py::_generate_ticket_id()'s TKT-XXXXXXXX format."""
    while True:
        tid = 'TKT-' + uuid.uuid4().hex[:8].upper()
        if tid not in used:
            used.add(tid)
            return tid


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _role_counts(total):
    """admin / supervisor / technician / standard split with sane minimums."""
    total = max(total, 4)
    admin_n = max(1, round(total * 0.05))
    supervisor_n = max(1, round(total * 0.10))
    technician_n = max(1, round(total * 0.20))
    standard_n = total - admin_n - supervisor_n - technician_n
    while standard_n < 0 and (technician_n > 1 or supervisor_n > 1):
        if technician_n > 1:
            technician_n -= 1
        elif supervisor_n > 1:
            supervisor_n -= 1
        standard_n = total - admin_n - supervisor_n - technician_n
    standard_n = max(0, standard_n)
    return {
        'admin': admin_n,
        'supervisor': supervisor_n,
        'technician': technician_n,
        'standard': standard_n,
    }


_EXTRA_DESIGNATIONS = ['operations_manager', 'business_development', 'procurement', 'general_manager']

_ACCESS_FLAGS = [
    'access_hvac', 'access_civil', 'access_cleaning', 'access_hr',
    'access_procurement_module', 'access_business_development',
    'access_report_generation', 'access_submitted_forms',
    'access_qhsi', 'access_files',
]


def _seed_users(db, User, rng, total_users, password):
    """Get-or-create deterministic `loadtest_<role>_<n>` users. Returns dict of role -> [User]."""
    counts = _role_counts(total_users)
    pools = {'admin': [], 'supervisor': [], 'technician': [], 'standard': []}

    role_plan = [
        ('admin', counts['admin'], 'admin', None),
        ('supervisor', counts['supervisor'], 'user', 'supervisor'),
        ('technician', counts['technician'], 'user', 'technician'),
        ('standard', counts['standard'], 'user', None),
    ]

    created = 0
    for role_key, n, role_value, designation in role_plan:
        for i in range(1, n + 1):
            username = f'loadtest_{role_key}_{i}'
            user = User.query.filter_by(username=username).first()
            if user is None:
                designation_value = designation
                if role_key == 'standard' and rng.random() < 0.08:
                    designation_value = rng.choice(_EXTRA_DESIGNATIONS)
                user = User(
                    username=username,
                    email=f'{username}@loadtest.local',
                    full_name=_random_name(rng),
                    role=role_value,
                    designation=designation_value,
                    is_active=True,
                    password_changed=True,
                    access_ticketing=True,
                    is_ticket_reporter=(rng.random() < 0.1),
                )
                for flag in _ACCESS_FLAGS:
                    setattr(user, flag, rng.random() < 0.35)
                user.set_password(password)
                db.session.add(user)
                created += 1
            pools[role_key].append(user)
        db.session.flush()

    db.session.commit()
    print(f"  Users: {sum(len(v) for v in pools.values())} total "
          f"(admin={len(pools['admin'])}, supervisor={len(pools['supervisor'])}, "
          f"technician={len(pools['technician'])}, standard={len(pools['standard'])}); "
          f"{created} newly created this run")
    return pools


# ---------------------------------------------------------------------------
# Location hierarchy (topped up per parent, not per-row get-or-create — see
# module docstring for why this differs from seed_ticketing_data.py's goc_*)
# ---------------------------------------------------------------------------

def _top_up_children(db, model, parent_field, parent_id, target_count, name_fn, extra_fields=None):
    """Ensure `model` has >= target_count rows for this parent; create the shortfall. Returns all rows."""
    existing = model.query.filter_by(**{parent_field: parent_id}).all()
    shortfall = target_count - len(existing)
    if shortfall > 0:
        start = len(existing) + 1
        for i in range(start, start + shortfall):
            kwargs = {parent_field: parent_id, 'name': name_fn(i)}
            if extra_fields:
                kwargs.update(extra_fields(i))
            row = model(**kwargs)
            db.session.add(row)
        db.session.flush()
        existing = model.query.filter_by(**{parent_field: parent_id}).all()
    return existing


def _seed_locations(db, TicketProject, TicketProperty, TicketZone, TicketSubZone, TicketBaseUnit,
                     rng, n_projects, props_per_project, zones_per_prop, subzones_per_zone, units_per_subzone):
    projects = []
    for p in range(1, n_projects + 1):
        name = f'LoadTest Project {p}'
        proj = TicketProject.query.filter_by(name=name).first()
        if proj is None:
            proj = TicketProject(
                name=name,
                client_name=f'LoadTest Client {p}',
                description='Synthetic project generated by scripts/seed_load_test_data.py for local stress testing.',
                is_active=True,
            )
            db.session.add(proj)
            db.session.flush()
        projects.append(proj)
    db.session.commit()

    leaves = []  # flat list of dicts for random ticket-location assignment
    zone_count = subzone_count = unit_count = 0
    for proj in projects:
        properties = _top_up_children(
            db, TicketProperty, 'project_id', proj.id, props_per_project,
            name_fn=lambda i, p=proj: f'{p.name} — Property {i}',
            extra_fields=lambda i: {
                'latitude': round(24.0 + random.random() * 2, 6),
                'longitude': round(54.0 + random.random() * 2, 6),
                'area': f'Zone {i}', 'city': 'Dubai', 'country': 'UAE',
                'is_active': True,
            },
        )
        for prop in properties:
            zones = _top_up_children(
                db, TicketZone, 'property_id', prop.id, zones_per_prop,
                name_fn=lambda i, pr=prop: f'{pr.name} / Zone {i}',
                extra_fields=lambda i: {'is_active': True},
            )
            zone_count += len(zones)
            for zone in zones:
                sub_zones = _top_up_children(
                    db, TicketSubZone, 'zone_id', zone.id, subzones_per_zone,
                    name_fn=lambda i, z=zone: f'{z.name} / Sub-zone {i}',
                    extra_fields=lambda i: {'is_active': True},
                )
                subzone_count += len(sub_zones)
                for sub_zone in sub_zones:
                    units = _top_up_children(
                        db, TicketBaseUnit, 'sub_zone_id', sub_zone.id, units_per_subzone,
                        name_fn=lambda i, sz=sub_zone: f'{sz.name} / Unit {i}',
                        extra_fields=lambda i: {'is_active': True},
                    )
                    unit_count += len(units)
                    for unit in units:
                        leaves.append({
                            'project_id': proj.id, 'project_name': proj.name,
                            'property_id': prop.id, 'property_name': prop.name,
                            'zone_id': zone.id, 'zone_name': zone.name,
                            'sub_zone_id': sub_zone.id, 'sub_zone_name': sub_zone.name,
                            'base_unit_id': unit.id, 'base_unit_name': unit.name,
                        })
        db.session.commit()

    property_count = len({l['property_id'] for l in leaves})
    print(f"  Location hierarchy: {len(projects)} projects, {property_count} properties, "
          f"{zone_count} zones, {subzone_count} sub-zones, {unit_count} base units")
    return projects, leaves


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def _seed_tickets(db, Ticket, rng, projects, leaves, user_pools, target_tickets):
    project_names = [p.name for p in projects]
    existing = Ticket.query.filter(Ticket.project.in_(project_names)).count()
    shortfall = target_tickets - existing
    if shortfall <= 0:
        print(f"  Tickets: {existing} already present for LoadTest projects (target {target_tickets}) — skipping")
        return

    used_ids = {t[0] for t in db.session.query(Ticket.ticket_id).filter(Ticket.ticket_id.like('TKT-%')).all()}

    reporters_weighted = (
        user_pools['standard'] * 7 + user_pools['supervisor'] * 3
        + user_pools['technician'] * 2 + user_pools['admin']
    ) or (user_pools['admin'] or [None])
    technicians = user_pools['technician'] or user_pools['standard']
    supervisors = user_pools['supervisor'] or user_pools['admin']

    rows = []
    batch_size = 500
    for n in range(shortfall):
        leaf = rng.choice(leaves)
        service_group, category, fault_type = rng.choice(SERVICE_COMBOS)
        priority = _weighted_choice(PRIORITIES, PRIORITY_WEIGHTS)
        status = _weighted_choice(STATUSES, STATUS_WEIGHTS)
        created_at = _random_past_datetime(rng)
        updated_at = created_at + timedelta(hours=rng.randint(0, 72))

        reporter = rng.choice(reporters_weighted)
        assigned_to_id = technician_id = supervisor_id = None
        if status in _ASSIGNED_OR_LATER and technicians:
            tech = rng.choice(technicians)
            technician_id = tech.id
            assigned_to_id = tech.id
        if (status in _ASSIGNED_OR_LATER or status == 'cancelled') and supervisors and rng.random() < 0.9:
            supervisor_id = rng.choice(supervisors).id
        elif status == 'cancelled' and supervisors and rng.random() < 0.5:
            supervisor_id = rng.choice(supervisors).id

        resolved_at = closed_at = None
        if status in _RESOLVED_TS_STATUSES:
            resolved_at = updated_at
        if status == 'closed':
            closed_at = updated_at

        rows.append({
            'ticket_id': _gen_ticket_id(used_ids),
            'reporter_id': reporter.id if reporter else None,
            'assigned_to_id': assigned_to_id,
            'supervisor_id': supervisor_id,
            'technician_id': technician_id,
            'project': leaf['project_name'],
            'service_group': service_group,
            'category': category,
            'fault_type': fault_type,
            'priority': priority,
            'title': f'{fault_type} — {category} at {leaf["property_name"]}',
            'work_description': (
                f'{category} ({fault_type}) reported at {leaf["property_name"]} / '
                f'{leaf["zone_name"]} / {leaf["sub_zone_name"]} / {leaf["base_unit_name"]}. '
                'Synthetic ticket generated for load testing.'
            ),
            'property_name': leaf['property_name'],
            'zone': leaf['zone_name'],
            'sub_zone': leaf['sub_zone_name'],
            'base_unit': leaf['base_unit_name'],
            'property_id': leaf['property_id'],
            'zone_id': leaf['zone_id'],
            'sub_zone_id': leaf['sub_zone_id'],
            'base_unit_id': leaf['base_unit_id'],
            'is_chargeable': rng.random() < 0.4,
            'status': status,
            'created_at': created_at,
            'updated_at': updated_at,
            'resolved_at': resolved_at,
            'closed_at': closed_at,
            'source': 'manual',
        })

        if len(rows) >= batch_size:
            db.session.bulk_insert_mappings(Ticket, rows)
            db.session.commit()
            rows = []

    if rows:
        db.session.bulk_insert_mappings(Ticket, rows)
        db.session.commit()

    total = Ticket.query.filter(Ticket.project.in_(project_names)).count()
    print(f"  Tickets: {total} present for LoadTest projects (target {target_tickets}); "
          f"{shortfall} created this run")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def seed_load_test_data(
    users=None, tickets=None, projects=None,
    properties_per_project=None, zones_per_property=None,
    subzones_per_zone=None, units_per_subzone=None,
    password=None, seed=None,
):
    """Seed high-volume synthetic data for load testing. Call inside an app context."""
    from app.models import (
        db, User, Ticket,
        TicketProject, TicketProperty, TicketZone, TicketSubZone, TicketBaseUnit,
    )

    users = users if users is not None else _env_int('LOADTEST_USERS', 200)
    tickets = tickets if tickets is not None else _env_int('LOADTEST_TICKETS', 3000)
    projects_n = projects if projects is not None else _env_int('LOADTEST_PROJECTS', 8)
    props_per_project = properties_per_project if properties_per_project is not None else _env_int('LOADTEST_PROPERTIES_PER_PROJECT', 6)
    zones_per_prop = zones_per_property if zones_per_property is not None else _env_int('LOADTEST_ZONES_PER_PROPERTY', 5)
    subzones_per_zone_n = subzones_per_zone if subzones_per_zone is not None else _env_int('LOADTEST_SUBZONES_PER_ZONE', 4)
    units_per_subzone_n = units_per_subzone if units_per_subzone is not None else _env_int('LOADTEST_UNITS_PER_SUBZONE', 5)
    password = password or os.environ.get('LOADTEST_PASSWORD', 'LoadTest#2024')

    rng = random.Random(seed) if seed is not None else random.Random()

    print(f"Seeding load-test data: users={users} tickets={tickets} projects={projects_n} "
          f"props/project={props_per_project} zones/prop={zones_per_prop} "
          f"subzones/zone={subzones_per_zone_n} units/subzone={units_per_subzone_n}")

    user_pools = _seed_users(db, User, rng, users, password)
    proj_rows, leaves = _seed_locations(
        db, TicketProject, TicketProperty, TicketZone, TicketSubZone, TicketBaseUnit,
        rng, projects_n, props_per_project, zones_per_prop, subzones_per_zone_n, units_per_subzone_n,
    )
    if not leaves:
        raise RuntimeError('No location leaves generated — cannot seed tickets without a base unit to attach them to.')
    _seed_tickets(db, Ticket, rng, proj_rows, leaves, user_pools, tickets)

    print(f"\nDone. Shared login password for all loadtest_* users: {password!r}")
    print("Example usernames: loadtest_technician_1, loadtest_supervisor_1, loadtest_admin_1")


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--users', type=int, default=None, help='Total User rows (env LOADTEST_USERS, default 200)')
    parser.add_argument('--tickets', type=int, default=None, help='Total Ticket rows (env LOADTEST_TICKETS, default 3000)')
    parser.add_argument('--projects', type=int, default=None, help='TicketProject rows (env LOADTEST_PROJECTS, default 8)')
    parser.add_argument('--properties-per-project', type=int, default=None, dest='properties_per_project')
    parser.add_argument('--zones-per-property', type=int, default=None, dest='zones_per_property')
    parser.add_argument('--subzones-per-zone', type=int, default=None, dest='subzones_per_zone')
    parser.add_argument('--units-per-subzone', type=int, default=None, dest='units_per_subzone')
    parser.add_argument('--password', type=str, default=None, help='Shared password for all seeded users')
    parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducible data')
    args = parser.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from Injaaz import create_app
    app = create_app()
    with app.app_context():
        seed_load_test_data(
            users=args.users, tickets=args.tickets, projects=args.projects,
            properties_per_project=args.properties_per_project,
            zones_per_property=args.zones_per_property,
            subzones_per_zone=args.subzones_per_zone,
            units_per_subzone=args.units_per_subzone,
            password=args.password, seed=args.seed,
        )


if __name__ == '__main__':
    main()
