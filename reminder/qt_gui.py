"""Milk-tea and sage desktop dashboard. Business data stays in the original Store."""
import ctypes
import logging
import os
import queue
import threading
import time
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QObject
from PySide6.QtGui import QAction, QFont, QFontDatabase, QKeySequence, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QLineEdit, QTextEdit, QScrollArea, QDialog,
    QSpinBox, QComboBox, QMenu, QSystemTrayIcon, QKeySequenceEdit, QTabWidget, QSizePolicy, QGraphicsDropShadowEffect)
from .storage import ROOT, Store
from .rules import load_config, next_action, ordinary_allowed, day_agenda, switch_action
from .focus import Focus, normalize_links
from .bridge import Bridge, PORT
from .session import Session
from .hotkeys import Hotkeys, DEFAULTS
from .theme import STYLE, app_icon
from .ai import AI
from .windows import listen
from .todo import TodoPage
from .bili_usage import WARNING as BILI_WARNING
from .allowed_videos import AllowedVideos


def label(text='', name=None, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback, name=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(lambda checked=False: callback())
    return widget


def card(name='card', padding=22):
    frame = QFrame()
    frame.setObjectName(name)
    if name == 'card':
        # Static, low elevation on the three dashboard panels only.
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(105, 86, 58, 42))
        frame.setGraphicsEffect(shadow)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(13)
    return frame, layout


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


class Desktop(QMainWindow):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def closeEvent(self, event):
        event.ignore()
        self.owner.hide()


