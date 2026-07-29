"""
Response composer — turns intent + tool output into widget-ready JSON.
"""
from module_assistant.knowledge import get_faq_by_id, is_confident_match, search_faqs

DEFAULT_SUGGESTIONS = [
    'How many pending forms?',
    'My last leave',
    'Find a document',
    'Change my password',
]


def _base_payload(intent: str, message: str, **kwargs):
    return {
        'intent': intent,
        'message': message,
        'cards': kwargs.get('cards', []),
        'actions': kwargs.get('actions', []),
        'sources': kwargs.get('sources', []),
        'suggestions': kwargs.get('suggestions', DEFAULT_SUGGESTIONS),
    }


def compose_greeting(user):
    name = (getattr(user, 'full_name', None) or getattr(user, 'username', None) or 'there').split()[0]
    return _base_payload(
        'greeting',
        f"Hello {name}! I'm the Injaaz assistant. Ask me anything — I'm here to help.",
        suggestions=[
            'How many pending forms?',
            'When was my last leave?',
            'Find safety policy',
            'How do I change my password?',
        ],
    )


def compose_pending_count(data):
    if not data.get('can_review'):
        return _base_payload(
            'pending_count',
            "You don't have a reviewer role, so there are no forms awaiting your approval. You can track forms you've submitted instead.",
            actions=[
                {'label': 'My submitted forms', 'href': '/workflow/submitted-forms', 'kind': 'link'},
                {'label': 'HR My Requests', 'href': '/hr/my-requests', 'kind': 'link'},
            ],
            suggestions=['My submitted forms', 'My last leave', 'Change my password'],
        )

    total = data.get('total', 0)
    if total == 0:
        return _base_payload(
            'pending_count',
            "You're all caught up — no forms are waiting for your review right now.",
            cards=[{'type': 'stat', 'label': 'Pending review', 'value': '0'}],
            actions=[{'label': 'Open Pending Review', 'href': '/workflow/pending-reviews', 'kind': 'link'}],
        )

    parts = []
    if data.get('hr'):
        parts.append(f"{data['hr']} HR")
    if data.get('inspection'):
        parts.append(f"{data['inspection']} inspection")
    if data.get('other'):
        parts.append(f"{data['other']} other")
    breakdown = f" ({', '.join(parts)})" if parts else ''

    cards = [
        {'type': 'stat', 'label': 'Pending review', 'value': str(total)},
    ]
    if data.get('hr'):
        cards.append({'type': 'stat', 'label': 'HR', 'value': str(data['hr'])})
    if data.get('inspection'):
        cards.append({'type': 'stat', 'label': 'Inspection', 'value': str(data['inspection'])})

    return _base_payload(
        'pending_count',
        f"You have {total} form{'s' if total != 1 else ''} waiting for your review{breakdown}.",
        cards=cards,
        actions=[{'label': 'Open Pending Review', 'href': '/workflow/pending-reviews', 'kind': 'link'}],
    )


def compose_my_drafts(data):
    drafts = data.get('drafts', 0)
    if not drafts:
        return _base_payload(
            'my_drafts',
            "You don't have any unfinished drafts right now. Forms you save without submitting will show up here.",
            actions=[{'label': 'Submitted forms', 'href': '/workflow/submitted-forms', 'kind': 'link'}],
        )
    return _base_payload(
        'my_drafts',
        f"You have {drafts} draft{'s' if drafts != 1 else ''} saved but not yet submitted. Open them to finish and submit.",
        cards=[{'type': 'stat', 'label': 'Drafts', 'value': str(drafts)}],
        actions=[
            {'label': 'Submitted forms', 'href': '/workflow/submitted-forms', 'kind': 'link'},
            {'label': 'HR My Requests', 'href': '/hr/my-requests', 'kind': 'link'},
        ],
    )


