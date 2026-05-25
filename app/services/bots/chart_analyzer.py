"""
ChartAnalyzer - 차트 이미지를 LLM(Gemini Vision)으로 분석하여 텍스트 코멘트 반환.

흐름:
  1. chartbot config_json 에서 ai_analysis 설정 로드
  2. 일봉·주봉 PNG 파일을 base64 인코딩
  3. 프롬프트 빌드 (사용자 지시 + 종목 메타데이터 prepend)
  4. LiteLLMClient.analyze_images_native() 호출
  5. 마크다운 → 텔레그램 HTML 변환 후 반환
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.crud import get_or_create_user, get_setting_by_category
from app.services.youtube.llm_client import LiteLLMClient, LiteLLMError, get_litellm_client
from app.services.youtube.settings_manager import AIGatewaySettings


# ─────────────────────────────────────────
# 기본 프롬프트 (사용자가 UI에서 편집 가능)
# ─────────────────────────────────────────
DEFAULT_PROMPT = """# 역할
- 당신은 자산운용사 트레이딩 데스크에서 10년 이상 차트 분석을 담당한 시니어 차티스트입니다.
- 매일 아침 운용역에게 텔레그램으로 자산의 기술적 관점을 보고합니다.

# 입력 차트 구성 (매우 중요 — 정확한 해석을 위해 숙지)
제공되는 각 차트는 4개 패널로 구성됩니다.

[Panel 1 - 가격 차트]
- 캔들스틱 (녹색=상승, 적색=하락)
- 이동평균선 4종:
  * EMA 12 (빨강 실선) - 단기 모멘텀
  * EMA 26 (파랑 실선) - 단기-중기
  * SMA 20 (진녹 실선) - 단기 추세
  * SMA 50 (주황 실선) - 중기 추세
- 볼린저밴드 (회색 점선 ±2σ, 음영 영역)
- 매물대 / Volume Profile: 좌측 Y축을 따라 그려진 옅은 주황색 가로막대.
  막대가 두꺼울수록 해당 가격대의 누적 거래량이 큼 (지지/저항 강도 지표).

[Panel 2 - RSI(14)]
- 보라색 선, 70 이상 과매수, 30 이하 과매도
- (배경의 옅은 노란색은 30-70 중립구간 표시일 뿐, 매물대 아님)

[Panel 3 - MACD]
- 파랑 = MACD (EMA12 - EMA26)
- 빨강 = Signal (MACD의 9-period EMA)
- 막대 = Histogram (녹색 양수, 적색 음수)

[Panel 4 - 거래량]
- 막대 = 일/주별 거래량 (전 캔들 대비 상승 녹색, 하락 적색)
- 파랑선 = 거래량 20기간 이동평균

# 분석 원칙
- 매크로, 펀더멘털, 밸류에이션은 일체 고려하지 않습니다.
  오직 차트의 가격 행동과 위 지표만으로 판단합니다.
- 일봉(단기, 1년)과 주봉(중장기, 5년)이 함께 제공된 경우 반드시 교차 분석하여
  시간프레임 간 신호의 일치/괴리를 명시합니다.
- "강세 추세", "조정 가능성" 같은 일반론을 피하고, 차트에서 읽히는 구체적
  근거(가격대, 지표값, 패턴)를 인용합니다.

# 출력 구조 (이 순서·헤더 유지)
1. **종합 의견 한 줄** — 추세 단계 + 모멘텀 + 단기 편향을 한 문장으로 압축
2. **주봉 관점 (중장기)** — 큰 흐름, 핵심 매물대, 이평선 배열, 보조지표
3. **일봉 관점 (단기)** — 최근 캔들 패턴, 이평선 정/역배열, 볼린저 위치, RSI/MACD 시그널
4. **시간프레임 통합 진단** — 일봉·주봉 신호 일치 또는 괴리, 우세한 방향
5. **시나리오** — 상승 시나리오와 하락 시나리오 각각의 트리거 가격과 1차 목표/이탈 시 대응 레벨
6. **트레이딩 관점** — 매수/매도/관망 판단, 핵심 관찰 가격대, 주요 리스크

# 보조 지시
- 피보나치 되돌림: 차트에서 명확한 swing high/low가 보이고 23.6/38.2/50/61.8%
  레벨이 의미 있는 가격대(매물대/이평선/지지저항)와 일치할 때만 언급. 억지 X.
- 일목균형표는 차트에 표시되지 않으므로 강제로 작성하지 않습니다.

