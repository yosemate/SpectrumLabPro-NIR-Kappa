"""Inset, grouped sidebar navigation painted in logical pixels."""
from PyQt5.QtCore import Qt, QRectF, QSize
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QStyledItemDelegate, QStyle
from appearance import palette_for


class NavigationDelegate(QStyledItemDelegate):
    GROUPS = {0: 'OPERAÇÃO E ANÁLISE', 5: 'SUPERVISÃO', 7: 'PREFERÊNCIAS'}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.compact_height = False

    def sizeHint(self, option, index):
        row, header = (34, 18) if self.compact_height else (44, 24)
        return QSize(210, row + (header if index.row() in self.GROUPS else 0))

    def paint(self, painter, option, index):
        p = palette_for()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        r = option.rect
        header = (18 if self.compact_height else 24) if index.row() in self.GROUPS else 0
        if header:
            font = QFont('Segoe UI')
            font.setPixelSize(10 if self.compact_height else 11)
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(p['muted']))
            painter.drawText(r.adjusted(18, 2, -10, -(r.height()-header)),
                             Qt.AlignVCenter, self.GROUPS[index.row()])
        area = QRectF(r.x()+8, r.y()+header+2, r.width()-16, r.height()-header-4)
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)
        if selected or hovered:
            fill = QColor(p['soft'])
            if not selected:
                fill.setAlpha(120)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(area, 7, 7)
        if selected:
            painter.setBrush(QColor(p['accent']))
            painter.drawRoundedRect(QRectF(area.left()+4, area.center().y()-11, 3, 22), 1.5, 1.5)
        color = QColor(p['accent'] if selected else p['muted'])
        painter.save()
        painter.translate(area.left()+15, area.center().y()-10)
        self.draw_icon(painter, index.row(), color)
        painter.restore()
        font = QFont('Segoe UI')
        font.setPixelSize(12 if self.compact_height else 13)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(p['text'] if selected else p['muted']))
        text_area = QRectF(area.left()+42, area.top()+2, area.width()-50, area.height()-4)
        painter.drawText(text_area, Qt.AlignVCenter | Qt.TextWordWrap, str(index.data()))
        if option.state & QStyle.State_HasFocus:
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(p['accent']), 1, Qt.DotLine))
            painter.drawRoundedRect(area.adjusted(1, 1, -1, -1), 6, 6)
        painter.restore()

    @staticmethod
    def draw_icon(painter, row, color):
        painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        if row == 0:
            for x,y,w,h in ((2,2,6,7),(12,2,6,4),(2,13,6,5),(12,10,6,8)):
                painter.drawRoundedRect(QRectF(x,y,w,h), 1, 1)
        elif row == 1:
            path=QPainterPath();path.moveTo(5,2);path.lineTo(17,10);path.lineTo(5,18);path.closeSubpath()
            painter.drawPath(path)
        elif row == 2:
            path=QPainterPath();path.moveTo(2,16);path.lineTo(6,12);path.lineTo(9,14);path.lineTo(13,5);path.lineTo(18,8)
            painter.drawPath(path)
            painter.drawLine(2,2,2,18);painter.drawLine(2,18,18,18)
        elif row == 3:
            for x,y in ((4,6),(10,14),(16,8)):
                painter.drawLine(x,2,x,18)
                painter.setBrush(QColor(color));painter.drawEllipse(QRectF(x-2,y-2,4,4));painter.setBrush(Qt.NoBrush)
        elif row == 4:
            painter.drawEllipse(QRectF(2,2,16,16))
            painter.drawLine(10,5,10,10);painter.drawLine(10,10,14,12)
        elif row == 5:
            path=QPainterPath();path.moveTo(12,2);path.cubicTo(7,1,5,5,7,9);path.lineTo(2,15)
            path.cubicTo(0,18,3,20,5,17);path.lineTo(11,11);path.cubicTo(16,13,20,8,18,5)
            path.lineTo(15,8);path.lineTo(12,5);path.closeSubpath();painter.drawPath(path)
        elif row == 6:
            path=QPainterPath();path.moveTo(3,15);path.lineTo(5,12);path.lineTo(5,7)
            path.cubicTo(5,0,15,0,15,7);path.lineTo(15,12);path.lineTo(17,15);path.closeSubpath()
            painter.drawPath(path);painter.drawArc(8,14,4,5,180*16,180*16)
        else:
            painter.drawEllipse(QRectF(5,5,10,10));painter.drawEllipse(QRectF(8,8,4,4))
            for x1,y1,x2,y2 in ((10,2,10,5),(10,15,10,18),(2,10,5,10),(15,10,18,10),
                                  (4,4,6,6),(14,14,16,16),(4,16,6,14),(14,6,16,4)):
                painter.drawLine(x1,y1,x2,y2)
