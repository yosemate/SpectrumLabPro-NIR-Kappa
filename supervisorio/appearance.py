"""Temas persistentes para widgets, estilos dinâmicos e gráficos."""
import json,os,re,tempfile,weakref
from pathlib import Path
from PyQt5 import sip
from PyQt5.QtCore import QObject,QEvent,QTimer,Qt
from PyQt5.QtGui import QColor,QPalette
from PyQt5.QtWidgets import (QApplication,QWidget,QLabel,QPushButton,QComboBox,QDialog,
                             QVBoxLayout,QHBoxLayout,QFrame,QTabWidget,QMenu)
from popup_design import popup_owner, popup_stylesheet
PALETTES={
 "light":{"canvas":"#AEB8BF","surface":"#BEC5C9","soft":"#A2B7B0","border":"#86969F",
          "text":"#162C36","muted":"#304650","disabled":"#66767F","accent":"#204B47",
          "positive":"#204A38","warning":"#5B3D12","danger":"#772735"},
 "dark":{"canvas":"#111B24","surface":"#1B2934","soft":"#223C40","border":"#2D4058",
         "text":"#E8EFF8","muted":"#A2B3C9","disabled":"#718299","accent":"#76D8D0",
         "positive":"#6DD6AE","warning":"#F0C478","danger":"#FF98A0"}
}
def current_theme():
    app=QApplication.instance()
    return app.property("spectrum_theme") or "light" if app else "light"
def palette_for(theme=None):return PALETTES.get(theme or current_theme(),PALETTES["light"])
def mapped_color(value,kind="text",theme=None):
    p=palette_for(theme);color=QColor(value)
    if not color.isValid():return value
    hue,saturation,lightness,_=color.getHslF()
    neutral=saturation<0.20 or hue<0
    if kind=="border":return p["border"]
    if kind=="surface":
        if neutral or (lightness<0.20 and 0.48<hue<0.72):
            return p["canvas"] if value.lower() in ("#202020","#0f172a","#18181b","#111B24") else p["surface"]
        if lightness<0.35:
            if hue<0.08 or hue>0.90:return "#C8B6BB" if (theme or current_theme())=="light" else "#38232F"
            return p["soft"]
        return {"positive":"#087F5B","danger":"#C73544","accent":"#087D7B"}[
            "danger" if hue<0.08 or hue>0.90 else "positive" if hue<0.47 else "accent"]
    if neutral:
        if lightness>0.82:return p["text"]
        return p["disabled"] if lightness<0.38 else p["muted"]
    if hue<0.08 or hue>0.90:return p["danger"]
    if hue<0.19:return p["warning"]
    if hue<0.47:return p["positive"]
    if kind=="accent" and hue>0.72:
        return "#7952B3" if (theme or current_theme())=="light" else "#C3ABF4"
    return p["accent"]
def theme_color(value,kind="text"):return mapped_color(value,kind)

COLOR=re.compile(r"#[0-9a-fA-F]{6}\b")
DECL=re.compile(r"(background(?:-color)?|color|border(?:-(?:color|top|bottom|left|right))?)\s*:\s*([^;{}]+)(;|$)",re.I)
def transform_stylesheet(source,theme):
    def block(text):
        strong=False
        bg=re.search(r"background(?:-color)?\s*:\s*([^;]+)",text,re.I)
        if bg:
            colors=COLOR.findall(bg.group(1))
            strong=any(QColor(c).hslSaturationF()>0.4 and QColor(c).lightnessF()>0.30 for c in colors)
        def declaration(match):
            prop,value,end=match.groups()
            kind="surface" if prop.lower().startswith("background") else "border" if prop.lower().startswith("border") else "text"
            if prop.lower()=="color" and strong:
                value=COLOR.sub(lambda m:"#FFFFFF" if QColor(m[0]).lightnessF()>0.82 else mapped_color(m[0],kind,theme),value)
            else:value=COLOR.sub(lambda m:mapped_color(m[0],kind,theme),value)
            if kind=="surface" and "qlineargradient" in value:
                colors=COLOR.findall(value)
                if colors:value=colors[0]
            return f"{prop}: {value}{end}"
        return DECL.sub(declaration,text)
    if "{" not in source:return block(source)
    return re.sub(r"\{([^{}]*)\}",lambda m:"{"+block(m.group(1))+"}",source)