def compose_my_submissions(data):
    total = data.get('total', 0)
    drafts = data.get('drafts', 0)
    in_progress = data.get('in_progress', 0)
    completed = data.get('completed', 0)

    cards = [
        {'type': 'stat', 'label': 'Total submitted', 'value': str(total)},
        {'type': 'stat', 'label': 'In progress', 'value': str(in_progress)},
        {'type': 'stat', 'label': 'Completed', 'value': str(completed)},
    ]
    if drafts:
        cards.append({'type': 'stat', 'label': 'Drafts', 'value': str(drafts)})

    return _base_payload(
        'my_submissions',
        f"You have {total} form{'s' if total != 1 else ''} on your account"
        + (f", including {drafts} draft{'s' if drafts != 1 else ''}" if drafts else '')
        + f". {in_progress} still in progress, {completed} completed.",
        cards=cards,
        actions=[
            {'label': 'Submitted forms', 'href': '/workflow/submitted-forms', 'kind': 'link'},
            {'label': 'HR My Requests', 'href': '/hr/my-requests', 'kind': 'link'},
        ],
    )


def compose_my_last_leave(data):
    if not data.get('has_leave'):
        return _base_payload(
            'my_last_leave',
            "I couldn't find any submitted leave applications on your account. If you recently applied, it may still be a draft.",
            actions=[
                {'label': 'Apply for leave', 'href': '/hr/leave-application-form', 'kind': 'link'},
                {'label': 'HR My Requests', 'href': '/hr/my-requests', 'kind': 'link'},
            ],
        )

    latest = data['entries'][0]
    cards = [{
        'type': 'leave',
        'leave_type': latest.get('leave_type_label', 'Leave'),
        'start_date': latest.get('start_date', '—'),
        'end_date': latest.get('end_date', '—'),
        'status': latest.get('workflow_status', 'submitted'),
        'total_days': str(latest.get('total_days', '')),
        'submission_id': latest.get('submission_id', ''),
    }]

    msg = (
        f"Your most recent leave was {latest.get('leave_type_label', 'leave')}, "
        f"from {latest.get('start_date', '—')} to {latest.get('end_date', '—')} "
        f"({latest.get('workflow_status', 'submitted').replace('_', ' ')})."
    )

    if data.get('count', 0) > 1:
        msg += f" You have {data['count']} leave record{'s' if data['count'] != 1 else ''} on file."

    return _base_payload(
        'my_last_leave',
        msg,
        cards=cards,
        actions=[{'label': 'View HR requests', 'href': '/hr/my-requests', 'kind': 'link'}],
    )


def compose_find_document(data):
    if not data.get('allowed'):
        return _base_payload(
            'find_document',
            "You don't have access to DocHub. Please contact your administrator to request document access.",
            suggestions=['Change my password', 'How many pending forms?', 'My submitted forms'],
        )

    docs = data.get('documents') or []
    query = data.get('query', '')

    if not docs:
        return _base_payload(
            'find_document',
            f"I couldn't find a published document matching \"{query}\". Try a different title or browse DocHub.",
            actions=[{'label': 'Open DocHub', 'href': '/dochub', 'kind': 'link'}],
        )

    cards = []
    actions = []
    for doc in docs[:3]:
        cards.append({
            'type': 'document',
            'id': doc['id'],
            'title': doc['title'],
            'category': doc.get('category', 'Internal'),
            'updated_at': doc.get('updated_at', ''),
            'preview_url': doc.get('preview_url'),
            'download_url': doc.get('download_url'),
        })

    if len(docs) == 1:
        d = docs[0]
        msg = f"Found **{d['title']}** ({d.get('category', 'Internal')})."
    else:
        msg = f"Found {len(docs)} document{'s' if len(docs) != 1 else ''} matching \"{query}\"."

    actions.append({'label': 'Open DocHub', 'href': '/dochub', 'kind': 'link'})

    return _base_payload('find_document', msg.replace('**', ''), cards=cards, actions=actions)


def compose_change_password():
    faq = get_faq_by_id('change_password') or {}
    answer = faq.get('answer') or (
        "Open Profile from the top navigation, go to the Security tab, and click Change password. "
        "Your new password must be at least 8 characters."
    )
    return _base_payload(
        'change_password',
        answer,
        actions=[
            {'label': 'Open Profile → Security', 'href': '#', 'kind': 'profile_security'},
        ],
        sources=[{'title': 'Account security', 'source': 'Injaaz Help'}],
    )


