import os
import json
import requests
import math
import random
from openai import OpenAI
import streamlit as st
from datetime import datetime, timedelta
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# --- 1. 기초 데이터 (도시 좌표) ---
CITY_COORDS = {
    "서울": {"lat": 37.5665, "lng": 126.9780},
    "제주": {"lat": 33.4996, "lng": 126.5312},
    "부산": {"lat": 35.1796, "lng": 129.0756},
    "강릉": {"lat": 37.7519, "lng": 128.8760},
    "경주": {"lat": 35.8562, "lng": 129.2247},
    "여수": {"lat": 34.7604, "lng": 127.6622},
    "전주": {"lat": 35.8242, "lng": 127.1480}
}

# --- 2. 날씨 API ---
def get_weather_forecast(lat, lng, start_date, end_date, api_key):
    weather_info = []
    duration = (end_date - start_date).days + 1
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lng}&appid={api_key}&units=metric&lang=kr"
    
    try:
        response = requests.get(url)
        if response.status_code != 200: raise Exception("API Error")
        data = response.json()
        
        for i in range(duration):
            target_date = start_date + timedelta(days=i)
            target_str = target_date.strftime("%Y-%m-%d")
            found = False
            for item in data['list']:
                if target_str in item['dt_txt'] and "12:00:00" in item['dt_txt']:
                    desc = item['weather'][0]['description']
                    context = "☔ 실내 권장" if any(x in desc for x in ["비", "눈", "폭우", "흐림"]) else "야외활동 최적"
                    weather_info.append({
                        "date": target_str, "temp": round(item['main']['temp'], 1),
                        "desc": desc, "context": context, "icon": item['weather'][0]['icon']
                    })
                    found = True
                    break
            if not found:
                weather_info.append({"date": target_str, "temp": "-", "desc": "정보 없음", "context": "정보 없음", "icon": ""})
    except Exception as e:
        for i in range(duration):
            d = start_date + timedelta(days=i)
            is_rain = (i % 2 != 0)
            weather_info.append({
                "date": d.strftime("%Y-%m-%d"), "temp": 22.0,
                "desc": "비" if is_rain else "맑음",
                "context": "☔ 실내 권장" if is_rain else "☀️ 야외 좋음", "icon": "10d" if is_rain else "01d"
            })
    return weather_info

# --- Page 1용: 카테고리별 실시간 Top 1 (총 3개) 수집 ---
def fetch_top_places(city, api_key):
    if not api_key: return []
    
    categories = [
        ("FD6", "맛집"), 
        ("CE7", "카페"), 
        ("AT4", "관광명소")
    ]
    
    results = []
    headers = {"Authorization": f"KakaoAK {api_key}"}
    base_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    
    for code, keyword in categories:
        params = {
            "query": f"{city} {keyword}", 
            "category_group_code": code, 
            "size": 1, 
            "sort": "accuracy"
        }
        try:
            res = requests.get(base_url, headers=headers, params=params).json()
            if res.get('documents'):
                doc = res['documents'][0]
                results.append({
                    "name": doc['place_name'],
                    "category": doc['category_name'].split(">")[-1].strip(),
                    "rating": round(random.uniform(4.0, 4.9), 1),
                    "reviews": random.randint(100, 2000),
                    "url": doc['place_url'],
                    "lat": float(doc['y']),
                    "lng": float(doc['x'])
                })
        except: pass
        
    return results

