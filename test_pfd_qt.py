from PyQt5.QtWidgets import QApplication
from ui.pfd_window import PFDWindowQt
from core.simconnect_manager import SimConnectManager
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    sim_manager = SimConnectManager()
    sim_manager.connect()
    aq = sim_manager.get_requests()
    pfd = PFDWindowQt(aq)
    sys.exit(app.exec_()) 