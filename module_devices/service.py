"""Device Management domain helpers — KPIs, map points, compliance, mutations."""
import logging
import random
from datetime import datetime, date, timezone, timedelta

from sqlalchemy import func, inspect, or_, text

from app.models import db, User, Device, Asset, TicketProperty

logger = logging.getLogger(__name__)

STALE_DAYS = 14
HEALTH_HEALTHY = 80
HEALTH_WARN = 55
VALID_STATUSES = frozenset({'online', 'offline', 'idle', 'update'})
VALID_TYPES = frozenset({'Laptop', 'Desktop', 'Mobile', 'Server', 'Tablet', 'Other'})


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_date(val):
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val).strip()[:10]
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def add_missing_columns(table, extras):
    inspector = inspect(db.engine)
    if table not in inspector.get_table_names():
        return
    existing = {col['name'] for col in inspector.get_columns(table)}
    missing = [(name, typ) for name, typ in extras if name not in existing]
    if not missing:
        return
    with db.engine.begin() as conn:
        for name, typ in missing:
            try:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {typ}'))
                logger.info('Added column %s.%s', table, name)
            except Exception as exc:
                err = str(exc).lower()
                if 'already exists' in err or 'duplicate' in err:
                    logger.info('Column %s.%s already exists', table, name)
                else:
                    logger.warning('Could not add %s.%s: %s', table, name, exc)


def ensure_device_columns(app):
    with app.app_context():
        try:
            db.create_all()
            add_missing_columns('devices', [
                ('building', 'VARCHAR(160)'),
                ('latitude', 'REAL'),
                ('longitude', 'REAL'),
                ('device_comment', 'TEXT'),
                ('asset_owner_name', 'VARCHAR(255)'),
                ('assignment_date', 'DATE'),
            ])
        except Exception as exc:
            logger.warning('Device column ensure: %s', exc)


def next_device_id():
    existing_ids = {row[0] for row in db.session.query(Device.device_id).all()}
    for _ in range(80):
        dev_id = 'DEV-' + str(random.randint(1000, 9999))
        if dev_id not in existing_ids:
            return dev_id
    return 'DEV-' + str(random.randint(10000, 99999))


def is_stale(device, now=None):
    now = now or utcnow()
    if not device.last_active_at:
        return True
    last = device.last_active_at
    if last.tzinfo is not None:
        last = last.replace(tzinfo=None)
    return (now - last) > timedelta(days=STALE_DAYS)


def resolve_user_id(data):
    if data.get('assigned_user_id') not in (None, ''):
        try:
            uid = int(data.get('assigned_user_id'))
        except (TypeError, ValueError):
            uid = None
        if uid and User.query.get(uid):
            return uid
        return None
    email = (data.get('assigned_user_email') or '').strip()
    if not email:
        return None
    user = User.query.filter_by(email=email).first()
    return user.id if user else None


def _parse_coord(data, key):
    if key not in data:
        return 'skip', None
    raw = data.get(key)
    if raw in (None, ''):
        return 'set', None
    try:
        return 'set', float(raw)
    except (TypeError, ValueError):
        return 'skip', None


def apply_device_payload(device, data, *, creating=False):
    """Apply JSON/form fields onto a Device. Returns the device."""
    if 'name' in data or creating:
        name = (data.get('name') or '').strip()
        if name:
            device.name = name
    if 'device_type' in data or creating:
        dtype = (data.get('device_type') or device.device_type or 'Laptop').strip()
        device.device_type = dtype if dtype in VALID_TYPES else (dtype or 'Laptop')
    if 'os' in data or creating:
        device.os = (data.get('os') or device.os or 'Windows 11').strip() or 'Windows 11'
    if 'status' in data:
        status = str(data.get('status') or '').strip().lower()
        if status in VALID_STATUSES:
            device.status = status
    elif creating:
        device.status = 'idle'
    if 'health' in data or creating:
        try:
            health = data.get('health')
            if health in (None, '') and creating:
                device.health = random.randint(80, 100)
            elif health not in (None, ''):
                device.health = max(0, min(100, int(float(health))))
        except (TypeError, ValueError):
            if creating and device.health is None:
                device.health = random.randint(80, 100)
    if any(k in data for k in ('assigned_user_id', 'assigned_user_email')) or creating:
        device.assigned_user_id = resolve_user_id(data)
    if 'serial_or_asset_tag' in data or creating:
        serial = (data.get('serial_or_asset_tag') or '').strip()
        device.serial_or_asset_tag = serial or None
    if 'building' in data or creating:
        building = (data.get('building') or '').strip()
        device.building = building or None
    for coord in ('latitude', 'longitude'):
        action, value = _parse_coord(data, coord)
        if action == 'set':
            setattr(device, coord, value)
    if 'device_comment' in data or creating:
        comment = (data.get('device_comment') or '').strip()
        device.device_comment = comment or None
    if 'asset_owner_name' in data or creating:
        owner = (data.get('asset_owner_name') or '').strip()
        device.asset_owner_name = owner or None
    if 'assignment_date' in data or creating:
        device.assignment_date = parse_date(data.get('assignment_date'))
    device.updated_at = utcnow()
    if creating and not device.last_active_at:
        device.last_active_at = utcnow()
    if creating and not device.device_id:
        device.device_id = next_device_id()
    return device


