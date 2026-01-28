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

# --- 3. AI 코스 생성 (로직 강화) ---
def fetch_candidate_places(city, theme, api_key):
    if not api_key: return []
    
    # [수정 1] 어떤 테마든 '맛집'과 '카페'는 기본으로 검색해서 후보군에 넣어야 함
    base_keywords = ["맛집", "카페"]
    theme_keywords = []
    
    if theme == "맛집/카페": theme_keywords = ["디저트", "베이커리", "브런치"]
    elif theme == "액티비티": theme_keywords = ["테마파크", "체험", "액티비티", "레저"]
    elif theme == "힐링": theme_keywords = ["공원", "산책", "휴양림", "스파", "북카페"]
    elif theme == "역사": theme_keywords = ["박물관", "유적지", "문화재", "절"]
    else: theme_keywords = ["가볼만한곳"]

    # 기본 키워드와 테마 키워드 합치기
    all_keywords = list(set(base_keywords + theme_keywords))

    candidates = []
    headers = {"Authorization": f"KakaoAK {api_key}"}
    base_url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    
    for kw in all_keywords:
        params = {"query": f"{city} {kw}", "size": 8, "sort": "accuracy"} # 사이즈 조절
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
    if not openai_key:
        st.error("🚨 OpenAI API 키가 입력되지 않았습니다.")
        return None

    client = OpenAI(api_key=openai_key)
    weather_summary = "\n".join([f"- Day {i+1} ({d['date']}): {d['desc']} ({d['context']})" for i, d in enumerate(weather_data)])
    candidates_str = json.dumps([{"name": c['name'], "url": c['url'], "cat": c['category']} for c in candidates], ensure_ascii=False)
    
    persona = f"당신은 {age}를 위한 {theme} 전문 여행 가이드입니다."
    
    # [수정 2] 테마별 일정 구조 지침 강화
    structure_prompt = ""
    if theme == "맛집/카페":
        structure_prompt = """
        [일정 구성 패턴 - 맛집/카페 테마]
        - 하루 동선을 반드시 다음 패턴에 가깝게 구성하세요:
          **[식사 -> 카페 -> 관광 -> 식사 -> 카페 ->술집]**
        - 하루에 최소 2곳의 맛집과 2곳의 카페를 배치하세요.
        - 유명한 디저트 카페나 베이커리를 우선 순위에 두세요.
        """
    else:
        structure_prompt = """
        [일정 구성 패턴 - 일반 테마]
        - 메인 테마({theme}) 위주로 구성하되, 중간에 **반드시 맛집 1곳과 카페 1곳 이상**을 섞어서 배치하세요.
        - 금강산도 식후경입니다. 배고프거나 지치지 않도록 적절한 타이밍에 식사와 휴식(카페)을 넣으세요.
        """

    style_prompt = ""
    if "J" in mbti:
        style_prompt = "[J형] 시간 엄수(10:30 등). 동선 효율 고려. alternatives는 빈 리스트."
    else:
        style_prompt = "[P형] 시간은 러프하게. alternatives 필수 작성(후보군 중 가까운 곳 2개)."

    prompt = f"""
    {persona}
    여행지: 대한민국 {city}
    기간: {len(weather_data)}일
    날씨: {weather_summary}
    [Candidate List (사용 가능한 장소 목록)] 
    {candidates_str}
    
    [미션] 
    1. 위 'Candidate List'에 있는 장소들 중에서만 선택하여 여행 코스를 짜세요. 
    2. 없는 장소를 지어내지 마세요.
    3. 날씨를 고려하여 비가 오면 실내 위주로 배치하세요.
    
    {structure_prompt}
    
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
        
        for day in course_data['schedule']:
            prev_lat, prev_lng = None, None
            
            for idx, place in enumerate(day['places']):
                if 'alternatives' in place and place['alternatives']:
                    clean_alts = []
                    for alt in place['alternatives']:
                        if isinstance(alt, dict): clean_alts.append(alt.get('name', str(alt)))
                        else: clean_alts.append(str(alt))
                    place['alternatives'] = clean_alts

                matched = candidate_map.get(place['name'])
                if not matched:
                    for c_name, c_data in candidate_map.items():
                        if place['name'] in c_name or c_name in place['name']:
                            matched = c_data; place['name'] = c_name; break
                
                if matched:
                    place['lat'] = matched['lat']; place['lng'] = matched['lng']; place['url'] = matched['url']
                else:
                    place['lat'] = 0.0; place['lng'] = 0.0; place['url'] = ""

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
        st.error(f"🚨 AI 코스 생성 중 오류 발생: {e}")
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