def compose_module_help(query: str, intent: str = 'module_help'):
    matches = search_faqs(query, limit=2)
    if not matches or not is_confident_match(query, matches[0]):
        return compose_contact_admin(unknown=True)

    best = matches[0]
    sources = [{'title': m.get('question', ''), 'source': m.get('source', 'Injaaz Help')} for m in matches]
    msg = best.get('answer', '')
    if len(matches) > 1 and matches[1].get('question') and matches[1].get('score', 0) >= best.get('score', 0) * 0.6:
        msg += f"\n\nRelated: {matches[1].get('question', '')}"

    actions = []
    link = best.get('link') or (get_faq_by_id(best.get('id', '')) or {}).get('link')
    if link:
        actions.append({'label': 'Open in app', 'href': link, 'kind': 'link'})

    return _base_payload(
        intent,
        msg,
        actions=actions,
        sources=sources,
    )


def compose_contact_admin(unknown: bool = False):
    if unknown:
        msg = (
            "I couldn't find an answer for that yet. You can raise a ticket so the team can help, "
            "or an administrator can add this to the knowledge base."
        )
    else:
        msg = (
            "To reach a person, raise a ticket in the Ticketing module and the team will follow up. "
            "For account or access issues, contact your administrator."
        )
    return _base_payload(
        'contact_admin',
        msg,
        actions=[
            {'label': 'Open Ticketing', 'href': '/tickets/', 'kind': 'link'},
        ],
        suggestions=['How many pending forms?', 'Find a document', 'What is Injaaz?'],
    )


def compose_my_profile(data):
    name = data.get('full_name') or 'you'
    is_self = data.get('is_self', True)
    label = 'your' if is_self else f"{name}'s"
    parts = []

    if data.get('employment_start_date'):
        line = f"Join date: {data['employment_start_date']}"
        if data.get('tenure'):
            line += f" ({data['tenure']} with the company)"
        parts.append(line)
    else:
        parts.append("Join date: not set")

    if data.get('job_designation'):
        parts.append(f"Title: {data['job_designation']}")
    elif data.get('designation'):
        parts.append(f"Role: {data['designation'].replace('_', ' ').title()}")

    if data.get('manager'):
        parts.append(f"Reporting to: {data['manager']}")

    if data.get('assigned_project'):
        parts.append(f"Project: {data['assigned_project']}")

    if data.get('annual_leave_days') is not None:
        parts.append(f"Annual leave entitlement: {data['annual_leave_days']} days")

    if data.get('email'):
        parts.append(f"Email: {data['email']}")

    if data.get('phone'):
        parts.append(f"Phone: {data['phone']}")

    msg = f"Here's {label} profile:\n" + "\n".join(f"• {p}" for p in parts)

    actions = [{'label': 'Open Profile', 'href': '#', 'kind': 'profile_security'}] if is_self else []
    return _base_payload(
        'my_profile',
        msg,
        actions=actions,
        suggestions=['My last leave', 'How many pending forms?', 'Find a document'],
    )


def compose_procurement_summary(data):
    if not data.get('has_data'):
        return _base_payload(
            'procurement_data',
            "You haven't submitted any materials or properties in Procurement yet. Head to the Procurement module to add your first entry.",
            actions=[{'label': 'Open Procurement', 'href': '/procurement/', 'kind': 'link'}],
            suggestions=['My tickets', 'My submissions', 'Find a document'],
        )

    mat = data.get('materials_count', 0)
    prop = data.get('properties_count', 0)
    cards = []
    if mat:
        cards.append({'type': 'stat', 'label': 'Materials', 'value': str(mat)})
    if prop:
        cards.append({'type': 'stat', 'label': 'Properties', 'value': str(prop)})

    msg = f"You have {mat} material{'s' if mat != 1 else ''}"
    if prop:
        msg += f" across {prop} propert{'ies' if prop != 1 else 'y'}"
    msg += " in the Procurement module."

    recent = data.get('recent_materials') or []
    if recent:
        names = [r['name'] for r in recent[:3] if r.get('name')]
        if names:
            msg += f" Recent: {', '.join(names)}."

    return _base_payload(
        'procurement_data',
        msg,
        cards=cards,
        actions=[{'label': 'Open Procurement', 'href': '/procurement/', 'kind': 'link'}],
        suggestions=['My tickets', 'How many pending forms?', 'My last leave'],
    )


