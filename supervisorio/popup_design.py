"""Shared SCADA dialog styling and operating indicators."""
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QDialog, QWidget, QPushButton, QLineEdit, QComboBox, QProgressBar


def popup_owner(widget):
    current = widget
    while current is not None:
        if isinstance(current, QDialog) or current.objectName() == "scaledDialogContent":
            return current
        current = current.parentWidget()
    return None


def popup_stylesheet(widget, palette, existing):
    """Override old control geometry while retaining semantic label colors."""
    p = palette
    foreground = "#FFFFFF" if QColor(p['canvas']).lightnessF() > .5 else "#102D31"
    controls = f"""QPushButton {{background:{p['surface']};color:{p['text']};border:1px solid {p['border']};border-radius:7px;padding:8px 12px;font-family:Segoe UI;font-size:11px;font-weight:400;}}
QPushButton:hover {{background:{p['soft']};}}
QPushButton:focus {{border:1px solid {p['accent']};}}
QPushButton:disabled {{background:{p['canvas']};color:{p['disabled']};border-color:{p['border']};}}
QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {{background:{p['canvas']};color:{p['text']};border:1px solid {p['border']};border-radius:7px;padding:7px 10px;font-size:11px;}}
QLineEdit:focus,QComboBox:focus {{border-color:{p['accent']};}}
QTableWidget {{background:{p['surface']};alternate-background-color:{p['canvas']};color:{p['text']};border:1px solid {p['border']};border-radius:7px;gridline-color:{p['border']};selection-background-color:{p['soft']};selection-color:{p['text']};}}
QHeaderView::section {{background:{p['soft']};color:{p['muted']};border:0;padding:8px;font-size:11px;}}
QProgressBar {{background:{p['soft']};color:{p['muted']};border:0;border-radius:4px;text-align:center;}}
QProgressBar::chunk {{background:{p['accent']};border-radius:4px;}}
"""
    if isinstance(widget, QDialog) or widget.objectName() == "scaledDialogContent":
        return f"QWidget {{font-family:Segoe UI;}}\nQDialog,QWidget#scaledDialogContent {{background:{p['surface']};color:{p['text']};}}\nQLabel {{color:{p['text']};}}\n" + controls
    if isinstance(widget, QPushButton):
        name = widget.objectName().lower()
        text = widget.text().lower()
        danger = any(term in name + text for term in ('emergency', 'emergência', 'delete', 'excluir'))
        secondary = any(term in name + text for term in ('cancel', 'abortar', 'sair', 'fechar', 'concluir'))
        primary = (widget.isDefault() and not secondary) or any(term in name for term in ('login', 'cadastrar', 'actuator', 'confirm', 'proceed', 'finish'))
        bg = p['accent'] if primary and not danger else p['surface']
        color = p['danger'] if danger else foreground if primary else p['text']
        border = p['danger'] if danger else p['accent'] if primary else p['border']
        return controls + f"QPushButton {{background:{bg};color:{color};border-color:{border};}}\nQPushButton:focus {{border-color:{border if danger else p['accent']};}}"
    if isinstance(widget, (QLineEdit, QComboBox, QProgressBar)):
        return controls
    return existing


class WarningSymbol(QWidget):
    """Draw a warning triangle without depending on emoji font support."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.setAccessibleName("Aviso de segurança")

    def paintEvent(self, event):
        from appearance import palette_for
        color = QColor(palette_for()['warning'])
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath(QPointF(20, 4))
        path.lineTo(37, 35); path.lineTo(3, 35); path.closeSubpath()
        painter.setPen(QPen(color, 2)); painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(QPen(color, 3, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(20, 14, 20, 24); painter.drawPoint(20, 30)


class AnimatedOperationBar(QProgressBar):
    """Indeterminate operation animation, including inside a scaled dialog."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 0)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        self.setAccessibleName("Operação em andamento")
        self.phase = 0
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(30)
        self.animation_timer.timeout.connect(self._advance)

    def _advance(self):
        self.phase = (self.phase + .018) % 1
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.animation_timer.start()

    def hideEvent(self, event):
        self.animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        from appearance import palette_for
        p = palette_for()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        track = QPainterPath(); track.addRoundedRect(rect, 4, 4)
        painter.setClipPath(track)
        painter.fillRect(rect, QColor(p['soft']))
        width = max(24, self.width() * .28)
        x = self.phase * (self.width() + width) - width
        painter.setPen(Qt.NoPen); painter.setBrush(QColor(p['warning']))
        painter.drawRoundedRect(QRectF(x, 0, width, self.height()), 4, 4)


class OperatingAlertDialog(QDialog):
    """Esc cannot dismiss an active operation; controller close still works."""
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)

    def close(self):
        self._controller_closing = True
        try:
            return super().close()
        finally:
            self._controller_closing = False

    def closeEvent(self, event):
        if getattr(self, '_controller_closing', False):
            super().closeEvent(event)
        else:
            event.ignore()
