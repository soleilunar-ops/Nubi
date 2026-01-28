import streamlit as st
import streamlit.components.v1 as components
import os
from dotenv import load_dotenv

# 1. 환경 변수 로드 (보안)
load_dotenv()
kakao_api_key = os.getenv("KAKAO_API_KEY")

# 2. 페이지 기본 설정
st.set_page_config(layout="wide", page_title="Location Dashboard")

st.title("📍 실시간 위치 기반 카카오맵")
st.caption("현재 계신 위치를 기반으로 지도를 렌더링합니다.")

# API 키 누락 방지 체크 (리스크 관리)
if not kakao_api_key:
    st.error("⚠️ API 키가 설정되지 않았습니다. .env 파일을 확인해주십시오.")
    st.stop()

# 3. HTML/JS 스크립트 작성
# Streamlit은 파이썬이지만, 지도는 브라우저(JS) 영역입니다.
# 20년 노하우: iframe 방식보다 html 컴포넌트 직접 주입이 반응 속도가 빠릅니다.
map_html = f"""
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <title>Kakao Map</title>
    </head>
    <style>
        body {{ margin: 0; padding: 0; }}
        #map {{ width: 100%; height: 600px; }}
    </style>
    <body>
        <div id="map"></div>
        <script type="text/javascript" src="//dapi.kakao.com/v2/maps/sdk.js?appkey={kakao_api_key}"></script>
        <script>
            var mapContainer = document.getElementById('map');
            
            // 기본 좌표 (판교 카카오 본사 - GPS 실패 시 폴백 데이터)
            var mapOption = {{
                center: new kakao.maps.LatLng(33.450701, 126.570667),
                level: 3
            }};

            var map = new kakao.maps.Map(mapContainer, mapOption);

            // HTML5 Geolocation API 사용 (현재 위치 추적)
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(function(position) {{
                    
                    var lat = position.coords.latitude; // 위도
                    var lon = position.coords.longitude; // 경도
                    
                    var locPosition = new kakao.maps.LatLng(lat, lon);
                    
                    // 마커 생성
                    var marker = new kakao.maps.Marker({{  
                        map: map, 
                        position: locPosition
                    }}); 
                    
                    // 지도 중심을 현재 위치로 이동
                    map.setCenter(locPosition);
                    
                }}, function(error) {{
                    // 위치 권한 거부 등의 에러 처리
                    console.error("Geolocation error: " + error.message);
                }});
                
            }} else {{ 
                alert('이 브라우저에서는 위치 정보를 사용할 수 없습니다.'); 
            }}
        </script>
    </body>
</html>
"""

# 4. 화면 렌더링
# 높이를 600px로 넉넉하게 잡아 시인성을 확보했습니다.
components.html(map_html, height=600)