def compose_ticket_summary(data):
    if not data.get('allowed'):
        return _base_payload(
            'my_tickets',
            "You don't have access to the Ticketing module yet. Ask your administrator to enable it for your account.",
            suggestions=['How many pending forms?', 'Contact admin', 'My last leave'],
        )

    total = data.get('total', 0)
    if total == 0:
        return _base_payload(
            'my_tickets',
            "You haven't raised any tickets yet. Use the Ticketing module to log a work order or service request.",
            actions=[{'label': 'Open Ticketing', 'href': '/tickets/', 'kind': 'link'}],
        )

    open_c = data.get('open', 0)
    in_prog = data.get('in_progress', 0)
    closed_c = data.get('closed', 0)

    cards = [{'type': 'stat', 'label': 'Total tickets', 'value': str(total)}]
    if open_c:
        cards.append({'type': 'stat', 'label': 'Open', 'value': str(open_c)})
    if in_prog:
        cards.append({'type': 'stat', 'label': 'In progress', 'value': str(in_prog)})
    if closed_c:
        cards.append({'type': 'stat', 'label': 'Closed', 'value': str(closed_c)})

    parts = []
    if open_c:
        parts.append(f"{open_c} open")
    if in_prog:
        parts.append(f"{in_prog} in progress")
    if closed_c:
        parts.append(f"{closed_c} closed")

    msg = f"You have {total} ticket{'s' if total != 1 else ''} — {', '.join(parts)}." if parts else f"You have {total} ticket{'s' if total != 1 else ''}."

    return _base_payload(
        'my_tickets',
        msg,
        cards=cards,
        actions=[{'label': 'View my tickets', 'href': '/tickets/list', 'kind': 'link'}],
        suggestions=['Critical assets', 'Which building has the most failures?', 'Why did maintenance costs increase?'],
    )


def compose_fm_failures_by_building(data):
    if not data.get('allowed'):
        return _base_payload(
            'fm_failures_by_building',
            "You need Service Tickets access to view FM failure analytics.",
            suggestions=['My tickets', 'Contact admin'],
        )
    buildings = data.get('buildings') or []
    if not buildings:
        return _base_payload(
            'fm_failures_by_building',
            "No work-order data yet to rank buildings by failures.",
            actions=[{'label': 'Open FM Assets', 'href': '/assets/', 'kind': 'link'}],
        )
    top = buildings[0]
    lines = [f"{b['building']}: {b['failure_count']}" for b in buildings[:8]]
    msg = (
        f"Highest failure volume is {top['building']} with {top['failure_count']} tickets "
        f"(of {data.get('total_tickets', 0)} total). Top buildings:\n- " + '\n- '.join(lines)
    )
    return _base_payload(
        'fm_failures_by_building',
        msg,
        actions=[
            {'label': 'FM Assets dashboard', 'href': '/assets/', 'kind': 'link'},
            {'label': 'Tickets', 'href': '/tickets/', 'kind': 'link'},
        ],
        suggestions=['Show all critical assets', 'Why did maintenance costs increase?'],
    )


def compose_fm_critical_assets(data):
    if not data.get('allowed'):
        return _base_payload(
            'fm_critical_assets',
            "You need Service Tickets access to view critical assets.",
            suggestions=['My tickets', 'Contact admin'],
        )
    assets = data.get('assets') or []
    if not assets:
        return _base_payload(
            'fm_critical_assets',
            "No critical assets right now (status critical or health under 40).",
            actions=[{'label': 'Open FM Assets', 'href': '/assets/', 'kind': 'link'}],
        )
    lines = [
        f"{a['asset_id']} {a['name']} — health {a['health_score'] if a['health_score'] is not None else 'n/a'} ({a['status']})"
        for a in assets[:10]
    ]
    msg = f"Found {data.get('count', len(assets))} critical asset(s):\n- " + '\n- '.join(lines)
    return _base_payload(
        'fm_critical_assets',
        msg,
        actions=[{'label': 'Open FM Assets', 'href': '/assets/list', 'kind': 'link'}],
        suggestions=['Which building has the most failures?', 'Budget utilization'],
    )


