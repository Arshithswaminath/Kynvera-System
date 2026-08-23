"""Idempotent reference/demo data bootstrap for local + Render startup.

Runs only when tables are empty (or demo accounts missing). Safe to re-run.
Disable with AUTO_SEED_DEMO_DATA=0.
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
        'sample_fill': 'skipped',
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

    # Demo supervisors / technicians (needed for assignment workflows)
    try:
        has_demo = User.query.filter_by(username='demo_sup_alpha').first() is not None
        has_teams = TicketSupervisorTeam.query.count() > 0
        if not has_demo or not has_teams:
            from scripts.seed_supervisors_teams import seed_supervisors_teams
            result = seed_supervisors_teams()
            summary['teams'] = (
                f'seeded (created_sup={len(result["created_supervisors"])}, '
                f'created_tech={len(result["created_technicians"])})'
            )
            logger.info('Seeded demo supervisor/technician teams: %s', summary['teams'])
        else:
            summary['teams'] = 'already_present'
    except Exception as exc:
        summary['teams'] = f'error: {exc}'
        logger.warning('Supervisor/team seed skipped: %s', exc)

    # Local only — fill remaining models so every dashboard has sample rows.
    flask_env = os.environ.get('FLASK_ENV', 'development').strip().lower()
    testing = os.environ.get('TESTING', '').strip().lower() in ('1', 'true', 'yes')
    if flask_env in ('development', 'dev', '') and not testing:
        try:
            from scripts.seed_all_sample_data import seed_all_sample_data
            seed_all_sample_data()
            summary['sample_fill'] = 'seeded'
            logger.info('Seeded local sample rows across remaining models')
        except Exception as exc:
            summary['sample_fill'] = f'error: {exc}'
            logger.warning('Local sample-data fill skipped: %s', exc)

    return summary
