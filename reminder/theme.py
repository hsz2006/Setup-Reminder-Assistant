from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

BG = '#DDD1BD'
CARD = '#EDE3D3'
SOFT = '#E6DCCB'
INK = '#443F35'
MUTED = '#7B7566'
SAGE = '#748067'

STYLE = '''
QWidget { color: #443F35; font-family: 'Microsoft YaHei UI'; font-size: 13px; }
QMainWindow, QDialog { background: #DDD1BD; }
QWidget#dashboard { background: #DDD1BD; }
QFrame#card { background: #EDE3D3; border: 1px solid #E4D8C5; border-top-color: #F5ECDD; border-bottom-color: #D6CAB7; border-radius: 18px; }
QFrame#hero { background: #E3DBC7; border: 1px solid #CEC9B1; border-radius: 14px; }
QFrame#taskRow { background: #E9DFCE; border: 1px solid #DED2BF; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel#title { font-size: 30px; font-weight: 650; color: #3D392F; }
QLabel#section { font-size: 18px; font-weight: 600; }
QLabel#biliWarning { color: #B43F36; font-size: 16px; font-weight: 600; }
QLabel#heroText { font-size: 22px; font-weight: 600; }
QLabel#muted { color: #7B7566; }
QLabel#date { font-size: 14px; color: #7B7566; }
QLabel#badge { color: #56644B; background: #D8DDC8; border-radius: 9px; padding: 5px 10px; font-size: 11px; }
QLabel#meetingBanner { background: #D1D8C0; color: #48533F; border-radius: 10px; padding: 10px 16px; }
QPushButton { background: #E5DBC8; border: 1px solid #CFC3AF; border-radius: 10px; padding: 10px 16px; }
QPushButton:hover { background: #DBD3BF; border-color: #AFAE95; }
QPushButton:pressed { background: #CEC9B1; }
QPushButton:focus { border: 2px solid #748067; }
QPushButton:disabled { color: #A19A8B; background: #E4DACA; border-color: #D6CBB9; }
QPushButton#primary { background: #748067; color: #F1EBDD; border: 1px solid #748067; font-weight: 600; }
QPushButton#primary:hover { background: #647158; }
QPushButton#primary:disabled { background: #A8AE97; border-color: #A8AE97; }
QPushButton#quiet { background: transparent; border: none; color: #777461; padding: 7px 9px; }
QPushButton#quiet:hover { background: #DED5C3; color: #454C3C; }
QPushButton#duration { background: #E6DCCA; padding: 8px 13px; min-width: 27px; }
QPushButton#duration:checked { background: #748067; color: #F1EBDD; border-color: #748067; }
QPushButton#round { border-radius: 12px; padding: 0px; min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; }
QLineEdit, QTextEdit, QPlainTextEdit, QKeySequenceEdit, QSpinBox, QComboBox {
 background: #F0E7D7; border: 1px solid #CFC3AF; border-radius: 10px; padding: 10px; selection-background-color: #748067; selection-color: #F5EFDF;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QKeySequenceEdit:focus { border: 1px solid #748067; }
QSpinBox:disabled, QTextEdit:disabled { background: #E2D9C9; color: #8A8477; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 7px; background: transparent; margin: 3px; }
QScrollBar::handle:vertical { background: #B7B59E; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QMenu { background: #EDE3D3; border: 1px solid #CFC3AF; padding: 6px; }
QMenu::item { padding: 8px 22px; border-radius: 6px; }
QMenu::item:selected { background: #D6DCC7; }
QTabWidget::pane { background: #EDE3D3; border: 1px solid #D2C7B3; border-radius: 12px; padding: 12px; }
QTabBar::tab { background: #DCD2C0; padding: 10px 20px; margin-right: 4px; border-top-left-radius: 9px; border-top-right-radius: 9px; }
QTabBar::tab:selected { background: #EDE3D3; color: #56644B; }
QTableView#improvementTodo { background: #F0E7D7; alternate-background-color: #EDE3D3; border: 1px solid #CFC3AF; gridline-color: #D6CBB9; selection-background-color: #D6DCC7; selection-color: #443F35; }
QTableView#improvementTodo::item { padding: 9px; }
QTableView#improvementTodo QLineEdit { padding: 1px 6px; border-radius: 4px; color: #443F35; background: #F0E7D7; }
QTableView#improvementTodo QHeaderView::section { background: #E5DBC8; color: #443F35; border: none; padding: 9px; }
QToolTip { background: #EDE3D3; color: #443F35; border: 1px solid #CFC3AF; padding: 6px; }
'''


def app_icon(size=128):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(SAGE))
    painter.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), size * .24, size * .24)
    path = QPainterPath()
    path.moveTo(size * .30, size * .70)
    path.cubicTo(size * .20, size * .33, size * .52, size * .22, size * .76, size * .25)
    path.cubicTo(size * .81, size * .51, size * .62, size * .76, size * .30, size * .70)
    painter.setBrush(QColor('#E9E3CB'))
    painter.drawPath(path)
    painter.setPen(QPen(QColor(SAGE), size * .035, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(size * .30, size * .78), QPointF(size * .63, size * .40))
    painter.end()
    return QIcon(pix)
