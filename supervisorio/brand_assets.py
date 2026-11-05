"""Marcas institucionais obtidas nos sites oficiais, incluídas no executável."""
import sys
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtGui import QPixmap,QPainter,QIcon
from PyQt5.QtWidgets import QWidget,QHBoxLayout,QLabel

def resource_path(name):
    return Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets'/'brands'/name

def application_icon():
    return QIcon(str(Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets'/'app_icon.ico'))

def logo_pixmap(name,width=100,height=28):
    pix=QPixmap(width*2,height*2);pix.fill(Qt.transparent)
    renderer=QSvgRenderer(str(resource_path(name+'.svg')))
    if not renderer.isValid():return QPixmap()
    size=renderer.defaultSize();size.scale(width*2-12,height*2-12,Qt.KeepAspectRatio)
    painter=QPainter(pix)
    from PyQt5.QtCore import QRectF
    renderer.render(painter,QRectF((pix.width()-size.width())/2,(pix.height()-size.height())/2,size.width(),size.height()))
    painter.end();pix.setDevicePixelRatio(2)
    return pix

def institutional_signature(parent=None):
    box=QWidget(parent);layout=QHBoxLayout(box);layout.setContentsMargins(0,0,0,0);layout.setSpacing(18)
    for name in ('senai','arauco'):
        label=QLabel();label.setObjectName('institution_'+name);label.setPixmap(logo_pixmap(name));label.setToolTip(name.upper())
        layout.addWidget(label)
    return box