# --- 거리 계산 및 이동수단 판별 함수 ---
def calculate_distance_time(lat1, lng1, lat2, lng2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLng = math.radians(lng2 - lng1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLng/2) * math.sin(dLng/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    dist_km = R * c
    
    if dist_km <= 1.0:
        minutes = int((dist_km / 4) * 60)
        return f"🚶 도보 약 {minutes}분 ({dist_km:.1f}km)"
    else:
        minutes = int((dist_km / 30) * 60) + 5
        return f"🚕 차량 약 {minutes}분 ({dist_km:.1f}km)"

# --- [수정] P성향을 위한 대안 장소 찾기 (Python 로직) ---
def find_alternatives(target_place, all_candidates, used_names):
    """
    선택된 장소(target_place)와 같은 카테고리이면서,
    가까운 거리에 있는 사용되지 않은 장소를 찾습니다.
    """
    alternatives = []
    target_cat = target_place.get('category', '')
    
    # 카테고리 단순화 (매칭 확률 높이기 위함)
    is_food = "음식점" in target_cat
    is_cafe = "카페" in target_cat
    
    for cand in all_candidates:
        if cand['name'] == target_place['name'] or cand['name'] in used_names:
            continue
            
        # 카테고리 유사성 체크
        cand_cat = cand.get('category', '')
        match = False
        if is_food and "음식점" in cand_cat: match = True
        elif is_cafe and "카페" in cand_cat: match = True
        elif not is_food and not is_cafe: # 관광지/기타의 경우
             if target_cat.split(">")[0] == cand_cat.split(">")[0]: # 대분류가 같으면
                 match = True
        
        if match:
            # 거리 계산 (직선 거리)
            dist = math.sqrt((target_place['lat'] - cand['lat'])**2 + (target_place['lng'] - cand['lng'])**2)
            # 너무 멀지 않은 곳 (약 5km 이내, 좌표상 0.05 정도)
            if dist < 0.05:
                alternatives.append(cand)
    
    # 가까운 순 정렬 후 상위 2개 리턴
    alternatives.sort(key=lambda x: (x['lat'] - target_place['lat'])**2 + (x['lng'] - target_place['lng'])**2)
    
    return [a['name'] for a in alternatives[:2]]

# --- 후보군 수집 로직 ---
def fetch_candidate_places(city, theme, api_key):
    if not api_key: return []
    
    # 1. 필수 카테고리 (맛집, 카페, 관광지는 무조건 포함)
    required_keywords = ["맛집", "카페", "가볼만한곳"] 
    
    # 2. 테마별 추가 키워드
    theme_keywords = []
    if theme == "맛집/카페": theme_keywords = ["디저트", "베이커리", "특색있는 식당"]
    elif theme == "액티비티": theme_keywords = ["체험", "레저", "테마파크", "원데이클래스"]
    elif theme == "힐링": theme_keywords = ["공원", "숲", "스파", "산책로", "서점"]
    elif theme == "역사": theme_keywords = ["박물관", "유적지", "문화재"]
    
    # 중복 제거하여 검색할 키워드 확정
    search_keywords = list(set(required_keywords + theme_keywords))
    
    candidates = []
    headers = {"Authorization": f"KakaoAK {api_key}"}
    base_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    
    for kw in search_keywords:
        params = {"query": f"{city} {kw}", "size": 7, "sort": "accuracy"}
        try:
            res = requests.get(base_url, headers=headers, params=params).json()
            for doc in res.get('documents', []):
                candidates.append({
                    "name": doc['place_name'],
                    "lat": float(doc['y']),
                    "lng": float(doc['x']),
                    "url": doc['place_url'],
                    "category": doc['category_name'],
                    "id": doc['id']
                })
        except: pass
    
    # ID 기준 중복 제거
    unique_candidates = {v['id']: v for v in candidates}.values()
    return list(unique_candidates)

# --- AI 코스 생성 로직 ---
def get_ai_course(openai_key, city, mbti, theme, age, weather_data, candidates):
    if not openai_key:
        return None

    client = OpenAI(api_key=openai_key)
    weather_summary = "\n".join([f"- Day {i+1}: {d['desc']}" for i, d in enumerate(weather_data)])
    
    candidates_lite = [{"name": c['name'], "cat": c['category']} for c in candidates]
    candidates_str = json.dumps(candidates_lite, ensure_ascii=False)
    
    # [슬롯 배치 최적화]
    slot_instruction = ""
    if theme == "맛집/카페":
        slot_instruction = """
        1. [식사] 맛집
        2. [카페] 카페/디저트
        3. [관광] 소화시킬 수 있는 가볼만한곳
        4. [식사] 또 다른 맛집
        5. [카페] 또 다른 카페
        """
    else:
        # [샌드위치 구조 유지]
        slot_instruction = f"""
        1. [테마] {theme} 관련 메인 명소
        2. [식사] 근처 맛집
        3. [카페] 휴식하기 좋은 카페
        4. [테마] {theme} 관련 명소 2 (또는 체험)
        5. [관광] 가볍게 산책하기 좋은 일반 관광지
        """

    prompt = f"""
    당신은 {age}를 위한 {theme} 전문 여행 가이드입니다.
    여행지: {city}
    일정: {len(weather_data)}일간
    
    [Available Places]
    {candidates_str}

    [필수 미션 - Slot System]
    각 날짜별로 **반드시 아래 순서(1번->5번)를 그대로 지켜서** 5개 장소를 선정하세요.
    순서를 절대 임의로 바꾸지 마세요.
    
    {slot_instruction}

    [동선 최적화 지시]
    장소를 고를 때, 1번부터 5번까지의 이동 경로가 너무 꼬이지 않도록
    **지리적으로 가까운 장소들끼리 묶어서** 선정해주세요.
    
    [Output Format]
    JSON Only.
    {{
        "title": "여행 제목",
        "schedule": [
            {{
                "day": 1, 
                "weather_note": "날씨",
                "places": [
                    {{ "name": "장소명", "desc": "이유" }},
                    ... (총 5개)
                ]
            }},
            ...
        ]
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a JSON generator. Respond strictly in JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )
        
        content = response.choices[0].message.content.replace("```json", "").replace("```", "")
        course_data = json.loads(content)
        
        candidate_map = {c['name']: c for c in candidates}
        
        all_used_names = set()
        for day in course_data['schedule']:
            for p in day['places']:
                all_used_names.add(p['name'])

        for day in course_data['schedule']:
            mapped_places = []
            for p in day['places']:
                matched = candidate_map.get(p['name'])
                if not matched:
                    for c_name, c_data in candidate_map.items():
                        if p['name'] in c_name or c_name in p['name']:
                            matched = c_data; p['name'] = c_name; break
                
                if matched:
                    p.update(matched)
                    mapped_places.append(p)
            
            # [수정됨] 거리 기반 재정렬 로직(optimize_route_order) 삭제
            # AI가 정해준 슬롯 순서(식-카-관...)를 그대로 유지합니다.
            optimized_places = mapped_places 
            
            final_places = []
            prev_lat, prev_lng = None, None
            
            is_p_type = "P" in mbti 

            for i, p in enumerate(optimized_places):
                if i == 0:
                    p['time'] = "10:00"
                    p['transport'] = "🏁 일정 시작"
                else:
                    time_obj = datetime.strptime(final_places[-1]['time'], "%H:%M")
                    next_time = time_obj + timedelta(hours=2) 
                    p['time'] = next_time.strftime("%H:%M")
                    
                    if prev_lat:
                        p['transport'] = calculate_distance_time(prev_lat, prev_lng, p['lat'], p['lng'])
                    else:
                        p['transport'] = "이동 정보 없음"
                
                prev_lat, prev_lng = p['lat'], p['lng']
                
                if is_p_type:
                    p['alternatives'] = find_alternatives(p, candidates, all_used_names)
                else:
                    p['alternatives'] = [] 
                
                final_places.append(p)
                
            day['places'] = final_places

        return course_data

    except Exception as e:
        print(f"Error: {e}")
        return None

# --- 4. 이미지 처리 ---
def get_image_metadata(uploaded_file):
    try:
        image = Image.open(uploaded_file)
        exif_data = {}
        if hasattr(image, '_getexif') and image._getexif():
            for tag, value in image._getexif().items():
                exif_data[TAGS.get(tag, tag)] = value
        
        def _convert(value):
            return float(value[0]) + (float(value[1])/60.0) + (float(value[2])/3600.0)

        lat, lng, date_time = None, None, "날짜 정보 없음"
        if "GPSInfo" in exif_data:
            gps = {GPSTAGS.get(k, k): v for k, v in exif_data["GPSInfo"].items()}
            if "GPSLatitude" in gps and "GPSLongitude" in gps:
                lat = _convert(gps["GPSLatitude"])
                lng = _convert(gps["GPSLongitude"])
                if gps.get("GPSLatitudeRef") == "S": lat = -lat
                if gps.get("GPSLongitudeRef") == "W": lng = -lng
        
        if "DateTimeOriginal" in exif_data:
            dt = datetime.strptime(exif_data["DateTimeOriginal"], "%Y:%m:%d %H:%M:%S")
            date_time = dt.strftime("%Y년 %m월 %d일 %H:%M")
        return {"lat": lat, "lng": lng, "date": date_time, "filename": uploaded_file.name}
    except: return None

def get_closest_city(lat, lng):
    min_dist = float('inf')
    closest_city = "기타"
    for city, coords in CITY_COORDS.items():
        dist = math.sqrt((lat - coords['lat'])**2 + (lng - coords['lng'])**2)
        if dist < min_dist:
            min_dist = dist
            closest_city = city
    if min_dist > 1.5: return "기타 지역"
    return closest_city