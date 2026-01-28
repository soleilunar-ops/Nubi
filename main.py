import streamlit as st
import streamlit.components.v1 as components
import os
import json
import base64
from io import BytesIO
from datetime import datetime, timedelta
from dotenv import load_dotenv
import utils
from PIL import Image

# 1. 설정 및 CSS
load_dotenv()
KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")      # JS SDK용 (지도 표시)
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY") # 검색용 (장소 데이터)
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
OPEN_API_KEY = os.getenv("OPEN_API_KEY")

st.set_page_config(page_title="Nubi", page_icon="🧶", layout="wide")

st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    * { font-family: 'Pretendard', sans-serif; }
    
    [data-testid="stSidebar"] { background-color: #F8F9FA; border-right: 1px solid #E9ECEF; }
    
    .hero-container {
        padding: 40px 20px;
        background: linear-gradient(135deg, #6C5CE7 0%, #a29bfe 100%);
        border-radius: 20px;
        color: white;
        margin-bottom: 30px;
        text-align: center;
        box-shadow: 0 10px 20px rgba(108, 92, 231, 0.2);
    }
    .hero-title { font-size: 2.5rem; font-weight: 800; margin-bottom: 10px; }
    .hero-subtitle { font-size: 1.1rem; opacity: 0.9; }
    
    div.stButton > button {
        width: 100%; height: 110px; border-radius: 16px;
        background: white; border: 1px solid #eee;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02); transition: 0.2s;
    }
    div.stButton > button:hover {
        transform: translateY(-5px); box-shadow: 0 8px 15px rgba(0,0,0,0.1);
        border-color: #6C5CE7; color: #6C5CE7;
    }
    div.stButton > button p { font-size: 1.2rem; font-weight: bold; }
    
    button[kind="primary"] {
        background-color: #6C5CE7 !important;
        border: none !important;
        color: white !important;
        font-weight: bold !important;
        padding: 10px 20px !important;
    }
    button[kind="primary"]:hover { background-color: #5a4ad1 !important; }

    .info-card {
        background: white; padding: 15px; border-radius: 12px;
        border: 1px solid #f0f0f0; margin-bottom: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    .photo-card {
        border-radius: 15px; overflow: hidden;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        margin-bottom: 15px; background: white;
    }
</style>
""", unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state['page'] = 'Home'
if 'selected_city' not in st.session_state: st.session_state['selected_city'] = None

with st.sidebar:
    st.title("🧶 Nubi")
    st.caption("AI Travel Planner")
    st.markdown("### 🧭 MENU")
    
    def go_home(): st.session_state['page'] = 'Home'
    def go_course(): 
        if st.session_state['selected_city']: st.session_state['page'] = 'Course'
        else: st.warning("도시를 먼저 선택해주세요.")
    def go_log(): st.session_state['page'] = 'Log'
    
    if st.button("🏠 홈으로 가기", use_container_width=True): go_home()
    if st.button("🗺️ 여행 계획 짜기", use_container_width=True): go_course()
    if st.button("📸 추억 기록 (Nubi Log)", use_container_width=True): go_log()
    
    st.divider()
    st.caption("Coming Soon")
    st.button("💰 예산 관리 (준비중)", disabled=True)
    st.button("✈️ 항공권 예약 (준비중)", disabled=True)

# --- PAGE 1: 홈 ---
if st.session_state['page'] == 'Home':
    st.markdown("""<div class="hero-container"><div class="hero-title">대한민국, 어디까지 가봤니?</div>
    <div class="hero-subtitle">Nubi가 당신의 취향에 딱 맞는 여행 코스를 단디 짜드립니다.</div></div>""", unsafe_allow_html=True)
    
    search = st.text_input("🔍 도시 검색 (예: 경주)", placeholder="도시명을 입력하세요")
    if search: st.session_state['selected_city'] = search; st.session_state['page'] = 'Course'; st.rerun()
    
    st.write("")
    st.subheader("🏙️ 인기 여행지")
    cities = {"서울": "🏙️", "제주": "🍊", "부산": "🌊", "강릉": "☕", "경주": "🏯", "여수": "🌉"}
    cols = st.columns(6)
    for i, (city, emoji) in enumerate(cities.items()):
        with cols[i]:
            if st.button(f"{emoji}\n{city}"): st.session_state['selected_city'] = city
            
    if st.session_state['selected_city']:
        city = st.session_state['selected_city']
        coords = utils.CITY_COORDS.get(city, utils.CITY_COORDS["서울"])
        st.divider()
        st.markdown(f"### 👀 **{city}** 퀵 뷰")
        c1, c2 = st.columns([1, 1.5])
        
        # [수정 1] 카테고리별(맛집/카페/관광지) 1위 장소 추출
        with st.spinner("🔥 카카오맵 추천 인기 장소(맛집, 카페, 관광지) 분석 중..."):
            places = utils.fetch_top_places(city, KAKAO_REST_API_KEY)

        with c1:
            st.caption(f"🔥 {city} 카테고리별 추천 Top 3 (Kakao Data)")
            if not places:
                st.info("데이터를 불러올 수 없습니다.")
            else:
                for p in places:
                    # [수정 2] 클릭 시 URL 이동 (Deep Linking)
                    st.markdown(f"""<div class="info-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:bold; font-size:1.1rem;">
                            <a href="{p['url']}" target="_blank" style="text-decoration:none; color:inherit; hover:text-decoration:underline;">{p['name']}</a>
                        </span>
                        <span style="color:#f1c40f; font-weight:bold;">★{p['rating']}</span>
                    </div>
                    <div style="font-size:0.8rem; color:gray; margin-top:5px;">
                        {p['category']} | 리뷰 {p['reviews']}+
                    </div>
                    </div>""", unsafe_allow_html=True)
            
            if st.button(f"🚀 {city} 상세 여행계획 짜러가기", type="primary", use_container_width=True):
                st.session_state['page'] = 'Course'
                st.rerun()
        
        with c2:
            # [수정 2] Page 1 지도에 상위 3개 장소 마커 표시 및 바운드 조정
            json_places = json.dumps(places, ensure_ascii=False)
            map_html = f"""
            <div id="map" style="width:100%;height:350px;border-radius:12px;"></div>
            <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}"></script>
            <script>
                var mapContainer = document.getElementById('map'),
                    mapOption = {{ center: new kakao.maps.LatLng({coords['lat']}, {coords['lng']}), level: 8 }};
                var map = new kakao.maps.Map(mapContainer, mapOption);
                
                var places = {json_places};
                var bounds = new kakao.maps.LatLngBounds();
                
                // 중심 좌표 추가
                bounds.extend(new kakao.maps.LatLng({coords['lat']}, {coords['lng']}));
                
                places.forEach(function(p) {{
                    var pos = new kakao.maps.LatLng(p.lat, p.lng);
                    bounds.extend(pos);
                    var marker = new kakao.maps.Marker({{ position: pos, map: map }});
                    
                    var content = '<div style="padding:5px;font-size:11px;background:white;border:1px solid #ccc;border-radius:3px;">' + p.name + '</div>';
                    var infowindow = new kakao.maps.InfoWindow({{ content: content }});
                    infowindow.open(map, marker);
                    
                    // 마커 클릭 시 페이지 이동
                    kakao.maps.event.addListener(marker, 'click', function() {{
                        if (p.url) {{ window.open(p.url, '_blank'); }}
                    }});
                }});
                
                // 마커가 있다면 지도 범위 재설정
                if (places.length > 0) {{ map.setBounds(bounds); }}
            </script>"""
            components.html(map_html, height=370)

# --- PAGE 2: AI 코스 설계 ---
elif st.session_state['page'] == 'Course':
    city = st.session_state['selected_city']
    st.markdown(f"## 🎒 **{city}** 여행 설계")
    with st.expander("🛠️ 여행 옵션", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            today = datetime.today()
            date_range = st.date_input("여행 일정 선택", (today, today + timedelta(days=1)), min_value=today, format="YYYY.MM.DD")
            age = st.selectbox("연령대", ["20대", "30대", "40대", "50대+"])
        with col2:
            mbti = st.radio("성향", ["J (계획형)", "P (즉흥형)"])
            theme = st.radio("테마", ["맛집/카페", "액티비티", "힐링", "역사"], horizontal=True)
        generate = st.button("✨ AI 코스 생성하기", type="primary", use_container_width=True) if isinstance(date_range, tuple) and len(date_range) == 2 else False

    if generate:
        with st.spinner(f"🔍 {city}의 핫플레이스(카카오 데이터)를 수집하고, 맞춤형 코스를 설계 중입니다..."):
            coords = utils.CITY_COORDS.get(city, utils.CITY_COORDS["서울"])
            
            # 1. 날씨 정보 조회
            weather_data = utils.get_weather_forecast(coords['lat'], coords['lng'], date_range[0], date_range[1], WEATHER_API_KEY)
            
            # 2. 카카오 API로 실존 장소 후보군(Candidates) 선행 수집
            candidates = utils.fetch_candidate_places(city, theme, KAKAO_REST_API_KEY)
            
            # 3. AI 코스 생성 (후보군 데이터 기반 + 거리 계산 적용)
            ai_result = utils.get_ai_course(OPEN_API_KEY, city, mbti, theme, age, weather_data, candidates)
            
            st.session_state['result'] = ai_result
            st.session_state['weather'] = weather_data
            st.session_state['mbti_type'] = mbti

    if 'result' in st.session_state and st.session_state['result']:
        res = st.session_state['result']
        st.success(f"📌 {res['title']}")
        tab_map, tab_detail = st.tabs(["🗺️ 지도 동선", "📝 상세 일정표"])
        
        with tab_map:
            st.caption("💡 지도 마커를 클릭하면 상세 정보(카카오맵)로 이동합니다.")
            all_schedules = res['schedule']; json_schedules = json.dumps(all_schedules, ensure_ascii=False)
            
            map_html = f"""
            <div id="map" style="width:100%;height:600px;border-radius:15px;box-shadow:0 4px 10px rgba(0,0,0,0.1);"></div>
            <script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}"></script>
            <script>
                var map = new kakao.maps.Map(document.getElementById('map'), {{ center: new kakao.maps.LatLng({coords['lat']}, {coords['lng']}), level: 7 }});
                var schedules = {json_schedules};
                var colors = ['#FF6B6B', '#4834d4', '#20bf6b', '#f0932b', '#eb4d4b'];
                var bounds = new kakao.maps.LatLngBounds();
                
                schedules.forEach((day, i) => {{
                    var path = [];
                    var color = colors[i % colors.length];
                    
                    day.places.forEach((p, pi) => {{
                        var pos = new kakao.maps.LatLng(p.lat, p.lng);
                        path.push(pos);
                        bounds.extend(pos);
                        
                        var content = '<div style="padding:5px;background:white;border:1px solid #ddd;border-radius:5px;font-size:11px;cursor:pointer;">' +
                                      '<span style="color:'+color+';font-weight:bold;">Day'+day.day+'-'+(pi+1)+'</span> '+p.name+'</div>';
                                      
                        var marker = new kakao.maps.Marker({{ position: pos, map: map }});
                        var infowindow = new kakao.maps.InfoWindow({{ content: content }});
                        infowindow.open(map, marker);
                        
                        kakao.maps.event.addListener(marker, 'click', function() {{
                            if (p.url) {{ window.open(p.url, '_blank'); }}
                        }});
                    }});
                    
                    new kakao.maps.Polyline({{ path: path, strokeWeight: 6, strokeColor: color, strokeOpacity: 0.8, strokeStyle: 'solid' }}).setMap(map);
                }});
                map.setBounds(bounds);
            </script>
            """
            components.html(map_html, height=620)
        
        with tab_detail:
            is_j = "J" in st.session_state.get('mbti_type', '')
            for day in res['schedule']:
                with st.expander(f"📅 Day {day['day']} ({day['weather_note']})", expanded=True):
                    for idx, p in enumerate(day['places']):
                        col_icon, col_info = st.columns([0.5, 9])
                        with col_icon: st.write("📍")
                        with col_info:
                            place_link = f"[{p['name']}]({p['url']})" if p.get('url') else p['name']
                            st.markdown(f"**{p.get('time', '00:00')} | {place_link}**")
                            
                            # [수정 3] 정확한 이동 거리 및 수단 표시 (utils에서 계산된 값)
                            if is_j: 
                                st.info(f"🚦 {p.get('transport', '이동 정보 없음')}")
                            else:
                                st.caption(f"🚦 {p.get('transport', '이동 정보 없음')}")
                                
                            if not is_j:
                                alts = p.get('alternatives', [])
                                if alts: 
                                    # [Bugfix] LLM이 가끔 딕셔너리를 반환할 경우 문자열로 추출
                                    safe_alts = [a['name'] if isinstance(a, dict) else str(a) for a in alts]
                                    st.caption(f"🧩 즉흥 대안: {', '.join(safe_alts)}")
                                else: st.caption("🧩 대안: 근처 탐색 권장")
                            
                            st.write(f"📝 {p['desc']}")
                            st.divider()

# --- PAGE 3: Nubi Log ---
elif st.session_state['page'] == 'Log':
    st.markdown("## 📸 **Nubi Log**: 여행의 발자취")
    col_up, col_view = st.columns([1, 2])
    uploaded_files = []
    with col_up:
        with st.container(border=True):
            st.subheader("📤 사진 업로드")
            uploaded_files = st.file_uploader("여행 사진을 선택하세요", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)
            if uploaded_files: st.success(f"{len(uploaded_files)}장의 사진을 로드했습니다.")
    
    def get_thumbnail_b64(image_file):
        try:
            img = Image.open(image_file); img.thumbnail((150, 150))
            buffered = BytesIO(); img.save(buffered, format="JPEG")
            return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode()}"
        except: return None

    if uploaded_files:
        photo_data = []
        gallery_groups = {}
        for file in uploaded_files:
            meta = utils.get_image_metadata(file)
            if meta and meta['lat'] and meta['lng']:
                meta['img_src'] = get_thumbnail_b64(file); meta['file_obj'] = file 
                photo_data.append(meta)
                city_name = utils.get_closest_city(meta['lat'], meta['lng'])
                if city_name not in gallery_groups: gallery_groups[city_name] = []
                gallery_groups[city_name].append(meta)
        
        with col_view:
            if not photo_data: st.warning("⚠️ 업로드된 사진에 GPS 정보가 없습니다.")
            else:
                st.subheader("🗺️ 추억 지도")
                center_lat = photo_data[0]['lat']; center_lng = photo_data[0]['lng']
                json_photos = json.dumps([{k:v for k,v in p.items() if k != 'file_obj'} for p in photo_data], ensure_ascii=False)
                map_html = f"""<div id="map" style="width:100%;height:500px;border-radius:15px;box-shadow:0 4px 10px rgba(0,0,0,0.1);"></div>
                <script type="text/javascript" src="https://dapi.kakao.com/v2/maps/sdk.js?appkey={KAKAO_API_KEY}"></script>
                <style>.photo-marker {{ position: relative; width: 60px; height: 60px; border-radius: 50%; border: 3px solid white; box-shadow: 0 3px 6px rgba(0,0,0,0.3); background-size: cover; background-position: center; cursor: pointer; transition: transform 0.2s; }} .photo-marker:hover {{ transform: scale(1.2); z-index: 999; border-color: #6C5CE7; }}</style>
                <script>
                    var map = new kakao.maps.Map(document.getElementById('map'), {{ center: new kakao.maps.LatLng({center_lat}, {center_lng}), level: 9 }});
                    var photos = {json_photos}; var bounds = new kakao.maps.LatLngBounds();
                    photos.forEach(function(p) {{
                        var pos = new kakao.maps.LatLng(p.lat, p.lng); bounds.extend(pos);
                        var content = '<div class="photo-marker" style="background-image: url(' + p.img_src + ');"></div>';
                        new kakao.maps.CustomOverlay({{ position: pos, content: content, yAnchor: 1 }}).setMap(map);
                    }});
                    map.setBounds(bounds);
                </script>"""
                components.html(map_html, height=520)

    if uploaded_files and gallery_groups:
        st.divider()
        st.subheader("🎞️ 지역별 앨범")
        tabs = st.tabs([f"📍 {city}" for city in gallery_groups.keys()])
        for i, city in enumerate(gallery_groups.keys()):
            with tabs[i]:
                photos = gallery_groups[city]
                cols = st.columns(4)
                for idx, item in enumerate(photos):
                    with cols[idx % 4]:
                        with st.container(border=True):
                            st.image(item['file_obj'], use_container_width=True)
                            st.caption(f"📅 {item['date']}")