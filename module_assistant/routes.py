"""
Injaaz Live Assistant API routes.
"""
import logging

from flask import Blueprint, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models import User, db
from common.error_responses import error_response, success_response
from module_assistant.intents import resolve_intent
from module_assistant.llm import is_llm_enabled
from module_assistant.responses import (
    compose_change_password,
    compose_contact_admin,
    compose_find_document,
    compose_greeting,
    compose_module_help,
    compose_my_drafts,
    compose_my_inspections,
    compose_my_last_leave,
    compose_my_profile,
    compose_my_submissions,
    compose_pending_count,
    compose_procurement_summary,
    compose_ticket_summary,
    compose_fm_failures_by_building,
    compose_fm_critical_assets,
    compose_fm_cost_trend,
    compose_fm_maintenance_report,
    compose_fallback,
    _base_payload,
)
from module_assistant.tools import (
    get_my_inspections_summary,
    get_my_leave_history,
    get_my_profile,
    get_my_submissions_summary,
    get_pending_summary,
    get_procurement_summary,
    get_ticket_summary,
    get_fm_failures_by_building,
    get_fm_critical_assets,
    get_fm_cost_trend,
    get_fm_maintenance_report_hint,
    search_documents,
)

logger = logging.getLogger(__name__)

assistant_bp = Blueprint('assistant_bp', __name__, url_prefix='/api/assistant')

# Live user data — always use structured tools (accurate counts, links, cards).
LIVE_DATA_INTENTS = {
    'pending_count', 'my_submissions', 'my_drafts', 'my_last_leave',
    'find_document', 'change_password', 'contact_admin',
    'procurement_data', 'my_tickets', 'my_inspections', 'my_profile',
    'fm_failures_by_building', 'fm_critical_assets', 'fm_cost_trend',
    'fm_maintenance_report', 'fm_portfolio_forecast',
}


def _current_user():
    user_id = get_jwt_identity()
    if not user_id:
        return None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = user_id
    return db.session.get(User, uid)


def _intent_chat(user, message: str) -> dict:
    """Keyword + live-data path used when the LLM is off."""
    intent_result = resolve_intent(message)
    intent = intent_result.intent
    entities = intent_result.entities or {}

    help_intents = {
        'module_help', 'ticketing_help', 'inspection_help', 'procurement_help',
        'qhsi_help', 'mmr_help', 'bd_help', 'hr_form_help', 'workflow_help', 'profile_help',
    }

    if intent in LIVE_DATA_INTENTS:
        if intent == 'pending_count':
            payload = compose_pending_count(get_pending_summary(user))
        elif intent == 'my_submissions':
            payload = compose_my_submissions(get_my_submissions_summary(user))
        elif intent == 'my_drafts':
            payload = compose_my_drafts(get_my_submissions_summary(user))
        elif intent == 'my_last_leave':
            payload = compose_my_last_leave(
                get_my_leave_history(
                    user,
                    leave_type_filter=entities.get('leave_type'),
                )
            )
        elif intent == 'find_document':
            query = entities.get('document_query') or message
            payload = compose_find_document(search_documents(user, query))
        elif intent == 'change_password':
            payload = compose_change_password()
        elif intent == 'procurement_data':
            payload = compose_procurement_summary(get_procurement_summary(user))
        elif intent == 'my_tickets':
            payload = compose_ticket_summary(get_ticket_summary(user))
        elif intent == 'fm_failures_by_building':
            payload = compose_fm_failures_by_building(get_fm_failures_by_building(user))
        elif intent == 'fm_critical_assets':
            payload = compose_fm_critical_assets(get_fm_critical_assets(user))
        elif intent == 'fm_cost_trend':
            payload = compose_fm_cost_trend(get_fm_cost_trend(user), user=user)
        elif intent == 'fm_maintenance_report':
            payload = compose_fm_maintenance_report(get_fm_maintenance_report_hint(user))
        elif intent == 'fm_portfolio_forecast':
            from module_assistant.responses import compose_fm_portfolio_forecast
            from app.models import PortfolioForecast
            row = PortfolioForecast.query.order_by(PortfolioForecast.created_at.desc()).first()
            payload = compose_fm_portfolio_forecast(row.to_dict() if row else None)
        elif intent == 'my_inspections':
            payload = compose_my_inspections(get_my_inspections_summary(user))
        elif intent == 'my_profile':
            payload = compose_my_profile(get_my_profile(user, person_name=entities.get('person_name')))
        else:
            payload = compose_contact_admin()
    elif intent == 'greeting':
        payload = compose_greeting(user)
    elif intent in help_intents:
        payload = compose_module_help(entities.get('help_query') or message, intent=intent)
    else:
        payload = compose_fallback(message)

    payload['confidence'] = round(intent_result.confidence, 2)
    return payload


