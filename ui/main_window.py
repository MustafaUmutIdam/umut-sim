from tkinter import *
import threading

class MainWindow:
    def __init__(self, root, sim_manager, autopilot, flight):
        self.root = root
        self.sim_manager = sim_manager
        self.autopilot = autopilot
        self.flight = flight

        self.setup_ui()

    def setup_ui(self):
        self.root.title("MSFS Otomatik Kalkış ve Işınlama Paneli")

        self.status_label = Label(self.root, text="SimConnect bağlantısı test edilmedi", fg="red")
        self.status_label.grid(row=0, column=0, columnspan=4, pady=5)

        Button(self.root, text="🔌 Bağlantıyı Test Et", command=self.test_connection).grid(row=1, column=0, padx=10)
        self.apply_button = Button(self.root, text="🚀 Otomatik Kalkış", command=self.start_takeoff, state=DISABLED)
        self.apply_button.grid(row=1, column=1, padx=10)

        self.teleport_button = Button(self.root, text="📍 Işınla ve Hız Ayarla", command=self.teleport, state=DISABLED)
        self.teleport_button.grid(row=1, column=2, padx=10)

        self.fly_button = Button(self.root, text="🧭 Fly To (NAV)", state=DISABLED, command=self.fly_to)
        self.fly_button.grid(row=1, column=3, padx=10)

        self.entries = {}

        # Tek satırlı koordinat girişi
        Label(self.root, text="Koordinat (LAT,LON):").grid(row=2, column=0)
        self.coord_entry = Entry(self.root, width=30)
        self.coord_entry.grid(row=2, column=1, columnspan=2)

        for i, label in enumerate(["ALT (ft)", "SPD (knot)", "HDG (°)"]):
            Label(self.root, text=label).grid(row=3 + i, column=0)
            entry = Entry(self.root)
            entry.grid(row=3 + i, column=1)
            self.entries[label] = entry

    def update_status(self, msg):
        self.status_label.config(text=msg)
        self.root.update()

    def test_connection(self):
        try:
            self.sim_manager.connect()
            aq = self.sim_manager.get_requests()
            lat = aq.get("PLANE_LATITUDE")
            lon = aq.get("PLANE_LONGITUDE")
            alt = aq.get("PLANE_ALTITUDE")

            self.update_status(f"✅ Bağlantı başarılı!\nLat: {lat:.6f}, Lon: {lon:.6f}, Alt: {alt:.1f}")
            self.apply_button.config(state=NORMAL)
            self.teleport_button.config(state=NORMAL)
            self.fly_button.config(state=NORMAL)

            # Set callbacks
            self.autopilot.aq = aq
            self.autopilot.ae = self.sim_manager.get_events()
            self.autopilot.status_callback = self.update_status

            self.flight.aq = aq
            self.flight.ae = self.sim_manager.get_events()
            self.flight.status_callback = self.update_status
        except Exception as e:
            self.update_status(f"Bağlantı hatası: {e}")

    def start_takeoff(self):
        threading.Thread(target=self.autopilot.takeoff_sequence).start()

    def teleport(self):
        try:
            # Yeni giriş formatı: "LAT,LON"
            coord_str = self.coord_entry.get().strip()
            lat, lon = map(float, coord_str.split(","))
            alt = float(self.entries["ALT (ft)"].get())
            spd = float(self.entries["SPD (knot)"].get())
            hdg = float(self.entries["HDG (°)"].get())

            self.flight.teleport(lat, lon, alt, spd, hdg)
        except Exception as e:
            self.update_status(f"Giriş hatası: {e}\n📌 Format: 39.989,36.431")

    def fly_to(self):
        try:
            coord_str = self.coord_entry.get().strip()
            lat, lon = map(float, coord_str.split(","))
            alt = float(self.entries["ALT (ft)"].get())

            self.flight.fly_to(lat, lon, alt)
        except Exception as e:
            self.update_status(f"Uçuş yönlendirme hatası: {e}\n📌 Format: 39.989,36.431")
