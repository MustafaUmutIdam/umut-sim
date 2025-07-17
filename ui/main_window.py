from tkinter import *
from ui.pfd_window import PFDWindow
from tkinter import filedialog     
import json, time, threading       


class MainWindow:
    def __init__(self, root, sim_manager, autopilot, flight):
        self.root        = root
        self.sim_manager = sim_manager
        self.autopilot   = autopilot
        self.flight      = flight

        self.scenario     = []
        self.entries      = {}
        self.data_stream  = None      # dış veri kaynağı
        self._build_ui()

    # --------------------------------------------------
    def _build_ui(self):
        self.root.title("MSFS Otomatik Kalkış & NAV Paneli")
        self.status_label = Label(self.root, text="SimConnect bağlanmadı", fg="red")
        self.status_label.grid(row=0, column=0, columnspan=5, pady=4)

        Button(self.root, text="🔌 Bağlantıyı Test Et",
               command=self.test_connection).grid(row=1, column=0, padx=6)
        self.takeoff_btn  = Button(self.root, text="🚀 Otomatik Kalkış",
                                   command=self.start_takeoff, state=DISABLED)
        self.takeoff_btn.grid(row=1, column=1, padx=6)
        self.teleport_btn = Button(self.root, text="📍 Işınla + Ayarla",
                                   command=self.teleport, state=DISABLED)
        self.teleport_btn.grid(row=1, column=2, padx=6)
        self.fly_btn      = Button(self.root, text="🧭 NAV (tek nokta)",
                                   command=self.fly_to, state=DISABLED)
        self.fly_btn.grid(row=1, column=3, padx=6)
        Button(self.root, text="📊 PFD",
               command=lambda: PFDWindow(self.root, self.flight)).grid(row=1, column=4, padx=6)

         # ✱ yeni: JSON senaryo yükle
        Button(self.root, text="📂 JSON Senaryo",
               command=self.load_json_scenario ).grid(row=1, column=5, padx=6)
        
        # ✱ yeni – 10 Hz veri takibi
        self.follow_btn = Button(self.root, text="📡 Veri Takip",
                                 command=self.follow_data, state=DISABLED)
        self.follow_btn.grid(row=1, column=6, padx=6)

        # Girdi alanları
        Label(self.root, text="Koordinat (LAT,LON)").grid(row=2, column=0)
        self.coord_entry = Entry(self.root, width=28)
        self.coord_entry.grid(row=2, column=1, columnspan=2)

        for i, label in enumerate(["ALT (ft)", "SPD (knot)", "HDG (°)"]):
            Label(self.root, text=label).grid(row=3+i, column=0)
            entry = Entry(self.root)
            entry.grid(row=3+i, column=1)
            self.entries[label] = entry

        # Senaryo
        Label(self.root, text="Senaryo Listesi").grid(row=6, column=0, pady=6)
        Button(self.root, text="➕ Ekle", command=self.add_wp).grid(row=6, column=1)
        self.run_scen_btn = Button(self.root, text="▶️ Başlat",
                                   command=self.run_scenario, state=DISABLED)
        self.run_scen_btn.grid(row=6, column=2)
        self.scen_listbox = Listbox(self.root, height=6, width=58)
        self.scen_listbox.grid(row=7, column=0, columnspan=4)

    # --------------------------------------------------
    def _status(self, msg):
        self.status_label.config(text=msg)
        self.root.update_idletasks()

    # --------------------------------------------------
    def test_connection(self):
        try:
            self.sim_manager.connect()
            aq = self.sim_manager.get_requests()

            lat = aq.get("PLANE_LATITUDE")
            lon = aq.get("PLANE_LONGITUDE")
            alt = aq.get("PLANE_ALTITUDE")
            self._status(f"✅ Bağlandı  LAT {lat:.4f}  LON {lon:.4f}  ALT {alt:.0f}")

            # Controller’lara referans ver
            self.autopilot.aq = self.flight.aq = aq
            self.autopilot.ae = self.flight.ae = self.sim_manager.get_events()
            self.autopilot.status_callback = self._status
            self.flight.status_callback    = self._status

            # UI kilitlerini aç
            for btn in (self.takeoff_btn, self.teleport_btn,
                        self.fly_btn, self.follow_btn):
                btn.config(state=NORMAL)
        except Exception as e:
            self._status(f"❌ Bağlantı hatası: {e}")

    # --------------------------------------------------
    def set_data_stream(self, stream_iter):
        """Haricî 10 Hz veri kaynağını atar (iterator/generator)."""
        self.data_stream = stream_iter
        self._status("ℹ️ Veri kaynağı alındı – 📡 butonu hazır")

    def follow_data(self):
        if not self.data_stream:
            self._status("❌ Önce set_data_stream() ile veri kaynağı gir.")
            return
        threading.Thread(target=self.flight.follow_stream,
                         args=(self.data_stream, 0.1), daemon=True).start()

    # --------------------------------------------------
    def start_takeoff(self):
        threading.Thread(target=self.autopilot.takeoff_sequence, daemon=True).start()

    def teleport(self):
        try:
            lat, lon = map(float, self.coord_entry.get().split(","))
            alt = float(self.entries["ALT (ft)"].get())
            spd = float(self.entries["SPD (knot)"].get())
            hdg = float(self.entries["HDG (°)"].get())
            self.flight.teleport(lat, lon, alt, spd, hdg)
        except Exception as e:
            self._status(f"❌ Girdi hatası: {e}  (örn 39.989,36.431)")

    def fly_to(self):
        try:
            lat, lon = map(float, self.coord_entry.get().split(","))
            alt = float(self.entries["ALT (ft)"].get())
            spd = float(self.entries["SPD (knot)"].get())          # ✱ yeni
            self.flight.fly_to(lat, lon, alt, spd)                 # ✱ spd parametresi
        except Exception as e:
            self._status(f"❌ NAV hatası: {e}")

    # -------- Senaryo yardımcıları --------
    def add_wp(self):
        try:
            lat, lon = map(float, self.coord_entry.get().split(","))
            alt = float(self.entries["ALT (ft)"].get())
            spd = float(self.entries["SPD (knot)"].get())

            wp = {"lat": lat, "lon": lon, "alt": alt, "spd": spd}
            self.scenario.append(wp)

            self.scen_listbox.insert(END, f"{lat:.4f}, {lon:.4f}  |  {alt} ft  | {spd} kt")
            self.run_scen_btn.config(state=NORMAL)
        except Exception as e:
            self._status(f"❌ Senaryo girişi hatası: {e}")

    def run_scenario(self):
        if not self.scenario:
            self._status("❌ Senaryo boş.")
            return
        threading.Thread(target=self.flight.fly_scenario, args=(self.scenario,), daemon=True).start()

    def load_json_scenario(self):
        """Dosyadan JSON senaryo seç → 10 Hz akışa çevir → follow_stream."""
        path = filedialog.askopenfilename(
            title="JSON senaryo dosyası seç",
            filetypes=[("JSON files", "*.json")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                waypoints = json.load(f)
            if not isinstance(waypoints, list):
                raise ValueError("Liste formatı bekleniyor")

            # --- waypoint listesini 10 Hz jeneratöre sar ---
            def stream():
                for wp in waypoints:
                    yield {
                        "lat":  wp.get("latitude")  or wp.get("lat"),
                        "lon":  wp.get("longitude") or wp.get("lon"),
                        "alt":  wp.get("altitude_m") or wp.get("alt"),
                        "heading_deg":  wp.get("heading_deg", 0),  
                        "flaps":   wp.get("flaps", 0),
                        "elev_trim": wp.get("elev_trim", 0),
                    }
                    time.sleep(0.1)

            # Haricî kaynağı ata, butonu aç
            self.set_data_stream(stream())
            self.follow_btn.config(state=NORMAL)
            self._status(f"✅ {len(waypoints)} noktalı senaryo yüklendi")
        except Exception as e:
            self._status(f"❌ JSON okuma hatası: {e}")
