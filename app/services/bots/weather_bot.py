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

    async def get_daily_min_max(self, city: str = "Seoul") -> Optional[Dict]:
        """
        하루의 최저/최고 온도를 Forecast API에서 계산
        - 오늘 데이터가 있으면 오늘 하루 사용
        - 오늘 데이터가 없으면 (저녁/밤) 내일 하루 사용

        Args:
            city: 도시명

        Returns:
            Dict: {"temp_min": float, "temp_max": float, "date": str} 또는 None
        """
        try:
            forecast_data = await self.get_forecast(city)
            
            if not forecast_data:
                return None

            now = datetime.now(ZoneInfo("Asia/Seoul"))
            today = now.date()
            
            # 날짜별로 온도 데이터 수집
            daily_temps = {}  # {date: [temps]}

            for item in forecast_data.get("list", []):
                # 예보 시간을 서울 시간대로 변환
                forecast_dt = datetime.fromtimestamp(
                    item["dt"], tz=ZoneInfo("Asia/Seoul")
                )
                forecast_date = forecast_dt.date()
                temp = item["main"]["temp"]
                
                # 날짜별로 온도 수집
                if forecast_date not in daily_temps:
                    daily_temps[forecast_date] = []
                daily_temps[forecast_date].append(temp)

            # 오늘 데이터가 있는지 확인
            if today in daily_temps and len(daily_temps[today]) >= 3:
                # 오늘 데이터가 충분하면 (최소 3개 이상) 오늘 사용
                temps = daily_temps[today]
                target_date = today
            else:
                # 오늘 데이터가 없거나 부족하면 다음날 사용
                from datetime import timedelta
                tomorrow = today + timedelta(days=1)
                if tomorrow in daily_temps:
                    temps = daily_temps[tomorrow]
                    target_date = tomorrow
                else:
                    return None

            # 최저/최고 계산
            if temps:
                return {
                    "temp_min": min(temps),
                    "temp_max": max(temps),
                    "date": target_date.strftime("%Y-%m-%d")
                }
            
            return None

        except Exception as e:
            print(f"❌ 최저/최고 온도 계산 실패: {e}")
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
