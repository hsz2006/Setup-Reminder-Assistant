import json
import random
from datetime import date, datetime
from .storage import ROOT

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def load_config(path=None):
    with open(path or ROOT / 'config' / 'schedule.json', encoding='utf-8-sig') as f:
        return json.load(f)


def school_day(day, cfg):
    iso = day.isoformat()
    # The supplied school calendar starts each teaching week on Sunday.
    week = (day - date.fromisoformat(cfg['term_start'])).days // 7 + 1
    if day.weekday() == 6:
        week += 1
    holiday = iso in cfg['holidays'] or cfg['winter_start'] <= iso <= cfg['winter_end']
    effective = cfg['makeup'].get(iso, day.weekday())
    return week, effective, holiday


def in_class(now, cfg):
    if not cfg['term_start'] <= now.date().isoformat() <= cfg['term_end']:
        return False
    week, dow, holiday = school_day(now.date(), cfg)
    if holiday:
        return False
    time = now.strftime('%H:%M')
    for c in cfg['courses']:
        if c.get('self_study') or dow != c['weekday']:
            continue
        if 'dates' in c:
            applies = now.date().isoformat() in c['dates']
        else:
            applies = week in c['weeks']
        if applies and c['start'] <= time < c['end']:
            return True
    return False


def ordinary_allowed(now, cfg):
    day = now.date().isoformat()
    return (cfg['active_from'] <= day <= cfg['winter_end'] and
            cfg['window_start'] <= now.strftime('%H:%M') <= cfg['window_end'] and
            not in_class(now, cfg))


def fixed_events(now, cfg):
    if now.date().isoformat() < cfg['active_from']:
        return []
    week, _, holiday = school_day(now.date(), cfg)
    items = []
    for item in cfg['fixed']:
        if now.weekday() != item['weekday'] or now.strftime('%H:%M') != item['start']:
            continue
        if item['kind'] == 'graph':
            if (week not in item['weeks'] or holiday or now.date().isoformat() in cfg['makeup'] or
                    not cfg['term_start'] <= now.date().isoformat() <= cfg['term_end']):
                continue
        items.append(item)
    return items


def scheduled(now, cfg):
    fixed = fixed_events(now, cfg)
    if fixed:
        return fixed[0]['action']
    slots = list(cfg['daily_times'])
    _, effective, holiday = school_day(now.date(), cfg)
    if effective == 2 and not holiday:
        slots.append('16:00')
    if now.strftime('%H:%M') in slots and ordinary_allowed(now, cfg):
        return ''
    return None


def next_action(now, cfg, tasks, offset=0):
    if tasks:
        task = tasks[offset % len(tasks)]
        return task['text'], task['id']
    _, dow, holiday = school_day(now.date(), cfg)
    t = now.strftime('%H:%M')
    slot = 'am' if t < '12:00' else 'pm' if t < '16:00' else 's1600' if t < '18:00' else 'evening'
    key = 'Holiday' if holiday else WEEKDAYS[dow]
    seed = 0
    for ch in now.date().isoformat() + '|' + slot:
        seed = (seed * 31 + ord(ch)) % 100003
    seed += offset
    default = cfg.get('default_tasks', {}).get(key, {}).get(slot)
    pool = cfg.get('generic_pool', [])
    if offset == 0 and seed % 100 < 70 and default:
        return default, None
    if pool:
        return pool[seed % len(pool)], None
    return default or '打开书，先看一小段。随时可以停下。', None


def light_actions(now, cfg, context=''):
    """Use explicit task context first, then the currently scheduled activity."""
    lower = context.lower()
    if any(word in lower for word in ('代码', 'matlab', 'python', '编程', 'debug')):
        group = 'code'
    elif any(word in lower for word in ('论文', '文献', 'paper')):
        group = 'paper'
    elif any(word in lower for word in ('科研', '实验', '仿真')):
        group = 'research'
    elif any(word in lower for word in ('课', '书', '讲义', '图论', '作业', '题', '笔记')):
        group = 'study'
    else:
        current = [item for item in day_agenda(now.date(), cfg)
                   if item['start'] <= now.strftime('%H:%M') < item['end']]
        group = 'research' if any(item['name'] == '科研' for item in current) else 'study'
    pool = cfg.get('generic_pool', [])
    indexes = cfg.get('light_action_contexts', {}).get(group, range(len(pool)))
    choices = [pool[i] for i in indexes if isinstance(i, int) and 0 <= i < len(pool)]
    return list(dict.fromkeys(choices or pool or ['打开手边正在学的书，只读一句。']))


def switch_action(now, cfg, tasks, current, context='', rng=None):
    """Equal category probability when both have alternatives; never repeat text."""
    rng = rng or random
    task_choices = list({t['text']: (t['text'], t['id']) for t in tasks
                         if t['text'].strip() and t['text'].strip() != current.strip()}.values())
    light_choices = [(text, None) for text in light_actions(now, cfg, context)
                     if text.strip() != current.strip()]
    if task_choices and light_choices:
        choices = task_choices if rng.random() < 0.5 else light_choices
    else:
        choices = task_choices or light_choices
    if not choices:
        # Even a user-edited pool with one repeated item must visibly change.
        fallback = '把正在学的讲义翻到上次停下的位置。'
        if fallback == current.strip():
            fallback = '打开手边正在学的书，只读一句。'
        return fallback, None
    return rng.choice(choices)


def day_agenda(day, cfg):
    """The dashboard uses the same week and exception rules as actual reminders."""
    iso = day.isoformat()
    week, dow, holiday = school_day(day, cfg)
    items = []
    if cfg['term_start'] <= iso <= cfg['term_end'] and not holiday:
        for course in cfg['courses']:
            if course.get('self_study') or course['weekday'] != dow:
                continue
            applies = iso in course['dates'] if 'dates' in course else week in course['weeks']
            if applies:
                items.append({'name': course['name'], 'start': course['start'], 'end': course['end'], 'kind': 'course'})
    for item in cfg['fixed']:
        candidate = datetime.combine(day, datetime.strptime(item['start'], '%H:%M').time())
        if item in fixed_events(candidate, cfg):
            items.append({'name': '图论自学' if item['kind'] == 'graph' else '科研',
                          'start': item['start'], 'end': item['end'], 'kind': item['kind']})
    return sorted(items, key=lambda item: (item['start'], item['name']))
