import os
import json
import requests
import math
import random
from openai import OpenAI
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

# --- [NEW] Page 1용: 카테고리별 실시간 Top 1 (총 3개) 수집 ---
def fetch_top_places(city, api_key):
    """
    Page 1 퀵뷰용 함수. '핫플레이스' 키워드를 사용하지 않고,
    맛집(FD6), 카페(CE7), 관광지(AT4) 카테고리에서 각각 상위 1개를 가져와
    다양성 있는 Top 3를 구성합니다.
    """
    if not api_key: return []
    
    # 다양성을 위해 3가지 카테고리 선정
    categories = [
        ("FD6", "맛집"),       # 음식점
        ("CE7", "카페"),       # 카페
        ("AT4", "관광명소")    # 관광지
    ]
    
    results = []
    headers = {"Authorization": f"KakaoAK {api_key}"}
    base_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    
    for code, keyword in categories:
        # 카테고리 코드 기반 검색 + 정확도순(accuracy) = 카카오 추천 로직
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
                    "rating": round(random.uniform(4.0, 4.9), 1), # API 별점 미제공으로 시뮬레이션
                    "reviews": random.randint(100, 2000),         # API 리뷰수 미제공으로 시뮬레이션
                    "url": doc['place_url'],
                    "lat": float(doc['y']),
                    "lng": float(doc['x'])
                })
        except: pass
        
    return results

# --- [NEW] 거리 계산 및 이동수단 판별 함수 (Haversine Algorithm) ---
def calculate_distance_time(lat1, lng1, lat2, lng2):
    R = 6371  # 지구 반지름 (km)
    dLat = math.radians(lat2 - lat1)
    dLng = math.radians(lng2 - lng1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLng/2) * math.sin(dLng/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    dist_km = R * c
    
    # [수정 3] 이동 로직 (도보 vs 차량)
    if dist_km <= 1.0: # 1km 이하는 도보 권장
        # 도보 시속 4km 가정
        minutes = int((dist_km / 4) * 60)
        return f"🚶 도보 약 {minutes}분 ({dist_km:.1f}km)"
    else:
        # 차량 시속 30km 가정 (시내 주행 + 신호 대기 고려) + 기본 5분
        minutes = int((dist_km / 30) * 60) + 5
        return f"🚕 차량 약 {minutes}분 ({dist_km:.1f}km)"

# --- 3. AI 코스 생성 (거리 계산 로직 추가) ---
def fetch_candidate_places(city, theme, api_key):
    if not api_key: return []
    
    keywords = []
    if theme == "맛집/카페": keywords = ["맛집", "카페", "디저트"]
    elif theme == "액티비티": keywords = ["테마파크", "체험", "액티비티", "레저"]
    elif theme == "힐링": keywords = ["공원", "산책", "휴양림", "스파", "북카페"]
    elif theme == "역사": keywords = ["박물관", "유적지", "문화재", "절"]
    else: keywords = ["가볼만한곳"]

    candidates = []
    headers = {"Authorization": f"KakaoAK {api_key}"}
    base_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    
    for kw in keywords:
        params = {"query": f"{city} {kw}", "size": 10, "sort": "accuracy"}
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
    
    unique_candidates = {v['id']: v for v in candidates}.values()
    return list(unique_candidates)

def get_ai_course(openai_key, city, mbti, theme, age, weather_data, candidates):
    client = OpenAI(api_key=openai_key)
    weather_summary = "\n".join([f"- Day {i+1} ({d['date']}): {d['desc']} ({d['context']})" for i, d in enumerate(weather_data)])
    candidates_str = json.dumps([{"name": c['name'], "url": c['url'], "cat": c['category']} for c in candidates], ensure_ascii=False)
    
    persona = f"당신은 {age}를 위한 {theme} 전문 여행 가이드입니다."
    if "20대" in age: persona += " 인스타 감성과 힙한 장소를 선호합니다."
    elif "40대" in age: persona += " 편안하고 쾌적한 동선, 주차 편의성을 중시합니다."
    
    style_prompt = ""
    if "J" in mbti:
        style_prompt = """
        [J형] 시간 엄수(10:30 등). 동선 효율 고려. alternatives는 빈 리스트.
        """
    else:
        style_prompt = """
        [P형] 시간은 러프하게. alternatives 필수 작성(후보군 중 가까운 곳 2개).
        """

    prompt = f"""
    {persona}
    여행지: 대한민국 {city}
    기간: {len(weather_data)}일
    날씨: {weather_summary}
    [Candidate List] {candidates_str}
    
    [미션] Candidate List 내 장소로 코스 구성. 비오면 실내.
    {style_prompt}
    
    [JSON Output Format]
    {{
        "title": "제목", "description": "요약",
        "schedule": [
            {{ "day": 1, "date": "YYYY-MM-DD", "weather_note": "날씨",
               "places": [
                   {{ "time": "시간", "name": "장소명", "transport": "이동정보(나중에계산됨)", "desc": "설명", "alternatives": [] }}
               ]
            }}
        ]
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "Output JSON only."}, {"role": "user", "content": prompt}],
            temperature=0.7
        )
        content = response.choices[0].message.content.replace("```json", "").replace("```", "")
        course_data = json.loads(content)
        
        candidate_map = {c['name']: c for c in candidates}
        
        # [데이터 후처리] 1. 좌표 매핑, 2. 정확한 거리 계산(Override), 3. 대안 장소 정제
        for day in course_data['schedule']:
            prev_lat, prev_lng = None, None
            
            for idx, place in enumerate(day['places']):
                # [Fix] 대안 장소(alternatives) 안전 정제 (dict -> str)
                if 'alternatives' in place and place['alternatives']:
                    clean_alts = []
                    for alt in place['alternatives']:
                        if isinstance(alt, dict): clean_alts.append(alt.get('name', str(alt)))
                        else: clean_alts.append(str(alt))
                    place['alternatives'] = clean_alts

                # 좌표 매핑
                matched = candidate_map.get(place['name'])
                if not matched:
                    for c_name, c_data in candidate_map.items():
                        if place['name'] in c_name or c_name in place['name']:
                            matched = c_data; place['name'] = c_name; break
                
                if matched:
                    place['lat'] = matched['lat']; place['lng'] = matched['lng']; place['url'] = matched['url']
                else:
                    place['lat'] = 0.0; place['lng'] = 0.0; place['url'] = ""

                # [수정 3] 거리/시간 계산 로직 적용 (Override)
                if idx == 0:
                    place['transport'] = "🏁 여행 시작"
                else:
                    if prev_lat and prev_lng and place['lat'] != 0:
                        real_transport = calculate_distance_time(prev_lat, prev_lng, place['lat'], place['lng'])
                        place['transport'] = real_transport
                    else:
                        place['transport'] = "이동 정보 계산 불가"
                
                prev_lat = place['lat']
                prev_lng = place['lng']

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