def resolve_coords(device):
    """Return (lat, lng, source) using device pins or a building fallback."""
    if device.latitude is not None and device.longitude is not None:
        return device.latitude, device.longitude, 'device'
    building = (device.building or '').strip()
    if not building:
        return None, None, None
    prop = (
        TicketProperty.query
        .filter(func.lower(TicketProperty.name) == building.lower())
        .filter(TicketProperty.latitude.isnot(None), TicketProperty.longitude.isnot(None))
        .first()
    )
    if prop:
        return prop.latitude, prop.longitude, 'property'
    asset = (
        Asset.query
        .filter(func.lower(Asset.building) == building.lower())
        .filter(Asset.latitude.isnot(None), Asset.longitude.isnot(None))
        .first()
    )
    if asset:
        return asset.latitude, asset.longitude, 'asset'
    return None, None, None


def device_map_points():
    points = []
    for device in Device.query.order_by(Device.device_id.asc()).all():
        lat, lng, source = resolve_coords(device)
        if lat is None or lng is None:
            continue
        row = device.to_dict()
        row.update({
            'latitude': lat,
            'longitude': lng,
            'coord_source': source,
        })
        points.append(row)
    return points


def compute_device_kpis():
    devices = Device.query.all()
    total = len(devices)
    if total == 0:
        return {
            'total': 0,
            'online': 0,
            'offline': 0,
            'idle': 0,
            'pending_updates': 0,
            'fleet_health_pct': None,
            'critical_count': 0,
            'healthy_count': 0,
            'attention_count': 0,
            'unassigned': 0,
            'assigned_pct': None,
            'stale_count': 0,
            'missing_serial': 0,
            'by_type': [],
            'by_os': [],
            'by_building': [],
            'status': {'online': 0, 'offline': 0, 'idle': 0, 'update': 0},
        }

    now = utcnow()
    online = sum(1 for d in devices if d.status == 'online')
    offline = sum(1 for d in devices if d.status == 'offline')
    idle = sum(1 for d in devices if d.status == 'idle')
    update = sum(1 for d in devices if d.status == 'update')
    healths = [int(d.health) for d in devices if d.health is not None]
    fleet_health = round(sum(healths) / len(healths), 1) if healths else None
    critical = sum(1 for d in devices if (d.health if d.health is not None else 0) < HEALTH_WARN)
    healthy = sum(1 for d in devices if (d.health if d.health is not None else 0) >= HEALTH_HEALTHY)
    attention = sum(
        1 for d in devices
        if HEALTH_WARN <= (d.health if d.health is not None else 0) < HEALTH_HEALTHY
    )
    unassigned = sum(1 for d in devices if not d.assigned_user_id)
    stale = sum(1 for d in devices if is_stale(d, now))
    missing_serial = sum(1 for d in devices if not (d.serial_or_asset_tag or '').strip())

    by_type = {}
    by_os = {}
    buildings = {}
    for d in devices:
        t = d.device_type or 'Other'
        by_type[t] = by_type.get(t, 0) + 1
        os_name = d.os or 'Unknown'
        by_os[os_name] = by_os.get(os_name, 0) + 1
        b = (d.building or '').strip() or 'Unspecified'
        entry = buildings.setdefault(b, {'building': b, 'count': 0, 'health_sum': 0, 'health_n': 0})
        entry['count'] += 1
        if d.health is not None:
            entry['health_sum'] += int(d.health)
            entry['health_n'] += 1

    by_building = []
    for entry in buildings.values():
        avg = round(entry['health_sum'] / entry['health_n'], 1) if entry['health_n'] else None
        by_building.append({
            'building': entry['building'],
            'count': entry['count'],
            'avg_health': avg,
        })
    by_building.sort(key=lambda row: (-row['count'], row['building']))

    return {
        'total': total,
        'online': online,
        'offline': offline,
        'idle': idle,
        'pending_updates': update,
        'fleet_health_pct': fleet_health,
        'critical_count': critical,
        'healthy_count': healthy,
        'attention_count': attention,
        'unassigned': unassigned,
        'assigned_pct': round(100.0 * (total - unassigned) / total, 1),
        'stale_count': stale,
        'missing_serial': missing_serial,
        'by_type': [{'type': k, 'count': v} for k, v in sorted(by_type.items(), key=lambda x: (-x[1], x[0]))],
        'by_os': [{'os': k, 'count': v} for k, v in sorted(by_os.items(), key=lambda x: (-x[1], x[0]))],
        'by_building': by_building,
        'status': {'online': online, 'offline': offline, 'idle': idle, 'update': update},
    }


