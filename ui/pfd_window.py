import math
import threading
import tkinter as tk
import time


class PFDWindow:
    """Primary Flight Display (PFD) window.
    Gösterge: IAS, irtifa, dikey hız, heading ve yapay ufuk (gökyüzü/toprak + ufuk)
    Gerçek cam kokpitlerdeki gibi bank ölçeği ile birlikte.
    """

    UPDATE_HZ = 30  # Yenileme hızı (Hz)

    # Bank ölçeği geometrisi
    BANK_SCALE_DEGS = [-60, -45, -30, -20, -10, 10, 20, 30, 45, 60]
    BANK_SCALE_MAJOR = {30, 60}
    BANK_SCALE_R = 60        # yarıçap (px)
    BANK_SCALE_CY = 60       # ölçek merkezinin y konumu (px)

    # ────────────────────────────────────────────────────────────────────
    def __init__(self, root: tk.Tk, flight_ctrl):
        self.flight = flight_ctrl
        self.aq = flight_ctrl.aq  # Uçağın anlık verilerini tutan dict‑benzeri arayüz

        # Genel pencere ölçüleri
        self.W, self.H = 640, 400
        self.MARGIN_X = 80                # yan panel genişliği
        self.center_left = self.MARGIN_X
        self.center_right = self.W - self.MARGIN_X
        self.center_cx = (self.center_left + self.center_right) / 2
        self.center_cy = self.H / 2

        # Üst seviye pencere
        self.top = tk.Toplevel(root)
        self.top.title("Gelişmiş PFD")
        self.top.resizable(False, False)

        self.cv = tk.Canvas(self.top, width=self.W, height=self.H, bg="black")
        self.cv.pack()

        # Dinamik olarak güncellenecek bank ölçeği elemanlarının id listeleri
        self.bank_scale_lines = []
        self.bank_scale_labels = []

        # Sabit uçak sembolü eleman id'lerini saklamak için
        self.aircraft_symbol_elements = []
        self.static_bank_triangle = None

        # Yan panelleri ve alt heading çizgisini tutmak için id'ler
        self.left_panel_rect = None
        self.right_panel_rect = None
        self.heading_line = None

        # Sabit grafiklerin çizimi
        self._draw_static()

        # Arka planda güncelleme döngüsü
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()
        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

    # ────────────────────────────────────────────────────────────────────
    #   Sabit (animasyonsuz) elemanlar
    # ────────────────────────────────────────────────────────────────────
    def _draw_static(self):
        # ░░░ Yan paneller ░░░
        self.left_panel_rect = self.cv.create_rectangle(
            0, 0, self.MARGIN_X, self.H, fill="#111", outline="#111")
        self.right_panel_rect = self.cv.create_rectangle(
            self.center_right, 0, self.W, self.H, fill="#111", outline="#111")

        # Metinsel göstergeler (IAS, ALT, VS)
        self.ias_text = self.cv.create_text(
            40, 40, fill="white", font=("Consolas", 18), anchor="w", text="-- kt")
        self.alt_text = self.cv.create_text(
            self.W - 40, 40, fill="white", font=("Consolas", 18), anchor="e", text="---- ft")
        self.vs_text = self.cv.create_text(
            self.W - 40, 80, fill="cyan", font=("Consolas", 12), anchor="e", text="0 fpm")

        # ░░░ Heading bandı ░░░
        self.heading_line = self.cv.create_line(0, self.H - 50, self.W, self.H - 50, fill="white")
        self.hdg_text = self.cv.create_text(
            self.W / 2, self.H - 25, fill="white", font=("Consolas", 16), text="HDG ---°")

        # Sabit heading işaretleri (her 30°)
        tape_width = self.center_right - self.center_left
        for i, deg_val in enumerate(range(0, 360, 30)):
            x_pos = self.center_left + (i / 12) * tape_width
            if deg_val == 0:
                x_pos = self.center_left + 10
            elif deg_val == 330:
                x_pos = self.center_right - 10
            self.cv.create_text(
                x_pos, self.H - 60, fill="white", font=("Consolas", 10),
                text=f"{deg_val if deg_val else 360}", tag="heading_markers")

        # ░░░ Yapay ufuk (gökyüzü / toprak) ░░░
        self.sky_poly = self.cv.create_polygon(
            self.center_left, 0, self.center_right, 0,
            self.center_right, self.H / 2, self.center_left, self.H / 2,
            fill="#00aaff", outline="")
        self.gnd_poly = self.cv.create_polygon(
            self.center_left, self.H / 2, self.center_right, self.H / 2,
            self.center_right, self.H, self.center_left, self.H,
            fill="#885400", outline="")
        self.horizon_line = self.cv.create_line(
            self.center_left, self.H / 2, self.center_right, self.H / 2,
            fill="yellow", width=3)

        # ░░░ Sabit uçak sembolü ░░░
        wing = 40
        self.aircraft_symbol_elements.append(
            self.cv.create_line(self.center_cx - wing, self.center_cy,
                                 self.center_cx - 5, self.center_cy,
                                 fill="white", width=3))
        self.aircraft_symbol_elements.append(
            self.cv.create_line(self.center_cx + 5, self.center_cy,
                                 self.center_cx + wing, self.center_cy,
                                 fill="white", width=3))
        self.aircraft_symbol_elements.append(
            self.cv.create_rectangle(self.center_cx - 5, self.center_cy - 5,
                                      self.center_cx + 5, self.center_cy + 5,
                                      outline="white", width=2))
        tri = 8
        self.static_bank_triangle = self.cv.create_polygon(
            self.center_cx, self.BANK_SCALE_CY - tri,
            self.center_cx - tri, self.BANK_SCALE_CY,
            self.center_cx + tri, self.BANK_SCALE_CY,
            fill="white", outline="white")
        self.aircraft_symbol_elements.append(self.static_bank_triangle)

    # ────────────────────────────────────────────────────────────────────
    # Nokta döndürme yardımcı fonksiyonu
    # ────────────────────────────────────────────────────────────────────
    def _rotate_point(self, px, py, rotation_cx, rotation_cy, angle_rad):
        dx, dy = px - rotation_cx, py - rotation_cy
        rx = rotation_cx + dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
        ry = rotation_cy + dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
        return rx, ry

    # ────────────────────────────────────────────────────────────────────
    def _draw_bank_scale(self, bank_angle_rad):
        """Bank ölçeğini (yay, çizgiler, etiketler) yeniden çizer."""
        for item in self.bank_scale_lines + self.bank_scale_labels:
            self.cv.delete(item)
        self.bank_scale_lines.clear()
        self.bank_scale_labels.clear()

        cx, cy, r = self.center_cx, self.BANK_SCALE_CY, self.BANK_SCALE_R

        for deg in self.BANK_SCALE_DEGS + [0]:
            if deg == 0:
                angle0 = math.radians(-90)
                tick_len = 16
                is_label = False
            else:
                angle0 = math.radians(deg - 90)
                tick_len = 12 if abs(deg) in self.BANK_SCALE_MAJOR else 8
                is_label = abs(deg) in self.BANK_SCALE_MAJOR

            x1b = cx + r * math.cos(angle0)
            y1b = cy + r * math.sin(angle0)
            x2b = cx + (r - tick_len) * math.cos(angle0)
            y2b = cy + (r - tick_len) * math.sin(angle0)

            p1x, p1y = self._rotate_point(x1b, y1b, cx, cy, bank_angle_rad)
            p2x, p2y = self._rotate_point(x2b, y2b, cx, cy, bank_angle_rad)
            self.bank_scale_lines.append(
                self.cv.create_line(p1x, p1y, p2x, p2y, width=2, fill="white"))

            if is_label:
                lx = cx + (r + 14) * math.cos(angle0)
                ly = cy + (r + 14) * math.sin(angle0)
                rlx, rly = self._rotate_point(lx, ly, cx, cy, bank_angle_rad)
                self.bank_scale_labels.append(
                    self.cv.create_text(rlx, rly, text=str(abs(deg)),
                                         fill="white", font=("Consolas", 8)))

    # ────────────────────────────────────────────────────────────────────
    def _loop(self):
        dt = 1 / self.UPDATE_HZ
        while not self._stop.is_set():
            try:
                self._update()
            except Exception as e:
                print(f"[PFD Hata] {e}")
            time.sleep(dt)

    # ────────────────────────────────────────────────────────────────────
    def _update(self):
        aq = self.aq
        if not aq:
            return  # Veri gelmediyse bekle

        # Sim verilerini al
        ias = aq.get("AIRSPEED_INDICATED", 0.0)
        alt = aq.get("PLANE_ALTITUDE", 0.0)
        vs = aq.get("VERTICAL_SPEED", 0.0)
        hdg = aq.get("PLANE_HEADING_DEGREES_TRUE", 0.0)
        pitch = aq.get("PLANE_PITCH_DEGREES", 0.0)
        bank = aq.get("PLANE_BANK_DEGREES", 0.0)

        # Metinleri güncelle
        self.cv.itemconfigure(self.ias_text, text=f"{ias:5.0f} kt")
        self.cv.itemconfigure(self.alt_text, text=f"{alt:6.0f} ft")
        self.cv.itemconfigure(self.vs_text, text=f"{vs: .0f} fpm")
        self.cv.itemconfigure(self.hdg_text, text=f"HDG {int(hdg)%360:03d}°")

        # Ufuk geometrisi
        pitch_px_per_deg = 4.0
        dy_pitch = -pitch * pitch_px_per_deg
        ai_cx, ai_cy = self.center_cx, self.center_cy

        bank_mul = 3.0  # Görsel etkiyi artır
        rot_rad = math.radians(-bank * bank_mul)
        BIG = 2000
        eff_horiz_y = ai_cy + dy_pitch

        sky_base = [
            (self.center_left, eff_horiz_y - BIG),
            (self.center_right, eff_horiz_y - BIG),
            (self.center_right, eff_horiz_y),
            (self.center_left, eff_horiz_y)
        ]
        gnd_base = [
            (self.center_left, eff_horiz_y),
            (self.center_right, eff_horiz_y),
            (self.center_right, eff_horiz_y + BIG),
            (self.center_left, eff_horiz_y + BIG)
        ]

        # Gökyüzü & toprak çokgenlerini döndür
        sky_rot = []
        for px, py in sky_base:
            rx, ry = self._rotate_point(px, py, ai_cx, ai_cy, rot_rad)
            sky_rot += [rx, ry]
        self.cv.coords(self.sky_poly, *sky_rot)

        gnd_rot = []
        for px, py in gnd_base:
            rx, ry = self._rotate_point(px, py, ai_cx, ai_cy, rot_rad)
            gnd_rot += [rx, ry]
        self.cv.coords(self.gnd_poly, *gnd_rot)

        # Ufuk çizgisi
        h1x, h1y = self._rotate_point(self.center_left, eff_horiz_y, ai_cx, ai_cy, rot_rad)
        h2x, h2y = self._rotate_point(self.center_right, eff_horiz_y, ai_cx, ai_cy, rot_rad)
        self.cv.coords(self.horizon_line, h1x, h1y, h2x, h2y)

        # Bank ölçeği
        self._draw_bank_scale(math.radians(bank))

        # ─ Katman sırası ayarla ─
        # Gökyüzü ve toprak en arkada kalsın
        self.cv.tag_lower(self.sky_poly)
        self.cv.tag_lower(self.gnd_poly)

        # Yan paneller mavi/kahverengiyi örtsün
        self.cv.tag_raise(self.left_panel_rect)
        self.cv.tag_raise(self.right_panel_rect)

        # Alt heading çizgisi
        self.cv.tag_raise(self.heading_line)

        # Metinler
        for t in (self.ias_text, self.alt_text, self.vs_text, self.hdg_text):
            self.cv.tag_raise(t)

        # Heading işaretleri
        self.cv.tag_raise("heading_markers")

        # Sabit uçak sembolü
        for elem in self.aircraft_symbol_elements:
            self.cv.tag_raise(elem)

        # Dinamik bank ölçeği (ufuk çizgisinin üstünde ama uçak sembolünün altında)
        for item in self.bank_scale_lines + self.bank_scale_labels:
            self.cv.tag_raise(item)

    # ────────────────────────────────────────────────────────────────────
    def _on_close(self):
        self._stop.set()
        self.top.destroy()


