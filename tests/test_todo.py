import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import QApplication, QLineEdit, QStyle, QStyleOptionFrame
from PySide6.QtGui import QInputMethodEvent
from PySide6.QtTest import QTest
from reminder.storage import Store
from reminder.todo import TodoModel, TodoPage
from reminder.theme import STYLE


class TodoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'test.sqlite3')
        self.store.set(TodoModel.KEY, ['课程同步', '二课同步', '页面调整'])

    def tearDown(self):
        self.temp.cleanup()

    def test_drag_payload_moves_up_down_and_persists_with_numbering(self):
        model = TodoModel(self.store)
        for source, destination, expected in [
            (2, 0, ['页面调整', '课程同步', '二课同步']),
            (0, 3, ['课程同步', '二课同步', '页面调整']),
        ]:
            payload = model.mimeData([model.index(source, 0), model.index(source, 1)])
            self.assertTrue(model.dropMimeData(payload, Qt.DropAction.MoveAction,
                                               destination, 0, QModelIndex()))
            reopened = TodoModel(Store(self.store.path))
            self.assertEqual([reopened.data(reopened.index(i, 1)) for i in range(3)], expected)
            self.assertEqual([model.data(model.index(i, 0)) for i in range(3)], [1, 2, 3])
        self.assertFalse(model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 1))

    def test_edit_add_delete_save_and_learning_task_isolation(self):
        self.store.add_tasks(['学习任务'])
        page = TodoPage(self.store)
        page.show()
        page.edit_button.click()
        page.model.setData(page.model.index(0, 1), '教务课表同步')
        page.model.delete(1)
        page.add_button.click()
        self.qt.processEvents()
        editor = page.table.findChild(QLineEdit)
        self.assertIsNotNone(editor)
        QTest.keyClicks(editor, 'API')
        QTest.mouseClick(page.edit_button, Qt.MouseButton.LeftButton)
        self.qt.processEvents()
        self.assertEqual(self.store.get(TodoModel.KEY), ['教务课表同步', '页面调整', 'API'])
        self.assertEqual([t['text'] for t in self.store.tasks()], ['学习任务'])
        self.assertFalse(page.model.editing)
        page.close()
        page.deleteLater()
        self.qt.processEvents()

    def test_drag_during_edit_does_not_save_unfinished_text_or_deletion(self):
        model = TodoModel(self.store)
        model.editing = True
        model.setData(model.index(0, 1), '未保存修改')
        model.delete(1)
        model.moveRows(QModelIndex(), 1, 1, QModelIndex(), 0)
        self.assertEqual(self.store.get(TodoModel.KEY), ['页面调整', '二课同步', '课程同步'])
        model.save()
        self.assertEqual(self.store.get(TodoModel.KEY), ['页面调整', '未保存修改'])

    def test_styled_editor_has_room_for_text_and_accepts_chinese(self):
        page = TodoPage(self.store)
        page.setStyleSheet(STYLE)
        page.resize(690, 420)
        page.show()
        page.edit_button.click()
        try:
            for new_row in (False, True):
                if new_row:
                    page.add_button.click()
                else:
                    index = page.model.index(0, 1)
                    page.table.setCurrentIndex(index)
                    page.table.edit(index)
                self.qt.processEvents()
                editor = next(e for e in page.table.findChildren(QLineEdit) if e.isVisible())
                editor.selectAll()
                event = QInputMethodEvent()
                event.setCommitString('中文输入')
                self.qt.sendEvent(editor, event)
                QTest.keyClicks(editor, ' API 123')
                self.assertEqual(editor.text(), '中文输入 API 123')
                option = QStyleOptionFrame()
                editor.initStyleOption(option)
                content = editor.style().subElementRect(QStyle.SubElement.SE_LineEditContents, option, editor)
                self.assertGreaterEqual(content.height(), editor.fontMetrics().height() + 2)
                self.assertTrue(page.table.visualRect(page.table.currentIndex()).contains(editor.geometry()))
                QTest.keyClick(editor, Qt.Key.Key_Return)
                self.qt.processEvents()
            page.edit_button.click()
            saved = self.store.get(TodoModel.KEY)
            self.assertEqual(saved[0], '中文输入 API 123')
            self.assertEqual(saved[-1], '中文输入 API 123')
        finally:
            page.close()
            page.deleteLater()
            self.qt.processEvents()


if __name__ == '__main__':
    unittest.main()
