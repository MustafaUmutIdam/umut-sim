import math, time, threading

# --- Coğrafi yardımcı fonksiyonlar ---
def _bearing(lat1, lon1, lat2, lon2):
    rlat1, rlat2 = map(math.radians, (lat1, lat2))
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(rlat2)
    y = math.cos(rlat1) * math.sin(rlat2) - math.sin(rlat1) * math.cos(rlat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def _haversine_nm(lat1, lon1, lat2, lon2):
    R_nm = 3440.065
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 2 * R_nm * math.asin(math.sqrt(a))

# --- FlightController ---
class FlightController:
    def __init__(self, aq, ae, status_callback=None):
        self.aq = aq
        self.ae = ae
        self.status_callback = status_callback
        # NAV thread kontrolü
        self.nav_thread = None
        self.nav_stop   = threading.Event()

    # --------------------------------------------------
    def set_status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    # --------------------------------------------------
    def teleport(self, lat, lon, alt, spd, hdg):
        try:
            self.aq.set("PLANE_LATITUDE", lat)
            self.aq.set("PLANE_LONGITUDE", lon)
            self.aq.set("PLANE_ALTITUDE", alt)
            self.aq.set("PLANE_HEADING_DEGREES_TRUE", hdg)

            if self.ae.find("HEADING_BUG_SET"):
                self.ae.find("HEADING_BUG_SET")(int(hdg))
            if self.ae.find("AP_HDG_HOLD_ON"):
                self.ae.find("AP_HDG_HOLD_ON")()

            if throttle := self.ae.find("THROTTLE_AXIS_SET_EX1"):
                throttle(8192)

            if self.ae.find("AP_MASTER"):
                self.ae.find("AP_MASTER")()
            if self.ae.find("AP_ALT_VAR_SET_ENGLISH"):
                self.ae.find("AP_ALT_VAR_SET_ENGLISH")(int(alt))
            if self.ae.find("AP_VS_SET_ENGLISH"):
                self.ae.find("AP_VS_SET_ENGLISH")(0)

            try:
                if self.ae.find("AP_SPD_VAR_SET"):
                    self.ae.find("AP_SPD_VAR_SET")(int(spd))
                if self.ae.find("AP_AUTOTHROTTLE_ARM"):
                    self.ae.find("AP_AUTOTHROTTLE_ARM")()
            except:
                pass

            self.set_status(f"📍 Işınlandı → LAT:{lat}, LON:{lon}, ALT:{alt}, SPD:{spd}")
        except Exception as e:
            self.set_status(f"❌ Işınlama hatası: {e}")

    # --------------------------------------------------
    def fly_to(self, tgt_lat, tgt_lon, tgt_alt):
        """Hedef koordinata tekil NAV döngüsüyle uç."""
        # — Eski NAV döngüsü çalışıyorsa durdur
        if self.nav_thread and self.nav_thread.is_alive():
            self.nav_stop.set()
            self.nav_thread.join()

        # Yeni NAV thread’i başlat
        self.nav_stop.clear()
        self.nav_thread = threading.Thread(
            target=self._nav_loop,
            args=(tgt_lat, tgt_lon, tgt_alt),
            daemon=True
        )
        self.nav_thread.start()

    def fly_scenario(self, waypoints):
    
        if self.nav_thread and self.nav_thread.is_alive():
            self.nav_stop.set()
            self.nav_thread.join()

        self.nav_stop.clear()
        self.nav_thread = threading.Thread(
            target=self._scenario_loop,
            args=(waypoints,),
            daemon=True
        )
        self.nav_thread.start()

    def _scenario_loop(self, waypoints):
        try:
            self.set_status("📍 Senaryo uçuşu başlatıldı...")
            for idx, wp in enumerate(waypoints):
                tgt_lat = wp["lat"]
                tgt_lon = wp["lon"]
                tgt_alt = wp["alt"]
                tgt_spd = wp.get("spd", 100)

                self.set_status(f"🎯 Hedef {idx+1}/{len(waypoints)} → LAT:{tgt_lat}, LON:{tgt_lon}, ALT:{tgt_alt}, SPD:{tgt_spd}")

                if self.ae.find("AP_MASTER"):
                    self.ae.find("AP_MASTER")()
                if self.ae.find("AP_HDG_HOLD_ON"):
                    self.ae.find("AP_HDG_HOLD_ON")()

                if self.ae.find("AP_SPD_VAR_SET"):
                    self.ae.find("AP_SPD_VAR_SET")(int(tgt_spd))

                while not self.nav_stop.is_set():
                    cur_lat = self.aq.get("PLANE_LATITUDE")
                    cur_lon = self.aq.get("PLANE_LONGITUDE")
                    cur_alt = self.aq.get("PLANE_ALTITUDE")

                    dist_nm = _haversine_nm(cur_lat, cur_lon, tgt_lat, tgt_lon)
                    alt_err = tgt_alt - cur_alt

                    if dist_nm < 0.3:
                        self.set_status(f"✅ Hedef {idx+1} ulaşıldı!")
                        break

                    brg = _bearing(cur_lat, cur_lon, tgt_lat, tgt_lon)

                    # ✅ Yönü ve HDG modunu sürekli güncelle
                    if self.ae.find("HEADING_BUG_SET"):
                        self.ae.find("HEADING_BUG_SET")(int(brg))
                    if self.ae.find("AP_HDG_HOLD_ON"):
                        self.ae.find("AP_HDG_HOLD_ON")()

                    # VS (vertical speed) hesaplama ve uygulama
                    vs_cmd = 0
                    if abs(alt_err) > 20:
                        vs_cmd = max(min(alt_err * 1.5, 500), -500)
                    if self.ae.find("AP_ALT_VAR_SET_ENGLISH"):
                        self.ae.find("AP_ALT_VAR_SET_ENGLISH")(int(tgt_alt))
                    if vs_cmd and self.ae.find("AP_VS_SET_ENGLISH"):
                        self.ae.find("AP_VS_SET_ENGLISH")(int(vs_cmd))

                    self.set_status(
                        f"🛫 {idx+1}. Hedefe Gidiliyor → Dist:{dist_nm:.1f} NM | AltFark:{alt_err:.0f} ft | BRG:{brg:.0f}°"
                    )
                    time.sleep(1)

            self.set_status("🏁 Senaryo tamamlandı.")
            if self.ae.find("AP_VS_SET_ENGLISH"):
                self.ae.find("AP_VS_SET_ENGLISH")(0)
        except Exception as e:
            self.set_status(f"❌ Senaryo NAV hatası: {e}")


    # --------------------------------------------------
    def _nav_loop(self, tgt_lat, tgt_lon, tgt_alt):
        try:
            self.set_status("🗺️ Navigasyon başladı…")
            ae, aq = self.ae, self.aq
            ae.find("AP_MASTER")()
            ae.find("AP_HDG_HOLD_ON")()

            while not self.nav_stop.is_set():
                cur_lat = self.aq.get("PLANE_LATITUDE")
                cur_lon = self.aq.get("PLANE_LONGITUDE")
                cur_alt = self.aq.get("PLANE_ALTITUDE")

                dist_nm = _haversine_nm(cur_lat, cur_lon, tgt_lat, tgt_lon)
                alt_err = tgt_alt - cur_alt

                if dist_nm < 0.3:
                    self.set_status(f"✅ Hedef {idx+1} ulaşıldı!")
                    break
                
                brg = _bearing(cur_lat, cur_lon, tgt_lat, tgt_lon)
                self.ae.find("HEADING_BUG_SET")(int(brg))
                

                vs_cmd = 0
                if abs(alt_err) > 20:
                    vs_cmd = max(min(alt_err * 1.5, 500), -500)

                self.ae.find("AP_ALT_VAR_SET_ENGLISH")(int(tgt_alt))
                if vs_cmd and self.ae.find("AP_VS_SET_ENGLISH"):
                    self.ae.find("AP_VS_SET_ENGLISH")(int(vs_cmd))

                self.set_status(
                    f"🛫 {idx+1}. Hedefe Gidiliyor → Dist:{dist_nm:.1f} NM | AltFark:{alt_err:.0f} ft | BRG:{brg:.0f}°"
                )
                time.sleep(1)


            # Döngüden çıkarken VS'yi sıfırla
            if ae.find("AP_VS_SET_ENGLISH"):
                ae.find("AP_VS_SET_ENGLISH")(0)
        except Exception as e:
            self.set_status(f"❌ NAV hata: {e}")