def compose_fm_cost_trend(data, user=None, narrate: bool = True):
    if not data.get('allowed'):
        return _base_payload(
            'fm_cost_trend',
            "You need Service Tickets access to view maintenance cost trends.",
            suggestions=['My tickets', 'Contact admin'],
        )
    this_c = data.get('this_month_cost', 0)
    prev_c = data.get('prev_month_cost', 0)
    delta = data.get('delta', 0)
    pct = data.get('delta_pct')
    direction = 'increased' if delta > 0 else ('decreased' if delta < 0 else 'held steady')
    pct_bit = f" ({pct:+.1f}%)" if pct is not None else ''
    facts = (
        f"Ticket-linked costs for {data.get('month_label', 'this month')}: {this_c} "
        f"across {data.get('this_month_tickets', 0)} tickets. "
        f"{data.get('prev_month_label', 'Last month')}: {prev_c} "
        f"({data.get('prev_month_tickets', 0)} tickets). Costs {direction} by {abs(delta)}{pct_bit}. "
        f"Asset registry maintenance total: {data.get('asset_maintenance_total', 0)}; "
        f"purchase total: {data.get('asset_purchase_total', 0)}."
    )

    msg = facts
    if narrate and user is not None:
        try:
            from module_assistant.llm import generate_reply, is_llm_enabled
            if is_llm_enabled():
                narrated = generate_reply(
                    'Explain briefly why maintenance costs may have changed based only on these facts. '
                    'Do not invent causes not supported by the numbers.',
                    [{'title': 'Cost facts', 'source': 'FM analytics', 'text': facts}],
                    user_name=(getattr(user, 'full_name', None) or 'there').split()[0],
                    account_context='',
                )
                if narrated:
                    msg = narrated
        except Exception:
            pass

    cards = [
        {'type': 'stat', 'label': 'This month', 'value': str(this_c)},
        {'type': 'stat', 'label': 'Last month', 'value': str(prev_c)},
        {'type': 'stat', 'label': 'Change', 'value': str(delta)},
    ]
    return _base_payload(
        'fm_cost_trend',
        msg,
        cards=cards,
        actions=[{'label': 'FM Assets KPIs', 'href': '/assets/', 'kind': 'link'}],
        suggestions=['Critical assets', 'Which building has the most failures?'],
    )


def compose_fm_maintenance_report(data):
    if not data.get('allowed'):
        return _base_payload(
            'fm_maintenance_report',
            "You don't have access to maintenance reporting yet.",
            suggestions=['Contact admin'],
        )
    month = data.get('month_label') or 'this month'
    hint = data.get('generate_hint') or (
        f'Use the Monthly Maintenance Report hub to generate the {month} pack.'
    )
    return _base_payload(
        'fm_maintenance_report',
        hint,
        actions=[
            {'label': f'Generate {month} MMR', 'href': data.get('mmr_url') or '/admin/mmr/', 'kind': 'link'},
            {'label': 'FM Executive dashboard', 'href': data.get('executive_url') or '/assets/executive', 'kind': 'link'},
            {'label': 'Tickets', 'href': data.get('tickets_url') or '/tickets/', 'kind': 'link'},
        ],
        suggestions=['Why did maintenance costs increase?', 'Critical assets', 'Portfolio forecast'],
    )