@assistant_bp.route('/chat', methods=['POST'])
@jwt_required()
def chat():
    """Process a user message and return a structured assistant response."""
    try:
        user = _current_user()
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(force=True, silent=True) or {}
        message = (data.get('message') or '').strip()
        composer = data.get('composer') if isinstance(data.get('composer'), dict) else None
        if not message and not composer:
            return error_response('Message is required', status_code=400, error_code='VALIDATION_ERROR')
        if not message:
            message = 'Please use these details.'

        if composer:
            from module_assistant.actions import propose_from_composer
            payload = propose_from_composer(user, composer)
            payload.setdefault('confidence', 1.0)
            return success_response(payload)

        if is_llm_enabled():
            from module_assistant.agent import run_agent
            from module_assistant.llm import StructuredLLMError
            try:
                payload = run_agent(user, message)
                payload.setdefault('confidence', 1.0)
                return success_response(payload)
            except StructuredLLMError as exc:
                logger.warning('Agent LLM unavailable, using intent fallback: %s', exc)

        payload = _intent_chat(user, message)
        return success_response(payload)

    except Exception as e:
        logger.error('Assistant chat error: %s', e, exc_info=True)
        return error_response('Assistant is temporarily unavailable', status_code=500, error_code='INTERNAL_ERROR')


@assistant_bp.route('/confirm', methods=['POST'])
@jwt_required()
def confirm_action():
    """Execute a pending write after the user taps Confirm."""
    try:
        user = _current_user()
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(force=True, silent=True) or {}
        action_id = data.get('action_id')
        if action_id is None:
            return error_response('action_id is required', status_code=400, error_code='VALIDATION_ERROR')

        from module_assistant.actions import execute_pending, get_owned_pending

        try:
            row = get_owned_pending(action_id, user)
        except LookupError:
            return error_response('Action not found', status_code=404, error_code='NOT_FOUND')
        except PermissionError:
            return error_response('You cannot confirm this action', status_code=403, error_code='FORBIDDEN')
        except ValueError:
            return error_response('Invalid action_id', status_code=400, error_code='VALIDATION_ERROR')

        result = execute_pending(row, user)
        if not result.get('ok'):
            return error_response(result.get('error') or 'Could not complete that action', status_code=400)

        payload = _base_payload(
            'action_done',
            result.get('message') or 'Done.',
            actions=result.get('actions') or [],
            suggestions=['How many pending forms?', 'My last leave', 'My tickets'],
        )
        payload['confidence'] = 1.0
        return success_response(payload)
    except Exception as e:
        logger.error('Assistant confirm error: %s', e, exc_info=True)
        return error_response('Could not confirm that action', status_code=500, error_code='INTERNAL_ERROR')


@assistant_bp.route('/cancel', methods=['POST'])
@jwt_required()
def cancel_action():
    """Discard a pending write proposal."""
    try:
        user = _current_user()
        if not user:
            return error_response('User not found', status_code=404, error_code='NOT_FOUND')

        data = request.get_json(force=True, silent=True) or {}
        action_id = data.get('action_id')
        if action_id is None:
            return error_response('action_id is required', status_code=400, error_code='VALIDATION_ERROR')

        from module_assistant.actions import cancel_pending, get_owned_pending

        try:
            row = get_owned_pending(action_id, user)
        except LookupError:
            return error_response('Action not found', status_code=404, error_code='NOT_FOUND')
        except PermissionError:
            return error_response('You cannot cancel this action', status_code=403, error_code='FORBIDDEN')
        except ValueError:
            return error_response('Invalid action_id', status_code=400, error_code='VALIDATION_ERROR')

        result = cancel_pending(row)
        if not result.get('ok'):
            return error_response(result.get('error') or 'Could not cancel', status_code=400)

        payload = _base_payload(
            'action_cancelled',
            result.get('message') or 'Cancelled.',
            suggestions=['Create a ticket draft', 'Save a leave draft', 'My last leave'],
        )
        payload['confidence'] = 1.0
        return success_response(payload)
    except Exception as e:
        logger.error('Assistant cancel error: %s', e, exc_info=True)
        return error_response('Could not cancel that action', status_code=500, error_code='INTERNAL_ERROR')
