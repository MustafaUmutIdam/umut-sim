import math
import time
import threading


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
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 2 * R_nm * math.asin(math.sqrt(a))


class FlightController:
    def __init__(self, aq, ae, status_callback=None):
        self.aq = aq
        self.ae = ae
        self.status_callback = status_callback
        self.nav_thread = None
        self.nav_stop = threading.Event()

    def _status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    def _ev(self, name, *args):
        ev = self.ae.find(name) if self.ae else None
        if ev:
            ev(*args)

    def stop_nav(self):
        if self.nav_thread and self.nav_thread.is_alive():
            self.nav_stop.set()
            self.nav_thread.join()

    def teleport(self, lat, lon, alt, spd, hdg):
        try:
            self.aq.set("PLANE_LATITUDE", lat)
            self.aq.set("PLANE_LONGITUDE", lon)
            self.aq.set("PLANE_ALTITUDE", alt)
            self.aq.set("PLANE_HEADING_DEGREES_TRUE", hdg)
            self._ev("HEADING_BUG_SET", int(hdg))
            self._ev("AP_MASTER")
            self._ev("AP_HDG_HOLD_ON")
            self._ev("AP_ALT_VAR_SET_ENGLISH", int(alt))
            self._ev("AP_VS_SET_ENGLISH", 0)
            self._ev("THROTTLE_AXIS_SET_EX1", 8192)
            self._ev("AP_SPD_VAR_SET", int(spd))
            self._ev("AP_AUTOTHROTTLE_ARM")

            self._status(f"📍 Işınlandı → LAT {lat:.4f}  LON {lon:.4f}  ALT {alt}  SPD {spd}")
        except Exception as e:
            self._status(f"❌ Işınlama hatası: {e}")

    def fly_to(self, lat, lon, alt):
        self.stop_nav()
        self.nav_stop.clear()
        self._prepare_autopilot(lat, lon, alt)

        # 0.5 saniye sonra tekrar uygula
        threading.Timer(0.5, lambda: self._prepare_autopilot(lat, lon, alt)).start()

        self.nav_thread = threading.Thread(
            target=self._nav_loop, args=(lat, lon, alt), daemon=True
        )
        self.nav_thread.start()


    def fly_scenario(self, waypoints):
        self.stop_nav()
        self.nav_stop.clear()

        if not waypoints:
            self._status("❌ Senaryo boş.")
            return

        self.nav_thread = threading.Thread(
            target=self._scenario_loop, args=(waypoints,), daemon=True
        )
        self.nav_thread.start()

    def _prepare_autopilot(self, tgt_lat, tgt_lon, tgt_alt, tgt_spd=90):
        cur_lat = self.aq.get("PLANE_LATITUDE") or 0.0
        cur_lon = self.aq.get("PLANE_LONGITUDE") or 0.0
        brg = _bearing(cur_lat, cur_lon, tgt_lat, tgt_lon)

        self._ev("AP_MASTER")
        self._ev("HEADING_BUG_SET", int(brg))
        self._ev("AP_HDG_HOLD_OFF")
        time.sleep(0.05)
        self._ev("AP_HDG_HOLD_ON")

        self._ev("AP_ALT_VAR_SET_ENGLISH", int(tgt_alt))
        self._ev("AP_VS_SET_ENGLISH", 0)
        self._ev("AP_SPD_VAR_SET", int(tgt_spd))

        self.aq.set("FLAPS_HANDLE_PERCENT", 0)
        self.aq.set("ELEVATOR_TRIM_POSITION", 0)
        self._ev("THROTTLE_AXIS_SET_EX1", 8192)
        self._ev("AP_AUTOTHROTTLE_ARM")

    def _nav_loop(self, tgt_lat, tgt_lon, tgt_alt):
        self._status("🗺️ NAV başladı…")
        try:
            while not self.nav_stop.is_set():
                cur_lat = self.aq.get("PLANE_LATITUDE")
                cur_lon = self.aq.get("PLANE_LONGITUDE")
                cur_alt = self.aq.get("PLANE_ALTITUDE")

                if None in (cur_lat, cur_lon, cur_alt):
                    time.sleep(0.5)
                    continue

                dist_nm = _haversine_nm(cur_lat, cur_lon, tgt_lat, tgt_lon)
                alt_err = tgt_alt - cur_alt

                if dist_nm < 0.3:
                    self._status("✅ Hedefe ulaşıldı")
                    break

                brg = _bearing(cur_lat, cur_lon, tgt_lat, tgt_lon)
                self._ev("HEADING_BUG_SET", int(brg))
                self._ev("AP_HDG_HOLD_ON")

                vs_cmd = 0
                if abs(alt_err) > 25:
                    vs_cmd = max(min(alt_err * 1.5, 500), -500)

                self._ev("AP_ALT_VAR_SET_ENGLISH", int(tgt_alt))
                self._ev("AP_VS_SET_ENGLISH", int(vs_cmd))

                self._status(
                    f"🛫 NAV → Dist {dist_nm:.2f} NM  AltFark {alt_err:.0f} ft  BRG {brg:.0f}°"
                )
                time.sleep(1)

            self._ev("AP_VS_SET_ENGLISH", 0)
        except Exception as e:
            self._status(f"❌ NAV hata: {e}")

    def _scenario_loop(self, waypoints):
        self._status("📍 Senaryo başladı…")
        try:
            for idx, wp in enumerate(waypoints, start=1):
                if self.nav_stop.is_set():
                    break

                tgt_lat = wp["lat"]
                tgt_lon = wp["lon"]
                tgt_alt = wp["alt"]
                tgt_spd = wp.get("spd", 90)

                self._status(
                    f"🎯 Nokta {idx}/{len(waypoints)} → LAT {tgt_lat:.4f}  LON {tgt_lon:.4f}  ALT {tgt_alt}  SPD {tgt_spd}"
                )

                self._prepare_autopilot(tgt_lat, tgt_lon, tgt_alt, tgt_spd)
                # 0.5 saniye sonra tekrar uygula
                threading.Timer(0.5, lambda: self._prepare_autopilot(tgt_lat, tgt_lon, tgt_alt, tgt_spd)).start()

                while not self.nav_stop.is_set():
                    cur_lat = self.aq.get("PLANE_LATITUDE")
                    cur_lon = self.aq.get("PLANE_LONGITUDE")
                    cur_alt = self.aq.get("PLANE_ALTITUDE")

                    if None in (cur_lat, cur_lon, cur_alt):
                        time.sleep(0.5)
                        continue

                    dist_nm = _haversine_nm(cur_lat, cur_lon, tgt_lat, tgt_lon)
                    alt_err = tgt_alt - cur_alt

                    if dist_nm < 0.3:
                        self._status(f"✅ Nokta {idx} tamamlandı")
                        break

                    brg = _bearing(cur_lat, cur_lon, tgt_lat, tgt_lon)
                    self._ev("HEADING_BUG_SET", int(brg))
                    self._ev("AP_HDG_HOLD_ON")

                    vs_cmd = 0
                    if abs(alt_err) > 25:
                        vs_cmd = max(min(alt_err * 1.5, 500), -500)

                    self._ev("AP_ALT_VAR_SET_ENGLISH", int(tgt_alt))
                    self._ev("AP_VS_SET_ENGLISH", int(vs_cmd))

                    self._status(
                        f"✈️ {idx}. Nokta → Dist {dist_nm:.2f} NM  AltFark {alt_err:.0f} ft  BRG {brg:.0f}°"
                    )
                    time.sleep(1)

            self._status("✅ Senaryo tamamlandı.")
            self._ev("AP_VS_SET_ENGLISH", 0)
        except Exception as e:
            self._status(f"❌ Senaryo hata: {e}")
