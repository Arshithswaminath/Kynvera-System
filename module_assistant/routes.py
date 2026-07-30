"""
Kynvera Live Assistant API routes.
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
    compose_llm_chat,
    compose_module_help,
    compose_my_drafts,
    compose_my_inspections,
    compose_my_last_leave,
    compose_my_profile,
    compose_my_submissions,
    compose_pending_count,
    compose_procurement_summary,
    compose_ticket_summary,
    compose_fallback,
)
from module_assistant.tools import (
    get_my_inspections_summary,
    get_my_leave_history,
    get_my_profile,
    get_my_submissions_summary,
    get_pending_summary,
    get_procurement_summary,
    get_ticket_summary,
    search_documents,
)

logger = logging.getLogger(__name__)

assistant_bp = Blueprint('assistant_bp', __name__, url_prefix='/api/assistant')

# Live user data — always use structured tools (accurate counts, links, cards).
LIVE_DATA_INTENTS = {
    'pending_count', 'my_submissions', 'my_drafts', 'my_last_leave',
    'find_document', 'change_password', 'contact_admin',
    'procurement_data', 'my_tickets', 'my_inspections', 'my_profile',
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
        if not message:
            return error_response('Message is required', status_code=400, error_code='VALIDATION_ERROR')

        intent_result = resolve_intent(message)
        intent = intent_result.intent
        entities = intent_result.entities or {}

        help_intents = {
            'module_help', 'ticketing_help', 'inspection_help', 'procurement_help',
            'mmr_help', 'bd_help', 'hr_form_help', 'workflow_help', 'profile_help',
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
            elif intent == 'my_inspections':
                payload = compose_my_inspections(get_my_inspections_summary(user))
            elif intent == 'my_profile':
                payload = compose_my_profile(get_my_profile(user, person_name=entities.get('person_name')))
            else:
                payload = compose_contact_admin()
        elif is_llm_enabled():
            payload = compose_llm_chat(message, user, intent='chat')
        elif intent == 'greeting':
            payload = compose_greeting(user)
        elif intent in help_intents:
            payload = compose_module_help(entities.get('help_query') or message, intent=intent)
        else:
            payload = compose_fallback(message)

        payload['confidence'] = round(intent_result.confidence, 2)
        return success_response(payload)

    except Exception as e:
        logger.error('Assistant chat error: %s', e, exc_info=True)
        return error_response('Assistant is temporarily unavailable', status_code=500, error_code='INTERNAL_ERROR')
