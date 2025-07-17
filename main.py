from tkinter import Tk
from core.simconnect_manager import SimConnectManager
from core.autopilot_controller import AutopilotController
from core.flight_controller import FlightController
from ui.main_window import MainWindow


if __name__ == "__main__":
    root = Tk()

    sim_manager = SimConnectManager()          # SimConnect sarmalayıcısı
    autopilot   = AutopilotController(None, None)
    flight      = FlightController(None, None)
    app = MainWindow(root, sim_manager, autopilot, flight)
    root.mainloop()
