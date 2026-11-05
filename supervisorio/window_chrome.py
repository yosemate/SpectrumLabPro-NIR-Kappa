"""Integrated window bar; native system move/resize and accessible controls."""
from PyQt5.QtCore import Qt, QObject, QEvent, QPoint, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QMenuBar, QAbstractButton,
                             QApplication, QSizeGrip, QSizePolicy)
from appearance import palette_for


class WindowButton(QAbstractButton):
    def __init__(self, kind, window, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.host_window = window
        self.setFixedSize(44, 32)
        self.setFocusPolicy(Qt.StrongFocus)
        names = {'minimize': 'Minimizar', 'maximize': 'Maximizar ou restaurar', 'close': 'Fechar programa'}
        self.setAccessibleName(names[kind])
        self.setToolTip(names[kind])

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        p = palette_for()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.isDown() or self.hasFocus():
            painter.fillRect(self.rect(), QColor(p['danger'] if self.kind == 'close' else p['soft']))
        color = '#FFFFFF' if self.kind == 'close' and (self.underMouse() or self.isDown() or self.hasFocus()) else p['text']
        painter.setPen(QPen(QColor(color), 1.25))
        x, y = self.width()/2, self.height()/2
        if self.kind == 'minimize':
            painter.drawLine(QPoint(int(x-5), int(y+3)), QPoint(int(x+5), int(y+3)))
        elif self.kind == 'close':
            painter.drawLine(QPoint(int(x-4), int(y-4)), QPoint(int(x+4), int(y+4)))
            painter.drawLine(QPoint(int(x+4), int(y-4)), QPoint(int(x-4), int(y+4)))
        elif self.host_window.isMaximized():
            painter.drawRect(QRectF(x-3, y-5, 8, 8))
            painter.fillRect(QRectF(x-5, y-3, 8, 8), QColor(p['surface']))
            painter.drawRect(QRectF(x-5, y-3, 8, 8))
        else:
            painter.drawRect(QRectF(x-5, y-5, 10, 10))


class WindowChrome(QWidget):
    def __init__(self, window):
        super().__init__(window)
        self.host_window = window
        self.drag_offset = None
        self.resize_origin = None
        self.setObjectName('windowChrome')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setFixedHeight(32)
        self.setAccessibleName('Barra da janela. Arraste para mover; clique duas vezes para maximizar.')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.setSpacing(0)
        old_menu = window.menuBar()
        self.menu = QMenuBar(self)
        self.menu.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        for action in list(old_menu.actions()):
            menu = action.menu()
            if menu is not None:
                menu.setParent(self.menu, menu.windowFlags())
                menu.hide()
                self.menu.addMenu(menu)
        old_menu.clear()
        layout.addWidget(self.menu)
        layout.addStretch(1)
        self.minimize_button = WindowButton('minimize', window, self)
        self.maximize_button = WindowButton('maximize', window, self)
        self.close_button = WindowButton('close', window, self)
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)
        for control in (self.minimize_button, self.maximize_button, self.close_button):
            layout.addWidget(control)
        window.setWindowFlag(Qt.FramelessWindowHint, True)
        window.setMenuWidget(self)
        self.grip = QSizeGrip(window)
        self.grip.setFixedSize(14, 14)
        self.grip.setToolTip('Redimensionar janela')
        window.setMouseTracking(True)
        window.responsive_shell.root.setMouseTracking(True)
        QApplication.instance().installEventFilter(self)
        self._scada_style_factory = lambda p: f'''
QWidget#windowChrome {{background:{p['surface']};border-bottom:1px solid {p['border']};}}
QMenuBar {{background:{p['surface']};color:{p['text']};font-size:13px;}}
QMenuBar::item {{padding:6px 10px;background:transparent;}}
QMenuBar::item:selected {{background:{p['soft']};}}
'''
        window.theme_manager.apply_widget(self)
        self.update_grip()

    def toggle_maximized(self):
        if self.host_window.isMaximized():
            self.host_window.showNormal()
        else:
            self.host_window.showMaximized()
        self.update_grip()

    def update_grip(self):
        self.grip.move(self.host_window.width()-self.grip.width()-2,
                       self.host_window.height()-self.grip.height()-2)
        self.grip.setVisible(not self.host_window.isMaximized())
        self.grip.raise_()
        self.maximize_button.update()

    def edges_at(self, global_position):
        if self.host_window.isMaximized() or self.host_window.isFullScreen():
            return Qt.Edges()
        point = self.host_window.mapFromGlobal(global_position)
        edges = Qt.Edges()
        if 0 <= point.x() < 5:
            edges |= Qt.LeftEdge
        elif self.host_window.width()-5 <= point.x() < self.host_window.width():
            edges |= Qt.RightEdge
        if 0 <= point.y() < 5:
            edges |= Qt.TopEdge
        elif self.host_window.height()-5 <= point.y() < self.host_window.height():
            edges |= Qt.BottomEdge
        return edges

    def eventFilter(self, obj, event):
        if obj is self.host_window and event.type() in (QEvent.Resize, QEvent.WindowStateChange):
            self.update_grip()
        if not isinstance(obj, QWidget) or obj.window() is not self.host_window:
            return False
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            edges = self.edges_at(event.globalPos())
            handle = self.host_window.windowHandle()
            if edges and handle:
                if not handle.startSystemResize(edges):
                    self.resize_origin = (edges, event.globalPos(), self.host_window.geometry())
                    self.host_window.grabMouse()
                return True
        elif event.type() == QEvent.MouseMove:
            if self.resize_origin:
                edges, origin, initial = self.resize_origin
                delta = event.globalPos()-origin
                rect = initial.adjusted(delta.x() if edges & Qt.LeftEdge else 0,
                                        delta.y() if edges & Qt.TopEdge else 0,
                                        delta.x() if edges & Qt.RightEdge else 0,
                                        delta.y() if edges & Qt.BottomEdge else 0)
                if rect.width() >= self.host_window.minimumWidth() and rect.height() >= self.host_window.minimumHeight():
                    self.host_window.setGeometry(rect)
                return True
            edges = self.edges_at(event.globalPos())
            if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
                self.host_window.setCursor(Qt.SizeFDiagCursor)
            elif edges in (Qt.RightEdge | Qt.TopEdge, Qt.LeftEdge | Qt.BottomEdge):
                self.host_window.setCursor(Qt.SizeBDiagCursor)
            elif edges & (Qt.LeftEdge | Qt.RightEdge):
                self.host_window.setCursor(Qt.SizeHorCursor)
            elif edges:
                self.host_window.setCursor(Qt.SizeVerCursor)
            else:
                self.host_window.unsetCursor()
        elif event.type() == QEvent.MouseButtonRelease and self.resize_origin:
            self.resize_origin = None
            self.host_window.releaseMouse()
            return True
        return False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximized()
            event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.host_window.windowHandle()
            if handle and handle.startSystemMove():
                return
            if not self.host_window.isMaximized():
                self.drag_offset = event.globalPos()-self.host_window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.host_window.move(event.globalPos()-self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_offset = None


def install_window_chrome(window):
    window.window_chrome = WindowChrome(window)