def preferences_path():
    base=os.environ.get("SPECTRUM_LAB_DATA_DIR")
    if not base:base=str(Path(os.environ.get("LOCALAPPDATA",str(Path.home()/".spectrum_lab")))/"SpectrumLabPro")
    return Path(base)/"interface.json"
def read_preference(path):
    try:
        theme=json.loads(path.read_text(encoding="utf-8")).get("theme")
        return theme if theme in (*PALETTES, "system") else "light"
    except (OSError,ValueError,TypeError,AttributeError):return "light"
def save_preference(path,theme):
    temporary=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,delete=False) as handle:
            temporary=Path(handle.name);json.dump({"theme":theme},handle);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path);return True,""
    except OSError as exc:return False,str(exc)
    finally:
        if temporary and temporary.exists():temporary.unlink(missing_ok=True)

class ThemeManager(QObject):
    def __init__(self,app):
        super().__init__(app)
        self.app=app;self.applying=False;self.path=preferences_path();self.last_error=""
        self.preference=read_preference(self.path)
        app.installEventFilter(self)
        self.set_theme(self.preference,False)
        self.system_timer=QTimer(self)
        self.system_timer.timeout.connect(self.refresh_system_theme)
        self.system_timer.start(2000)
    @staticmethod
    def system_theme():
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return "light" if winreg.QueryValueEx(key,"AppsUseLightTheme")[0] else "dark"
        except (ImportError,OSError):
            return "light"
    def refresh_system_theme(self):
        if self.preference=="system" and self.system_theme()!=self.theme:
            self.set_theme("system",False)
    def refresh_preferences_path(self):
        path=preferences_path()
        if path!=self.path:self.path=path;self.set_theme(read_preference(path),False)
    def eventFilter(self,obj,event):
        if isinstance(obj,QWidget) and not self.applying and event.type() in (QEvent.StyleChange,QEvent.Show):
            if not getattr(obj,"_theme_queued",False):
                obj._theme_queued=True
                ref=weakref.ref(obj)
                def apply_later():
                    widget=ref()
                    if widget is not None and not sip.isdeleted(widget):
                        widget._theme_queued=False;self.apply_widget(widget)
                QTimer.singleShot(0,apply_later)
        return False
    def apply_widget(self,widget):
        if sip.isdeleted(widget):return
        current=widget.styleSheet()
        if current!=getattr(widget,"_theme_last_qss",None):
            widget._theme_base_qss=current
        source=getattr(widget,"_theme_base_qss",current)
        # Evita que os estilos de caixas sejam herdados pelos rótulos internos.
        scoped=source
        if scoped:
            name=widget.objectName()
            if not name:
                name=f"themeWidget{id(widget)}";widget.setObjectName(name)
            if "{" not in scoped and re.search(r"(?:background|border)\s*[-:]",scoped):
                scoped=f"#{name} {{ {scoped} }}"
            scoped=re.sub(r"(?<![\w#])QFrame\s*\{",f"QFrame#{name} {{",scoped)
            if isinstance(widget,QLabel):
                scoped=re.sub(r"(?:background(?:-color)?|border(?:-(?:top|bottom|left|right|color))?)\s*:[^;{}]+;?","",scoped)
        factory=getattr(widget,"_scada_style_factory",None)
        rendered=factory(palette_for(self.theme)) if factory else transform_stylesheet(scoped,self.theme)
        in_popup = popup_owner(widget) is not None
        if in_popup:
            rendered = popup_stylesheet(widget, palette_for(self.theme), rendered)
        widget._theme_last_qss=rendered
        previous=self.applying;self.applying=True
        try:
            if current!=rendered:widget.setStyleSheet(rendered)
            if isinstance(widget,(QLabel,QPushButton)) and not in_popup:
                text=widget.text()
                clean=re.sub(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u25B6\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                if clean!=text:widget.setText(clean)
                if text and not clean and isinstance(widget,QLabel):widget.hide()
            if isinstance(widget,QComboBox) and not in_popup:
                for i in range(widget.count()):
                    text=widget.itemText(i)
                    clean=re.sub(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u25B6\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                    if clean!=text:widget.setItemText(i,clean)
            if isinstance(widget,QTabWidget) and not in_popup:
                for i in range(widget.count()):
                    text=widget.tabText(i)
                    clean=re.sub(r"[\U0001F000-\U0001FAFF\u25B6\u2300-\u23FF\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                    if clean!=text:widget.setTabText(i,clean)
            if isinstance(widget,QMenu):
                for action in widget.actions():
                    text=action.text()
                    clean=re.sub(r"[\U0001F000-\U0001FAFF\u25B6\u2300-\u23FF\u2600-\u27BF\uFE0F\u200D]","",text).strip()
                    if clean!=text:action.setText(clean)
            p=palette_for(self.theme)
            widget.setPalette(self.app.palette())
            if hasattr(widget,"setBackgroundBrush"):widget.setBackgroundBrush(QColor(p["canvas"]))
            widget.update()
        finally:self.applying=previous
    def set_theme(self,theme,persist=True):
        if theme not in (*PALETTES,"system"):raise ValueError("Tema inválido.")
        self.preference=theme
        theme=self.system_theme() if theme=="system" else theme
        self.theme=theme;self.app.setProperty("spectrum_theme",theme)
        p=palette_for(theme);pal=QPalette()
        for role,key in ((QPalette.Window,"canvas"),(QPalette.WindowText,"text"),(QPalette.Base,"surface"),
                         (QPalette.AlternateBase,"soft"),(QPalette.Text,"text"),(QPalette.Button,"soft"),
                         (QPalette.ButtonText,"text"),(QPalette.Highlight,"accent"),
                         (QPalette.ToolTipBase,"surface"),(QPalette.ToolTipText,"text")):
            pal.setColor(role,QColor(p[key]))
        pal.setColor(QPalette.HighlightedText,QColor("#FFFFFF"))
        # Fusion uses these roles for bevels and native-looking control edges.
        # Default Light/Midlight can otherwise leave white strips in a gray theme.
        for role,key in ((QPalette.Light,"surface"),(QPalette.Midlight,"surface"),
                         (QPalette.Dark,"border"),(QPalette.Mid,"border"),
                         (QPalette.Shadow,"border"),(QPalette.BrightText,"text")):
            pal.setColor(role,QColor(p[key]))
        for role in (QPalette.Text,QPalette.WindowText,QPalette.ButtonText):
            pal.setColor(QPalette.Disabled,role,QColor(p["disabled"]))
        self.applying=True
        try:self.app.setPalette(pal)
        finally:self.applying=False
        for widget in self.app.allWidgets():self.apply_widget(widget)
        if persist:
            ok,self.last_error=save_preference(self.path,self.preference);return ok
        return True

def ensure_theme_manager():
    app=QApplication.instance()
    manager=getattr(app,"_spectrum_themes",None)
    if manager is None:manager=ThemeManager(app);app._spectrum_themes=manager
    else:manager.refresh_preferences_path()
    return manager

class AppearanceDialog(QDialog):
    def __init__(self,manager,parent=None):
        super().__init__(parent)
        self.manager=manager
        self.setWindowTitle("Configurações · Aparência")
        self.resize(420,240)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,22);layout.setSpacing(14)
        title=QLabel("Aparência");title.setStyleSheet("color: #FFFFFF; font-size: 22px; font-weight: 600;")
        layout.addWidget(title)
        label=QLabel("Escolha o tema da interface. A preferência será lembrada.")
        label.setWordWrap(True);label.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout.addWidget(label)
        self.selector=QComboBox()
        self.selector.addItem("Claro","light");self.selector.addItem("Escuro","dark")
        self.selector.addItem("Seguir o sistema","system")
        self.selector.setCurrentIndex(self.selector.findData(manager.preference))
        self.selector.setMinimumHeight(38)
        self.selector.currentIndexChanged.connect(self.change_theme)
        layout.addWidget(self.selector)
        self.feedback=QLabel("A alteração é aplicada imediatamente.")
        self.feedback.setWordWrap(True);self.feedback.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        layout.addWidget(self.feedback)
        row=QHBoxLayout();row.addStretch()
        close=QPushButton("Concluir");close.clicked.connect(self.accept);row.addWidget(close)
        layout.addLayout(row)
        for widget in (self,*self.findChildren(QWidget)):manager.apply_widget(widget)
    def change_theme(self):
        ok=self.manager.set_theme(self.selector.currentData())
        self.feedback.setText("Preferência salva." if ok else "Tema aplicado nesta sessão. Não foi possível salvar a preferência.")
