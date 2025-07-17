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


    def follow_stream(self, stream, interval=0.1):
        self.stop_nav()
        self.nav_stop.clear()
        self._status("📡 Veri takibi başladı…")

        def _loop():
            try:
                self._ev("AP_MASTER_OFF")

                for frame in stream:
                    if self.nav_stop.is_set():
                        break

                    lat = frame.get("lat")
                    lon = frame.get("lon")
                    alt = frame.get("alt")
                    hdg = frame.get("heading_deg")
                    pitch = frame.get("pitch_deg") or frame.get("pitch")
                    roll  = frame.get("roll_deg")  or frame.get("bank") or frame.get("roll")
                    yaw   = frame.get("yaw_deg")

                    # Pozisyon
                    if lat is not None: self.aq.set("PLANE_LATITUDE", lat)
                    if lon is not None: self.aq.set("PLANE_LONGITUDE", lon)
                    if alt is not None: self.aq.set("PLANE_ALTITUDE", alt)

                    if hdg is not None:
                        print(f"Trying to set heading to {hdg}")
                        hdg_deg = frame["heading_deg"]
                        hdg_rad = math.radians(hdg_deg) * 366 / 360
                        self._ev("HEADING_BUG_SET", int(hdg))
                        self.aq.set("PLANE_HEADING_DEGREES_TRUE", hdg_rad) # Asıl heading set 
                        print(f"Trying to set heading to {hdg_rad}")

                        
                    self._status(
                        f"📡 LAT {lat:.4f} LON {lon:.4f} ALT {alt} HDG {hdg}"
                    )
                    time.sleep(interval)

                self._status("✅ Veri takibi bitti.")
            except Exception as e:
                self._status(f"❌ Veri takibi hata: {e}")

        threading.Thread(target=_loop, daemon=True).start()

    def teleport(self, lat, lon, alt, spd, hdg=None, step_m=5):
        """
        Hedefe kademeli ‘ışınlama’: her saniye ≈ step_m metre.
        • lat, lon, alt : hedef konum
        • spd          : uçuş hızı (otopilot için)
        • hdg=None     : ilk adımda zorla heading -> otomatik hesap; elle verirsen bu kullanılır
        • step_m       : yatay adım (metre)
        """
        try:
            # --- Mevcut konum / irtifa ---
            cur_lat = self.aq.get("PLANE_LATITUDE")
            cur_lon = self.aq.get("PLANE_LONGITUDE")
            cur_alt = self.aq.get("PLANE_ALTITUDE")

            if None in (cur_lat, cur_lon, cur_alt):
                self._status("❌ Sim verisi alınamadı.")
                return

            # --- Bearing & toplam mesafe (metre) ---
            bearing_deg = _bearing(cur_lat, cur_lon, lat, lon)
            total_nm    = _haversine_nm(cur_lat, cur_lon, lat, lon)
            total_m     = total_nm * 1852.0
            alt_diff    = alt - cur_alt
            steps       = max(1, int(total_m // step_m))

            # Bir adımda kaç derece gidilecek? (yaklaşık)
            def meters_to_deg_lat(m):  return m / 111_111.0
            def meters_to_deg_lon(m, latitude):
                return m / (111_111.0 * math.cos(math.radians(latitude)))

            d_lat_per = meters_to_deg_lat(step_m * math.cos(math.radians(bearing_deg)))
            d_lon_per = meters_to_deg_lon(step_m * math.sin(math.radians(bearing_deg)), cur_lat)
            d_alt_per = alt_diff / steps if steps else 0.0

            self._status(f"🚀 Kademeli ışınlama → {steps} adım, ~{step_m} m/step")

            # Otomatik heading: ilk adımda ayarla
            first_hdg = int(hdg if hdg is not None else bearing_deg)
            self._ev("HEADING_BUG_SET", first_hdg)
            self._ev("AP_HDG_HOLD_ON")

            # ---- Adım döngüsü (ayrı thread) ----
            def _step_loop():
                nonlocal cur_lat, cur_lon, cur_alt
                for i in range(steps):
                    if self.nav_stop.is_set():
                        break

                    cur_lat += d_lat_per
                    cur_lon += d_lon_per
                    cur_alt += d_alt_per

                    self.aq.set("PLANE_LATITUDE",  cur_lat)
                    self.aq.set("PLANE_LONGITUDE", cur_lon)
                    self.aq.set("PLANE_ALTITUDE",  cur_alt)

                    self._ev("AP_ALT_VAR_SET_ENGLISH", int(cur_alt))
                    self._status(f"📍 Step {i+1}/{steps}  LAT:{cur_lat:.6f}  LON:{cur_lon:.6f}  ALT:{cur_alt:.1f}")
                    time.sleep(0.1)

                # Son değerleri hedefe eşitle
                self.aq.set("PLANE_LATITUDE",  lat)
                self.aq.set("PLANE_LONGITUDE", lon)
                self.aq.set("PLANE_ALTITUDE",  alt)
                self._status("✅ Işınlama tamamlandı.")

                # Seyir parametreleri
                self._ev("AP_MASTER")
                self._ev("AP_ALT_VAR_SET_ENGLISH", int(alt))
                self._ev("AP_VS_SET_ENGLISH", 0)
                self._ev("AP_SPD_VAR_SET", int(spd))
                self._ev("AP_AUTOTHROTTLE_ARM")
                self._ev("THROTTLE_AXIS_SET_EX1", 8192)

            threading.Thread(target=_step_loop, daemon=True).start()

        except Exception as e:
            self._status(f"❌ Işınlama hatası: {e}")

    def fly_to(self, lat, lon, alt, spd):
        self._ev("AP_ALT_HOLD_OFF")
        self.stop_nav()
        self.nav_stop.clear()
        self._prepare_autopilot(lat, lon, alt, spd)                # ✱ spd ile
        
        threading.Timer(0.5, lambda: self._prepare_autopilot(lat, lon, alt, spd)).start()
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

    def _prepare_autopilot(self, tgt_lat, tgt_lon, tgt_alt, tgt_spd):
        self._ev("AP_ALT_HOLD_OFF")

        cur_lat = self.aq.get("PLANE_LATITUDE") or 0.0
        cur_lon = self.aq.get("PLANE_LONGITUDE") or 0.0
        cur_alt = self.aq.get("PLANE_ALTITUDE")   or 0.0
        brg     = _bearing(cur_lat, cur_lon, tgt_lat, tgt_lon)
        alt_err = tgt_alt - cur_alt

        self._ev("AP_MASTER")
        self._ev("HEADING_BUG_SET", int(brg))
        self._ev("AP_HDG_HOLD_OFF"); time.sleep(0.05); self._ev("AP_HDG_HOLD_ON")

        # ---- dikey profil ----
        self._ev("AP_ALT_VAR_SET_ENGLISH", int(tgt_alt))
        initial_vs = 800 if alt_err > 0 else -800          # ±800 ft/dk
        self._ev("AP_VS_SET_ENGLISH", initial_vs)

        # ---- hız ----
        self._ev("AP_SPD_VAR_SET", int(tgt_spd))           # ✱ hedef hız

        # trim / throttle
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

                if abs(alt_err) < 100 and abs(dist_nm) < 3:
                    self._ev("AP_ALT_HOLD_ON")
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
                threading.Timer(0.5, lambda lat=tgt_lat, lon=tgt_lon, alt=tgt_alt, spd=tgt_spd:
                self._prepare_autopilot(lat, lon, alt, spd)).start()

                while not self.nav_stop.is_set():
                    cur_lat = self.aq.get("PLANE_LATITUDE")
                    cur_lon = self.aq.get("PLANE_LONGITUDE")
                    cur_alt = self.aq.get("PLANE_ALTITUDE")

                    if None in (cur_lat, cur_lon, cur_alt):
                        time.sleep(0.5)
                        continue

                    dist_nm = _haversine_nm(cur_lat, cur_lon, tgt_lat, tgt_lon)
                    alt_err = tgt_alt - cur_alt

                    if abs(alt_err) < 100 and abs(dist_nm) < 3:
                        self._ev("AP_ALT_HOLD_ON")

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
