from appearance import theme_color
"""
SPECTRUM-LAB PRO | Módulo de Visualização Espectral & Gráficos Analíticos
Implementa:
1. SpectralSplineChartWidget: Barras espectrais dos 6 canais com sobreposição
   de curva spline cúbica suave (interpolação contínua) e alternância ADC vs %.
2. ScatterPlotWidget: Gráfico de dispersão 2D de bancada com histórico das últimas
   20 leituras em buffer circular e ponto atual em destaque fluorescente.
Estilo: Windows 11 Fluent Design / Power BI Dark Theme (#202020 / #2b2b2b / #3d3d3d).
"""

from collections import deque
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame,
    QPushButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QPropertyAnimation, pyqtProperty, QEasingCurve, QRectF, QPointF, QPoint
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QLinearGradient,
    QRadialGradient, QPainterPath
)


class SingleBarWidget(QWidget):
    """
    Barra vertical espectral individual refinada com animação suave e design Fluent.
    """
    def __init__(self, wavelength, color_hex, label_name, parent=None):
        super().__init__(parent)
        self.wavelength = wavelength
        self.color_hex = color_hex
        self.label_name = label_name
        self._current_value = 0.0
        self.target_value = 0.0
        self.max_value = 100.0
        self.unit_str = "%"

        self.anim = QPropertyAnimation(self, b"animatedValue")
        self.anim.setDuration(600)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_animated_value(self):
        return self._current_value

    def set_animated_value(self, val):
        self._current_value = val
        self.update()
        if self.parent() and hasattr(self.parent(), "update_spline"):
            self.parent().update_spline()

    animatedValue = pyqtProperty(float, get_animated_value, set_animated_value)

    def animate_to(self, target_val, max_val, unit="%"):
        self.target_value = target_val
        self.max_value = max(1.0, max_val)
        self.unit_str = unit
        self.anim.stop()
        self.anim.setStartValue(self._current_value)
        self.anim.setEndValue(float(target_val))
        self.anim.start()

    def get_top_center_point(self):
        """Retorna as coordenadas (x, y) relativas ao widget pai para traçado da spline."""
        w = self.width()
        h = self.height()
        top_pad = 32
        bot_pad = 42
        max_h = max(10, h - top_pad - bot_pad)
        ratio = max(0.0, min(1.0, self._current_value / self.max_value))
        bar_h = ratio * max_h
        y = h - bot_pad - bar_h
        x = w / 2.0
        p = self.mapToParent(QPoint(int(x), int(y)))
        return QPointF(float(p.x()), float(p.y()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        top_padding = 32
        bottom_padding = 42
        bar_width = min(95.0, max(18.0, w * 0.62))
        max_bar_height = max(10.0, h - top_padding - bottom_padding)

        ratio = max(0.0, min(1.0, self._current_value / self.max_value))
        bar_h = ratio * max_bar_height

        x = (w - bar_width) / 2.0
        y = h - bottom_padding - bar_h

        # 1. Background Track (#202020 / #1a1a1a)
        track_rect = QRectF(x, top_padding, bar_width, max_bar_height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(theme_color("#1e1e1e","surface"))))
        painter.drawRoundedRect(track_rect, 6, 6)

        # 2. Filled Bar with Fluent Gradient
        if bar_h > 1.0:
            bar_rect = QRectF(x, y, bar_width, bar_h)
            gradient = QLinearGradient(x, y + bar_h, x, y)
            base_col = QColor(theme_color(self.color_hex,"accent"))
            light_col = base_col.lighter(112)
            base_col.setAlpha(75)
            light_col.setAlpha(75)
            gradient.setColorAt(0.0, base_col)
            gradient.setColorAt(1.0, light_col)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(bar_rect, 6, 6)

            # Glowing Cap Line
            painter.setPen(QPen(light_col, 2))
            painter.drawLine(int(x + 2), int(y), int(x + bar_width - 2), int(y))

        # 3. Numeric Value text on top
        if self.unit_str == "%":
            val_text = f"{self._current_value:.1f}%"
        else:
            val_text = f"{int(self._current_value)}"
        painter.setPen(QPen(QColor(theme_color("#F3F4F6","text"))))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(QRectF(0, y - 20, w, 18), Qt.AlignCenter, val_text)

        # 4. Wavelength Label below bar
        painter.setPen(QPen(QColor(theme_color(self.color_hex,"accent"))))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(QRectF(0, h - bottom_padding + 4, w, 18), Qt.AlignCenter, self.wavelength)

        # 5. Secondary Name
        painter.setPen(QPen(QColor(theme_color("#9CA3AF","text"))))
        painter.setFont(QFont("Segoe UI", 7, QFont.Normal))
        painter.drawText(QRectF(0, h - bottom_padding + 22, w, 14), Qt.AlignCenter, self.label_name)


class SplineOverlay(QWidget):
    """
    Camada transparente sobre as barras para traçar a curva spline contínua.
    """
    def __init__(self, chart_parent):
        super().__init__(chart_parent)
        self.chart_parent = chart_parent
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        try:
            points = self.chart_parent.get_bar_points()
            if not points or len(points) < 2:
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            # Catmull-Rom to Cubic Bezier Conversion
            n = len(points)
            path = QPainterPath()
            path.moveTo(points[0])

            for i in range(n - 1):
                p0 = points[i - 1] if i > 0 else QPointF(2 * points[0].x() - points[1].x(), 2 * points[0].y() - points[1].y())
                p1 = points[i]
                p2 = points[i + 1]
                p3 = points[i + 2] if i + 2 < n else QPointF(2 * points[-1].x() - points[-2].x(), 2 * points[-1].y() - points[-2].y())

                c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6.0, p1.y() + (p2.y() - p0.y()) / 6.0)
                c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6.0, p2.y() - (p3.y() - p1.y()) / 6.0)
                path.cubicTo(c1, c2, p2)

            # Soft Area Gradient under Spline
            fill_path = QPainterPath(path)
            fill_path.lineTo(points[-1].x(), self.height() - 42)
            fill_path.lineTo(points[0].x(), self.height() - 42)
            fill_path.closeSubpath()

            area_grad = QLinearGradient(0, 32, 0, self.height() - 42)
            area_grad.setColorAt(0.0, QColor(8, 125, 123, 0))
            area_grad.setColorAt(1.0, QColor(8, 125, 123, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(area_grad))
            painter.drawPath(fill_path)

            # Glow behind spline
            glow_pen = QPen(QColor(8, 125, 123, 0), 5)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

            # Main Spline Curve line
            spline_pen = QPen(QColor(theme_color("#38BDF8","text")), 2.2)
            painter.setPen(spline_pen)
            painter.drawPath(path)

            # Draw highlight dots at vertices
            for pt in points:
                painter.setPen(QPen(QColor(theme_color("#FFFFFF","text")), 1.5))
                painter.setBrush(QBrush(QColor(theme_color("#0284C7","text"))))
                painter.drawEllipse(pt, 3.5, 3.5)
        except Exception:
            pass


class SpectralSplineChartWidget(QFrame):
    """
    Card Principal Espectral GY-AS7263 com 6 canais, curva spline suave
    e alternador de unidades (ADC vs Refletância %).
    """
    CHANNELS = [
        ('610nm', '#087D7B', 'Vermelho'),
        ('680nm', '#087D7B', 'Verm. Prof.'),
        ('730nm', '#087D7B', 'NIR 730'),
        ('760nm', '#087D7B', 'NIR 760'),
        ('810nm', '#087D7B', 'NIR 810'),
        ('860nm', '#087D7B', 'NIR 860')
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardFrame")
        self.setStyleSheet("""
            QFrame#cardFrame {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
        """)

        self.unit_mode = "%"   # "%" ou "ADC"
        self._raw_adc_values = [0.0] * 6
        self._percent_values = [0.0] * 6

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        # Header Bar
        header_layout = QHBoxLayout()
        title_icon = QLabel("📊")
        title_icon.setStyleSheet("font-size: 14px;")

        chart_title = QLabel("Bandas espectrais · 610–860 nm")
        chart_title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold; font-family: 'Segoe UI'; letter-spacing: 0.5px;")

        header_layout.addWidget(title_icon)
        header_layout.addWidget(chart_title)
        header_layout.addStretch()

        # Unit Selector Toggle (Refletância %, Normalizado pela soma %, ADC Bruto)
        self.btn_unit_pct = QPushButton("Refletância (%)")
        self.btn_unit_pct.setCheckable(True)
        self.btn_unit_pct.setChecked(True)

        self.btn_unit_snv = QPushButton("Normalizado pela soma (%)")
        self.btn_unit_snv.setCheckable(True)

        self.btn_unit_adc = QPushButton("Contagens (ADC)")
        self.btn_unit_adc.setCheckable(True)

        self.unit_group = QButtonGroup(self)
        self.unit_group.addButton(self.btn_unit_pct)
        self.unit_group.addButton(self.btn_unit_snv)
        self.unit_group.addButton(self.btn_unit_adc)
        self.unit_group.setExclusive(True)

        selector_style = """
            QPushButton {
                background-color: #202020;
                color: #9CA3AF;
                border: 1px solid #3d3d3d;
                padding: 4px 9px;
                font-size: 10px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:checked {
                background-color: #0078D4;
                color: #FFFFFF;
                border: 1px solid #60CDFF;
            }
            QPushButton:hover:!checked {
                background-color: #333333;
                color: #E5E7EB;
            }
        """
        self.btn_unit_pct.setStyleSheet(selector_style)
        self.btn_unit_snv.setStyleSheet(selector_style)
        self.btn_unit_adc.setStyleSheet(selector_style)

        self.btn_unit_pct.clicked.connect(lambda: self.set_unit_mode("%"))
        self.btn_unit_snv.clicked.connect(lambda: self.set_unit_mode("SNV"))
        self.btn_unit_adc.clicked.connect(lambda: self.set_unit_mode("ADC"))

        main_layout.addLayout(header_layout)
        self.selector_layout = QHBoxLayout()
        self.btn_unit_snv.setText('Normalizado (%)')
        self.selector_layout.addWidget(self.btn_unit_pct)
        self.selector_layout.addWidget(self.btn_unit_snv)
        self.selector_layout.addWidget(self.btn_unit_adc)
        main_layout.addLayout(self.selector_layout)

        self._snv_values = [0.0] * 6

        # Bars Area Container
        self.bars_container = QWidget(self)
        bars_layout = QHBoxLayout(self.bars_container)
        bars_layout.setContentsMargins(0, 0, 0, 0)
        bars_layout.setSpacing(6)

        self.bars = []
        for wl, color, name in self.CHANNELS:
            bar = SingleBarWidget(wl, color, name, self.bars_container)
            bars_layout.addWidget(bar)
            self.bars.append(bar)

        main_layout.addWidget(self.bars_container, stretch=1)

        # Spline Overlay
        self.spline_overlay = SplineOverlay(self)
        self.spline_overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "bars_container") and hasattr(self, "spline_overlay") and self.spline_overlay is not None:
            geom = self.bars_container.geometry()
            self.spline_overlay.setGeometry(geom)

    def get_bar_points(self):
        pts = []
        for bar in self.bars:
            p_container = bar.get_top_center_point()
            pts.append(p_container)
        return pts

    def update_spline(self):
        self.spline_overlay.update()

    def set_unit_mode(self, mode: str):
        self.unit_mode = mode
        if mode == "%":
            self.btn_unit_pct.setChecked(True)
        elif mode == "SNV":
            self.btn_unit_snv.setChecked(True)
        else:
            self.btn_unit_adc.setChecked(True)
        self.refresh_display()

    def update_spectrum(self, raw_counts, r_calibrated=None, r_snv=None):
        if not raw_counts or len(raw_counts) < 6:
            raw_counts = [0.0] * 6

        self._raw_adc_values = [float(v) for v in raw_counts[:6]]

        # Se vetor calibrado R_i foi fornecido:
        if r_calibrated and len(r_calibrated) >= 6:
            self._percent_values = [min(100.0, max(0.0, float(v) * 100.0)) for v in r_calibrated[:6]]
        else:
            max_c = max(self._raw_adc_values)
            if max_c > 0:
                self._percent_values = [min(100.0, (v / max(1.0, max_c)) * 100.0) for v in self._raw_adc_values]
            else:
                self._percent_values = [0.0] * 6

        # Se vetor normalizado SNV foi fornecido:
        if r_snv and len(r_snv) >= 6:
            self._snv_values = [min(100.0, max(0.0, float(v) * 100.0)) for v in r_snv[:6]]
        else:
            sum_c = sum(self._raw_adc_values)
            if sum_c > 0:
                self._snv_values = [(v / sum_c) * 100.0 for v in self._raw_adc_values]
            else:
                self._snv_values = [0.0] * 6

        self.refresh_display()

    def refresh_display(self):
        if self.unit_mode == "%":
            vals = self._percent_values
            scale_max = 100.0
            unit_lbl = "%"
        elif self.unit_mode == "SNV":
            vals = self._snv_values
            max_v = max(vals) if vals else 30.0
            scale_max = max(30.0, max_v * 1.15)
            unit_lbl = "%"
        else:
            vals = self._raw_adc_values
            max_v = max(vals) if vals else 1000.0
            scale_max = max(1000.0, max_v * 1.15)
            unit_lbl = "ADC"

        for bar, val in zip(self.bars, vals):
            bar.animate_to(val, scale_max, unit_lbl)


class ScatterPlotWidget(QFrame):
    """
    Card de Gráfico de Dispersão 2D (Scatter Plot) de Bancada.
    Metodologia Quimiométrica de Celulose em Suspensão Aquosa:
    - Eixo X (Assinatura das Fibras de Celulose): Razão R_norm[680 nm] / R_norm[730 nm] (Bandas S / T)
    - Eixo Y (Matriz Aquosa / Espessura da Gota): Razão R_norm[860 nm] / R_norm[760 nm] (Bandas W / U)
    - Histórico das últimas 20 leituras em buffer circular
    - Ponto atual destacado em ciano neon (#38BDF8)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("cardFrame")
        self.setStyleSheet("""
            QFrame#cardFrame {
                background-color: #2b2b2b;
                border: 1px solid #3d3d3d;
                border-radius: 8px;
            }
        """)

        self.history = deque(maxlen=20)
        self.current_point = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title_icon = QLabel("🎯")
        title_icon.setStyleSheet("font-size: 14px;")

        lbl_title = QLabel("DISPERSÃO 2D (CELULOSE R680/R730 vs ÁGUA R860/R760)")
        lbl_title.setStyleSheet("color: #FFFFFF; font-size: 11px; font-weight: bold; font-family: 'Segoe UI'; letter-spacing: 0.5px;")

        self.lbl_stats = QLabel("Pontos: 0/20")
        self.lbl_stats.setStyleSheet("color: #9CA3AF; font-size: 10px; font-family: 'Segoe UI';")

        header.addWidget(title_icon)
        header.addWidget(lbl_title)
        header.addStretch()
        header.addWidget(self.lbl_stats)
        layout.addLayout(header)

        # Plot Canvas
        self.canvas = ScatterCanvas(self)
        layout.addWidget(self.canvas, stretch=1)

    def add_measurement(self, spectral_values, label="Amostra", r_norm=None):
        if not spectral_values or len(spectral_values) < 6:
            return

        if r_norm and len(r_norm) >= 6:
            vec = r_norm
        else:
            total = sum(spectral_values[:6])
            if total > 0:
                vec = [float(v) / total for v in spectral_values[:6]]
            else:
                vec = [0.0] * 6

        r680 = max(1e-5, vec[1])  # Canal 680nm (S)
        r730 = max(1e-5, vec[2])  # Canal 730nm (T)
        r760 = max(1e-5, vec[3])  # Canal 760nm (U)
        r860 = max(1e-5, vec[5])  # Canal 860nm (W)

        # Eixo X: Fibras de Celulose
        ratio_celulose = r680 / r730
        # Eixo Y: Matriz Aquosa / Espessura
        ratio_agua = r860 / r760

        pt = (ratio_celulose, ratio_agua, label)
        self.history.append(pt)
        self.current_point = pt
        self.lbl_stats.setText(f"Pontos: {len(self.history)}/20 | X(Cel): {ratio_celulose:.2f} | Y(H2O): {ratio_agua:.2f}")
        self.canvas.update()

    def clear_history(self):
        self.history.clear()
        self.current_point = None
        self.lbl_stats.setText("Pontos: 0/20")
        self.canvas.update()


class ScatterCanvas(QWidget):
    """
    Área de desenho do plano cartesiano 2D com eixos, grid e pontos históricos.
    Mapeia:
    X: R_norm[680nm] / R_norm[730nm] (Assinatura Celulose)
    Y: R_norm[860nm] / R_norm[760nm] (Matriz Aquosa / Espessura)
    """
    def __init__(self, parent_scatter):
        super().__init__(parent_scatter)
        self.parent_scatter = parent_scatter

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        pad_left = 42
        pad_right = 16
        pad_top = 16
        pad_bottom = 32

        plot_w = max(10, w - pad_left - pad_right)
        plot_h = max(10, h - pad_top - pad_bottom)

        plot_rect = QRectF(pad_left, pad_top, plot_w, plot_h)
        painter.setPen(QPen(QColor(theme_color("#3d3d3d","border")), 1))
        painter.setBrush(QBrush(QColor(theme_color("#202020","surface"))))
        painter.drawRoundedRect(plot_rect, 6, 6)

        x_min, x_max = 0.0, 3.0
        y_min, y_max = 0.0, 3.0

        def to_screen(x_val, y_val):
            norm_x = max(0.0, min(1.0, (x_val - x_min) / (x_max - x_min)))
            norm_y = max(0.0, min(1.0, (y_val - y_min) / (y_max - y_min)))
            sx = pad_left + norm_x * plot_w
            sy = pad_top + (1.0 - norm_y) * plot_h
            return sx, sy

        painter.setFont(QFont("Segoe UI", 7, QFont.Normal))
        grid_pen = QPen(QColor(theme_color("#333333","border")), 1, Qt.DotLine)
        text_pen = QPen(QColor(theme_color("#888888","text")))

        for x_tick in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
            sx, _ = to_screen(x_tick, 0)
            painter.setPen(grid_pen)
            painter.drawLine(int(sx), pad_top, int(sx), int(pad_top + plot_h))
            painter.setPen(text_pen)
            painter.drawText(QRectF(sx - 15, pad_top + plot_h + 4, 30, 14), Qt.AlignCenter, f"{x_tick:.1f}")

        for y_tick in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
            _, sy = to_screen(0, y_tick)
            painter.setPen(grid_pen)
            painter.drawLine(pad_left, int(sy), int(pad_left + plot_w), int(sy))
            painter.setPen(text_pen)
            painter.drawText(QRectF(2, sy - 7, pad_left - 6, 14), Qt.AlignRight, f"{y_tick:.1f}")

        # Rótulo Eixo X
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.setPen(QPen(QColor(theme_color("#9CA3AF","text"))))
        painter.drawText(QRectF(pad_left, h - 15, plot_w, 14), Qt.AlignCenter, "Eixo X: Celulose (R680 / R730)")

        # Rótulo Eixo Y
        painter.save()
        painter.translate(12, pad_top + plot_h / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-plot_h / 2, -8, plot_h, 14), Qt.AlignCenter, "Eixo Y: Água/Gota (R860 / R760)")
        painter.restore()

        pts = list(self.parent_scatter.history)
        n_pts = len(pts)

        for idx, (px, py, lbl) in enumerate(pts):
            sx, sy = to_screen(px, py)
            age = (idx + 1) / max(1, n_pts)
            alpha = int(40 + age * 160)
            size = 5.0 + age * 2.0

            painter.setPen(QPen(QColor(56, 189, 248, alpha), 1))
            painter.setBrush(QBrush(QColor(14, 165, 233, alpha)))
            painter.drawEllipse(QPointF(sx, sy), size / 2, size / 2)

        if self.parent_scatter.current_point:
            cx, cy, clbl = self.parent_scatter.current_point
            sx, sy = to_screen(cx, cy)

            glow = QRadialGradient(sx, sy, 14)
            glow.setColorAt(0.0, QColor(56, 189, 248, 220))
            glow.setColorAt(0.5, QColor(8, 125, 123, 0))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(sx, sy), 14, 14)

            painter.setPen(QPen(QColor(theme_color("#FFFFFF","text")), 2))
            painter.setBrush(QBrush(QColor(theme_color("#38BDF8","text"))))
            painter.drawEllipse(QPointF(sx, sy), 5.0, 5.0)

            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            painter.setPen(QPen(QColor(theme_color("#FFFFFF","text"))))
            painter.drawText(QRectF(sx + 8, sy - 14, 140, 16), Qt.AlignLeft, f"{clbl}")

