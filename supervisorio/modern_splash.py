"""Abertura animada; progresso acompanha as etapas reais de inicialização."""
from PyQt5.QtWidgets import QWidget,QApplication,QGraphicsOpacityEffect
from PyQt5.QtCore import Qt,QTimer,pyqtSignal,QPropertyAnimation,QEasingCurve,QRectF,QPointF,QElapsedTimer
from PyQt5.QtGui import QPainter,QColor,QPen,QFont,QPainterPath
from appearance import palette_for
from brand_assets import logo_pixmap
from version import __version__

class AnimatedSplashScreen(QWidget):
    finished=pyqtSignal()
    def __init__(self, minimum_duration_ms=4500):
        super().__init__();self.setWindowFlags(Qt.FramelessWindowHint|Qt.SplashScreen)
        self.setAttribute(Qt.WA_TranslucentBackground,True)
        area=QApplication.primaryScreen().availableGeometry()
        scale=min(1,(area.width()-40)/900,(area.height()-40)/520)
        self.resize(round(900*scale),round(520*scale));self.move(area.center()-self.rect().center())
        self.progress_val=0;self.status='Preparando o supervisório';self.phase=0;self._finishing=False
        self.minimum_duration_ms=max(0,int(minimum_duration_ms))
        self.elapsed=QElapsedTimer();self._ready=False;self.loading_phase=0.0;self.display_progress=0.0
        self.timer=QTimer(self);self.timer.timeout.connect(self.advance_animation)
        self.opacity_effect=QGraphicsOpacityEffect(self);self.setGraphicsEffect(self.opacity_effect);self.opacity_effect.setOpacity(1)
        self.logos=[logo_pixmap(n,100,28) for n in ('senai','arauco')]
    def start_animation(self):
        self.elapsed.start();self.show();self.timer.start(25)
    def advance_animation(self):
        self.phase=min(1,self.phase+.018)
        self.loading_phase=(self.loading_phase+.015)%1
        self.display_progress += (self.progress_val-self.display_progress)*.08
        if self._ready and not self._finishing and self.elapsed.isValid() and self.elapsed.elapsed()>=self.minimum_duration_ms:
            self._begin_fade()
        self.update()
    def set_stage(self,value,status):
        self.progress_val=max(self.progress_val,min(100,int(value)));self.status=status;self.update();QApplication.processEvents()
    def mark_ready(self):
        if self._ready:return
        self._ready=True
        self.set_stage(100,'Supervisório pronto')
        if self.elapsed.isValid() and self.elapsed.elapsed()>=self.minimum_duration_ms:
            self._begin_fade()
    def _begin_fade(self):
        if self._finishing:return
        self._finishing=True;self.fade_anim=QPropertyAnimation(self.opacity_effect,b'opacity',self)
        self.fade_anim.setDuration(450);self.fade_anim.setStartValue(1);self.fade_anim.setEndValue(0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutQuad);self.fade_anim.finished.connect(self.on_fade_finished);self.fade_anim.start()
    def on_fade_finished(self):self.timer.stop();self.hide();self.finished.emit()
    def paintEvent(self,event):
        c=palette_for();p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.scale(self.width()/900,self.height()/520)
        p.setPen(Qt.NoPen);p.setBrush(QColor(c['surface']));p.drawRoundedRect(QRectF(0,0,900,520),14,14)
        p.setBrush(QColor(c['soft']));p.drawRect(QRectF(450,0,450,520))
        def text(x,y,value,size,key='text'):
            font=QFont('Segoe UI');font.setPixelSize(size);p.setFont(font);p.setPen(QColor(c[key]));p.drawText(QPointF(x,y),value)
        text(45,68,'SCADA',27);text(45,89,'SPECTRUMLAB PRO · '+__version__,10,'muted')
        text(45,174,'TECNOLOGIA APLICADA À CELULOSE',10,'accent')
        text(45,230,'Da luz',43);text(45,277,'à análise.',43)
        text(45,323,'Controle da bancada, aquisição espectral',13,'muted');text(45,344,'e análise demonstrativa de celulose.',13,'muted')
        p.setPen(Qt.NoPen);p.setBrush(QColor(c['border']));p.drawRoundedRect(QRectF(45,391,340,8),4,4)
        fill_width=340*self.display_progress/100
        track=QPainterPath();track.addRoundedRect(QRectF(45,391,fill_width,8),4,4)
        p.fillPath(track,QColor(c['accent']))
        p.save();p.setClipPath(track)
        shine=QColor(c['surface']);shine.setAlpha(80)
        p.fillRect(QRectF(45+self.loading_phase*400-60,391,60,8),shine);p.restore()
        text(45,421,self.status,11,'muted');text(351,421,f'{self.progress_val}%',10,'accent')
        for i,logo in enumerate(self.logos):p.drawPixmap(45+i*122,461,logo)
        bottom=310;points=[]
        for i,v in enumerate([.32,.48,.59,.67,.75,.81]):
            x=500+i*62;y=bottom-190*v*self.phase
            p.setPen(QPen(QColor(c['border']),1));p.drawLine(QPointF(x-19,130),QPointF(x-19,bottom))
            fill=QColor(c['accent']);fill.setAlpha(55);p.setPen(Qt.NoPen);p.setBrush(fill)
            p.drawRoundedRect(QRectF(x-19,y,38,bottom-y),3,3);points.append(QPointF(x,y))
        path=QPainterPath();path.moveTo(points[0])
        for point in points[1:]:path.lineTo(point)
        p.setPen(QPen(QColor(c['accent']),2.3));p.setBrush(Qt.NoBrush);p.drawPath(path);p.setBrush(QColor(c['surface']))
        for point in points:p.drawEllipse(point,3,3)
        text(490,367,'Seis canais. Uma nova perspectiva.',18);text(490,394,'Protótipo acadêmico · SENAI / Projeto ARAUCO',11,'muted')
