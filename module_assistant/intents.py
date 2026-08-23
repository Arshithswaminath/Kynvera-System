"""
Intent router for the Kynvera assistant (pattern + keyword scoring, no LLM).
"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntentResult:
    intent: str
    confidence: float
    entities: dict = field(default_factory=dict)


_INTENT_PATTERNS = {
    'greeting': [
        r'\b(hi|hello|hey|good\s+(morning|afternoon|evening))\b',
        r'\bhelp\s*me\b',
        r'^help$',
    ],
    'pending_count': [
        r'\bpending\b',
        r'\bawaiting\s+(my\s+)?review\b',
        r'\bhow\s+many\s+(forms?|submissions?)\b.*\b(pending|review|wait)',
        r'\b(pending|waiting)\s+(forms?|submissions?|reviews?)\b',
        r'\bforms?\s+(to|for)\s+review\b',
    ],
    'my_submissions': [
        r'\bmy\s+(submitted\s+)?forms?\b',
        r'\bmy\s+requests?\b',
        r'\bsubmitted\s+forms?\b',
        r'\bforms?\s+i\s+submitted\b',
        r'\bmy\s+submissions?\b',
    ],
    'my_drafts': [
        r'\bmy\s+drafts?\b',
        r'\bunfinished\s+forms?\b',
        r'\bsaved\s+drafts?\b',
        r'\bdraft\s+forms?\b',
    ],
    'my_last_leave': [
        r'\blast\s+leave\b',
        r'\bwhen\s+(did\s+)?i\s+(take|took)\s+(my\s+)?(last\s+)?leave\b',
        r'\bmy\s+leave\s+history\b',
        r'\b(annual|sick)\s+leave\b.*\b(when|last|recent)\b',
        r'\bwhen\s+was\s+my\s+(last\s+)?(vacation|holiday|leave)\b',
    ],
    'find_document': [
        r'\b(get|find|open|download|show|fetch)\b.*\b(document|doc|policy|manual|file)\b',
        r'\b(document|policy|manual)\b.*\b(get|find|download|open)\b',
        r'\bdochub\b',
        r'\bcan\s+i\s+get\b.*\b(document|policy|manual|file)\b',
    ],
    'change_password': [
        r'\bchange\s+(my\s+)?password\b',
        r'\breset\s+(my\s+)?password\b',
        r'\bupdate\s+(my\s+)?password\b',
        r'\bpassword\s+(change|reset|update|security)\b',
        r'\bhow\s+(do\s+i|to)\s+change\s+my\s+password\b',
    ],
    'procurement_data': [
        r'\bhow\s+many\s+materials?\b',
        r'\bmy\s+materials?\b',
        r'\bmaterial\s+count\b',
        r'\bwhat\s+materials?\s+(do\s+i|have\s+i|i\s+have)\b',
        r'\blist\s+(my\s+)?materials?\b',
        r'\bmaterials?\s+i\s+have\b',
        r'\bhow\s+many\s+properties\b',
        r'\bmy\s+properties\b',
        r'\bin\s+(the\s+)?procurement\b',
    ],
    'my_tickets': [
        r'\bmy\s+(open\s+)?tickets?\b',
        r'\bmy\s+work\s+orders?\b',
        r'\bhow\s+many\s+tickets?\b',
        r'\bopen\s+tickets?\b',
        r'\btickets?\s+i\s+(have|raised|created|opened)\b',
        r'\bmy\s+ticket\s+status\b',
    ],
    'fm_failures_by_building': [
        r'\bwhich\s+building\b.*\b(most\s+)?(failures?|tickets?|work\s*orders?)\b',
        r'\b(most|highest)\s+(failures?|tickets?)\b',
        r'\bfailures?\s+by\s+building\b',
        r'\bbuilding\s+with\s+the\s+most\b',
        r'\bwhich\s+propert(y|ies)\s+ha(s|ve)\s+the\s+most\b',
    ],
    'fm_critical_assets': [
        r'\bcritical\s+assets?\b',
        r'\bshow\s+(all\s+)?critical\s+assets?\b',
        r'\bassets?\s+(in\s+)?critical\b',
        r'\blow\s+health\s+assets?\b',
        r'\bunhealthy\s+assets?\b',
    ],
    'fm_cost_trend': [
        r'\bwhy\s+did\s+(maintenance\s+)?costs?\s+increase\b',
        r'\bmaintenance\s+costs?\s+(this\s+)?month\b',
        r'\bcost\s+(trend|increase|up)\b',
        r'\bwhy\s+(are|were)\s+(maintenance\s+)?costs?\s+(up|high|rising)\b',
        r'\bbudget\s+utilization\b',
    ],
    'fm_maintenance_report': [
        r'\bgenerate\s+.*maintenance\s+report\b',
        r'\bmaintenance\s+report\s+(for\s+)?(this\s+)?month\b',
        r'\bmonthly\s+maintenance\s+report\b',
        r'\b(create|make|open)\s+.*\bmmr\b',
    ],
    'fm_portfolio_forecast': [
        r'\bportfolio\s+forecast\b',
        r'\bforecast\s+(budget|failures?|spare)\b',
        r'\bbudget\s+forecast\b',
        r'\bpredict\s+(failures?|spare\s+parts?|budget)\b',
    ],
    'my_inspections': [
        r'\bmy\s+inspections?\b',
        r'\bmy\s+(hvac|civil|cleaning)\s+(forms?|inspections?|reports?)\b',
        r'\bmy\s+site\s+visits?\b',
        r'\bmy\s+inspection\s+submissions?\b',
        r'\bhow\s+many\s+(hvac|civil|cleaning|inspection)\s+(forms?|submissions?)\b',
    ],
    'ticketing_help': [
        r'\b(work\s*order|ticket)s?\b',
        r'\bservice\s+request\b',
        r'\braise\s+a\s+(ticket|work\s*order)\b',
    ],
    'inspection_help': [
        r'\b(hvac|mep|civil|cleaning)\b',
        r'\binspection\s+(form|report|site|visit)\b',
        r'\bsite\s+(visit|inspection)\b',
        r'\bstart\s+an?\s+inspection\b',
    ],
    'procurement_help': [
        r'\bprocurement\b',
        r'\bmaterial\s+(list|catalog)\b',
        r'\bpricing\b',
        r'\b(register|registered)\s+propert(y|ies)\b',
    ],
    'qhsi_help': [
        r'\bqhsi\b',
        r'\bqhse\b',
        r'\bstaff\s+compliance\b',
        r'\btraining\s+(booking|session|meeting)\b',
        r'\b(uniform|ppe|safety\s+kit)\b',
    ],
    'mmr_help': [
        r'\bmmr\b',
        r'\bmonthly\s+(maintenance\s+)?report\b',
        r'\bchargeable\b',
        r'\breport\s+(schedule|generation)\b',
    ],
    'bd_help': [
        r'\bbusiness\s+development\b',
        r'\bbd\s+(module|project|pipeline|email)\b',
        r'\bpipeline\b',
        r'\b(deals?|leads?|contacts?)\b',
    ],
    'hr_form_help': [
        r'\b(termination|asset|visa|passport|grievance|appraisal|interview|clearance|commencement|contract\s+renewal|duty\s+resumption|long\s+vacation)\b',
        r'\bhr\s+(form|module)\b',
        r'\bhow\s+(do\s+i|to)\s+(submit|apply\s+for|fill|complete)\b.*\bform\b',
    ],
    'workflow_help': [
        r'\bwho\s+(approves?|reviews?|signs?)\b',
        r'\bapproval\s+(chain|flow|process|workflow)\b',
        r'\bwhat\s+happens\s+(after|when)\s+i\s+submit\b',
        r'\b(rejected|rejection)\b',
    ],
    'my_profile': [
        r'\bwhen\s+(did\s+i|i)\s+(join|joined|start|started)\b',
        r'\bwhen\s+(was\s+)?my\s+(join|start|joining|employment)\s+(date|day)?\b',
        r'\bmy\s+(join|joining|start|employment|commencement)\s+date\b',
        r'\bhow\s+long\s+(have\s+i|i\s+have)\s+(been|worked|working)\b',
        r'\bmy\s+tenure\b',
        r'\bmy\s+(job\s+)?title\b',
        r'\bmy\s+(designation|position|role)\b',
        r'\bmy\s+leave\s+balance\b',
        r'\bhow\s+many\s+(annual\s+)?leave\s+days?\b',
        r'\bmy\s+manager\b',
        r'\bwho\s+is\s+my\s+manager\b',
        r'\bmy\s+(assigned\s+)?project\b',
        r'\bmy\s+(phone|contact)\b',
        r'\bmy\s+email\b',
        r'\btell\s+me\s+about\s+my(self|self\b|\s+profile)?\b',
        r'\bwho\s+am\s+i\b',
    ],
    'profile_help': [
        r'\bupdate\s+(my\s+)?profile\b',
        r'\b(set|change|add)\s+(my\s+)?signature\b',
        r'\bdefault\s+signature\b',
        r'\bmy\s+(profile|account)\b',
    ],
    'contact_admin': [
        r'\b(talk|speak|connect)\s+to\s+(a\s+)?(person|human|someone|admin|support)\b',
        r'\breport\s+(a\s+)?(problem|issue|bug)\b',
        r'\bcontact\s+(admin|support|it)\b',
        r'\bneed\s+help\s+from\s+(a\s+)?(person|human|someone)\b',
    ],
    'module_help': [
        r'\bhow\s+(do\s+i|to)\s+(submit|apply|create|start)\b',
        r'\bwhere\s+(is|can\s+i)\b.*\b(hr|inspection|procurement|ticket|leave)\b',
        r'\bhow\s+does\b.*\b(work|module|workflow)\b',
        r'\bwhat\s+is\s+injaaz\b',
        r'\bwhat\s+(modules?|features?)\b',
    ],
}

_INTENT_KEYWORDS = {
    'greeting': {'hi', 'hello', 'hey', 'help', 'start'},
    'pending_count': {'pending', 'review', 'awaiting', 'waiting', 'count', 'many'},
    'my_submissions': {'submitted', 'requests', 'submissions'},
    'my_drafts': {'draft', 'drafts', 'unfinished', 'saved'},
    'my_last_leave': {'leave', 'vacation', 'holiday', 'annual', 'sick', 'last'},
    'find_document': {'document', 'doc', 'policy', 'manual', 'download', 'dochub', 'file'},
    'change_password': {'password', 'reset', 'security'},
    'procurement_data': {'materials', 'material', 'properties', 'property', 'count', 'many', 'list', 'procurement', 'have'},
    'my_tickets': {'tickets', 'ticket', 'workorders', 'open', 'raised', 'work', 'orders'},
    'fm_failures_by_building': {'building', 'failures', 'failure', 'most', 'property', 'tickets'},
    'fm_critical_assets': {'critical', 'assets', 'asset', 'health', 'unhealthy'},
    'fm_cost_trend': {'cost', 'costs', 'maintenance', 'increase', 'budget', 'trend', 'month'},
    'fm_maintenance_report': {'maintenance', 'report', 'generate', 'monthly', 'mmr'},
    'fm_portfolio_forecast': {'forecast', 'budget', 'failures', 'spare', 'parts', 'portfolio', 'predict'},
    'my_inspections': {'inspections', 'inspection', 'hvac', 'civil', 'cleaning', 'site', 'visits'},
    'ticketing_help': {'ticket', 'tickets', 'ticketing', 'workorder', 'work', 'order', 'service'},
    'inspection_help': {'inspection', 'hvac', 'mep', 'civil', 'cleaning', 'site', 'visit'},
    'procurement_help': {'procurement', 'material', 'materials', 'pricing', 'property', 'properties'},
    'qhsi_help': {'qhsi', 'qhse', 'compliance', 'training', 'uniform', 'ppe', 'safety'},
    'mmr_help': {'mmr', 'monthly', 'report', 'chargeable', 'schedule'},
    'bd_help': {'business', 'development', 'pipeline', 'deals', 'leads', 'contacts'},
    'hr_form_help': {'termination', 'asset', 'visa', 'passport', 'grievance', 'appraisal',
                     'interview', 'clearance', 'commencement', 'vacation'},
    'workflow_help': {'approves', 'approval', 'reviews', 'chain', 'rejected', 'rejection', 'signs'},
    'my_profile': {'join', 'joined', 'tenure', 'employment', 'title', 'designation', 'balance', 'manager', 'project', 'email', 'phone', 'started', 'position', 'myself'},
    'profile_help': {'profile', 'signature', 'account'},
    'contact_admin': {'person', 'human', 'someone', 'admin', 'support', 'problem', 'issue', 'bug'},
    'module_help': {'how', 'submit', 'where', 'modules', 'features'},
}

_STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'i', 'me',
    'my', 'we', 'our', 'you', 'your', 'it', 'its', 'this', 'that', 'there',
    'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how', 'of',
    'at', 'by', 'for', 'with', 'about', 'into', 'through', 'during', 'to',
    'from', 'in', 'on', 'and', 'or', 'but', 'if', 'so', 'as', 'any',
}


def _tokenize(text: str) -> set:
    return {t for t in re.findall(r'[a-z0-9]+', (text or '').lower()) if t not in _STOPWORDS and len(t) > 1}


def _extract_document_query(message: str) -> Optional[str]:
    m = (message or '').strip()
    patterns = [
        r'(?:get|find|open|download|show|fetch)\s+(?:me\s+)?(?:the\s+)?(.+?)(?:\s+document|\s+policy|\s+manual|\s+file)?\s*$',
        r'(?:document|policy|manual|file)\s+(?:called|named|titled)\s+(.+)$',
        r'can\s+i\s+get\s+(?:the\s+)?(.+?)(?:\s+document|\s+policy|\s+manual)?\s*$',
    ]
    for pat in patterns:
        match = re.search(pat, m, re.IGNORECASE)
        if match:
            q = match.group(1).strip(' ?.,!')
            if q and q.lower() not in ('a', 'this', 'that', 'it'):
                return q
    return None


def _extract_person_name(message: str) -> Optional[str]:
    """Extract a person's name from a profile query, e.g. 'when did Arshith join?' → 'Arshith'."""
    patterns = [
        r'\bwhen\s+(?:did\s+)?(\w+)\s+(?:join|start|joined|started)\b',
        r'\bwhen\s+(?:was\s+)?(\w+)(?:\'s)?\s+(?:join|start|employment|commencement)\s+date\b',
        r'\b(\w+)(?:\'s)?\s+(?:join|joining|start|tenure|employment)\s+date\b',
        r'\bwho\s+is\s+(\w+)(?:\'s)?\s+manager\b',
        r'\b(\w+)(?:\'s)?\s+(?:profile|job\s+title|designation|leave\s+balance)\b',
        r'\btell\s+me\s+about\s+(\w+)\b',
    ]
    skip = {
        'i', 'my', 'me', 'we', 'our', 'you', 'your', 'he', 'she', 'they', 'their',
        'the', 'a', 'an', 'this', 'that', 'it', 'when', 'who', 'what', 'where',
        'did', 'does', 'has', 'was', 'tell', 'show', 'get',
    }
    for pat in patterns:
        m = re.search(pat, message, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if name.lower() not in skip:
                return name
    return None


def _extract_leave_type(message: str) -> Optional[str]:
    m = (message or '').lower()
    for lt in ('annual', 'sick', 'unpaid', 'compassionate', 'study', 'hajj'):
        if lt in m:
            return lt
    return None


def resolve_intent(message: str) -> IntentResult:
    """Score message against intent patterns; return best match."""
    text = (message or '').strip()
    if not text:
        return IntentResult('fallback', 0.0)

    lower = text.lower()
    tokens = _tokenize(lower)
    scores: dict[str, float] = {}

    for intent, patterns in _INTENT_PATTERNS.items():
        score = 0.0
        for pat in patterns:
            if re.search(pat, lower, re.IGNORECASE):
                score += 2.0
        kw = _INTENT_KEYWORDS.get(intent, set())
        overlap = len(tokens & kw)
        if overlap:
            score += overlap * 0.5
        if score > 0:
            scores[intent] = score

    if not scores:
        return IntentResult('fallback', 0.0, {'raw_query': text})

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]
    total = sum(scores.values()) or 1.0
    confidence = min(1.0, best_score / total)

    entities = {'raw_query': text}
    if best_intent == 'my_profile':
        name = _extract_person_name(text)
        if name:
            entities['person_name'] = name
    if best_intent == 'find_document':
        q = _extract_document_query(text)
        if q:
            entities['document_query'] = q
        else:
            entities['document_query'] = text
    if best_intent == 'my_last_leave':
        lt = _extract_leave_type(text)
        if lt:
            entities['leave_type'] = lt

    # All help-style intents carry the raw query so the merged knowledge brain can answer.
    _HELP_INTENTS = {
        'module_help', 'ticketing_help', 'inspection_help', 'procurement_help',
        'qhsi_help', 'mmr_help', 'bd_help', 'hr_form_help', 'workflow_help', 'profile_help',
    }
    if best_intent in _HELP_INTENTS:
        entities['help_query'] = text

    # Short greetings should not lose to weak keyword overlap elsewhere
    if lower in ('hi', 'hello', 'hey', 'help'):
        return IntentResult('greeting', 1.0, entities)

    return IntentResult(best_intent, confidence, entities)