def compose_fm_portfolio_forecast(forecast):
    if not forecast:
        return _base_payload(
            'fm_portfolio_forecast',
            "No portfolio forecast cached yet. Open the FM Executive dashboard and run “Portfolio forecast”.",
            actions=[{'label': 'Executive dashboard', 'href': '/assets/executive', 'kind': 'link'}],
            suggestions=['Critical assets', 'Why did maintenance costs increase?'],
        )
    msg = (
        f"Portfolio forecast ({forecast.get('horizon_days', 90)} days): "
        f"budget {forecast.get('budget_forecast')}, "
        f"failures {forecast.get('failure_count_forecast')}. "
        f"{forecast.get('narrative') or ''}"
    )
    return _base_payload(
        'fm_portfolio_forecast',
        msg,
        cards=[
            {'type': 'stat', 'label': 'Budget forecast', 'value': str(forecast.get('budget_forecast'))},
            {'type': 'stat', 'label': 'Failures', 'value': str(forecast.get('failure_count_forecast'))},
        ],
        actions=[{'label': 'Executive dashboard', 'href': '/assets/executive', 'kind': 'link'}],
        suggestions=['Generate maintenance report', 'Critical assets'],
    )


def compose_my_inspections(data):
    if not data.get('has_data'):
        return _base_payload(
            'my_inspections',
            "You haven't submitted any inspection forms yet. Start one from the Inspection hub.",
            actions=[{'label': 'Open Inspection hub', 'href': '/inspection/', 'kind': 'link'}],
            suggestions=['My submissions', 'How many pending forms?', 'My last leave'],
        )

    total = data.get('total', 0)
    cards = [{'type': 'stat', 'label': 'Total inspections', 'value': str(total)}]
    parts = []
    if data.get('hvac'):
        cards.append({'type': 'stat', 'label': 'HVAC & MEP', 'value': str(data['hvac'])})
        parts.append(f"{data['hvac']} HVAC")
    if data.get('civil'):
        cards.append({'type': 'stat', 'label': 'Civil', 'value': str(data['civil'])})
        parts.append(f"{data['civil']} Civil")
    if data.get('cleaning'):
        cards.append({'type': 'stat', 'label': 'Cleaning', 'value': str(data['cleaning'])})
        parts.append(f"{data['cleaning']} Cleaning")

    breakdown = f" ({', '.join(parts)})" if parts else ''
    msg = f"You have {total} inspection submission{'s' if total != 1 else ''}{breakdown}."

    return _base_payload(
        'my_inspections',
        msg,
        cards=cards,
        actions=[{'label': 'Open Inspection hub', 'href': '/inspection/', 'kind': 'link'}],
        suggestions=['My submissions', 'How many pending forms?', 'My last leave'],
    )


def compose_llm_chat(message: str, user, intent: str = 'llm_chat'):
    """Natural-language reply using LLM + knowledge-base context. Falls back if LLM call fails."""
    from module_assistant.llm import generate_reply
    from module_assistant.rag import retrieve_context
    from module_assistant.tools import get_account_context

    name = (getattr(user, 'full_name', None) or getattr(user, 'username', None) or 'there').split()[0]
    chunks = retrieve_context(message, limit=4, user=user)
    try:
        account_context = get_account_context(user)
    except Exception:
        account_context = ''
    reply = generate_reply(message, chunks, user_name=name, account_context=account_context)

    if not reply:
        if intent == 'greeting':
            return compose_greeting(user)
        return compose_fallback(message)

    sources = [
        {'title': c.get('title', ''), 'source': c.get('source', 'Injaaz Help')}
        for c in chunks[:1]
        if c.get('text')
    ]
    actions = []
    for c in chunks:
        link = c.get('link')
        if link:
            actions.append({'label': 'Open in app', 'href': link, 'kind': 'link'})
            break
    if not actions:
        actions.append({'label': 'Open Ticketing', 'href': '/tickets/', 'kind': 'link'})

    return _base_payload(
        intent if intent != 'llm_chat' else 'chat',
        reply,
        actions=actions,
        sources=sources,
        suggestions=[
            'How many pending forms?',
            'My last leave',
            'Where is Injaaz?',
            'Find a document',
        ],
    )


def compose_fallback(query: str = ''):
    # Always answer from the knowledge base (FAQs + admin records + links) when
    # there is any keyword overlap. Only escalate when nothing matches at all.
    if query:
        matches = search_faqs(query, limit=2)
        if matches and is_confident_match(query, matches[0]):
            return compose_module_help(query, intent='fallback')

    return compose_contact_admin(unknown=True)