# ────────────────────────────────────────────────────────────────────
# PyQt5 tabanlı modern PFD (taslak)
# ────────────────────────────────────────────────────────────────────
from PyQt5 import QtWidgets, QtGui, QtCore
import math

class PFDWindowQt(QtWidgets.QWidget):
    """Modern, gerçekçi PFD (Primary Flight Display) - PyQt5 ile."""
    UPDATE_HZ = 30
    def __init__(self, aq, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gelişmiş PFD (PyQt5)")
        self.setFixedSize(640, 480)
        self.aq = aq
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(int(1000/self.UPDATE_HZ))
        self.show()

    def paintEvent(self, event):
        qp = QtGui.QPainter(self)
        qp.setRenderHint(QtGui.QPainter.Antialiasing)
        self.draw_pfd(qp)

    def draw_pfd(self, qp):
        W, H = self.width(), self.height()
        cx, cy = W//2, H//2
        # --- Uçuş verileri ---
        aq = self.aq
        ias = aq.get("AIRSPEED_INDICATED") or 0.0 if self.aq else 0.0
        alt = aq.get("PLANE_ALTITUDE") or 0.0 if self.aq else 0.0
        vs = aq.get("VERTICAL_SPEED") or 0.0 if self.aq else 0.0
        hdg = aq.get("PLANE_HEADING_DEGREES_TRUE") or 0.0 if self.aq else 0.0
        pitch = aq.get("PLANE_PITCH_DEGREES") or 0.0 if self.aq else 0.0
        bank = aq.get("PLANE_BANK_DEGREES") or 0.0 if self.aq else 0.0

        # --- Yapay ufuk ---
        sky_color = QtGui.QColor(0,170,255)
        gnd_color = QtGui.QColor(136,84,0)
        horizon_y = cy - pitch*4
        bank_rad = math.radians(bank)
        # Gökyüzü
        qp.save()
        qp.translate(cx, cy)
        qp.rotate(-bank)
        qp.setBrush(sky_color)
        qp.setPen(QtCore.Qt.NoPen)
        qp.drawRect(int(-W), int(-H), int(2*W), int(horizon_y-cy))
        # Toprak
        qp.setBrush(gnd_color)
        qp.drawRect(int(-W), int(horizon_y-cy), int(2*W), int(H))
        # Ufuk çizgisi
        qp.setPen(QtGui.QPen(QtGui.QColor("yellow"), 3))
        qp.drawLine(int(-W), int(horizon_y-cy), int(W), int(horizon_y-cy))
        qp.restore()

        # --- Bank ölçeği ---
        qp.save()
        qp.translate(cx, cy-100)
        qp.rotate(-bank)
        qp.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
        for deg in [-60,-45,-30,-20,-10,0,10,20,30,45,60]:
            angle = math.radians(deg)
            r1 = 60
            r2 = 60-12 if abs(deg) in (30,60) else 60-8
            x1 = r1*math.sin(angle)
            y1 = -r1*math.cos(angle)
            x2 = r2*math.sin(angle)
            y2 = -r2*math.cos(angle)
            qp.drawLine(int(x1),int(y1),int(x2),int(y2))
            if abs(deg) in (30,60):
                qp.setFont(QtGui.QFont("Consolas",8))
                qp.drawText(int(1.2*x1)-8,int(1.2*y1)+4,str(abs(deg)))
        qp.restore()

        # --- Hız şeridi (sol) ---
        qp.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
        qp.setBrush(QtGui.QColor(30,30,30,220))
        qp.drawRect(20,cy-70,50,140)
        qp.setFont(QtGui.QFont("Consolas",14,QtGui.QFont.Bold))
        qp.setPen(QtGui.QColor("lime"))
        qp.drawText(25,cy+10,f"{ias:5.0f}")
        qp.setFont(QtGui.QFont("Consolas",8))
        for i in range(-2,3):
            val = ias + i*10
            qp.drawText(55,cy+10-i*28,f"{val:3.0f}")

        # --- İrtifa şeridi (sağ) ---
        qp.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
        qp.setBrush(QtGui.QColor(30,30,30,220))
        qp.drawRect(W-70,cy-70,50,140)
        qp.setFont(QtGui.QFont("Consolas",14,QtGui.QFont.Bold))
        qp.setPen(QtGui.QColor("cyan"))
        qp.drawText(W-65,cy+10,f"{alt:6.0f}")
        qp.setFont(QtGui.QFont("Consolas",8))
        for i in range(-2,3):
            val = alt + i*100
            qp.drawText(W-35,cy+10-i*28,f"{val:5.0f}")

        # --- Heading bandı (alt) ---
        qp.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
        qp.setBrush(QtGui.QColor(30,30,30,220))
        qp.drawRect(cx-80,H-60,160,40)
        qp.setFont(QtGui.QFont("Consolas",16,QtGui.QFont.Bold))
        qp.setPen(QtGui.QColor("white"))
        qp.drawText(cx-30,H-30,f"{int(hdg)%360:03d}°")
        # Heading işaretleri
        qp.setFont(QtGui.QFont("Consolas",8))
        for i in range(-3,4):
            val = (hdg + i*10)%360
            qp.drawText(cx+i*40-8,H-40,f"{int(val):03d}")
        # --- Uçak sembolü (merkez) ---
        qp.setPen(QtGui.QPen(QtGui.QColor("white"), 3))
        qp.drawLine(cx-30,cy,cx-5,cy)
        qp.drawLine(cx+5,cy,cx+30,cy)
        qp.drawRect(cx-5,cy-5,10,10)
        # --- VS göstergesi (sağda küçük) ---
        qp.setFont(QtGui.QFont("Consolas",10))
        qp.setPen(QtGui.QColor("magenta"))
        qp.drawText(W-65,cy-80,f"VS {vs: .0f}")
        qp.end()

# Not: Bu class'ı kullanmak için bir PyQt5 uygulaması başlatılmalı ve aq (veri kaynağı) ile örneklenmeli.
