from SimConnect import SimConnect, AircraftRequests, AircraftEvents

class SimConnectManager:
    def __init__(self):
        self.sm = None
        self.aq = None
        self.ae = None

    def connect(self):
        self.sm = SimConnect()
        self.aq = AircraftRequests(self.sm, _time=2000)
        self.ae = AircraftEvents(self.sm)

    def get_requests(self):
        return self.aq

    def get_events(self):
        return self.ae
