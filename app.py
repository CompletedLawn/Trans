import sys
import subprocess

# Auto-install missing dependencies at runtime (useful when deploying only app.py on share.streamlit)
required_packages = ["folium", "streamlit-folium", "matplotlib", "pandas", "numpy"]
for package in required_packages:
    try:
        __import__(package.replace("-", "_"))
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium import plugins
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import zipfile
import io
import math

# Page settings
st.set_page_config(
    layout="wide",
    page_title="국민 교통 소외 분석 및 버스 노선 추천 서비스 (Transit Desert Finder)",
    page_icon="🚌"
)

# Inject custom modern CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    * {
        font-family: 'Inter', 'Noto Sans KR', sans-serif;
    }
    
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #FF4B4B 0%, #7F00FF 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        text-align: left;
    }
    
    .sub-title {
        font-size: 1.1rem;
        color: #555;
        margin-bottom: 1.5rem;
        text-align: left;
    }
    
    /* Glassmorphism containers */
    .glass-card {
        background: rgba(255, 255, 255, 0.85);
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
        border: 1px solid rgba(255, 255, 255, 0.5);
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 10px 30px 0 rgba(0, 0, 0, 0.05);
        margin-bottom: 1.5rem;
    }
    
    .metric-label {
        font-size: 0.85rem;
        color: #777;
        font-weight: 600;
        margin-bottom: 0.2rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1A1A1A;
    }
    
    .metric-sub {
        font-size: 0.85rem;
        margin-top: 0.3rem;
        font-weight: 500;
    }
    
    .accent-text-green { color: #00B074; }
    .accent-text-red { color: #FF3B30; }
    .accent-text-blue { color: #007AFF; }
    
    /* Table styling */
    .styled-table {
        width: 100%;
        border-collapse: collapse;
        margin: 1rem 0;
        font-size: 0.9rem;
        border-radius: 8px;
        overflow: hidden;
    }
    .styled-table th {
        background-color: #7F00FF;
        color: white;
        text-align: left;
        font-weight: bold;
        padding: 12px 15px;
    }
    .styled-table td {
        padding: 12px 15px;
        border-bottom: 1px solid #dddddd;
    }
    .styled-table tr:nth-of-type(even) {
        background-color: #f3f3f3;
    }
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------
# Helper Functions
# ----------------------------------------------------

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points in km."""
    R = 6371.0 # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def generate_simulated_network_for_bounds(lat_min, lat_max, lon_min, lon_max):
    """
    Dynamically generates a stable simulated transit network
    inside the user's visible map viewports.
    """
    # Seed based on coordinates so panning back/forth is stable
    coord_hash = int(abs(lat_min + lon_min + lat_max + lon_max) * 1000) % 100000
    np.random.seed(coord_hash)
    
    lat_center = (lat_min + lat_max) / 2
    lon_center = (lon_min + lon_max) / 2
    lat_span = lat_max - lat_min
    lon_span = lon_max - lon_min
    
    stops = []
    routes = []
    stop_routes = []
    
    # 1. Subway Line A (Diagonal SW -> NE)
    sub1_id = "SUB_A"
    routes.append((sub1_id, "수도권 광역 메트로 A선", "subway", 70))
    n_sub1 = 6
    lats_s1 = np.linspace(lat_min + 0.15 * lat_span, lat_max - 0.15 * lat_span, n_sub1)
    lons_s1 = np.linspace(lon_min + 0.15 * lon_span, lon_max - 0.15 * lon_span, n_sub1)
    for i in range(n_sub1):
        stop_id = f"S_A_{i}"
        name = f"메트로A선 {int(lons_s1[i]*1000)%100}역"
        stops.append((stop_id, name, lats_s1[i], lons_s1[i], "subway"))
        stop_routes.append((stop_id, sub1_id))
        
    # 2. Subway Line B (Diagonal NW -> SE)
    sub2_id = "SUB_B"
    routes.append((sub2_id, "수도권 광역 메트로 B선", "subway", 55))
    n_sub2 = 5
    lats_s2 = np.linspace(lat_max - 0.2 * lat_span, lat_min + 0.2 * lat_span, n_sub2)
    lons_s2 = np.linspace(lon_min + 0.15 * lon_span, lon_max - 0.15 * lon_span, n_sub2)
    for i in range(n_sub2):
        stop_id = f"S_B_{i}"
        name = f"메트로B선 {int(lons_s2[i]*1000)%100}역"
        stops.append((stop_id, name, lats_s2[i], lons_s2[i], "subway"))
        stop_routes.append((stop_id, sub2_id))
        
    # 3. Create Bus Lines (4 lines)
    bus_colors = ["blue", "green", "red", "yellow"]
    for b in range(4):
        bus_id = f"BUS_{100 + b*15}"
        routes.append((bus_id, f"{100 + b*15}번 시내버스", "bus", 24 + b*6))
        
        # A route path with random walk structure to look like a street network
        n_bus_stops = 8
        start_lat = np.random.uniform(lat_min + 0.1*lat_span, lat_max - 0.1*lat_span)
        start_lon = np.random.uniform(lon_min + 0.1*lon_span, lon_max - 0.1*lon_span)
        
        curr_lat, curr_lon = start_lat, start_lon
        for i in range(n_bus_stops):
            stop_id = f"B_{b}_{i}"
            name = f"{100 + b*15}번 버스정류장 ({int(curr_lat*1000)%100}-{int(curr_lon*1000)%100})"
            stops.append((stop_id, name, curr_lat, curr_lon, "bus"))
            stop_routes.append((stop_id, bus_id))
            
            # Step in random direction
            curr_lat += np.random.uniform(-0.15 * lat_span, 0.15 * lat_span)
            curr_lon += np.random.uniform(-0.15 * lon_span, 0.15 * lon_span)
            # Clip inside map bounds
            curr_lat = np.clip(curr_lat, lat_min + 0.05*lat_span, lat_max - 0.05*lat_span)
            curr_lon = np.clip(curr_lon, lon_min + 0.05*lon_span, lon_max - 0.05*lon_span)
            
    # Convert to DataFrames
    stops_df = pd.DataFrame(stops, columns=["stop_id", "stop_name", "stop_lat", "stop_lon", "stop_type"])
    routes_df = pd.DataFrame(routes, columns=["route_id", "route_short_name", "route_type", "frequency"])
    stop_routes_df = pd.DataFrame(stop_routes, columns=["stop_id", "route_id"])
    
    return stops_df, routes_df, stop_routes_df

def parse_gtfs_zip(uploaded_file):
    """
    Parses an uploaded GTFS zip file containing stops, routes,
    trips, and stop_times, optimizing memory/CPU.
    """
    with zipfile.ZipFile(uploaded_file) as z:
        namelist = z.namelist()
        
        # Look for files
        def find_name(suffix):
            for n in namelist:
                if n.endswith(suffix):
                    return n
            return None
            
        stops_name = find_name("stops.txt")
        routes_name = find_name("routes.txt")
        trips_name = find_name("trips.txt")
        stop_times_name = find_name("stop_times.txt")
        
        if not (stops_name and routes_name):
            raise ValueError("GTFS zip 파일에 stops.txt와 routes.txt가 반드시 포함되어야 합니다.")
            
        with z.open(stops_name) as f:
            stops_df = pd.read_csv(f)
        with z.open(routes_name) as f:
            routes_df = pd.read_csv(f)
            
        # Parse stop-to-route relation
        if trips_name and stop_times_name:
            with z.open(trips_name) as f:
                trips_df = pd.read_csv(f)
            with z.open(stop_times_name) as f:
                # Memory optimization: read only necessary columns
                stop_times_df = pd.read_csv(f, usecols=["trip_id", "stop_id"])
                
            trip_routes = trips_df[["trip_id", "route_id"]].drop_duplicates()
            stop_trips = stop_times_df.drop_duplicates()
            stop_routes_raw = pd.merge(stop_trips, trip_routes, on="trip_id")
            stop_routes_df = stop_routes_raw[["stop_id", "route_id"]].drop_duplicates()
            
            # Frequency approximation
            freq = trips_df.groupby("route_id").size().reset_index(name="frequency")
            routes_df = pd.merge(routes_df, freq, on="route_id", how="left")
            routes_df["frequency"] = routes_df["frequency"].fillna(12)
        else:
            stop_routes_df = pd.DataFrame(columns=["stop_id", "route_id"])
            routes_df["frequency"] = 12
            
        # Standardize columns
        stops_df = stops_df[["stop_id", "stop_name", "stop_lat", "stop_lon"]].copy()
        
        # Map route types (GTFS codes: 0, 1, 2 = Rail/Subway; 3 = Bus; others)
        if "route_type" in routes_df.columns:
            def map_route_type(t):
                if t in [0, 1, 2]:
                    return "subway"
                return "bus"
            routes_df["route_class"] = routes_df["route_type"].apply(map_route_type)
        else:
            routes_df["route_class"] = "bus"
            
        # Get stop type mapping
        if not stop_routes_df.empty:
            merged = pd.merge(stop_routes_df, routes_df, on="route_id")
            stop_types = merged.groupby("stop_id")["route_class"].apply(
                lambda x: "subway" if "subway" in x.values else "bus"
            ).reset_index(name="stop_type")
            stops_df = pd.merge(stops_df, stop_types, on="stop_id", how="left")
            stops_df["stop_type"] = stops_df["stop_type"].fillna("bus")
        else:
            stops_df["stop_type"] = "bus"
            
        return stops_df, routes_df, stop_routes_df

def calculate_accessibility_grid(stops_df, routes_df, stop_routes_df, lat_min, lat_max, lon_min, lon_max, grid_size, w_subway, w_bus, dist_decay):
    """
    Vectorized computation of the Transit Accessibility Index (TAI)
    over a grid inside the specified bounds.
    """
    # 1. Map stop weights based on frequency and stop type
    if not stop_routes_df.empty and "frequency" in routes_df.columns:
        # Get average frequency of routes at each stop
        merged = pd.merge(stop_routes_df, routes_df, on="route_id")
        stop_weights = merged.groupby("stop_id")["frequency"].sum().reset_index(name="frequency_sum")
        stops_with_weight = pd.merge(stops_df, stop_weights, on="stop_id", how="left")
        stops_with_weight["frequency_sum"] = stops_with_weight["frequency_sum"].fillna(5)
    else:
        stops_with_weight = stops_df.copy()
        stops_with_weight["frequency_sum"] = 10
        
    def get_weight(row):
        base = w_subway if row["stop_type"] == "subway" else w_bus
        # Scale weight by frequency
        return base * (1 + math.log(row["frequency_sum"] + 1))
        
    stops_with_weight["weight"] = stops_with_weight.apply(get_weight, axis=1)
    
    # 2. Filter stops inside/near viewport (buffer by 0.05 degrees to catch border effects)
    buffer = 0.02
    visible_stops = stops_with_weight[
        (stops_with_weight["stop_lat"] >= lat_min - buffer) &
        (stops_with_weight["stop_lat"] <= lat_max + buffer) &
        (stops_with_weight["stop_lon"] >= lon_min - buffer) &
        (stops_with_weight["stop_lon"] <= lon_max + buffer)
    ]
    
    if visible_stops.empty:
        # Fallback empty grid
        lats = np.linspace(lat_min, lat_max, grid_size)
        lons = np.linspace(lon_min, lon_max, grid_size)
        lat_mesh, lon_mesh = np.meshgrid(lats, lons)
        return lat_mesh, lon_mesh, np.zeros_like(lat_mesh), visible_stops
        
    # 3. Create grid coordinates
    lats = np.linspace(lat_min, lat_max, grid_size)
    lons = np.linspace(lon_min, lon_max, grid_size)
    lat_mesh, lon_mesh = np.meshgrid(lats, lons)
    grid_coords = np.stack([lat_mesh.ravel(), lon_mesh.ravel()], axis=1) # (G, 2)
    
    # Vectorized distance calculation
    stop_coords = visible_stops[["stop_lat", "stop_lon"]].values # (S, 2)
    stop_weights = visible_stops["weight"].values # (S,)
    
    # Simple spatial distance (in km approximation)
    lat_mid = (lat_min + lat_max) / 2 * np.pi / 180.0
    cos_lat = np.cos(lat_mid)
    
    dlat = grid_coords[:, np.newaxis, 0] - stop_coords[np.newaxis, :, 0] # (G, S)
    dlon = (grid_coords[:, np.newaxis, 1] - stop_coords[np.newaxis, :, 1]) * cos_lat # (G, S)
    dist = np.sqrt(dlat**2 + dlon**2) * 111.0 # distance in km (G, S)
    
    # Compute accessibility using gravity model: sum(weight / (dist + epsilon)^p)
    epsilon = 0.25 # 250m smoothing to prevent infinity spikes
    scores = np.sum(stop_weights[np.newaxis, :] / (dist + epsilon)**dist_decay, axis=1) # (G,)
    
    # Normalize score to 0-100 range
    min_s = np.min(scores)
    max_s = np.max(scores)
    if max_s > min_s:
        scores_norm = (scores - min_s) / (max_s - min_s) * 100
    else:
        scores_norm = np.zeros_like(scores)
        
    score_grid = scores_norm.reshape(lat_mesh.shape)
    
    return lat_mesh, lon_mesh, score_grid, visible_stops

# ----------------------------------------------------
# UI Header
# ----------------------------------------------------
st.markdown('<div class="main-title">🚌 대중교통 소외지역(Transit Desert) 탐색 및 노선 추천</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">전국 공공 GTFS 데이터 또는 시뮬레이션 데이터를 활용하여, 지도상 보이는 지역의 대중교통 소외도를 실시간으로 평가하고 신설 버스 노선을 자동으로 계획합니다.</div>', unsafe_allow_html=True)

# ----------------------------------------------------
# Sidebar Configuration
# ----------------------------------------------------
with st.sidebar:
    st.markdown("### 🛠️ 데이터 설정 (Data Configuration)")
    
    # GTFS File Uploader
    uploaded_file = st.file_uploader(
        "GTFS zip 파일 업로드 (선택)",
        type=["zip"],
        help="지자체/공공데이터포털에서 다운로드한 버스/철도 GTFS zip 파일을 업로드하세요."
    )
    
    # Fallback/Demo mode
    if uploaded_file is None:
        st.info("💡 업로드된 파일이 없어 **서울 마포/용산 데모 시뮬레이션**을 기본 가동합니다. 지도를 움직이시면 해당 영역에 맞게 대중교통망이 동적 생성됩니다.")
        mode = "demo"
    else:
        st.success("✅ GTFS 파일이 업로드되었습니다!")
        mode = "uploaded"
        
    st.markdown("---")
    st.markdown("### ⚙️ 분석 매개변수 (Parameters)")
    
    grid_size = st.slider("분석 그리드 해상도 (Grid Size)", min_value=10, max_value=25, value=15, step=1,
                          help="그리드가 촘촘할수록 정밀도가 향상되나 연산 시간이 증가합니다.")
    
    w_subway = st.slider("지하철 가중치 (Subway Weight)", min_value=10, max_value=100, value=60, step=5,
                         help="지하철역 주변의 대중교통 편의 수준 기여도입니다.")
                         
    w_bus = st.slider("일반버스 가중치 (Bus Weight)", min_value=5, max_value=50, value=15, step=5,
                      help="버스 정류장 주변의 대중교통 편의 수준 기여도입니다.")
                      
    dist_decay = st.slider("거리 감쇄 지수 (Distance Decay)", min_value=1.0, max_value=3.0, value=1.5, step=0.1,
                           help="정류장에서 멀어질수록 교통 편의도가 얼마나 빨리 감소하는지 결정합니다.")
                           
    st.markdown("---")
    st.markdown("### 📘 분석 방법 소개")
    st.caption("""
    1. **교통 편의 지표(TAI)**:
       각 격자점에서 모든 정류장까지의 거리를 계산한 후, 정류장 종류(지하철/버스)와 운행 빈도(frequency)에 비례하고 거리(distance)에 반비례하도록 가중 합산한 값입니다.
    2. **교통 소외 지역(Transit Desert)**:
       지도 화면 내에서 TAI 점수가 가장 낮고, 실제 주거/업무 등 교통 수요가 잠재될 수 있는 가장자리 영역을 찾아냅니다.
    3. **최적 노선 추천**:
       소외지역(출발지)에서 가장 가까운 교통 허브(지하철역 또는 다중 환승역)를 찾아 두 지점을 잇는 최적 버스 노선 궤적을 제안합니다.
    """)

# ----------------------------------------------------
# Load and Parse GTFS Data (cached or in session state)
# ----------------------------------------------------
@st.cache_data(show_spinner="GTFS 데이터를 파싱하는 중...")
def get_data(uploaded_file, mode):
    if mode == "uploaded" and uploaded_file is not None:
        try:
            return parse_gtfs_zip(uploaded_file)
        except Exception as e:
            st.error(f"GTFS 파싱 에러: {e}. 데모 시뮬레이션 모드로 전환합니다.")
            return None
    return None

data_loaded = get_data(uploaded_file, mode)

# Maintain default viewport center/zoom in Session State
if 'center_lat' not in st.session_state:
    # Seoul Mapo center as default
    st.session_state.center_lat = 37.545
    st.session_state.center_lon = 126.95
    st.session_state.zoom = 14

# Define visible bounds fallback
lat_min, lat_max = st.session_state.center_lat - 0.02, st.session_state.center_lat + 0.02
lon_min, lon_max = st.session_state.center_lon - 0.035, st.session_state.center_lon + 0.035

# ----------------------------------------------------
# Initialize Map View and Get Viewport Bounds
# ----------------------------------------------------
# Define map object
m = folium.Map(
    location=[st.session_state.center_lat, st.session_state.center_lon],
    zoom_start=st.session_state.zoom,
    tiles="CartoDB positron"
)

# ----------------------------------------------------
# Main Execution Pipeline
# ----------------------------------------------------
# 1. Fetch Transit Network Data (either from file or dynamic generator)
if data_loaded is not None:
    stops_df, routes_df, stop_routes_df = data_loaded
else:
    # If in demo mode, generate stops dynamically based on coordinates
    stops_df, routes_df, stop_routes_df = generate_simulated_network_for_bounds(lat_min, lat_max, lon_min, lon_max)

# 2. Run initial calculation of accessibility
lat_mesh, lon_mesh, score_grid, visible_stops = calculate_accessibility_grid(
    stops_df, routes_df, stop_routes_df,
    lat_min, lat_max, lon_min, lon_max,
    grid_size, w_subway, w_bus, dist_decay
)

# 3. Locate the Transit Desert & Hub for Recommendation
transit_desert_lat, transit_desert_lon = None, None
hub_lat, hub_lon = None, None
hub_name = ""
recommended_stops = []
improvement_rate = 0.0

if not visible_stops.empty:
    # Transit desert: Grid point with the lowest score
    min_idx = np.unravel_index(np.argmin(score_grid), score_grid.shape)
    transit_desert_lat = lat_mesh[min_idx]
    transit_desert_lon = lon_mesh[min_idx]
    
    # Find the nearest High-Accessibility Hub (e.g. Subway station or high weight stop)
    subway_hubs = visible_stops[visible_stops["stop_type"] == "subway"]
    if subway_hubs.empty:
        # If no subway stops, get the stop with the highest weight
        subway_hubs = visible_stops
        
    if not subway_hubs.empty:
        # Calculate distance from desert to each subway hub
        subway_hubs = subway_hubs.copy()
        subway_hubs["dist_to_desert"] = subway_hubs.apply(
            lambda row: haversine_distance(transit_desert_lat, transit_desert_lon, row["stop_lat"], row["stop_lon"]),
            axis=1
        )
        nearest_hub = subway_hubs.sort_values("dist_to_desert").iloc[0]
        hub_lat, hub_lon = nearest_hub["stop_lat"], nearest_hub["stop_lon"]
        hub_name = nearest_hub["stop_name"]
        hub_dist = nearest_hub["dist_to_desert"]
        
        # 4. Generate Recommended Route Points (Desert -> Intermediate Stop 1 -> Intermediate Stop 2 -> Hub)
        # Create a 4-point path
        d_lat = hub_lat - transit_desert_lat
        d_lon = hub_lon - transit_desert_lon
        
        step1_lat = transit_desert_lat + d_lat * 0.33
        step1_lon = transit_desert_lon + d_lon * 0.33
        step2_lat = transit_desert_lat + d_lat * 0.66
        step2_lon = transit_desert_lon + d_lon * 0.66
        
        recommended_stops = [
            {"name": "신설 정류장 (기점 - 교통 소외지)", "lat": transit_desert_lat, "lon": transit_desert_lon},
            {"name": "신설 정류장 (중간지점 A)", "lat": step1_lat, "lon": step1_lon},
            {"name": "신설 정류장 (중간지점 B)", "lat": step2_lat, "lon": step2_lon},
            {"name": f"기존 연계 허브 ({hub_name})", "lat": hub_lat, "lon": hub_lon}
        ]
        
        # 5. Predict Improvement: Recalculate TAI including the new recommended route
        new_stops = visible_stops.copy()
        for idx, r_stop in enumerate(recommended_stops[:-1]): # exclude the last one since it's already an existing hub
            new_row = pd.DataFrame([{
                "stop_id": f"NEW_REC_{idx}",
                "stop_name": r_stop["name"],
                "stop_lat": r_stop["lat"],
                "stop_lon": r_stop["lon"],
                "stop_type": "bus",
                "frequency_sum": 30, # Moderate frequency
                "weight": w_bus * (1 + math.log(31))
            }])
            new_stops = pd.concat([new_stops, new_row], ignore_index=True)
            
        # Recalculate grid for the desert point specifically
        # Grid coords for the desert point
        desert_coord = np.array([[transit_desert_lat, transit_desert_lon]])
        new_stop_coords = new_stops[["stop_lat", "stop_lon"]].values
        new_stop_weights = new_stops["weight"].values
        
        # Distance calculation for desert point
        lat_mid = transit_desert_lat * np.pi / 180.0
        cos_lat = np.cos(lat_mid)
        dlat_n = desert_coord[:, np.newaxis, 0] - new_stop_coords[np.newaxis, :, 0]
        dlon_n = (desert_coord[:, np.newaxis, 1] - new_stop_coords[np.newaxis, :, 1]) * cos_lat
        dist_n = np.sqrt(dlat_n**2 + dlon_n**2) * 111.0
        
        epsilon = 0.25
        score_new = np.sum(new_stop_weights[np.newaxis, :] / (dist_n + epsilon)**dist_decay, axis=1)[0]
        
        # Normalize comparison
        # Find raw original score at desert index
        raw_original_scores = np.sum(visible_stops["weight"].values[np.newaxis, :] / (dist + epsilon)**dist_decay, axis=1)
        raw_original_min = np.min(raw_original_scores)
        raw_original_max = np.max(raw_original_scores)
        
        raw_score_desert = raw_original_scores[min_idx[0] * grid_size + min_idx[1]]
        
        # Compute percentage improvement in raw accessibility index
        if raw_score_desert > 0:
            improvement_rate = ((score_new - raw_score_desert) / raw_score_desert) * 100
        else:
            improvement_rate = 100.0 # high relative jump

# ----------------------------------------------------
# Add Folium Map Layers
# ----------------------------------------------------
# 1. Add Heatmap Layer representing "Transit Desert Index" (Inconvenience = 100 - Accessibility)
if transit_desert_lat is not None:
    heat_data = []
    for r in range(grid_size):
        for c in range(grid_size):
            inconvenience = 100 - score_grid[r, c]
            # Add weight for the heatmap: higher weight means higher inconvenience (more red)
            heat_data.append([lat_mesh[r, c], lon_mesh[r, c], inconvenience / 100.0])
            
    # Scale heat intensity
    plugins.HeatMap(
        heat_data,
        radius=25,
        blur=20,
        min_opacity=0.15,
        max_zoom=1,
        gradient={0.2: 'blue', 0.4: 'cyan', 0.6: 'lime', 0.8: 'yellow', 1.0: 'red'}
    ).add_to(m)

# 2. Add Stops to map
for idx, stop in visible_stops.iterrows():
    if stop["stop_type"] == "subway":
        folium.CircleMarker(
            location=[stop["stop_lat"], stop["stop_lon"]],
            radius=8,
            color="#0066CC",
            fill=True,
            fill_color="#0088FF",
            fill_opacity=0.9,
            popup=f"🚉 지하철: {stop['stop_name']}",
            tooltip=stop["stop_name"]
        ).add_to(m)
    else:
        folium.CircleMarker(
            location=[stop["stop_lat"], stop["stop_lon"]],
            radius=4,
            color="#009933",
            fill=True,
            fill_color="#33CC66",
            fill_opacity=0.7,
            popup=f"🚌 버스정류장: {stop['stop_name']}",
            tooltip=stop["stop_name"]
        ).add_to(m)

# 3. Add Recommendation features to map
if transit_desert_lat is not None and hub_lat is not None:
    # Transit Desert Area
    folium.Marker(
        location=[transit_desert_lat, transit_desert_lon],
        icon=folium.Icon(color="red", icon="exclamation-triangle", prefix="fa"),
        popup="🚨 **대중교통 소외지역 최저점**<br>이 곳의 대중교통 접근성이 가장 취약합니다.",
        tooltip="🚨 최저 대중교통 편의도 포인트"
    ).add_to(m)
    
    # Recommended Route Line
    route_coords = [[s["lat"], s["lon"]] for s in recommended_stops]
    folium.PolyLine(
        locations=route_coords,
        color="#8B008B",
        weight=5,
        dash_array="8, 8",
        opacity=0.85,
        tooltip="⚡ 추천 신설 버스 노선",
        popup=f"🚌 **추천 버스 노선**<br>소외지역에서 🚉 **{hub_name}**을 연계하는 노선입니다."
    ).add_to(m)
    
    # Recommended Intermediate Stops
    for idx, r_stop in enumerate(recommended_stops[1:-1]): # intermediate ones
        folium.Marker(
            location=[r_stop["lat"], r_stop["lon"]],
            icon=folium.DivIcon(html=f"""
                <div style="
                    background-color: #FFC000;
                    border: 2px solid #8B008B;
                    border-radius: 50%;
                    width: 20px;
                    height: 20px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 10px;
                    font-weight: bold;
                    color: black;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.3);
                ">{idx+1}</div>
            """),
            popup=f"📍 <b>{r_stop['name']}</b><br>추천 신설 정류소입니다."
        ).add_to(m)

# ----------------------------------------------------
# Main Layout: Two Columns
# Column 1: Map Viewport
# Column 2: Analytics & Insights Dashboard
# ----------------------------------------------------
col_map, col_stats = st.columns([7, 5])

with col_map:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("##### 📍 실시간 교통편의 분석 지도 (Interactive Analysis Map)")
    st.caption("💡 지도 화면을 드래그하거나 확대/축소하여 원하는 지역을 화면에 띄우면, 현재 화면 구도에 맞춰 실시간으로 대중교통 편의성을 분석합니다.")
    
    # Render st-folium map
    map_data = st_folium(
        m,
        width="100%",
        height=580,
        key="folium_map"
    )
    
    # Capture map bounds change and rerun calculations
    if map_data and map_data.get("bounds"):
        bounds = map_data["bounds"]
        sw = bounds["_southWest"]
        ne = bounds["_northEast"]
        
        # Calculate new center
        center_lat = (sw["lat"] + ne["lat"]) / 2
        center_lon = (sw["lng"] + ne["lng"]) / 2
        zoom = map_data.get("zoom", st.session_state.zoom)
        
        # To avoid infinite loop, only update and rerun if view shifted significantly
        lat_shift = abs(st.session_state.center_lat - center_lat)
        lon_shift = abs(st.session_state.center_lon - center_lon)
        zoom_shift = abs(st.session_state.zoom - zoom)
        
        if lat_shift > 0.0005 or lon_shift > 0.0005 or zoom_shift >= 1:
            st.session_state.center_lat = center_lat
            st.session_state.center_lon = center_lon
            st.session_state.zoom = zoom
            st.rerun()
            
    st.markdown('</div>', unsafe_allow_html=True)

with col_stats:
    if transit_desert_lat is None:
        st.info("ℹ️ 현재 지도 화면 내에 분석 가능한 대중교통 노선/정류장 데이터가 부족합니다. 지도를 줌 아웃하거나 정류장이 위치한 곳으로 이동해 주세요.")
    else:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown("##### 📊 실시간 편의성 지표 (Accessibility Metrics)")
        
        # Calculate stats
        avg_score = np.mean(score_grid)
        min_score = np.min(score_grid)
        desert_index = 100 - avg_score
        
        # Display Stats Cards
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <div style="border-left: 4px solid #7F00FF; padding-left: 10px;">
                <div class="metric-label">평균 교통 편의도</div>
                <div class="metric-value">{avg_score:.1f} / 100</div>
                <div class="metric-sub accent-text-blue">현재 뷰포트 영역 평균</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            desert_class = "심각 (Red)" if min_score < 15 else "보통 (Yellow)" if min_score < 40 else "양호 (Green)"
            desert_color = "accent-text-red" if min_score < 15 else "accent-text-blue" if min_score >= 40 else "accent-text-green"
            st.markdown(f"""
            <div style="border-left: 4px solid #FF3B30; padding-left: 10px;">
                <div class="metric-label">교통 소외도 등급</div>
                <div class="metric-value {desert_color}">{desert_class}</div>
                <div class="metric-sub">최저 편의 지수: {min_score:.1f}</div>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Display Recommendation Details
        st.markdown("##### 💡 최적 버스 노선 신설 추천 (Recommended Bus Line)")
        st.markdown(f"""
        현재 영역 내에서 대중교통망 접근성이 가장 취약한 지점을 시작으로 기존 대형 연계 거점까지 도달하는 버스 노선 신설을 추천합니다.
        
        * **출발 거점 (소외지역):** 위도 `{transit_desert_lat:.5f}`, 경도 `{transit_desert_lon:.5f}`
        * **종점 연계 허브:** `{hub_name}` (`{hub_dist:.2f} km` 연결)
        * **예상 노선 총길이:** 약 `{hub_dist:.2f} km` (정류장 4개 계획)
        """)
        
        # TAI Improvement Card
        st.markdown(f"""
        <div style="background-color: rgba(127,0,255,0.06); border: 1px solid rgba(127,0,255,0.15); border-radius: 12px; padding: 1rem; margin-top: 1rem;">
            <div class="metric-label" style="color: #7F00FF;">노선 신설에 따른 효과 분석</div>
            <div style="display: flex; align-items: baseline; gap: 10px;">
                <span class="metric-value accent-text-green">+{improvement_rate:.1f}%</span>
                <span style="font-size: 0.9rem; color: #555;">소외지 교통 편의 지수 향상</span>
            </div>
            <div style="font-size: 0.8rem; color: #777; margin-top: 0.5rem;">
                기존 편의도: <b>{raw_score_desert:.2f}</b> → 노선 신설 후 예측 편의도: <b>{score_new:.2f}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------------------------------
# Bottom Analysis Section (Tabs)
# ----------------------------------------------------
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
tab_report, tab_stops, tab_instructions = st.tabs([
    "📋 세부 분석 리포트 (Detailed Report)",
    "📍 탐색 정류장 및 노선 목록 (Visible Stops & Routes)",
    "⚙️ 전국 공공 GTFS 데이터 획득 가이드 (GTFS Guide)"
])

with tab_report:
    st.markdown("### 📊 교통 인프라 분포 및 노선 시뮬레이션")
    if transit_desert_lat is not None:
        col_fig, col_text = st.columns([6, 6])
        
        with col_fig:
            # Render a Matplotlib bar graph showing TAI comparison
            fig, ax = plt.subplots(figsize=(8, 4.5))
            categories = ['기존 소외지 편의 지수', '신설 노선 도입 후 편의 지수', '화면 내 평균 편의 지수']
            values = [raw_score_desert, score_new, avg_score]
            colors = ['#FF3B30', '#00B074', '#007AFF']
            
            bars = ax.bar(categories, values, color=colors, width=0.55)
            ax.set_ylabel('대중교통 편의도 (TAI)')
            ax.set_title('노선 신설 전/후 교통 편의 효과 분석', fontsize=12, fontweight='bold', pad=15)
            ax.set_ylim(0, max(max(values)*1.2, 100))
            
            for bar in bars:
                height = bar.get_height()
                ax.annotate(f'{height:.1f}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=10, fontweight='bold')
                            
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            plt.tight_layout()
            st.pyplot(fig)
            
        with col_text:
            st.markdown(f"""
            #### 🔍 분석 진단 결과
            - **인프라 쏠림 현상:** 분석 화면 내에서 지하철 및 버스 노선의 중심가 집중으로 인해 외곽 혹은 언덕 주거 단지 인근은 상대적으로 소외 지수(Inconvenience Index)가 매우 높게 분포되어 있습니다.
            - **연계 노선 신설의 타당성:** 추천 노선은 단거리 순환선 개념으로, **{hub_name}**까지의 단시간 이동 편의성을 극대화합니다. 이는 버스 1대 운행만으로도 배차 간격 대비 대중교통 인프라가 전혀 없는 음영 구역을 단번에 제거하는 고효율 성과를 기대할 수 있습니다.
            """)
            
            # Recommendation Stop Table
            st.markdown("#### 🚌 추천 신설 노선 정류장 리스트")
            st.markdown(f"""
            <table class="styled-table">
                <thead>
                    <tr>
                        <th>구분</th>
                        <th>정류장 명칭</th>
                        <th>위도 (Latitude)</th>
                        <th>경도 (Longitude)</th>
                        <th>정류장 속성</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>기점</td>
                        <td><b>{recommended_stops[0]['name']}</b></td>
                        <td>{recommended_stops[0]['lat']:.5f}</td>
                        <td>{recommended_stops[0]['lon']:.5f}</td>
                        <td>신설 (마이크로 버스)</td>
                    </tr>
                    <tr>
                        <td>경유지 1</td>
                        <td>{recommended_stops[1]['name']}</td>
                        <td>{recommended_stops[1]['lat']:.5f}</td>
                        <td>{recommended_stops[1]['lon']:.5f}</td>
                        <td>신설 (지선 정류소)</td>
                    </tr>
                    <tr>
                        <td>경유지 2</td>
                        <td>{recommended_stops[2]['name']}</td>
                        <td>{recommended_stops[2]['lat']:.5f}</td>
                        <td>{recommended_stops[2]['lon']:.5f}</td>
                        <td>신설 (지선 정류소)</td>
                    </tr>
                    <tr>
                        <td>종점</td>
                        <td><b>{recommended_stops[3]['name']}</b></td>
                        <td>{recommended_stops[3]['lat']:.5f}</td>
                        <td>{recommended_stops[3]['lon']:.5f}</td>
                        <td>기존 연계 환승역</td>
                    </tr>
                </tbody>
            </table>
            """, unsafe_allow_html=True)
            
with tab_stops:
    st.markdown("### 📌 현재 분석 영역 내 기존 정류장 목록")
    if not visible_stops.empty:
        # Style and clean columns
        disp_stops = visible_stops[["stop_id", "stop_name", "stop_type", "stop_lat", "stop_lon", "frequency_sum"]].copy()
        disp_stops.columns = ["정류장 ID", "정류장 명칭", "구분", "위도", "경도", "총 운행 횟수/일"]
        disp_stops["구분"] = disp_stops["구분"].apply(lambda x: "🚉 지하철" if x == "subway" else "🚌 버스")
        st.dataframe(disp_stops, use_container_width=True)
    else:
        st.warning("분석 화면 범위 내에 정류장이 없습니다.")

with tab_instructions:
    st.markdown("### 📁 공공 GTFS 데이터 획득 및 분석 방법")
    st.markdown("""
    본 서비스는 표준 대중교통 데이터 규격인 **GTFS(General Transit Feed Specification)** 데이터를 사용하여 분석을 진행합니다. 
    자신이 원하는 도심의 대형 대중교통망 데이터로 실시간 분석을 돌려보려면 아래의 방법으로 데이터를 획득하여 분석해 보실 수 있습니다.
    
    1. **공공데이터포털(data.go.kr) 접속:**
       - 검색어에 **'국토교통부 버스 노선 정보'** 또는 **'국가대중교통정보센터 GTFS'** 를 검색합니다.
       - 각 지방자치단체의 대중교통 노선 데이터(GTFS 포맷)를 제공받을 수 있습니다.
    
    2. **국가교통데이터스퀘어(transportation.go.kr) 혹은 서울교통정보센터(TOPIS):**
       - 서울특별시, 부산광역시, 경기도 등 주요 지자체는 TOPIS 혹은 각 기관 자료실에서 전국/지방 버스 노선 및 지하철 노선의 통합 GTFS 파일을 배포하고 있습니다.
       
    3. **데이터 구조 필수 체크:**
       - 다운로드받은 `.zip` 파일 내부에는 최소한 아래 파일들이 쉼표 구분자(CSV format)로 존재해야 합니다:
         - `stops.txt` (정류소 위치 및 정보)
         - `routes.txt` (노선 정보)
         - `trips.txt` (노선별 세부 운행 정보 - 선택사항)
         - `stop_times.txt` (정류소별 시간표 정보 - 선택사항)
         
    4. **파일 업로드:**
       - 좌측 사이드바의 **GTFS zip 파일 업로드** 영역에 다운로드받은 zip 파일을 그대로 끌어다 넣으시면(Drag & Drop) 전국 어느 지역이든 즉시 실제 데이터 기반으로 교통 편의성을 분석해 볼 수 있습니다.
    """)

st.markdown('</div>', unsafe_allow_html=True)