# 출력 형식
- 마크다운, 개조식 (불릿 위주, 한 줄 한 호흡)
- 가격은 차트에서 읽히는 수준으로 표기 (예: "약 185달러 부근", "1,250원 매물대")
- 단정적 예측 대신 "조건부 시나리오"로 작성 (예: "X 돌파 시 → Y 시도")
- 전체 분량: 한글 1,500~2,500자 권장"""

# 텔레그램 HTML 출력 지시 (사용자 프롬프트 뒤에 append)
_TELEGRAM_FORMAT_INSTRUCTION = """

[출력 형식 제한]
- 텔레그램 메시지 발송용이므로 아래 HTML 태그만 사용하세요: <b>, <i>, <code>, <pre>
- 헤딩(#, ##)은 <b>섹션명</b>: 형태로 변환
- **굵게**는 <b>굵게</b>, *기울임*은 <i>기울임</i>으로 변환
- 불릿(-) 은 그대로 유지
- 1200자 이내 권장"""


@dataclass
class AiAnalysisConfig:
    """chartbot config_json의 ai_analysis 블록"""
    enabled: bool = False
    model: str = "gemini/gemini-2.5-flash"
    prompt: str = DEFAULT_PROMPT
    include_weekly: bool = True
    max_output_tokens: int = 2000
    temperature: float = 0.4

    @classmethod
    def from_dict(cls, d: dict) -> "AiAnalysisConfig":
        return cls(
            enabled=bool(d.get("enabled", False)),
            model=str(d.get("model", "gemini/gemini-2.5-flash")),
            prompt=str(d.get("prompt", DEFAULT_PROMPT)),
            include_weekly=bool(d.get("include_weekly", True)),
            max_output_tokens=int(d.get("max_output_tokens", 2000)),
            temperature=float(d.get("temperature", 0.4)),
        )


def _load_ai_config() -> Optional[AiAnalysisConfig]:
    """DB에서 chartbot ai_analysis 설정 로드. 설정 없거나 비활성이면 None 반환."""
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")
        if not setting or not setting.config_json:
            return None
        config = json.loads(setting.config_json)
        ai_cfg = config.get("ai_analysis")
        if not ai_cfg or not ai_cfg.get("enabled", False):
            return None
        return AiAnalysisConfig.from_dict(ai_cfg)
    except Exception as e:
        print(f"⚠️ ChartAnalyzer 설정 로드 실패: {e}")
        return None
    finally:
        db.close()


def _get_litellm_client(model: str) -> LiteLLMClient:
    """
    차트봇 전용 LiteLLM 클라이언트 팩토리.
    chartbot config에 litellm_base_url이 설정된 경우 그것을 우선 사용하고,
    없으면 유튜브봇 AI Gateway 설정으로 fallback.
    """
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        setting = get_setting_by_category(db, user.user_id, "chartbot")
        if setting and setting.config_json:
            config = json.loads(setting.config_json)
            base_url = (config.get("litellm_base_url") or "").strip()
            api_key = (config.get("litellm_api_key") or "").strip()
            if base_url:
                custom = AIGatewaySettings(
                    base_url=base_url,
                    api_key=api_key,
                    primary_model=model,
                )
                return get_litellm_client(settings=custom)
    except Exception as e:
        print(f"⚠️ Chartbot LiteLLM 설정 로드 실패, 유튜브봇 설정으로 fallback: {e}")
    finally:
        db.close()
    return get_litellm_client()


def _build_prompt(
    user_prompt: str,
    ticker: str,
    name: str,
    market: str,
    chart_labels: List[str],
) -> str:
    """
    종목 메타데이터와 이미지 순서 정보를 prepend한 최종 프롬프트 생성.

    chart_labels: 실제로 포함된 차트 순서대로 기술.
    예: ["일봉 (1년)", "주봉 (5년)"]  또는  ["일봉 (1년)"]
    """
    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")

    # 이미지 순서 라벨 (LLM이 어느 이미지가 어떤 기간인지 명확히 인지)
    image_order_lines = "\n".join(
        f"  - 이미지 {i+1}: {label}" for i, label in enumerate(chart_labels)
    )
    multi_tf_note = (
        "\n- 일봉과 주봉이 함께 제공된 경우, 단기(일봉)와 중장기(주봉) 흐름을 "
        "교차 분석하여 방향성의 일치 또는 괴리를 반드시 언급해주세요."
        if len(chart_labels) >= 2 else ""
    )

    meta = (
        f"[종목 정보]\n"
        f"- 종목명: {name}\n"
        f"- 티커: {ticker}\n"
        f"- 시장: {market}\n"
        f"- 분석 시점: {now_kst}\n\n"
        f"[제공된 차트 이미지 순서]\n"
        f"{image_order_lines}\n"
        f"{multi_tf_note}\n\n"
        f"[분석 지시]\n"
    )
    return meta + user_prompt + _TELEGRAM_FORMAT_INSTRUCTION


def _md_to_telegram_html(text: str) -> str:
    """
    LLM 출력의 마크다운 패턴을 텔레그램 호환 HTML로 변환.
    프롬프트에서 HTML 출력을 지시하지만 LLM이 마크다운을 섞어 출력하는 경우 대비.
    """
    # 코드 펜스 (```...```) → <pre>...</pre>
    text = re.sub(r"```[a-zA-Z]*\n?([\s\S]*?)```", r"<pre>\1</pre>", text)

    # 인라인 코드 `code` → <code>code</code>
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)

    # **굵게** → <b>굵게</b>
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    # *기울임* → <i>기울임</i> (단, **는 이미 변환됨)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)

    # # 헤딩 → <b>텍스트</b>
    text = re.sub(r"^#{1,3}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 텔레그램 미지원 HTML 태그 제거 (h1~h6, ul, ol, li, hr, br 등)
    # \b 단어 경계로 <pre> 같은 다른 태그가 걸리지 않도록 보호
    text = re.sub(r"<(h[1-6]|ul|ol|li|hr|br|div|span|p)\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</(h[1-6]|ul|ol|li|hr|br|div|span|p)\b>", "", text, flags=re.IGNORECASE)

    return text.strip()


def _split_message(text: str, limit: int = 4000) -> List[str]:
    """텔레그램 메시지 길이 제한(4096자) 대비 분할. 줄바꿈 기준."""
    if len(text) <= limit:
        return [text]
    parts = []
    current = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > limit and current:
            parts.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        parts.append("".join(current))
    return parts


class ChartAnalyzer:
    """
    차트 이미지 → AI 기술분석 텍스트 변환기.
    ChartBot에서 호출되며, LiteLLM Gateway(Gemini Vision)를 사용한다.
    """

    async def analyze(
        self,
        daily_path: Optional[str],
        weekly_path: Optional[str],
        ticker: str,
        name: str,
        market: str,
        config: Optional[AiAnalysisConfig] = None,
    ) -> Optional[str]:
        """
        차트 이미지를 분석하여 텔레그램 HTML 형식의 분석 텍스트 반환.

        Args:
            daily_path: 일봉 차트 PNG 절대 경로 (None 허용)
            weekly_path: 주봉 차트 PNG 절대 경로 (None 허용)
            ticker: 종목 티커
            name: 종목명
            market: 시장 코드 (US / KR)
            config: 외부에서 주입 가능 (None이면 DB에서 로드)

        Returns:
            분석 텍스트 (HTML) 또는 None (비활성/실패)
        """
        cfg = config or _load_ai_config()
        if cfg is None:
            return None

        images: List[Tuple[bytes, str]] = []
        chart_labels: List[str] = []
        for path, label, period in [
            (daily_path, "일봉", "1년"),
            (weekly_path, "주봉", "5년"),
        ]:
            if not path:
                continue
            if label == "주봉" and not cfg.include_weekly:
                continue
            try:
                with open(path, "rb") as f:
                    images.append((f.read(), "image/png"))
                chart_labels.append(f"{label} ({period})")
            except Exception as e:
                print(f"⚠️ ChartAnalyzer 이미지 로드 실패 ({label}): {e}")

        if not images:
            print("⚠️ ChartAnalyzer: 분석할 이미지가 없습니다.")
            return None

        prompt = _build_prompt(cfg.prompt, ticker, name, market, chart_labels)

        try:
            client = _get_litellm_client(cfg.model)
            raw = await client.analyze_images_native(
                model=cfg.model,
                images=images,
                prompt=prompt,
                temperature=cfg.temperature,
                max_output_tokens=cfg.max_output_tokens,
            )
        except LiteLLMError as e:
            print(f"❌ ChartAnalyzer LLM 호출 실패 ({ticker}): {e}")
            return None
        except Exception as e:
            print(f"❌ ChartAnalyzer 예기치 않은 오류 ({ticker}): {e}")
            return None

        return _md_to_telegram_html(raw)

    def split_for_telegram(self, text: str) -> List[str]:
        """분석 텍스트를 텔레그램 메시지 길이(4000자) 단위로 분할."""
        return _split_message(text)


chart_analyzer = ChartAnalyzer()
