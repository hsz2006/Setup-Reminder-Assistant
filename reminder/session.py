"""Reminder delivery and meeting mode, independent of the desktop toolkit."""
from .rules import scheduled, ordinary_allowed


class Session:
    def __init__(self, store, focus, cfg, now):
        self.store, self.focus, self.cfg = store, focus, cfg
        self.last_tick = now.timestamp()
        self.last_return = 0

    @property
    def meeting(self):
        return bool(self.store.get('meeting_mode', False))

    def set_meeting(self, enabled, now):
        if self.meeting and not enabled:
            # Consume anything that expired during the meeting before restoring alerts.
            self.poll(now)
        self.store.set('meeting_mode', bool(enabled))

    def poll(self, now, locked=False, returned=False):
        stamp = now.timestamp()
        current = self.focus.current(stamp)
        meeting = self.meeting
        event = None
        due = scheduled(now, self.cfg)
        if due is not None and self.store.claim('schedule:' + now.strftime('%Y-%m-%d %H:%M')):
            if not locked and stamp - self.last_tick < 60:
                event = (due, '现在的下一步')
        if returned and not locked and ordinary_allowed(now, self.cfg) and stamp - self.last_return > 60:
            event = event or ('', '回到电脑前，先做一小步')
            self.last_return = stamp
        snooze_end = self.store.get('snooze_end', 0)
        if snooze_end and stamp >= snooze_end and (not locked or meeting):
            self.store.set('snooze_end', 0)
            event = event or ('', '暂缓时间到了')
        rest_end = self.store.get('rest_end', 0)
        if rest_end and stamp >= rest_end and (not locked or meeting):
            self.store.set('rest_end', 0)
            event = event or ('', '休息时间到了')
        previous = self.store.get('focus', {})
        if previous and not current and (not locked or meeting) and self.store.claim('focus_end:' + previous['id']):
            event = event or ('这一段专注结束了。可以休息，也可以自行继续。', '专注结束')
        self.last_tick = stamp
        return None if meeting or current else event
