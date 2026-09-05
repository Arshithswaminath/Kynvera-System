"""Idempotent reference bootstrap for local + Render startup.

Runs only when tables are empty (or demo accounts missing). Safe to re-run.
Disable with AUTO_SEED_DEMO_DATA=0.

Does NOT recreate demo supervisor/technician logins after you delete them.
Does NOT load sample HR / hiring / leave / manpower rows. Those come back
on every restart if seeded here, which overwrites a user deleting them.
Fill dashboards only when asked:

  ./venv/bin/python scripts/seed_all_sample_data.py
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _auto_seed_enabled() -> bool:
    return os.environ.get('AUTO_SEED_DEMO_DATA', '1').strip().lower() not in (
        '0', 'false', 'no', 'off',
    )


def bootstrap_demo_data() -> dict:
    """Seed ticketing reference data, FM assets, and demo teams when empty.

    Must be called inside an application context after schema ensure + admin.
    """
    summary = {
        'enabled': _auto_seed_enabled(),
        'ticketing': 'skipped',
        'fm_assets': 'skipped',
        'teams': 'skipped',
        'sample_fill': 'skipped',  # never auto; opt-in via scripts/seed_all_sample_data.py
    }
    if not summary['enabled']:
        logger.info('AUTO_SEED_DEMO_DATA disabled — skipping reference/demo seeds')
        return summary

    from app.models import Asset, TicketProject, TicketSupervisorTeam, User

    # Ticketing projects / locations / title templates
    try:
        if TicketProject.query.count() == 0:
            from scripts.seed_ticketing_data import seed_ticketing_data
            seed_ticketing_data()
            summary['ticketing'] = f'seeded ({TicketProject.query.count()} projects)'
            logger.info('Seeded ticketing reference data: %s', summary['ticketing'])
        else:
            summary['ticketing'] = 'already_present'
    except Exception as exc:
        summary['ticketing'] = f'error: {exc}'
        logger.warning('Ticketing seed skipped: %s', exc)

    # FM assets / predictions / floor plans / sample asset-linked tickets
    try:
        if Asset.query.count() == 0:
            from scripts.seed_fm_assets import seed as seed_fm_assets
            seed_fm_assets()
            summary['fm_assets'] = f'seeded ({Asset.query.count()} assets)'
            logger.info('Seeded FM assets sample data: %s', summary['fm_assets'])
        else:
            summary['fm_assets'] = 'already_present'
    except Exception as exc:
        summary['fm_assets'] = f'error: {exc}'
        logger.warning('FM assets seed skipped: %s', exc)

    # Demo supervisors / technicians — first boot only. If the operator deleted
    # those accounts, missing usernames must not bring them back on restart.
    try:
        demo_usernames = (
            'demo_sup_alpha',
            'demo_sup_bravo',
            'demo_tech_alpha_1',
            'demo_tech_bravo_1',
        )
        has_demo = User.query.filter(User.username.in_(demo_usernames)).count() > 0
        has_teams = TicketSupervisorTeam.query.count() > 0
        other_people = User.query.filter(~User.username.in_(('email_intake',))).count()
        if has_demo:
            summary['teams'] = 'already_present'
        elif other_people <= 1 and not has_teams:
            from scripts.seed_supervisors_teams import seed_supervisors_teams
            result = seed_supervisors_teams()
            summary['teams'] = (
                f'seeded (created_sup={len(result["created_supervisors"])}, '
                f'created_tech={len(result["created_technicians"])})'
            )
            logger.info('Seeded demo supervisor/technician teams: %s', summary['teams'])
        else:
            summary['teams'] = 'skipped_removed'
            logger.info(
                'Demo supervisor/technician teams not reseeded '
                '(accounts were removed or the user directory is already in use)'
            )
    except Exception as exc:
        summary['teams'] = f'error: {exc}'
        logger.warning('Supervisor/team seed skipped: %s', exc)

    return summary
