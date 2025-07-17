import time


class AutopilotController:
    """
    ***Sadece otomatik kalkış ile ilgili.***
    Kalkış biter bitmez AP'yi “VS mode”a bırakıyoruz, böylece
    sonradan FlightController hedef irtifa gönderebildiğinde
    uçağın sabit irtifaya ‘kilitlenme’ problemi kalmıyor.
    """

    def __init__(self, aq, ae, status_callback=None):
        self.aq = aq
        self.ae = ae
        self.status_callback = status_callback

    # --------------------------------------------------
    def set_status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    # --------------------------------------------------
    def takeoff_sequence(self):
        try:
            # Park frenini bırak
            if ev := self.ae.find("PARKING_BRAKES"):
                ev()

            # Tam gaz + kalkış konfigurasyonu
            self.aq.set("GENERAL_ENG_THROTTLE_LEVER_POSITION:1", 100)
            self.aq.set("FLAPS_HANDLE_PERCENT", 25)
            self.aq.set("ELEVATOR_TRIM_POSITION", 100)
            self.set_status("🚀 Kalkış başladı...")

            # 70 kt IAS’ya ulaşana kadar bekle
            while (spd := self.aq.get("AIRSPEED_INDICATED")) is None or spd < 70:
                time.sleep(0.5)

            # Anlık irtifaya +350 ft’lik bir tırmanış talimatı ver
            cur_alt    = self.aq.get("PLANE_ALTITUDE")
            target_alt = cur_alt + 350

            if ev := self.ae.find("AP_MASTER"):
                ev()
            if ev := self.ae.find("AP_ALT_VAR_SET_ENGLISH"):
                ev(int(target_alt))
            if ev := self.ae.find("AP_VS_SET_ENGLISH"):
                ev(1000)                       # 1000 ft/dk tırman

            self.set_status(f"🛫 {int(target_alt)} ft’e tırmanılıyor...")

            # Hedef irtifaya ±50 ft yaklaşınca VS’yi sıfırla ‑ ALT HOLD bırakma!
            while True:
                cur_alt = self.aq.get("PLANE_ALTITUDE")
                if cur_alt and abs(cur_alt - target_alt) < 50:
                    if ev := self.ae.find("AP_VS_SET_ENGLISH"):
                        ev(0)
                    break
                time.sleep(1)
                
            # VS’yi 0’a çektikten hemen sonra:
            if ev := self.ae.find("AP_ALT_HOLD_OFF"):
                ev()                       # ✱ ALT kilidini kapat
            
                

            # Motor gücünü seyir değerine çek
            if ev := self.ae.find("THROTTLE_AXIS_SET_EX1"):
                ev(6554)                       # ≈ %50 güç

            self.set_status("🛩️ Düz uçuş başladı – ışınlama / NAV artık serbest.")
        except Exception as e:
            self.set_status(f"❌ Kalkış hatası: {e}")
