"""Independent improvement backlog, with persistent drag ordering."""
import json

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QMimeData
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableView, QAbstractItemView, QHeaderView, QStyledItemDelegate)


class TodoDelegate(QStyledItemDelegate):
    def updateEditorGeometry(self, editor, option, index):
        # Use the cell area rather than the padded display-text rectangle.
        editor.setGeometry(option.rect.adjusted(3, 2, -3, -2))


class TodoModel(QAbstractTableModel):
    KEY = 'improvement_todo'
    MIME = 'application/x-study-reminder-todo-row'

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.entries = [[text, text] for text in store.get(self.KEY, [])]
        self.saved_order = list(self.entries)
        self.editing = False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.entries)

    def columnCount(self, parent=QModelIndex()):
        return 2

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return index.row() + 1 if index.column() == 0 else self.entries[index.row()][0]

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return ('序号', '改进内容')[section]

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        if self.editing and index.column() == 1:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not self.editing or not index.isValid() or index.column() != 1 or role != Qt.ItemDataRole.EditRole:
            return False
        self.entries[index.row()][0] = str(value)
        self.dataChanged.emit(index, index, [role, Qt.ItemDataRole.DisplayRole])
        return True

    def mimeTypes(self):
        return [self.MIME]

    def mimeData(self, indexes):
        mime = QMimeData()
        rows = sorted({index.row() for index in indexes if index.isValid()})
        if rows:
            mime.setData(self.MIME, json.dumps(rows[0]).encode())
        return mime

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.DropAction.IgnoreAction:
            return True
        if action != Qt.DropAction.MoveAction or not data.hasFormat(self.MIME):
            return False
        try:
            source = int(json.loads(bytes(data.data(self.MIME))))
        except (ValueError, TypeError):
            return False
        destination = row if row >= 0 else (parent.row() if parent.isValid() else self.rowCount())
        return self.moveRows(QModelIndex(), source, 1, QModelIndex(), destination)

    def moveRows(self, source_parent, source, count, destination_parent, destination):
        if source_parent.isValid() or destination_parent.isValid() or count != 1:
            return False
        if not 0 <= source < len(self.entries) or not 0 <= destination <= len(self.entries):
            return False
        if destination in (source, source + 1):
            return False
        self.beginMoveRows(source_parent, source, source, destination_parent, destination)
        entry = self.entries.pop(source)
        self.entries.insert(destination - (destination > source), entry)
        self.endMoveRows()
        self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, 0))
        # Dragging persists the order, but does not commit unfinished text edits.
        visible = [entry for entry in self.entries if entry[1] is not None]
        visible_ids = {id(entry) for entry in visible}
        reordered = iter(visible)
        self.saved_order = [next(reordered) if id(entry) in visible_ids else entry
                            for entry in self.saved_order]
        self.store.set(self.KEY, [entry[1] for entry in self.saved_order])
        return True

    def add(self):
        row = self.rowCount()
        self.beginInsertRows(QModelIndex(), row, row)
        self.entries.append(['', None])
        self.endInsertRows()

    def delete(self, row):
        if 0 <= row < self.rowCount():
            self.beginRemoveRows(QModelIndex(), row, row)
            self.entries.pop(row)
            self.endRemoveRows()

    def save(self):
        texts = [text.strip() for text, _ in self.entries if text.strip()]
        self.store.set(self.KEY, texts)
        self.beginResetModel()
        self.entries = [[text, text] for text in texts]
        self.saved_order = list(self.entries)
        self.editing = False
        self.endResetModel()


class TodoPage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        hint = QLabel('拖动条目调整顺序，松开后自动保存。')
        hint.setObjectName('muted')
        layout.addWidget(hint)
        self.model = TodoModel(store, self)
        self.table = QTableView()
        self.table.setObjectName('improvementTodo')
        self.table.setModel(self.model)
        self.table.setItemDelegate(TodoDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setDragDropOverwriteMode(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(230)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        self.add_button = QPushButton('添加')
        self.delete_button = QPushButton('删除')
        self.edit_button = QPushButton('编辑')
        for widget in (self.add_button, self.delete_button):
            widget.hide()
            row.addWidget(widget)
        row.addStretch()
        row.addWidget(self.edit_button)
        layout.addLayout(row)
        self.add_button.clicked.connect(self.add)
        self.delete_button.clicked.connect(lambda: self.model.delete(self.table.currentIndex().row()))
        self.edit_button.clicked.connect(self.toggle_edit)

    def add(self):
        self.model.add()
        index = self.model.index(self.model.rowCount() - 1, 1)
        self.table.setCurrentIndex(index)
        self.table.edit(index)

    def toggle_edit(self):
        if self.model.editing:
            self.table.setFocus()  # Commit the active cell editor before saving.
            self.model.save()
        else:
            self.model.editing = True
        editing = self.model.editing
        self.edit_button.setText('保存' if editing else '编辑')
        self.add_button.setVisible(editing)
        self.delete_button.setVisible(editing)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
            if editing else QAbstractItemView.EditTrigger.NoEditTriggers)