def _naive_dt(value):
    if not value:
        return None
    if getattr(value, 'tzinfo', None) is not None:
        return value.replace(tzinfo=None)
    return value


def _delta_chip(current, previous):
    """Week-over-week style chip, e.g. +8.5% / -4.0% / —."""
    if previous in (None, 0):
        if not current:
            return {'pct': None, 'label': '—', 'up': None, 'css': 'is-flat'}
        return {'pct': 100.0, 'label': '+100%', 'up': True, 'css': 'is-up'}
    pct = round(100.0 * (current - previous) / previous, 1)
    if pct > 0:
        css, up = 'is-up', True
    elif pct < 0:
        css, up = 'is-down', False
    else:
        css, up = 'is-flat', None
    sign = '+' if pct >= 0 else ''
    return {'pct': pct, 'label': f'{sign}{pct}%', 'up': up, 'css': css}


def _mean(values):
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 1)


def _shift_month(d, delta):
    month = d.month - 1 + delta
    year = d.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def _bucket_for(day, buckets):
    for bucket in buckets:
        if bucket['start'] <= day <= bucket['end']:
            return bucket['key']
    return None


def _clamp_day(year, month, day):
    last = (_shift_month(date(year, month, 1), 1) - timedelta(days=1)).day
    return date(year, month, min(day, last))


WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
WEEK_NUMS = (1, 2, 3, 4)


