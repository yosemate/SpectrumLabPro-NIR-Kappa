"""Composição SCADA aprovada: controles à esquerda, bandas à direita, diagnóstico abaixo."""
from PyQt5.QtCore import Qt,QTimer,QSize,QRectF
from PyQt5.QtGui import QPainter,QColor,QPen,QPainterPath
from PyQt5.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,
                             QSplitter,QDialog,QSizePolicy)
from brand_assets import institutional_signature
from diagnostics import ControllerDiagnosticsCard
from responsive_layout import ScaledCanvasView

class SpectrumMark(QWidget):
    """Six spectral bands and a response curve, drawn crisply at any display scale."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFixedSize(36,36)
        self.setAccessibleName("Ícone de espectro óptico")
    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#123F48'))
        painter.drawRoundedRect(QRectF(0,0,36,36),9,9)
        for i,(height,color) in enumerate(zip((8,14,21,17,12,7),
                ('#7BDDD4','#55CFC5','#37BDB2','#44AEC0','#789ED4','#A394D6'))):
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(6+i*4.2,29-height,2.6,height),1.3,1.3)
        curve=QPainterPath();curve.moveTo(5,21)
        curve.cubicTo(11,21,12,6,18,8)
        curve.cubicTo(23,9,24,19,31,20)
        painter.setPen(QPen(QColor('#DCF8F5'),1.4));painter.setBrush(Qt.NoBrush)
        painter.drawPath(curve)


def panel():
    box=QFrame();box.setObjectName('scadaPanel');return box

def label(text,size=12,muted=False):
    out=QLabel(text)
    out.setStyleSheet(f'font-size: {size}px;'+('color: #9CA3AF;' if muted else ''))
    return out

def open_login(window):
    if window.authenticated_user:
        window.logout_action();return
    from auth_dialogs import DialogLogin
    dialog=DialogLogin(window.auth_manager,window)
    if dialog.exec_()==QDialog.Accepted and dialog.usuario_logado:
        window.authenticated_user=dialog.usuario_logado
        window.is_manual_mode_unlocked=True
        window.current_operator_name=dialog.usuario_logado.get('username','Operador')
        window.log_message('Sessão autenticada: '+window.current_operator_name)

def build_dashboard(w):
    from responsive_ui import build_responsive_dashboard
    build_responsive_dashboard(w)
