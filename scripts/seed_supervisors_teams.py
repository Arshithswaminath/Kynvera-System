"""Create two demo supervisors with one ticketing technician each (User + roster Technician row).

Usage (from project root):
  python scripts/seed_supervisors_teams.py

Environment:
  SEED_TEAM_PASSWORD   Password for all seeded accounts (default: DemoTech2026!)

Idempotent: re-run updates existing rows and re-activates supervisor team links.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Injaaz import create_app
from app.models import db, User, Technician, TicketSupervisorTeam
from sqlalchemy import inspect, text

PASSWORD = os.environ.get('SEED_TEAM_PASSWORD', 'DemoTech2026!')

TEAMS = (
    ('alpha', 'Demo Supervisor Alpha', 'tech_alpha_1', 'Demo Tech — Team Alpha', 'EMP-DEMO-ALPHA-TECH-01', 'HVAC'),
    ('bravo', 'Demo Supervisor Bravo', 'tech_bravo_1', 'Demo Tech — Team Bravo', 'EMP-DEMO-BRAVO-TECH-01', 'Electrical'),
)


def _ensure_technicians_supervisor_column():
    try:
        inspector = inspect(db.engine)
        if 'technicians' not in inspector.get_table_names():
            db.create_all()
            return
        colnames = {c['name'] for c in inspector.get_columns('technicians')}
        if 'supervisor_user_id' in colnames:
            return
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE technicians ADD COLUMN supervisor_user_id INTEGER'))
    except Exception as exc:
        print(f'Note: could not ensure technicians.supervisor_user_id column: {exc}')


def main():
    app = create_app()
    with app.app_context():
        _ensure_technicians_supervisor_column()
        created_supervisors = []
        created_technicians = []

        for slug, sup_name, tech_slug, tech_full, emp_id, dept in TEAMS:
            uname_sup = f'demo_sup_{slug}'
            sup = User.query.filter_by(username=uname_sup).first()
            if not sup:
                sup = User(
                    username=uname_sup,
                    email=f'{uname_sup}@demo.injaaz.local',
                    full_name=sup_name,
                    role='user',
                    designation='supervisor',
                    is_active=True,
                    access_ticketing=True,
                )
                sup.set_password(PASSWORD)
                db.session.add(sup)
                db.session.flush()
                created_supervisors.append(uname_sup)
            else:
                sup.designation = 'supervisor'
                sup.access_ticketing = True
                sup.is_active = True
                if not sup.full_name:
                    sup.full_name = sup_name

            uname_tech = f'demo_{tech_slug}'
            tech_user = User.query.filter_by(username=uname_tech).first()
            if not tech_user:
                tech_user = User(
                    username=uname_tech,
                    email=f'{uname_tech}@demo.injaaz.local',
                    full_name=tech_full,
                    role='user',
                    designation='technician',
                    is_active=True,
                    access_ticketing=True,
                )
                tech_user.set_password(PASSWORD)
                db.session.add(tech_user)
                db.session.flush()
                created_technicians.append(uname_tech)
            else:
                tech_user.designation = 'technician'
                tech_user.access_ticketing = True
                tech_user.is_active = True
                if not tech_user.full_name:
                    tech_user.full_name = tech_full

            pair = TicketSupervisorTeam.query.filter_by(
                supervisor_id=sup.id, technician_id=tech_user.id,
            ).first()
            if not pair:
                db.session.add(TicketSupervisorTeam(supervisor_id=sup.id, technician_id=tech_user.id))
            else:
                pair.is_active = True

            roster = Technician.query.filter_by(employee_id=emp_id).first()
            if not roster:
                db.session.add(
                    Technician(
                        employee_id=emp_id,
                        full_name=tech_full,
                        designation='Field Technician',
                        department=dept,
                        specialization=None,
                        status='active',
                        supervisor_user_id=sup.id,
                    )
                )
            else:
                roster.supervisor_user_id = sup.id
                roster.full_name = tech_full
                roster.department = dept
                roster.status = 'active'

        db.session.commit()
        print('Seeding finished successfully.')
        print(f'Shared demo password: {PASSWORD}')
        if created_supervisors:
            print(f'Created supervisor account(s): {", ".join(created_supervisors)}')
        if created_technicians:
            print(f'Created technician login(s): {", ".join(created_technicians)}')
        print('Supervisors:', ', '.join(f'demo_sup_{s[0]}' for s in TEAMS))
        print('Technicians:', ', '.join(f'demo_{s[2]}' for s in TEAMS))


if __name__ == '__main__':
    main()