def _week_of_month(day):
    return min(4, (day.day - 1) // 7 + 1)


def _month_buckets(year, today):
    buckets = []
    for month_n in range(1, 13):
        cursor = date(year, month_n, 1)
        month_end = _shift_month(cursor, 1) - timedelta(days=1)
        buckets.append({
            'key': cursor.isoformat(),
            'start': cursor,
            'end': month_end,
            'label': cursor.strftime('%b'),
            'current': year == today.year and month_n == today.month,
        })
    return buckets


def _week_buckets(year, month, today):
    start = date(year, month, 1)
    month_end = _shift_month(start, 1) - timedelta(days=1)
    buckets = []
    for week_n in WEEK_NUMS:
        b_start = date(year, month, 1 + (week_n - 1) * 7)
        b_end = month_end if week_n == 4 else date(year, month, min(month_end.day, week_n * 7))
        buckets.append({
            'key': f'w{week_n}',
            'start': b_start,
            'end': b_end,
            'label': f'Week {week_n}',
            'current': (
                year == today.year
                and month == today.month
                and _week_of_month(today) == week_n
            ),
        })
    return start, month_end, buckets


def _resolve_cursor(period, today, year=None, month=None):
    try:
        y = int(year) if year not in (None, '') else today.year
    except (TypeError, ValueError):
        y = today.year
    try:
        m = int(month) if month not in (None, '') else today.month
    except (TypeError, ValueError):
        m = today.month
    y = max(2000, min(y, today.year))
    m = max(1, min(m, 12))
    current_month = date(today.year, today.month, 1)
    if period == 'week':
        cursor = date(y, m, 1)
        if cursor > current_month:
            cursor = current_month
        return cursor
    return date(y, 1, 1)


def _heat_row_key(mode, day):
    if mode == 'weeknum':
        return f'w{_week_of_month(day)}'
    return WEEKDAYS[day.weekday()]


def _period_spec(period, today, year=None, month=None):
    """Weekly: weeks of a month. Monthly/Yearly: Jan–Dec by week of month."""
    if period not in ('week', 'month', 'all'):
        period = 'week'
    cursor = _resolve_cursor(period, today, year, month)

    if period == 'week':
        start, month_end, buckets = _week_buckets(cursor.year, cursor.month, today)
        prev_start = _shift_month(start, -1)
        prev_end = start - timedelta(days=1)
        next_cursor = _shift_month(start, 1)
        meta = {
            'period': 'week',
            'label': 'Weekly',
            'enroll_kicker': 'Enrolled this month',
            'empty_hint': 'No last-seen activity this month.',
            'heat_absolute': True,
            'heat_row_mode': 'weekday',
            'heat_axis': [{'key': name, 'label': name} for name in WEEKDAYS],
            'heat_tip': 'Each column is a week of this month. Each row is a weekday. Darker squares mean more devices were last seen then.',
            'caption': start.strftime('%B %Y'),
            'end': month_end,
            'nav': {
                'mode': 'month',
                'label': start.strftime('%B %Y'),
                'year': start.year,
                'month': start.month,
                'prev_year': prev_start.year,
                'prev_month': prev_start.month,
                'next_year': next_cursor.year,
                'next_month': next_cursor.month,
                'can_prev': True,
                'can_next': next_cursor <= date(today.year, today.month, 1),
            },
        }
    elif period == 'month':
        year = cursor.year
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        buckets = _month_buckets(year, today)
        meta = {
            'period': 'month',
            'label': 'Monthly',
            'enroll_kicker': 'Enrolled this year',
            'empty_hint': 'No last-seen activity this year.',
            'heat_absolute': False,
            'heat_row_mode': 'weeknum',
            'heat_axis': [{'key': f'w{n}', 'label': f'Week {n}'} for n in WEEK_NUMS],
            'heat_tip': 'Each column is a month. Each row is a week of that month. Darker squares mean more devices were last seen then.',
            'caption': f'Jan – Dec {year}',
            'end': end,
            'nav': {
                'mode': 'year',
                'label': str(year),
                'year': year,
                'month': today.month if year == today.year else 1,
                'prev_year': year - 1,
                'prev_month': 1,
                'next_year': year + 1,
                'next_month': 1,
                'can_prev': year > 2000,
                'can_next': year < today.year,
            },
        }
        prev_start = date(year - 1, 1, 1)
        prev_end = date(year - 1, 12, 31)
    else:
        year = cursor.year
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        buckets = _month_buckets(year, today)
        meta = {
            'period': 'all',
            'label': 'Yearly',
            'enroll_kicker': 'Enrolled this year',
            'empty_hint': 'No last-seen activity this year.',
            'heat_absolute': False,
            'heat_row_mode': 'weeknum',
            'heat_axis': [{'key': f'w{n}', 'label': f'Week {n}'} for n in WEEK_NUMS],
            'heat_tip': 'Each column is a month. Each row is a week of that month. Darker squares mean more devices were last seen then.',
            'caption': f'Jan – Dec {year}',
            'end': end,
            'nav': {
                'mode': 'year',
                'label': str(year),
                'year': year,
                'month': today.month if year == today.year else 1,
                'prev_year': year - 1,
                'prev_month': 1,
                'next_year': year + 1,
                'next_month': 1,
                'can_prev': year > 2000,
                'can_next': year < today.year,
            },
        }
        prev_start = date(year - 1, 1, 1)
        prev_end = date(year - 1, 12, 31)

    keys = [bucket['key'] for bucket in buckets]
    meta.update({
        'start': start,
        'prev_start': prev_start,
        'prev_end': prev_end,
        'buckets': buckets,
        'keys': keys,
    })
    return meta


def compute_overview(period='week', year=None, month=None):
    """Dashboard overview widgets: mix, activity, follow-ups, timeline."""
    kpis = compute_device_kpis()
    devices = Device.query.all()
    now = utcnow()
    today = now.date()
    spec = _period_spec(period, today, year=year, month=month)
    buckets = spec['buckets']
    keys = spec['keys']
    yesterday = today - timedelta(days=1)
    range_end = spec['end'] if spec['end'] <= today else today

    enrolled_by_key = {key: 0 for key in keys}
    health_sum_by_key = {key: 0 for key in keys}
    health_n_by_key = {key: 0 for key in keys}
    heat_axis = spec['heat_axis']
    heat = {
        row['key']: {key: 0 for key in keys}
        for row in heat_axis
    }

    def bump_heat(when):
        when = _naive_dt(when)
        if not when:
            return
        day = when.date()
        key = _bucket_for(day, buckets)
        if not key:
            return
        row_key = _heat_row_key(spec['heat_row_mode'], day)
        if row_key in heat:
            heat[row_key][key] += 1

    enrolled_prev = 0
    seen_today = 0
    seen_yesterday = 0
    seen_in_range = 0
    health_now_vals = []
    health_prev_vals = []

    for device in devices:
        created = _naive_dt(device.created_at)
        if created:
            created_day = created.date()
            key = _bucket_for(created_day, buckets)
            if key:
                enrolled_by_key[key] += 1
            elif spec['prev_start'] <= created_day <= spec['prev_end']:
                enrolled_prev += 1
        when = _naive_dt(device.last_active_at or device.created_at)
        bump_heat(when)
        if not when:
            continue
        seen_day = when.date()
        if seen_day == today:
            seen_today += 1
        elif seen_day == yesterday:
            seen_yesterday += 1
        if spec['start'] <= seen_day <= range_end:
            seen_in_range += 1
        key = _bucket_for(seen_day, buckets)
        if key and device.health is not None:
            health_sum_by_key[key] += int(device.health)
            health_n_by_key[key] += 1
        if device.health is None:
            continue
        score = int(device.health)
        if spec['start'] <= seen_day <= range_end:
            health_now_vals.append(score)
        elif spec['prev_start'] <= seen_day <= spec['prev_end']:
            health_prev_vals.append(score)

    enrolled_spark = [enrolled_by_key[key] for key in keys]
    enrolled_in_range = sum(enrolled_spark)
    spark_max = max(enrolled_spark) if any(enrolled_spark) else 1
    health_spark = [
        round(health_sum_by_key[key] / health_n_by_key[key]) if health_n_by_key[key] else 0
        for key in keys
    ]
    health_spark_max = max(health_spark) if any(health_spark) else 1

    total = kpis['total'] or 0
    mix_parts = [
        ('Online', kpis['online'], '#e85d3a', False),
        ('Idle', kpis['idle'], '#ff8e68', False),
        ('Update', kpis['pending_updates'], '#ffc4a8', True),
        ('Offline', kpis['offline'], '#f6efe8', True),
    ]
    mix = []
    for label, count, color, label_dark in mix_parts:
        pct = round(100.0 * count / total, 1) if total else 0
        mix.append({
            'label': label,
            'count': count,
            'pct': pct,
            'color': color,
            'show_label': pct >= 12,
            'label_dark': label_dark,
        })
    ready_pct = round(100.0 * kpis['online'] / total) if total else 0

    follow_ups = [
        {
            'id': 'offline',
            'label': 'Confirm offline devices',
            'hint': f"{kpis['offline']} offline",
            'done': kpis['offline'] == 0,
            'href': '/admin/devices/all?status=offline',
        },
        {
            'id': 'update',
            'label': 'Patch devices needing update',
            'hint': f"{kpis['pending_updates']} pending",
            'done': kpis['pending_updates'] == 0,
            'href': '/admin/devices/all?status=update',
        },
        {
            'id': 'assign',
            'label': 'Assign owners',
            'hint': f"{kpis['unassigned']} unassigned",
            'done': kpis['unassigned'] == 0,
            'href': '/admin/devices/compliance',
        },
        {
            'id': 'critical',
            'label': 'Review critical health',
            'hint': f"{kpis['critical_count']} under 55%",
            'done': kpis['critical_count'] == 0,
            'href': '/admin/devices/compliance',
        },
    ]
    done_n = sum(1 for row in follow_ups if row['done'])
    follow_pct = round(100.0 * done_n / len(follow_ups)) if follow_ups else 100

    peak_idx = max(range(len(enrolled_spark)), key=lambda i: enrolled_spark[i]) if enrolled_spark else 0
    timeline = []
    for i, bucket in enumerate(buckets):
        count = enrolled_spark[i]
        timeline.append({
            'iso': bucket['key'],
            'label': bucket['label'],
            'count': count,
            'is_today': bucket['current'],
            'is_peak': i == peak_idx and count > 0,
            'pill': f"{count} enroll{'s' if count != 1 else ''}",
        })

    heat_peak = 0
    heat_rows = []
    for row in heat_axis:
        cells = []
        for key in keys:
            n = heat[row['key']][key]
            heat_peak = max(heat_peak, n)
            cells.append({'count': n, 'level': 0})
        heat_rows.append({'label': row['label'], 'key': row['key'], 'cells': cells})
    for row in heat_rows:
        for cell in row['cells']:
            n = cell['count']
            if n <= 0:
                cell['level'] = 0
            elif spec['heat_absolute']:
                cell['level'] = 1 if n == 1 else 2 if n == 2 else 3
            elif heat_peak <= 1:
                cell['level'] = 1
            elif n >= heat_peak:
                cell['level'] = 3
            elif n / heat_peak < 0.34:
                cell['level'] = 1
            elif n / heat_peak < 0.67:
                cell['level'] = 2
            else:
                cell['level'] = 3
    heat_empty = heat_peak <= 0

    health_now = _mean(health_now_vals)
    if health_now is None:
        health_now = kpis['fleet_health_pct']
    prev_health = _mean(health_prev_vals)
    enroll_delta = _delta_chip(enrolled_in_range, enrolled_prev)
    if health_now is None or prev_health is None:
        health_delta = {'pct': None, 'label': '—', 'up': None, 'css': 'is-flat'}
    else:
        health_delta = _delta_chip(health_now, prev_health)
    online_delta = _delta_chip(seen_today, seen_yesterday)
    if health_delta['pct'] is not None:
        hero_delta = health_delta
    elif kpis['fleet_health_pct'] is not None:
        hero_delta = {
            'pct': kpis['fleet_health_pct'],
            'label': f"{kpis['fleet_health_pct']}%",
            'up': None,
            'css': 'is-flat',
        }
    else:
        hero_delta = {'pct': None, 'label': '—', 'up': None, 'css': 'is-flat'}

    day = now.day
    if 10 <= day % 100 <= 20:
        ordinal = 'th'
    else:
        ordinal = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    today_label = f"{now.strftime('%A')}, {now.strftime('%B')} {day}{ordinal}, {now.year}"

    return {
        'kpis': kpis,
        'today_label': today_label,
        'period': spec['period'],
        'period_label': spec['label'],
        'period_options': (('week', 'Weekly'), ('month', 'Monthly'), ('all', 'Yearly')),
        'range_caption': spec.get('caption') or f"{spec['start'].strftime('%d %b')} – {today.strftime('%d %b %Y')}",
        'enroll_kicker': spec['enroll_kicker'],
        'enrolled_this_week': enrolled_in_range,
        'enrolled_in_range': enrolled_in_range,
        'enrolled_prev_week': enrolled_prev,
        'enrolled_spark': enrolled_spark,
        'spark_max': spark_max,
        'health_spark': health_spark,
        'health_spark_max': health_spark_max,
        'day_labels': [bucket['label'] for bucket in buckets],
        'bucket_count': len(buckets),
        'mix': mix,
        'ready_pct': ready_pct,
        'heat_rows': heat_rows,
        'heat_empty': heat_empty,
        'heat_empty_hint': spec['empty_hint'],
        'heat_nav': spec['nav'],
        'heat_tip': spec.get('heat_tip') or '',
        'follow_ups': follow_ups,
        'follow_pct': follow_pct,
        'follow_done': done_n,
        'timeline': timeline,
        'seen_today': seen_today,
        'seen_in_range': seen_in_range,
        'enroll_delta': enroll_delta,
        'health_delta': health_delta,
        'online_delta': online_delta,
        'hero_delta': hero_delta,
    }


def _device_summaries(devices, limit=20):
    rows = []
    for d in devices[:limit]:
        rows.append({
            'id': d.id,
            'device_id': d.device_id,
            'name': d.name,
            'status': d.status,
            'health': d.health,
            'building': d.building,
        })
    return rows


def compute_compliance():
    devices = Device.query.order_by(Device.name.asc()).all()
    now = utcnow()
    critical = [d for d in devices if (d.health if d.health is not None else 0) < HEALTH_WARN]
    attention = [
        d for d in devices
        if HEALTH_WARN <= (d.health if d.health is not None else 0) < HEALTH_HEALTHY
    ]
    healthy = [d for d in devices if (d.health if d.health is not None else 0) >= HEALTH_HEALTHY]
    needs_update = [d for d in devices if d.status == 'update']
    offline = [d for d in devices if d.status == 'offline']
    stale = [d for d in devices if is_stale(d, now)]
    unassigned = [d for d in devices if not d.assigned_user_id]
    missing_serial = [d for d in devices if not (d.serial_or_asset_tag or '').strip()]
    checks = [
        {
            'id': 'critical',
            'label': 'Critical health',
            'hint': 'Health under 55%',
            'severity': 'high',
            'count': len(critical),
            'devices': _device_summaries(critical),
        },
        {
            'id': 'needs_update',
            'label': 'Needs update',
            'hint': 'Marked as pending update',
            'severity': 'high',
            'count': len(needs_update),
            'devices': _device_summaries(needs_update),
        },
        {
            'id': 'offline',
            'label': 'Offline',
            'hint': 'Inventory status is offline',
            'severity': 'medium',
            'count': len(offline),
            'devices': _device_summaries(offline),
        },
        {
            'id': 'stale',
            'label': 'No recent activity',
            'hint': f'Last seen more than {STALE_DAYS} days ago, or never',
            'severity': 'medium',
            'count': len(stale),
            'devices': _device_summaries(stale),
        },
        {
            'id': 'unassigned',
            'label': 'Unassigned',
            'hint': 'No user on the device',
            'severity': 'medium',
            'count': len(unassigned),
            'devices': _device_summaries(unassigned),
        },
        {
            'id': 'missing_serial',
            'label': 'Missing serial / asset tag',
            'hint': 'Required for custody tracking',
            'severity': 'low',
            'count': len(missing_serial),
            'devices': _device_summaries(missing_serial),
        },
        {
            'id': 'attention',
            'label': 'Needs attention',
            'hint': 'Health 55–79%',
            'severity': 'low',
            'count': len(attention),
            'devices': _device_summaries(attention),
        },
        {
            'id': 'healthy',
            'label': 'Healthy devices',
            'hint': 'Health 80% or above',
            'severity': 'ok',
            'count': len(healthy),
            'devices': _device_summaries(healthy),
        },
    ]
    open_issues = sum(c['count'] for c in checks if c['severity'] in ('high', 'medium', 'low') and c['id'] != 'healthy')
    return {
        'total': len(devices),
        'open_issues': open_issues,
        'healthy_count': len(healthy),
        'checks': checks,
    }


def filter_devices_query():
    from flask import request
    query = Device.query
    status = (request.args.get('status') or '').strip().lower()
    device_type = (request.args.get('device_type') or '').strip()
    q = (request.args.get('q') or '').strip()
    building = (request.args.get('building') or '').strip()
    if status and status in VALID_STATUSES:
        query = query.filter(Device.status == status)
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if building:
        query = query.filter(func.lower(Device.building) == building.lower())
    if q:
        like = f'%{q}%'
        query = query.filter(or_(
            Device.name.ilike(like),
            Device.device_id.ilike(like),
            Device.os.ilike(like),
            Device.serial_or_asset_tag.ilike(like),
            Device.building.ilike(like),
            Device.asset_owner_name.ilike(like),
        ))
    return query.order_by(Device.created_at.desc())
