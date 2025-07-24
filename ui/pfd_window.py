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

    # Pitch merdiveni (ladder) ayarları
    PITCH_LADDER_DEGS = list(range(-30, 35, 5))  # -30° .. +30° arası her 5°

    # Görsel ölçekler
    PITCH_PX_PER_DEG = 4.0   # Dik açı başına piksel kayma

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

        # Pitch ladder öğeleri {deg: (line_id, [text_ids])}
        self.pitch_ladder_items = {}

        # Önceki durum için önbellekler
        self._prev_bank_deg = None

        # Sabit (değişmeyecek) değerler
        self.pitch_px_per_deg = self.PITCH_PX_PER_DEG

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

        # ░░░ Pitch merdiveni ░░░
        self._create_pitch_ladder()

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
    #   Pitch ladder oluşturma ve güncelleme
    # ────────────────────────────────────────────────────────────────────
    def _create_pitch_ladder(self):
        """Pitch merdiveni yatay çizgilerini ve etiketleri oluşturarak item id'lerini saklar."""
        cx = self.center_cx
        for deg in self.PITCH_LADDER_DEGS:
            if deg == 0:
                # Horizon çizgisi zaten var
                continue
            is_major = deg % 10 == 0
            line_len = 120 if is_major else 80
            y_offset = -deg * self.pitch_px_per_deg
            y = self.center_cy + y_offset
            x1 = cx - line_len / 2
            x2 = cx + line_len / 2
            line_id = self.cv.create_line(x1, y, x2, y, fill="white", width=2, tag="pitch_ladder")
            text_ids = []
            if is_major:
                txt = str(abs(deg))
                text_ids.append(self.cv.create_text(x1 - 22, y, text=txt, fill="white", font=("Consolas", 8), tag="pitch_ladder"))
                text_ids.append(self.cv.create_text(x2 + 22, y, text=txt, fill="white", font=("Consolas", 8), tag="pitch_ladder"))
            self.pitch_ladder_items[deg] = (line_id, text_ids)

    def _update_pitch_ladder(self, pitch_deg: float, rot_rad: float):
        """Pitch ladder öğelerinin konumunu günceller.
        Y konumu: center_cy - (pitch - ladder_deg) * px/deg
        """
        cx = self.center_cx
        for deg, (line_id, text_ids) in self.pitch_ladder_items.items():
            # Yeni temel koordinatlar (döndürülmeden)
            is_major = deg % 10 == 0
            line_len = 120 if is_major else 80
            y = self.center_cy - (pitch_deg - deg) * self.pitch_px_per_deg
            x1 = cx - line_len / 2
            x2 = cx + line_len / 2
            # Döndür
            p1x, p1y = self._rotate_point(x1, y, cx, self.center_cy, rot_rad)
            p2x, p2y = self._rotate_point(x2, y, cx, self.center_cy, rot_rad)
            self.cv.coords(line_id, p1x, p1y, p2x, p2y)
            # Etiketler
            if text_ids:
                lx, ly = self._rotate_point(x1 - 22, y, cx, self.center_cy, rot_rad)
                rx, ry = self._rotate_point(x2 + 22, y, cx, self.center_cy, rot_rad)
                self.cv.coords(text_ids[0], lx, ly)
                self.cv.coords(text_ids[1], rx, ry)

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
        dy_pitch = -pitch * self.pitch_px_per_deg
        ai_cx, ai_cy = self.center_cx, self.center_cy

        rot_rad = math.radians(-bank)
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

        # Bank ölçeği (yalnızca anlamlı değişimde yeniden çiz)
        if self._prev_bank_deg is None or abs(bank - self._prev_bank_deg) > 0.5:
            self._draw_bank_scale(math.radians(bank))
            self._prev_bank_deg = bank

        # Pitch merdiveni
        self._update_pitch_ladder(pitch, rot_rad)

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

        # Pitch ladder çizgileri (bank ölçeğinden önce, uçak sembolünün altında olmayacak şekilde)
        self.cv.tag_raise("pitch_ladder")

        # Sabit uçak sembolü her zaman en üstte kalsın
        for elem in self.aircraft_symbol_elements:
            self.cv.tag_raise(elem)

        # Dinamik bank ölçeği (ufuk çizgisinin üstünde ama uçak sembolünün altında)
        for item in self.bank_scale_lines + self.bank_scale_labels:
            self.cv.tag_raise(item)

    # ────────────────────────────────────────────────────────────────────
    def _on_close(self):
        self._stop.set()
        self.top.destroy()
