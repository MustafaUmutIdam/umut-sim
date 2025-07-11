import time

class AutopilotController:
    def __init__(self, aq, ae, status_callback=None):
        self.aq = aq
        self.ae = ae
        self.status_callback = status_callback

    def set_status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    def takeoff_sequence(self):
        try:
            # El freni ve kalkış ayarları
            pb = self.ae.find("PARKING_BRAKES")
            if pb: pb()

            self.aq.set("GENERAL_ENG_THROTTLE_LEVER_POSITION:1", 100)
            self.aq.set("FLAPS_HANDLE_PERCENT", 25)
            self.aq.set("ELEVATOR_TRIM_POSITION", 100)
            self.set_status("🚀 Kalkış başladı...")

            while True:
                spd = self.aq.get("AIRSPEED_INDICATED")
                if spd and spd >= 70:
                    break
                time.sleep(0.5)

            alt = self.aq.get("PLANE_ALTITUDE")
            target_alt = alt + 200

            # Otopilot ayarları
            self.ae.find("AP_ALT_VAR_SET_ENGLISH")(int(target_alt))
            self.ae.find("AP_MASTER")()
            if self.ae.find("AP_VS_SET_ENGLISH"):
                self.ae.find("AP_VS_SET_ENGLISH")(1000)

            self.set_status(f"🛫 {int(target_alt)} ft'e tırmanılıyor...")

            while True:
                cur_alt = self.aq.get("PLANE_ALTITUDE")
                alt_hold = self.aq.get("AUTOPILOT_ALTITUDE_LOCK")
                if cur_alt and alt_hold and abs(cur_alt - target_alt) < 50:
                    break
                time.sleep(1)

            # Düz uçuş
            self.ae.find("THROTTLE_AXIS_SET_EX1")(6554)
            self.set_status("🛩️ Düz uçuş başladı. Işınlama yapılabilir.")
        except Exception as e:
            self.set_status(f"Hata: {e}")