class App:
    def __init__(self, background=False, store=None, bridge_port=PORT, system_integration=True, clock=None):
        self.qt = QApplication.instance() or QApplication([])
        if self.qt.platformName() == 'offscreen' and os.name == 'nt':
            for font_file in ('msyh.ttc', 'msyhbd.ttc'):
                QFontDatabase.addApplicationFont(os.path.join(os.environ['WINDIR'], 'Fonts', font_file))
        self.qt.setQuitOnLastWindowClosed(False)
        self.qt.setApplicationName('启动提醒助手')
        self.qt.setStyle('Fusion')
        self.qt.setFont(QFont('Microsoft YaHei UI', 10))
        self.qt.setStyleSheet(STYLE)
        self.icon = app_icon()
        self.qt.setWindowIcon(self.icon)
        self.store = store or Store()
        self.clock = clock or datetime.now
        self.system_integration = system_integration
        self.cfg = load_config()
        self.focus = Focus(self.store)
        self.session = Session(self.store, self.focus, self.cfg, self.clock())
        self.events = queue.Queue()
        self.bridge = Bridge(self.store, self.focus, self.events)
        self.bridge.start(port=bridge_port)
        self.log = logging.getLogger('reminder.desktop.' + str(id(self)))
        self.log.setLevel(logging.INFO)
        self.log.propagate = False
        self.log_handler = logging.FileHandler(self.store.path.parent / 'app.log', encoding='utf-8')
        self.log_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.log.addHandler(self.log_handler)
        self.root = Desktop(self)
        self.root.setWindowTitle('启动提醒助手')
        self.root.setWindowIcon(self.icon)
        self.root.setMinimumSize(920, 650)
        available = self.qt.primaryScreen().availableGeometry()
        self.root.resize(min(1160, available.width() - 50), min(800, available.height() - 50))
        self.root.move(available.center() - self.root.rect().center())
        self.dialogs = []
        self.popup = None
        self.settings_dialog = None
        self.quick_dialog = None
        self.allow_dialog = None
        self.locked = False
        self.pending_return = False
        self.show_all_agenda = False
        self.task_signature = None
        self.agenda_signature = None
        self.deferred_draft = None
        self.closed = False
        self.build_dashboard()
        self.hotkeys = Hotkeys(self.qt, {'toggle': self.toggle_window, 'capture': self.quick_capture}, native=system_integration)
        try:
            self.hotkeys.configure(self.store.get('hotkeys', DEFAULTS))
        except ValueError as error:
            self.status.setText(str(error) + ' 可在设置 → 快捷键中修改。')
        self.tray = None
        if system_integration:
            self.build_tray()
            listen(self.events)
            self.native_caption()
        self.refresh()
        self.update_meeting_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(700)
        self.login_timer = QTimer()
        self.login_timer.setSingleShot(True)
        self.login_timer.timeout.connect(self.login_reminder)
        if system_integration:
            self.login_timer.start(1200)
        if not background:
            self.show()

    def native_caption(self):
        if os.name != 'nt':
            return
        try:
            from ctypes import wintypes
            dwm = ctypes.WinDLL('dwmapi')
            dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            for attribute, value in [(35, 0xBDD1DD), (36, 0x353F44), (33, 2)]:
                number = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(int(self.root.winId()), attribute, ctypes.byref(number), ctypes.sizeof(number))
        except OSError:
            pass

    def build_dashboard(self):
        dashboard = QWidget()
        dashboard.setObjectName('dashboard')
        self.root.setCentralWidget(dashboard)
        outer = QVBoxLayout(dashboard)
        outer.setContentsMargins(28, 24, 28, 14)
        outer.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(7)
        heading.addWidget(label('从一个小动作开始', 'title'))
        self.date_label = label('', 'date')
        heading.addWidget(self.date_label)
        header.addLayout(heading, 1)
        self.meeting_button = button('会议免打扰', self.toggle_meeting)
        header.addWidget(self.meeting_button)
        header.addWidget(button('设置', self.open_settings, 'quiet'))
        outer.addLayout(header)
        self.meeting_banner = label('会议免打扰已开启 · 所有提醒暂停，专注计时继续。需要你手动恢复。', 'meetingBanner', True)
        outer.addWidget(self.meeting_banner)
        middle = QHBoxLayout()
        middle.setSpacing(18)
        self.schedule_card, schedule_layout = card()
        schedule_head = QHBoxLayout()
        schedule_head.addWidget(label('今日安排', 'section'), 1)
        self.agenda_button = button('查看全天', self.toggle_agenda, 'quiet')
        schedule_head.addWidget(self.agenda_button)
        schedule_layout.addLayout(schedule_head)
        self.agenda_scroll = QScrollArea()
        self.agenda_scroll.setWidgetResizable(True)
        agenda_content = QWidget()
        self.agenda_rows = QVBoxLayout(agenda_content)
        self.agenda_rows.setContentsMargins(0, 2, 0, 0)
        self.agenda_rows.setSpacing(14)
        self.agenda_scroll.setWidget(agenda_content)
        schedule_layout.addWidget(self.agenda_scroll, 1)
        schedule_layout.addWidget(label('安排只负责提醒，不会自动进入专注。', 'muted', True))
        middle.addWidget(self.schedule_card, 34)
        self.tasks_card, tasks_layout = card()
        task_head = QHBoxLayout()
        task_head.addWidget(label('下一步任务', 'section'), 1)
        self.task_count = label('', 'muted')
        task_head.addWidget(self.task_count)
        task_head.addWidget(button('随手复盘', self.review_dialog, 'quiet'))
        tasks_layout.addLayout(task_head)
        hero, hero_layout = card('hero', 18)
        hero_row = QHBoxLayout()
        self.hero_done = button('', self.complete_hero, 'round')
        self.hero_done.setToolTip('标记当前任务完成')
        hero_row.addWidget(self.hero_done)
        self.hero_text = label('', 'heroText', True)
        self.hero_text.setMinimumWidth(180)
        hero_row.addWidget(self.hero_text, 1)
        hero_layout.addLayout(hero_row)
        self.hero_hint = label('先接上一个小步骤，想继续时再继续。', 'muted', True)
        hero_layout.addWidget(self.hero_hint)
        tasks_layout.addWidget(hero)
        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        task_content = QWidget()
        self.task_rows = QVBoxLayout(task_content)
        self.task_rows.setContentsMargins(0, 0, 0, 0)
        self.task_rows.setSpacing(8)
        self.task_scroll.setWidget(task_content)
        tasks_layout.addWidget(self.task_scroll, 1)
        capture = QHBoxLayout()
        self.task_input = QLineEdit(self.store.get('capture_draft', ''))
        self.task_input.setPlaceholderText('记下想做的事…')
        self.task_input.returnPressed.connect(self.manual_task)
        self.task_input.textChanged.connect(lambda value: self.store.set('capture_draft', value))
        capture.addWidget(self.task_input, 1)
        capture.addWidget(button('记下', self.manual_task))
        self.ai_button = button('AI 拆小', self.draft)
        capture.addWidget(self.ai_button)
        tasks_layout.addLayout(capture)
        middle.addWidget(self.tasks_card, 66)
        outer.addLayout(middle, 1)
        self.focus_card, focus_layout = card()
        focus_top = QHBoxLayout()
        focus_title = QVBoxLayout()
        focus_title.addWidget(label('专注由你决定', 'section'))
        self.focus_label = label('提醒不计时，专注才会限制网站。', 'muted')
        focus_title.addWidget(self.focus_label)
        focus_top.addLayout(focus_title, 1)
        self.allow_button = button('允许的视频', self.edit_allowlist, 'quiet')
        focus_top.addWidget(self.allow_button)
        focus_layout.addLayout(focus_top)
        controls = QHBoxLayout()
        self.duration_buttons = []
        for minutes in (15, 25, 45, 60, 90):
            b = button(str(minutes), lambda value=minutes: self.minutes.setValue(value), 'duration')
            b.setCheckable(True)
            self.duration_buttons.append((minutes, b))
            controls.addWidget(b)
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 1440)
        self.minutes.setSuffix(' 分钟')
        self.minutes.setValue(25)
        self.minutes.setMaximumWidth(130)
        self.minutes.valueChanged.connect(self.update_duration)
        self.update_duration(25)
        controls.addWidget(self.minutes)
        controls.addStretch(1)
        self.start_button = button('开始专注', self.start_focus, 'primary')
        self.start_button.setMinimumWidth(150)
        controls.addWidget(self.start_button)
        focus_layout.addLayout(controls)
        self.browser_label = label('', 'muted')
        focus_layout.addWidget(self.browser_label)
        self.usage_label = label('', 'muted', True)
        focus_layout.addWidget(self.usage_label)
        outer.addWidget(self.focus_card)
        footer = QHBoxLayout()
        self.status = label('后台运行中 · 关闭窗口收进托盘', 'muted', True)
        footer.addWidget(self.status, 1)
        footer.addWidget(button('预览提醒', self.preview, 'quiet'))
        outer.addLayout(footer)

    def update_duration(self, value):
        for minutes, widget in self.duration_buttons:
            widget.setChecked(minutes == value)

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.icon, self.root)
        self.tray.setToolTip('启动提醒助手')
        menu = QMenu()
        menu.addAction('打开助手', self.show)
        menu.addAction('快速记任务', self.quick_capture)
        self.tray_meeting = menu.addAction('开启会议免打扰', self.toggle_meeting)
        menu.addSeparator()
        menu.addAction('设置', self.open_settings)
        menu.addAction('退出后台…', self.quit)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def show(self):
        self.root.showNormal()
        if os.name == 'nt' and self.qt.platformName() == 'windows':
            # A launcher using SW_HIDE can leave Qt logically visible but HWND hidden.
            from ctypes import wintypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.ShowWindow.restype = wintypes.BOOL
            user32.ShowWindow(int(self.root.winId()), 9)  # SW_RESTORE
        self.root.raise_()
        self.root.activateWindow()

    def hide(self):
        self.root.hide()

    def toggle_window(self):
        if self.root.isVisible() and not self.root.isMinimized():
            self.hide()
        else:
            self.show()

    def new_dialog(self, title, width=590, topmost=False):
        win = QDialog(self.root)
        win.setWindowTitle(title)
        win.setWindowIcon(self.icon)
        win.setMinimumWidth(width)
        win.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        if topmost:
            win.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        layout = QVBoxLayout(win)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(16)
        self.dialogs.append(win)
        win.finished.connect(lambda result, dialog=win: self.dialogs.remove(dialog) if dialog in self.dialogs else None)
        return win, layout

    def present(self, win):
        win.adjustSize()
        screen = self.root.screen().availableGeometry()
        win.move(screen.center() - win.rect().center())
        win.show()
        win.raise_()
        win.activateWindow()

    def notice(self, title, text):
        self.status.setText(text)
        if self.session.meeting:
            return
        win, layout = self.new_dialog(title)
        layout.addWidget(label(title, 'section'))
        layout.addWidget(label(text, wrap=True))
        layout.addWidget(button('知道了', win.accept, 'primary'), alignment=Qt.AlignmentFlag.AlignRight)
        self.present(win)

    def confirm(self, title, text, callback):
        win, layout = self.new_dialog(title)
        layout.addWidget(label(title, 'section'))
        layout.addWidget(label(text, wrap=True))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button('取消', win.reject))
        def accept():
            win.accept()
            callback()
        row.addWidget(button('确认', accept, 'primary'))
        layout.addLayout(row)
        self.present(win)

    def toggle_meeting(self):
        enabled = not self.session.meeting
        self.session.set_meeting(enabled, self.clock())
        if enabled:
            if self.popup:
                self.popup.reject()
            for win in list(self.dialogs):
                win.hide()
            self.root.hide()
        self.update_meeting_ui()
        if not enabled and self.deferred_draft is not None:
            self.status.setText('会议免打扰已关闭。AI 草稿已保留，可在任务区继续查看。')
            self.ai_button.setText('查看草稿')

    def update_meeting_ui(self):
        enabled = self.session.meeting
        self.meeting_button.setText('恢复提醒' if enabled else '会议免打扰')
        self.meeting_banner.setVisible(enabled)
        if self.tray:
            self.tray_meeting.setText('恢复提醒' if enabled else '开启会议免打扰')
            self.tray.setToolTip('启动提醒助手 · 会议免打扰' if enabled else '启动提醒助手')

    def refresh(self):
        now = self.clock()
        self.date_label.setText(f'{now.month}月{now.day}日 · 星期' + '一二三四五六日'[now.weekday()])
        tasks = self.store.tasks(all_pending=True)
        signature = [(task['id'], task['text'], task['due']) for task in tasks]
        eligible = [task for task in tasks if not task['due'] or task['due'] <= now.date().isoformat()]
        self.hero_id = eligible[0]['id'] if eligible else None
        text, _ = next_action(now, self.cfg, eligible)
        self.hero_text.setText(text)
        self.hero_done.setEnabled(self.hero_id is not None)
        self.hero_hint.setText('先接上一个小步骤，想继续时再继续。' if eligible else '还没有当前待办，可以先做这个小动作，或记下一件事。')
        if signature != self.task_signature:
            self.task_signature = signature
            self.task_count.setText(f'{len(tasks)} 项待办')
            clear_layout(self.task_rows)
            for task in tasks:
                row, row_layout = card('taskRow', 10)
                content = QHBoxLayout()
                content.addWidget(button('', lambda task_id=task['id']: self.set_task(task_id, 'done'), 'round'))
                text_col = QVBoxLayout()
                text_col.setSpacing(3)
                text_col.addWidget(label(task['text'], wrap=True))
                if task['due']:
                    text_col.addWidget(label(task['due'], 'muted'))
                content.addLayout(text_col, 1)
                content.addWidget(button('编辑', lambda t=dict(task): self.edit_task(t), 'quiet'))
                content.addWidget(button('搁置', lambda task_id=task['id']: self.set_task(task_id, 'shelved'), 'quiet'))
                row_layout.addLayout(content)
                self.task_rows.addWidget(row)
            if not tasks:
                self.task_rows.addWidget(label('把模糊的想法记下来，之后再拆小。', 'muted', True))
            self.task_rows.addStretch(1)
        agenda = day_agenda(now.date(), self.cfg)
        agenda_key = (now.strftime('%Y-%m-%d %H:%M'), self.show_all_agenda, str(agenda))
        if agenda_key != self.agenda_signature:
            self.agenda_signature = agenda_key
            clear_layout(self.agenda_rows)
            shown = agenda if self.show_all_agenda else [item for item in agenda if item['end'] > now.strftime('%H:%M')][:3]
            for item in shown:
                block = QWidget()
                layout = QVBoxLayout(block)
                layout.setContentsMargins(3, 3, 3, 7)
                layout.setSpacing(6)
                top = QHBoxLayout()
                top.addWidget(label(item['start'], 'section'))
                top.addStretch()
                state = '已结束' if item['end'] <= now.strftime('%H:%M') else '进行中' if item['start'] <= now.strftime('%H:%M') else '接下来'
                top.addWidget(label(state, 'badge'))
                layout.addLayout(top)
                layout.addWidget(label(item['name'], wrap=True))
                layout.addWidget(label(item['start'] + ' — ' + item['end'], 'muted'))
                self.agenda_rows.addWidget(block)
            if not shown:
                self.agenda_rows.addWidget(label('今天接下来没有固定安排。\n可以按自己的节奏开始。', 'muted', True))
            self.agenda_rows.addStretch(1)
        try:
            current = self.focus.blocking()
            count = len(current['allow']) if current else len(normalize_links(self.store.get('allow_draft', '')))
            self.allow_button.setText(f'已允许 {count} 个视频  ›')
        except ValueError:
            self.allow_button.setText('检查允许列表  ›')

    def toggle_agenda(self):
        self.show_all_agenda = not self.show_all_agenda
        self.agenda_button.setText('只看接下来' if self.show_all_agenda else '查看全天')
        self.refresh()

    def manual_task(self):
        text = self.task_input.text().strip()
        if text:
            self.store.add_tasks([text])
            self.task_input.clear()
            self.refresh()

    def complete_hero(self):
        if self.hero_id is not None:
            self.set_task(self.hero_id, 'done')

    def set_task(self, task_id, status):
        self.store.update_task(task_id, status=status)
        self.refresh()

    def edit_task(self, task):
        win, layout = self.new_dialog('编辑下一步')
        text = QLineEdit(task['text'])
        layout.addWidget(text)
        def save():
            try:
                self.store.update_task(task['id'], text=text.text())
                win.accept()
                self.refresh()
            except ValueError as error:
                self.notice('无法保存', str(error))
        layout.addWidget(button('保存', save, 'primary'))
        self.present(win)

    def quick_capture(self):
        if self.quick_dialog and self.quick_dialog.isVisible():
            self.quick_dialog.raise_()
            self.quick_dialog.activateWindow()
            return
        win, layout = self.new_dialog('快速记下一步', width=520, topmost=True)
        self.quick_dialog = win
        layout.addWidget(label('先记下来，不用现在想清楚', 'section'))
        text = QLineEdit(self.store.get('quick_draft', ''))
        text.setPlaceholderText('下一步想做什么？')
        text.textChanged.connect(lambda value: self.store.set('quick_draft', value))
        layout.addWidget(text)
        def save():
            if text.text().strip():
                self.store.add_tasks([text.text()])
                self.store.set('quick_draft', '')
                win.accept()
                self.refresh()
        text.returnPressed.connect(save)
        layout.addWidget(button('记下', save, 'primary'), alignment=Qt.AlignmentFlag.AlignRight)
        self.present(win)
        text.setFocus()

    def review_dialog(self):
        win, layout = self.new_dialog('随手复盘')
        layout.addWidget(label('完成了什么 / 卡在哪里', 'section'))
        text = QTextEdit()
        text.setPlainText(self.store.get('review_draft', ''))
        text.setPlaceholderText('两句话也可以。不需要每天填写。')
        text.setMinimumHeight(150)
        text.textChanged.connect(lambda: self.store.set('review_draft', text.toPlainText()))
        layout.addWidget(text)
        def save():
            self.store.review(text.toPlainText())
            self.store.set('review_draft', '')
            win.accept()
            self.status.setText('复盘已保存在本机。')
        layout.addWidget(button('保存复盘', save, 'primary'))
        self.present(win)

    def draft(self):
        if self.deferred_draft is not None:
            tasks, self.deferred_draft = self.deferred_draft, None
            self.ai_button.setText('AI 拆小')
            self.confirm_draft(tasks)
            return
        prompt = self.task_input.text().strip()
        if not prompt:
            return
        self.ai_button.setEnabled(False)
        self.status.setText('正在拆成小步骤，确认后才会保存。')
        def worker():
            try:
                self.events.put(('draft', AI(self.store).ask(prompt, draft=True)))
            except Exception as error:
                self.events.put(('ai_error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def confirm_draft(self, tasks):
        win, layout = self.new_dialog('确认任务草稿')
        layout.addWidget(label('每行一个步骤，可以修改后再保存。', wrap=True))
        text = QTextEdit()
        text.setPlainText('\n'.join(tasks))
        layout.addWidget(text)
        due = QLineEdit()
        due.setPlaceholderText('计划日期 YYYY-MM-DD，可留空')
        layout.addWidget(due)
        def save():
            try:
                self.store.add_tasks(text.toPlainText().splitlines(), due.text().strip())
                self.task_input.clear()
                win.accept()
                self.refresh()
            except ValueError as error:
                self.notice('无法保存', str(error))
        layout.addWidget(button('确认保存', save, 'primary'))
        self.present(win)

    def edit_allowlist(self):
        current = self.focus.blocking()
        if current:
            if self.allow_dialog and self.allow_dialog.isVisible():
                self.allow_dialog.reject()
            win, layout = self.new_dialog('当前允许的视频', width=700)
            self.allow_dialog = win
            page = AllowedVideos(self.store, self.focus, current, self.notice, win)
            layout.addWidget(page)
            win.finished.connect(lambda result: page.stop())
            self.present(win)
            return
        win, layout = self.new_dialog('允许的视频与音乐', width=640)
        self.allow_dialog = win
        layout.addWidget(label('每行一个视频链接或 BV 号。\n课程合集在浏览器扩展中提取后，粘贴到这里。', wrap=True))
        text = QTextEdit()
        text.setPlainText(self.store.get('allow_draft', ''))
        layout.addWidget(text)
        active = bool(self.focus.blocking())
        text.setReadOnly(active)
        if active:
            layout.addWidget(label('专注期间允许列表不可修改。', 'muted'))
        def save():
            if self.focus.blocking():
                self.notice('网站限制进行中', '个人专注和 B 站锁定均结束后才能修改允许列表。')
                return
            try:
                normalize_links(text.toPlainText())
                self.store.set('allow_draft', text.toPlainText().strip())
                self.refresh()
                win.accept()
            except ValueError as error:
                self.notice('检查视频链接', str(error))
        save_button = button('保存允许列表', save, 'primary')
        save_button.setEnabled(not active)
        layout.addWidget(save_button)
        self.present(win)

    def start_focus(self):
        if not self.bridge.ready():
            self.notice('先连接浏览器', 'Chrome 和 Edge 扩展都在线后才能开始。请打开两个浏览器。')
            return
        minutes = self.minutes.value()
        links = self.store.get('allow_draft', '')
        try:
            allow = normalize_links(links)
        except ValueError as error:
            self.notice('检查允许列表', str(error))
            return
        end = datetime.fromtimestamp(time.time() + minutes * 60).strftime('%H:%M')
        def begin():
            try:
                if not self.bridge.ready():
                    raise ValueError('浏览器连接已中断，请重新连接后开始。')
                self.focus.start(minutes, links)
                self.bridge.changed.set()
                QTimer.singleShot(1500, self.bridge.changed.clear)
                if self.popup:
                    self.popup.reject()
                self.tick()
            except ValueError as error:
                self.notice('未能开始专注', str(error))
        self.confirm('确认开始专注', f'专注 {minutes} 分钟，预计 {end} 结束。\n允许 {len(allow)} 个视频及其分 P。\n期间不能暂停、缩短、提前结束或修改允许列表。', begin)

    def preview(self):
        if self.session.meeting:
            self.status.setText('会议免打扰中。请先手动恢复提醒，再预览卡片。')
        elif self.focus.current():
            self.notice('专注进行中', '专注期间暂停启动提醒。')
        else:
            self.remind('')

    def remind(self, fixed='', title='先做一个小动作', bili=False):
        if self.session.meeting or self.focus.current():
            return None
        if self.popup:
            self.popup.reject()
        win, layout = self.new_dialog('启动提醒助手', width=560, topmost=True)
        self.popup = win
        if bili:
            layout.addWidget(label(BILI_WARNING, 'biliWarning', True))
        layout.addWidget(label(title, 'section'))
        text = label('', 'heroText', True)
        text.setMinimumHeight(70)
        layout.addWidget(text)
        now = self.clock()
        initial = fixed or next_action(now, self.cfg, self.store.tasks(now.date().isoformat()))[0]
        if bili:
            initial = switch_action(now, self.cfg, self.store.tasks(now.date().isoformat()),
                                    self.store.get('bili_last_action', ''), context=initial)[0]
            self.store.set('bili_last_action', initial)
        text.setText(initial)
        def choose():
            now = self.clock()
            candidate, _ = switch_action(now, self.cfg, self.store.tasks(now.date().isoformat()),
                                         text.text(), context=initial)
            text.setText(candidate)
            if bili:
                self.store.set('bili_last_action', candidate)
        layout.addWidget(label('做到这一步就可以停下。是否继续，由你决定。', 'muted', True))
        row = QHBoxLayout()
        row.addWidget(button('我开始了', win.accept, 'primary'))
        row.addWidget(button('换一步', choose))
        row.addWidget(button('休息一会', lambda: self.rest(win)))
        layout.addLayout(row)
        def focus_entry():
            win.accept()
            self.show()
            self.minutes.setFocus()
        footer = QHBoxLayout()
        footer.addWidget(button('暂缓 5 分钟', lambda: self.snooze(win)))
        footer.addStretch()
        footer.addWidget(button('进入专注  ›', focus_entry, 'quiet'))
        layout.addLayout(footer)
        win.finished.connect(lambda result: setattr(self, 'popup', None) if self.popup is win else None)
        self.present(win)
        self.log.info('Reminder displayed: %s', title)
        return win

    def snooze(self, parent):
        self.store.set('snooze_end', self.clock().timestamp() + 5 * 60)
        parent.accept()

    def rest(self, parent):
        win, layout = self.new_dialog('休息一会', width=380, topmost=True)
        layout.addWidget(label('选择休息分钟数', 'section'))
        value = QComboBox()
        value.setEditable(True)
        value.addItems(['5', '10', '20', '30', '60'])
        value.setCurrentText('10')
        layout.addWidget(value)
        def save():
            try:
                minutes = int(value.currentText())
                if not 1 <= minutes <= 1440:
                    raise ValueError()
            except ValueError:
                self.notice('时长无效', '请输入 1—1440 分钟。')
                return
            self.store.set('rest_end', time.time() + minutes * 60)
            win.accept()
            parent.accept()
        layout.addWidget(button('开始休息', save, 'primary'))
        self.present(win)

    def open_settings(self):
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.settings_dialog.raise_()
            return
        win, layout = self.new_dialog('设置', width=690)
        self.settings_dialog = win
        tabs = QTabWidget()
        layout.addWidget(tabs)
        shortcuts = QWidget()
        box = QVBoxLayout(shortcuts)
        box.setSpacing(14)
        box.addWidget(label('点击输入框，直接按下新的组合键。', 'section', True))
        box.addWidget(label('支持 Ctrl / Alt / Shift 搭配字母、数字、空格或 F1—F11。保存时检查系统占用。', 'muted', True))
        editors = {}
        current = self.store.get('hotkeys', DEFAULTS)
        for key, title in [('toggle', '显示 / 隐藏主窗口'), ('capture', '快速记录任务')]:
            box.addWidget(label(title))
            editor = QKeySequenceEdit(QKeySequence(current[key]))
            editor.setMaximumSequenceLength(1)
            editors[key] = editor
            box.addWidget(editor)
        result = label('', 'muted', True)
        box.addWidget(result)
        def save_keys():
            proposed = {key: editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText) for key, editor in editors.items()}
            try:
                self.hotkeys.configure(proposed)
                self.store.set('hotkeys', proposed)
                result.setText('已保存并生效。')
                self.status.setText('快捷键已更新。')
            except ValueError as error:
                result.setText(str(error))
        row = QHBoxLayout()
        def defaults():
            for key, editor in editors.items():
                editor.setKeySequence(QKeySequence(DEFAULTS[key]))
        row.addWidget(button('填入默认组合', defaults))
        row.addStretch()
        row.addWidget(button('保存快捷键', save_keys, 'primary'))
        box.addLayout(row)
        tabs.addTab(shortcuts, '快捷键')
        connection = QWidget()
        box = QVBoxLayout(connection)
        box.setSpacing(13)
        box.addWidget(label('浏览器连接', 'section'))
        box.addWidget(label('本机配对码，仅用于连接 Chrome / Edge 扩展。', 'muted', True))
        token = QLineEdit(self.bridge.token)
        token.setReadOnly(True)
        box.addWidget(token)
        box.addWidget(button('复制配对码', lambda: self.qt.clipboard().setText(self.bridge.token)))
        box.addSpacing(12)
        box.addWidget(label('AI 仍通过配置文件启用，模型可以随时更换。', wrap=True))
        box.addWidget(button('打开 AI 配置', lambda: os.startfile(ROOT / 'config' / 'ai.json')))
        box.addWidget(button('打开日历与课程配置', lambda: os.startfile(ROOT / 'config' / 'schedule.json')))
        def reload_rules():
            try:
                cfg = load_config()
                day_agenda(self.clock().date(), cfg)
                ordinary_allowed(self.clock(), cfg)
                self.cfg = cfg
                self.session.cfg = cfg
                self.agenda_signature = None
                self.refresh()
                self.status.setText('日历与课程配置已重新读取。')
            except (ValueError, KeyError, OSError) as error:
                self.notice('配置未更新', str(error))
        box.addWidget(button('重新读取日历配置', reload_rules))
        tabs.addTab(connection, '连接与配置')
        behavior = QWidget()
        box = QVBoxLayout(behavior)
        box.setSpacing(15)
        box.addWidget(label('后台与会议', 'section'))
        box.addWidget(label('点叉或 Alt+F4 会收进托盘，提醒继续运行。\n会议免打扰会收起窗口，暂停全部提醒，直到手动恢复。\n专注计时与网站限制不受会议模式影响，到期照常解除。', wrap=True))
        box.addWidget(button('恢复提醒' if self.session.meeting else '开启会议免打扰', lambda: (win.accept(), self.toggle_meeting())))
        box.addWidget(label('真正退出后，本次登录期间不再提醒。专注期间不可退出。', 'muted', True))
        box.addWidget(button('退出后台程序…', self.quit))
        box.addWidget(button('打开使用说明', lambda: os.startfile(ROOT / 'README.md')))
        tabs.addTab(behavior, '后台与会议')
        tabs.addTab(TodoPage(self.store), 'ToDo List')
        self.present(win)

    def login_reminder(self):
        if ordinary_allowed(self.clock(), self.cfg) and not self.locked and not self.session.meeting:
            self.remind('')

    def tick(self):
        if self.closed:
            return
        try:
            while not self.events.empty():
                kind, data = self.events.get_nowait()
                if kind == 'show':
                    self.show()
                elif kind == 'locked':
                    self.locked = data
                elif kind in ('unlock', 'resume') and data >= self.cfg['unlock_after_minutes'] * 60:
                    self.pending_return = True
                elif kind == 'draft':
                    self.ai_button.setEnabled(True)
                    if self.session.meeting:
                        self.deferred_draft = data
                        self.ai_button.setText('查看草稿')
                    else:
                        self.confirm_draft(data)
                elif kind == 'ai_error':
                    self.ai_button.setEnabled(True)
                    self.notice('AI 暂不可用', data)
                elif kind == 'error':
                    self.status.setText(data)
                    self.log.error(data)
                elif kind == 'windows_ready':
                    self.log.info('Windows lock/suspend listener ready')
            now = self.clock()
            returned = self.pending_return and not self.locked
            if returned:
                self.pending_return = False
            event = self.session.poll(now, self.locked, returned)
            usage_action = self.bridge.usage_action(now.timestamp(), self.locked)
            if usage_action == 'bili_lock':
                QTimer.singleShot(1500, self.bridge.changed.clear)
                self.status.setText('B 站累计停留已达 30 分钟，已锁定至次日早上 08:00。')
                self.log.info('Bilibili locked until next day 08:00 after 30-minute usage threshold')
            if event:
                self.remind(*event)
            if usage_action == 'remind' and not self.popup:
                if self.remind(bili=True):
                    self.bridge.usage_delivered()
            current = self.focus.current()
            self.start_button.setEnabled(not current)
            self.minutes.setEnabled(not current)
            for _, widget in self.duration_buttons:
                widget.setEnabled(not current)
            if current:
                seconds = max(0, int(current['end'] - time.time()))
                self.focus_label.setText(f'专注中  {seconds // 60:02d}:{seconds % 60:02d}  ·  {datetime.fromtimestamp(current["end"]).strftime("%H:%M")} 结束')
                self.start_button.setText('专注进行中')
            else:
                self.focus_label.setText('提醒不计时，专注才会限制网站。')
                self.start_button.setText('开始专注')
            clients = self.bridge.status()
            summaries = []
            for browser in ('Chrome', 'Edge'):
                client = clients.get(browser, {})
                online = time.time() - client.get('seen', 0) < 45
                text = '未连接' if not online else '连接异常' if client.get('error') else '已连接'
                if online and current and not client.get('error'):
                    text = '限制已同步' if client.get('id') == current['id'] else '正在同步…'
                summaries.append(browser + ' · ' + text)
            self.browser_label.setText('    /    '.join(summaries))
            bili_lock = self.focus.bili_lock()
            if bili_lock:
                self.usage_label.setText('B 站已锁定至 ' + datetime.fromtimestamp(bili_lock['end']).strftime('%m月%d日 08:00') + ' · 允许视频仍可播放')
            else:
                with self.bridge.usage_lock:
                    seconds = int(self.bridge.usage.seconds)
                    activity = dict(self.bridge.usage.clients)
                observed = any(time.time() - value['seen'] < 12 for value in activity.values())
                self.usage_label.setText(f'B 站本轮累计 {seconds // 60} 分 {seconds % 60} 秒 · 30 分钟后锁定' +
                                        (' · 计时上报正常' if observed else ' · 未收到计时上报，请重新加载扩展 1.2.0'))
            self.bridge.desktop = {'framework': 'Qt', 'version': 2, 'meeting_mode': self.session.meeting, 'locked': self.locked,
                                   'hotkeys': {key: value['text'] for key, value in self.hotkeys.bindings.items()},
                                   'tray_visible': bool(self.tray and self.tray.isVisible())}
            self.refresh()
        except Exception:
            self.log.exception('Desktop tick failed')
            self.status.setText('运行出现错误，请查看 data/app.log。')

    def quit(self):
        if self.focus.blocking():
            self.notice('网站限制进行中', '个人专注或 B 站锁定结束前不能退出后台。可以关闭窗口或开启会议免打扰。')
            return
        def exit_confirmed():
            if self.focus.blocking():
                self.notice('网站限制进行中', '个人专注或 B 站锁定结束前不能退出。')
                return
            self.shutdown()
            self.qt.quit()
        self.confirm('退出后台程序？', '退出后本次登录期间不再提醒。\n如果只是共享屏幕，可以使用会议免打扰。', exit_confirmed)

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        self.login_timer.stop()
        self.hotkeys.close()
        if self.tray:
            self.tray.hide()
        for win in list(self.dialogs):
            win.reject()
        self.root.hide()
        self.bridge.changed.set()
        self.bridge.server.shutdown()
        self.bridge.server.server_close()
        self.log_handler.close()
        self.log.removeHandler(self.log_handler)

    def run(self):
        try:
            self.qt.exec()
        finally:
            self.shutdown()
