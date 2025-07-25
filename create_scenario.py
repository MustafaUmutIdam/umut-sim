import json
import math
import random

# Başlangıç konumu
start_lat = 40.891508
start_lon = 29.303727
start_alt = 1000

# Parametreler
step_distance_m = 20  
step_altitude_m = 10
num_points = 600
R = 6371000

# Sabit heading: batı (270 derece)
heading = 240

# Sahte kanat açısı üretimi
def random_attitude():
    return {
        "roll_deg": round(random.uniform(-5, 5), 2),
        "pitch_deg": round(random.uniform(-2, 2), 2),
        "yaw_deg": round(random.uniform(-3, 3), 2)
    }

# Yeni pozisyonu heading'e göre hesapla
def move_from(lat, lon, heading_deg, distance_m):
    heading_rad = math.radians(heading_deg)
    delta_lat = (distance_m * math.cos(heading_rad)) / R * (180 / math.pi)
    delta_lon = (distance_m * math.sin(heading_rad)) / (R * math.cos(math.radians(lat))) * (180 / math.pi)
    return lat + delta_lat, lon + delta_lon

lat = start_lat
lon = start_lon
alt = start_alt

waypoints = []

for i in range(num_points):
    lat, lon = move_from(lat, lon, heading, step_distance_m)
    alt += step_altitude_m

    attitude = random_attitude()

    waypoints.append({
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "altitude_m": round(alt, 2),
        "heading_deg": heading,  
        **attitude
    })

with open("scenario_waypoints.json", "w", encoding="utf-8") as f:
    json.dump(waypoints, f, indent=2)

print("✅ scenario_waypoints.json oluşturuldu! Nokta sayısı:", len(waypoints))
