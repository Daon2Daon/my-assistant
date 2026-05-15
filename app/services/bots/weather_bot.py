"""
날씨 알림 봇
OpenWeatherMap API를 사용한 날씨 정보 수집 및 알림
"""

import httpx
from typing import Dict, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from app.config import settings
from app.database import SessionLocal
from app.crud import get_or_create_user, create_log, is_setting_active
from app.services.notification import notification_service


class WeatherBot:
    """날씨 알림 봇"""

    def __init__(self):
        self.api_key = settings.OPENWEATHER_API_KEY
        self.base_url = "https://api.openweathermap.org/data/2.5"

    async def get_weather(
        self, city: str = "Seoul", lang: str = "kr"
    ) -> Optional[Dict]:
        """
        OpenWeatherMap API로 현재 날씨 조회

        Args:
            city: 도시명 (기본값: Seoul)
            lang: 언어 (기본값: kr)

        Returns:
            Dict: 날씨 정보 또는 None
        """
        try:
            url = f"{self.base_url}/weather"
            params = {
                "q": city,
                "appid": self.api_key,
                "units": "metric",  # 섭씨 온도
                "lang": lang,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)

                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"❌ 날씨 API 오류: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            print(f"❌ 날씨 조회 실패: {e}")
            return None

    async def get_forecast(
        self, city: str = "Seoul", lang: str = "kr"
    ) -> Optional[Dict]:
        """
        OpenWeatherMap API로 5일 날씨 예보 조회

        Args:
            city: 도시명
            lang: 언어

        Returns:
            Dict: 날씨 예보 정보 또는 None
        """
        try:
            url = f"{self.base_url}/forecast"
            params = {
                "q": city,
                "appid": self.api_key,
                "units": "metric",
                "lang": lang,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)

                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"❌ 예보 API 오류: {response.status_code}")
                    return None

        except Exception as e:
            print(f"❌ 예보 조회 실패: {e}")
            return None

    async def get_coords(self, city: str) -> Optional[tuple[float, float]]:
        """
        도시명을 위경도로 변환 (OWM Geocoding API 사용).

        Returns:
            (lat, lon) 또는 None
        """
        try:
            url = "https://api.openweathermap.org/geo/1.0/direct"
            params = {"q": city, "limit": 1, "appid": self.api_key}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
            if resp.status_code != 200 or not resp.json():
                return None
            data = resp.json()[0]
            return data["lat"], data["lon"]
        except Exception as e:
            print(f"⚠️  Geocoding 실패 ({city}): {e}")
            return None

    async def get_daily_min_max(self, city: str = "Seoul") -> Optional[Dict]:
        """
        하루 최저/최고 기온 조회.

        [1순위] One Call API 3.0 — daily[0].temp.min/max (가장 정확한 일별 예보)
        [2순위] Forecast API 3시간 예보 폴백
          - 각 구간의 temp_min/temp_max 를 집계해 일별 범위를 계산
          - 오늘 구간이 1개 이상 있으면 오늘 날짜 데이터 사용
          - 오늘 구간이 없으면 내일 데이터 사용 (저녁 이후 발송 시)

        Returns:
            Dict: {"temp_min": float, "temp_max": float, "date": str, "source": str}
        """
        result = await self._get_daily_min_max_onecall(city)
        if result:
            return result
        return await self._get_daily_min_max_forecast(city)

    async def _get_daily_min_max_onecall(self, city: str) -> Optional[Dict]:
        """One Call API 3.0으로 일별 최저/최고 조회."""
        try:
            coords = await self.get_coords(city)
            if not coords:
                return None
            lat, lon = coords

            url = "https://api.openweathermap.org/data/3.0/onecall"
            params = {
                "lat": lat,
                "lon": lon,
                "exclude": "current,minutely,hourly,alerts",
                "appid": self.api_key,
                "units": "metric",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)

            if resp.status_code != 200:
                print(f"⚠️  One Call API 응답 오류 {resp.status_code} — Forecast API로 폴백")
                return None

            daily = resp.json().get("daily", [])
            if not daily:
                return None

            today_data = daily[0]
            temp_min = today_data["temp"]["min"]
            temp_max = today_data["temp"]["max"]
            now = datetime.now(ZoneInfo("Asia/Seoul"))
            print(
                f"🌡️  One Call API: 오늘 최저 {temp_min:.1f}°C / 최고 {temp_max:.1f}°C"
                f" (lat={lat:.4f}, lon={lon:.4f})"
            )
            return {
                "temp_min": temp_min,
                "temp_max": temp_max,
                "date": now.strftime("%Y-%m-%d"),
                "source": "onecall",
            }

        except Exception as e:
            print(f"⚠️  One Call API 호출 실패: {e}")
            return None

    async def _get_daily_min_max_forecast(self, city: str) -> Optional[Dict]:
        """Forecast API 3시간 예보에서 일별 최저/최고를 계산."""
        try:
            forecast_data = await self.get_forecast(city)
            if not forecast_data:
                return None

            now = datetime.now(ZoneInfo("Asia/Seoul"))
            today = now.date()

            # 날짜별로 (temp_min 목록, temp_max 목록) 수집
            # temp_min/temp_max는 각 3시간 구간의 범위값으로
            # 단일 temp 포인트보다 정확한 일별 범위를 얻을 수 있음
            daily_mins: Dict = {}
            daily_maxs: Dict = {}

            for item in forecast_data.get("list", []):
                forecast_dt = datetime.fromtimestamp(
                    item["dt"], tz=ZoneInfo("Asia/Seoul")
                )
                forecast_date = forecast_dt.date()
                main = item["main"]
                t_min = main.get("temp_min", main["temp"])
                t_max = main.get("temp_max", main["temp"])

                if forecast_date not in daily_mins:
                    daily_mins[forecast_date] = []
                    daily_maxs[forecast_date] = []
                daily_mins[forecast_date].append(t_min)
                daily_maxs[forecast_date].append(t_max)

            # 오늘 구간이 1개라도 있으면 오늘 사용 (>= 3 임계값 제거)
            if today in daily_mins:
                target_date = today
            else:
                from datetime import timedelta
                tomorrow = today + timedelta(days=1)
                if tomorrow in daily_mins:
                    print(
                        f"⚠️  오늘({today}) Forecast 구간 없음 — 내일({tomorrow}) 데이터 사용"
                    )
                    target_date = tomorrow
                else:
                    return None

            temp_min = min(daily_mins[target_date])
            temp_max = max(daily_maxs[target_date])
            count = len(daily_mins[target_date])
            print(
                f"🌡️  Forecast API 폴백: {target_date} 구간 {count}개"
                f" → 최저 {temp_min:.1f}°C / 최고 {temp_max:.1f}°C"
            )
            return {
                "temp_min": temp_min,
                "temp_max": temp_max,
                "date": target_date.strftime("%Y-%m-%d"),
                "source": "forecast",
            }

        except Exception as e:
            print(f"❌ Forecast API 최저/최고 계산 실패: {e}")
            return None

    def format_weather_message(
        self, 
        weather_data: Dict, 
        daily_min_max: Optional[Dict] = None
    ) -> str:
        """
        날씨 데이터를 메시지 형식으로 포맷팅

        Args:
            weather_data: OpenWeatherMap Current Weather API 응답 데이터
            daily_min_max: 오늘의 최저/최고 온도 (Forecast API에서 계산)

        Returns:
            str: 포맷팅된 메시지
        """
        try:
            # 기본 정보 추출
            city = weather_data.get("name", "알 수 없음")
            main = weather_data.get("main", {})
            weather = weather_data.get("weather", [{}])[0]
            wind = weather_data.get("wind", {})
            clouds = weather_data.get("clouds", {})

            temp = main.get("temp", 0)
            feels_like = main.get("feels_like", 0)
            humidity = main.get("humidity", 0)
            description = weather.get("description", "정보 없음")
            wind_speed = wind.get("speed", 0)
            cloudiness = clouds.get("all", 0)

            # 최저/최고 온도 결정
            # Forecast API에서 가져온 값이 있으면 사용, 없으면 Current API의 값 사용
            if daily_min_max:
                temp_min = daily_min_max.get("temp_min", main.get("temp_min", 0))
                temp_max = daily_min_max.get("temp_max", main.get("temp_max", 0))
            else:
                temp_min = main.get("temp_min", 0)
                temp_max = main.get("temp_max", 0)

            # 우산 필요 여부 판단 (비/눈이 오거나 습도가 높은 경우)
            weather_main = weather.get("main", "")
            needs_umbrella = "필요" if weather_main in ["Rain", "Drizzle", "Thunderstorm", "Snow"] else "불필요"

            # 메시지 구성
            message = f"""☀️ 오늘의 날씨 ({city})

📅 {datetime.now(ZoneInfo("Asia/Seoul")).strftime('%Y년 %m월 %d일 %H:%M')}

🌡️ 온도 정보:
- 현재 기온: {temp:.1f}°C
- 체감 기온: {feels_like:.1f}°C
- 최저 / 최고: {temp_min:.1f}°C / {temp_max:.1f}°C

🌦️ 날씨 상태: {description}

💧 습도: {humidity}%
💨 풍속: {wind_speed:.1f}m/s
☁️ 구름: {cloudiness}%

☂️ 우산: {needs_umbrella}"""

            return message

        except Exception as e:
            print(f"❌ 메시지 포맷팅 실패: {e}")
            return "날씨 정보를 가져올 수 없습니다."

    async def send_weather_notification(self, city: str = "Seoul"):
        """
        날씨 알림 발송
        DB에서 사용자 정보를 조회하고 카카오톡 메시지 발송

        Args:
            city: 도시명
        """
        db = SessionLocal()

        try:
            # 사용자 조회
            user = get_or_create_user(db)

            # Settings에서 날씨 알림 활성화 여부 확인
            if not is_setting_active(db, user.user_id, "weather"):
                print("⏸️  날씨 알림이 비활성화되어 있습니다")
                create_log(db, "weather", "SKIP", "날씨 알림 비활성화 상태")
                return

            # 현재 날씨 정보 조회
            weather_data = await self.get_weather(city)

            if not weather_data:
                # 로그 기록
                create_log(db, "weather", "FAIL", f"날씨 정보 조회 실패 - {city}")
                return

            # 오늘의 최저/최고 온도 조회 (Forecast API)
            daily_min_max = await self.get_daily_min_max(city)

            # 메시지 포맷팅
            message = self.format_weather_message(weather_data, daily_min_max)

            # 연동된 채널 확인
            available_channels = notification_service.get_available_channels(user)
            if not available_channels:
                create_log(db, "weather", "FAIL", "연동된 알림 채널이 없습니다")
                print("⚠️  알림 채널 연동이 필요합니다 (텔레그램)")
                return

            # 알림 발송 (연동된 모든 채널로 자동 발송)
            try:
                result = await notification_service.send(user, message)

                if result.success:
                    # 성공 로그
                    create_log(
                        db,
                        "weather",
                        "SUCCESS",
                        f"날씨 알림 발송 성공 - {city} ({result.message})",
                    )
                    print(f"✅ 날씨 알림 발송 완료 - {city}")
                else:
                    # 실패 로그
                    create_log(db, "weather", "FAIL", f"알림 발송 실패: {result.message}")
                    print(f"❌ 알림 발송 실패: {result.message}")

            except Exception as e:
                create_log(db, "weather", "FAIL", f"알림 발송 오류: {str(e)}")
                print(f"❌ 알림 발송 오류: {e}")

        except Exception as e:
            create_log(db, "weather", "FAIL", f"날씨 알림 오류: {str(e)}")
            print(f"❌ 날씨 알림 오류: {e}")

        finally:
            db.close()


# 싱글톤 인스턴스
weather_bot = WeatherBot()


# 스케줄러에서 호출할 함수
def send_weather_notification_sync(city: str = "Seoul"):
    """
    동기 방식으로 날씨 알림 발송
    스케줄러에서 비동기 함수를 호출하기 위한 래퍼
    """
    import asyncio

    try:
        asyncio.run(weather_bot.send_weather_notification(city))
    except Exception as e:
        print(f"❌ 날씨 알림 실행 오류: {e}")
