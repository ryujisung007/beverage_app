"""
AI 가상 소비자 조사 플랫폼
━━━━━━━━━━━━━━━━━━━━━━━━━━
6-Phase 소비자 조사 프로세스를 AI로 자동화하는 실전 도구
Gemini API (v1 REST) 연동 | Streamlit Cloud 배포 대응
"""

import streamlit as st
import requests
import json
import time
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 기본 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.set_page_config(
    page_title="AI 소비자 조사 플랫폼",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 커스텀 CSS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1975BC 0%, #0d5a94 100%);
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .main-header h1 { color: white; margin: 0; font-size: 1.8rem; }
    .main-header p { color: #B8D8F0; margin: 0.3rem 0 0 0; font-size: 0.95rem; }
    
    .phase-card {
        background: white;
        border: 1px solid #E8EDF2;
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 0.8rem;
        border-left: 4px solid #1975BC;
    }
    .phase-card h4 { color: #1975BC; margin: 0 0 0.3rem 0; }
    .phase-card p { color: #555; margin: 0; font-size: 0.85rem; }
    
    .result-box {
        background: #F8FBFF;
        border: 1px solid #D0E3F5;
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    
    .stat-card {
        background: linear-gradient(135deg, #1975BC 0%, #2386CD 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
    }
    .stat-card h2 { color: white; margin: 0; font-size: 2rem; }
    .stat-card p { color: #B8D8F0; margin: 0; font-size: 0.8rem; }
    
    .note-box {
        background: #FDF5E6;
        border: 1px solid #F0D080;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        font-size: 0.85rem;
        color: #7A5C1E;
    }
    
    .stChatMessage { border-radius: 12px !important; }
    
    div[data-testid="stSidebar"] { background: #F8FBFF; }
</style>
""", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Gemini API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GEMINI_MODELS = [
    ("gemini-2.5-pro", "v1"),
    ("gemini-2.5-flash", "v1beta"),
    ("gemini-1.5-pro", "v1"),
    ("gemini-1.5-flash", "v1"),
]

def get_api_key():
    """API 키 가져오기 (secrets 또는 sidebar 입력)"""
    if "GOOGLE_API_KEY" in st.secrets:
        return st.secrets["GOOGLE_API_KEY"]
    if "google_api_key" in st.session_state and st.session_state.google_api_key:
        return st.session_state.google_api_key
    return None


def call_gemini(prompt, system_context="", max_tokens=8192):
    """Gemini API 호출 (REST direct, fallback chain)"""
    api_key = get_api_key()
    if not api_key:
        return "⚠️ API 키가 설정되지 않았습니다. 사이드바에서 입력해주세요."
    
    # system_instruction 대신 첫 user 메시지로 주입
    if system_context:
        full_prompt = f"{system_context}\n\n---\n\n{prompt}"
    else:
        full_prompt = prompt
    
    payload = {
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7
        }
    }
    
    for model, api_ver in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model}:generateContent?key={api_key}"
        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                if text:
                    return text
            # 400/429 등은 다음 모델로 fallback
        except requests.exceptions.Timeout:
            continue
        except Exception:
            continue
    
    return "⚠️ 모든 모델 호출 실패. API 키 및 네트워크를 확인해주세요."


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 세션 상태 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def init_session():
    defaults = {
        "current_page": "🏠 홈",
        "chat_histories": {f"phase_{i}": [] for i in range(6)},
        "sensory_data": None,
        "ai_prediction": None,
        "formula_data": None,
        "panel_config": None,
        "concept_results": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 사이드바
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

with st.sidebar:
    st.markdown("## 🔬 AI 소비자 조사")
    st.markdown("---")
    
    pages = [
        "🏠 홈",
        "👥 Phase 0: 패널 설계",
        "💡 Phase 1: 컨셉 수용도",
        "📊 Phase 2: 시장성 확대",
        "🧪 Phase 3: 배합비 최적화",
        "👅 Phase 4: 관능 검증",
        "🎯 Phase 5: AI 정합성",
    ]
    
    for page in pages:
        if st.button(page, use_container_width=True,
                     type="primary" if st.session_state.current_page == page else "secondary"):
            st.session_state.current_page = page
            st.rerun()
    
    st.markdown("---")
    
    # API 키 입력
    with st.expander("⚙️ API 설정", expanded=not bool(get_api_key())):
        api_input = st.text_input(
            "Google API Key",
            type="password",
            value=st.session_state.get("google_api_key", ""),
            key="api_key_input"
        )
        if api_input:
            st.session_state.google_api_key = api_input
            st.success("✅ API 키 설정됨")
    
    st.markdown("---")
    st.caption("Powered by Gemini 2.5 Pro")
    st.caption(f"© {datetime.now().year} BRK LAB")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공통 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def render_chat_ui(phase_key, system_prompt, placeholder_text, preset_prompts=None):
    """재사용 가능한 챗 UI 렌더링"""
    
    history = st.session_state.chat_histories[phase_key]
    
    # 프리셋 프롬프트 버튼
    if preset_prompts:
        st.markdown("**📋 예시 명령문:**")
        cols = st.columns(len(preset_prompts))
        for i, (label, prompt) in enumerate(preset_prompts):
            with cols[i]:
                if st.button(f"▶ {label}", key=f"preset_{phase_key}_{i}", use_container_width=True):
                    history.append({"role": "user", "content": prompt})
                    with st.spinner("🤖 AI 분석 중..."):
                        response = call_gemini(prompt, system_context=system_prompt)
                    history.append({"role": "assistant", "content": response})
                    st.rerun()
        st.markdown("---")
    
    # 채팅 이력 표시
    chat_container = st.container(height=500)
    with chat_container:
        if not history:
            st.info("💬 아래 입력창에 명령을 입력하거나, 위 예시 버튼을 클릭하세요.")
        for msg in history:
            role = msg["role"]
            icon = "👤" if role == "user" else "🤖"
            with st.chat_message(role, avatar=icon):
                st.markdown(msg["content"])
    
    # 입력창
    user_input = st.chat_input(placeholder_text, key=f"chat_{phase_key}")
    if user_input:
        history.append({"role": "user", "content": user_input})
        with st.spinner("🤖 AI가 분석 중입니다..."):
            response = call_gemini(user_input, system_context=system_prompt)
        history.append({"role": "assistant", "content": response})
        st.rerun()
    
    # 초기화 버튼
    col1, col2 = st.columns([8, 2])
    with col2:
        if st.button("🗑️ 대화 초기화", key=f"clear_{phase_key}"):
            st.session_state.chat_histories[phase_key] = []
            st.rerun()


def make_spider_chart(categories, values_dict, title="관능 평가 스파이더맵", 
                      golden_std=None):
    """스파이더맵(레이더 차트) 생성"""
    fig = go.Figure()
    
    colors = ["#1975BC", "#E85D24", "#2ECC71", "#9B59B6"]
    
    for i, (name, values) in enumerate(values_dict.items()):
        fig.add_trace(go.Scatterpolar(
            r=values + [values[0]],  # 닫기
            theta=categories + [categories[0]],
            fill='toself',
            fillcolor=f"rgba({int(colors[i%4][1:3],16)},{int(colors[i%4][3:5],16)},{int(colors[i%4][5:7],16)},0.15)",
            line=dict(color=colors[i%4], width=2.5),
            name=name,
            marker=dict(size=6)
        ))
    
    # 골든 스탠다드 기준선
    if golden_std is not None:
        std_values = [golden_std] * len(categories)
        fig.add_trace(go.Scatterpolar(
            r=std_values + [std_values[0]],
            theta=categories + [categories[0]],
            fill=None,
            line=dict(color="#FF4444", width=1.5, dash="dash"),
            name=f"골든 스탠다드 ({golden_std}점)",
            marker=dict(size=0)
        ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 7], tickvals=[1,2,3,4,5,6,7]),
            angularaxis=dict(tickfont=dict(size=13))
        ),
        showlegend=True,
        title=dict(text=title, font=dict(size=16)),
        height=500,
        margin=dict(t=60, b=40)
    )
    return fig


def make_concordance_chart(categories, ai_pred, actual, product_name):
    """AI 예측 vs 실측 비교 차트"""
    fig = go.Figure()
    
    x = np.arange(len(categories))
    
    fig.add_trace(go.Bar(
        x=categories, y=ai_pred,
        name=f"AI 예측",
        marker_color="#1975BC",
        opacity=0.85,
        text=[f"{v:.1f}" for v in ai_pred],
        textposition="outside"
    ))
    fig.add_trace(go.Bar(
        x=categories, y=actual,
        name=f"실제 관능",
        marker_color="#E85D24",
        opacity=0.85,
        text=[f"{v:.1f}" for v in actual],
        textposition="outside"
    ))
    
    fig.update_layout(
        barmode="group",
        title=f"{product_name} — AI 예측 vs 실제 소비자 관능 비교",
        yaxis=dict(range=[0, 7.5], title="점수 (7점 척도)"),
        xaxis=dict(title="관능 속성"),
        height=420,
        margin=dict(t=50, b=40)
    )
    return fig


def make_error_heatmap(categories, products, errors):
    """오차 히트맵"""
    fig = go.Figure(data=go.Heatmap(
        z=errors,
        x=categories,
        y=products,
        colorscale=[[0, "#2ECC71"], [0.5, "#F1C40F"], [1, "#E74C3C"]],
        text=[[f"{v:+.2f}" for v in row] for row in errors],
        texttemplate="%{text}",
        textfont=dict(size=14),
        zmin=-0.5, zmax=0.5,
        colorbar=dict(title="오차")
    ))
    fig.update_layout(
        title="속성별 AI 예측 오차 히트맵",
        height=300,
        margin=dict(t=50, b=40)
    )
    return fig


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 페이지: 홈
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def page_home():
    st.markdown("""
    <div class="main-header">
        <h1>🔬 AI 가상 소비자 조사 플랫폼</h1>
        <p>6-Phase 신제품 소비자 검증 프로세스 │ Gemini AI 연동 │ 실시간 분석</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 요약 통계
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<div class="stat-card"><h2>6</h2><p>Phase 프로세스</p></div>', 
                    unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="stat-card"><h2>800+</h2><p>가상 패널 시뮬레이션</p></div>', 
                    unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="stat-card"><h2>93%</h2><p>AI 정합도 목표</p></div>', 
                    unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="stat-card"><h2>5</h2><p>관능 평가 속성</p></div>', 
                    unsafe_allow_html=True)
    
    st.markdown("### 📋 프로세스 전체 흐름")
    
    phases = [
        ("Phase 0", "👥 패널 설계", "스크리닝 조건 설정, 쿼터 할당, 층화 추출"),
        ("Phase 1", "💡 컨셉 수용도 (N=100)", "다중 컨셉 평가, T2B 분석, 혁신성 점수"),
        ("Phase 2", "📊 시장성 확대 (N=500)", "페르소나 프로파일링, PSM 가격 분석"),
        ("Phase 3", "🧪 배합비 최적화", "데이터 드리븐 레시피, Brix/pH/산도 시뮬레이션"),
        ("Phase 4", "👅 관능 검증 (N=200)", "7점 척도 관능 평가, 스파이더맵 시각화"),
        ("Phase 5", "🎯 AI 정합성 검증", "AI 예측 vs 실제 소비자 비교 분석"),
    ]
    
    cols = st.columns(3)
    for i, (phase, title, desc) in enumerate(phases):
        with cols[i % 3]:
            st.markdown(f"""
            <div class="phase-card">
                <h4>{phase}: {title}</h4>
                <p>{desc}</p>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("""
    <div class="note-box">
    💡 <b>사용 방법:</b> 왼쪽 사이드바에서 Phase를 선택하고, 챗 UI에서 AI에게 명령을 입력하세요. 
    각 Phase의 예시 명령문 버튼을 클릭하면 즉시 시연할 수 있습니다.
    </div>
    """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 0: 패널 설계
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def page_phase0():
    st.markdown("""
    <div class="main-header">
        <h1>👥 Phase 0: AI 가상 소비자 패널 설계</h1>
        <p>스크리닝 조건 설정 → 쿼터 할당 → 층화 추출 → 패널 구성 완료</p>
    </div>
    """, unsafe_allow_html=True)
    
    system_prompt = """당신은 식품 소비자 조사 전문가 AI입니다. 
사용자가 패널 설계를 요청하면 다음을 반드시 포함하여 답변하세요:
1. 스크리닝 기준 (5단계)
2. 성별/연령 쿼터 할당표 (표 형식)
3. 층화 추출 기준 (음용 빈도별)
4. 패널 대표성 검증 지표
5. 스크리닝 통과율 추정

표는 마크다운 테이블로 작성하세요.
전문 용어는 사용하되 괄호 안에 간략한 설명을 붙여주세요.
답변은 한국어로 작성하세요."""
    
    presets = [
        ("100인 패널 설계", 
         "가상 소비자 패널 100명을 구성해줘.\n스크리닝 조건: 20~40대, 월 1회 이상 기능성 음료 구매자.\n성별·연령 쿼터를 할당하고, 음용 빈도별 층화 추출해줘."),
        ("500인 확대 패널",
         "기존 100인 패널 설계를 바탕으로 500명으로 확대해줘.\n신규 조건: 지역별 분포(수도권 60%, 비수도권 40%) 추가.\n20대 비중을 40%로 상향 조정해줘."),
        ("200인 관능 패널",
         "최종 관능 평가용 200인 패널을 설계해줘.\n훈련 패널 30명과 소비자 패널 170명으로 이원화.\n훈련 패널은 관능 훈련 이수자만, 소비자 패널은 일반 소비자 기준 적용."),
    ]
    
    render_chat_ui("phase_0", system_prompt, 
                   "패널 설계 명령을 입력하세요...", presets)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 1: 컨셉 수용도
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def page_phase1():
    st.markdown("""
    <div class="main-header">
        <h1>💡 Phase 1: 컨셉 수용도 조사 (N=100)</h1>
        <p>다중 컨셉 제시 → 구매의향 T2B 분석 → 혁신성 평가 → 최종 후보 선정</p>
    </div>
    """, unsafe_allow_html=True)
    
    system_prompt = """당신은 식품 신제품 컨셉 평가 전문가 AI입니다.
사용자가 컨셉 평가를 요청하면 다음을 반드시 포함하여 답변하세요:
1. 각 컨셉별 구매 의향 T2B(Top 2 Box: 7점 척도에서 6+7점 비율) 분석
2. 혁신성 점수 (7점 만점)
3. 타겟 적합도 분석
4. 경쟁 강도 평가
5. R&D 과제 도출
6. 최종 채택/탈락 판정

결과는 마크다운 테이블로 비교표를 만들어주세요.
통계적 유의성(p-value)도 표기해주세요.
답변은 한국어로 작성하세요."""
    
    presets = [
        ("3종 컨셉 평가",
         "100인 패널에게 3종 컨셉을 제시해줘.\n① 포커스 샷 (L-테아닌 집중력 음료)\n② 포레스트 브레스 (유칼립투스 리프레시 음료)\n③ 블룸 콤부 (꽃 발효 콤부차)\n구매 의향(T2B)과 혁신성을 7점 척도로 평가해줘."),
        ("2종 심화 분석",
         "포커스 샷과 포레스트 브레스 2종에 대해 심화 분석해줘.\n각 컨셉의 강점/약점/기회/위협(SWOT)과\n예상 타겟 시장 규모를 분석해줘."),
    ]
    
    render_chat_ui("phase_1", system_prompt,
                   "컨셉 평가 명령을 입력하세요...", presets)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 2: 시장성 확대
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def page_phase2():
    st.markdown("""
    <div class="main-header">
        <h1>📊 Phase 2: 시장성 확대 조사 (N=500)</h1>
        <p>대규모 수용도 검증 → 페르소나 프로파일링 → PSM 가격 분석</p>
    </div>
    """, unsafe_allow_html=True)
    
    system_prompt = """당신은 식품 시장 분석 전문가 AI입니다.
사용자가 시장성 분석을 요청하면 다음을 포함하여 답변하세요:
1. 타겟 페르소나 프로필 (인구통계, 라이프스타일, 핵심 니즈)
2. 구매 의향 T2B 재검증 결과
3. PSM(Price Sensitivity Meter) 분석: OPP(최적가격), PME(너무 비싼 가격), PMC(너무 싼 가격)
4. 채널 선호도 분석
5. 재구매 의향률
6. R&D 과제 구체화

결과는 마크다운 테이블로 정리해주세요.
답변은 한국어로 작성하세요."""
    
    presets = [
        ("500인 시장성 조사",
         "패널을 500명으로 확대해줘.\n선정된 2종(포커스 샷, 포레스트 브레스)에 대해:\n1) 타겟 페르소나 프로파일링\n2) PSM 가격 민감도 분석으로 최적 가격(OPP) 산출\n3) 구매 의향 T2B 재검증해줘."),
        ("채널 전략 분석",
         "포커스 샷과 포레스트 브레스의 유통 채널별 적합도를 분석해줘.\nCVS, 대형마트, 온라인(마켓컬리/쿠팡), 팝업스토어 4개 채널 비교."),
    ]
    
    render_chat_ui("phase_2", system_prompt,
                   "시장성 분석 명령을 입력하세요...", presets)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 3: 배합비 최적화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def page_phase3():
    st.markdown("""
    <div class="main-header">
        <h1>🧪 Phase 3: AI 기반 배합비 최적화</h1>
        <p>소비자 피드백 기반 → 데이터 드리븐 레시피 → Brix/pH/산도 시뮬레이션</p>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["💬 AI 배합비 도출", "🔧 배합비 시뮬레이터"])
    
    with tab1:
        system_prompt = """당신은 음료 R&D 배합 전문가 AI입니다.
식품공전 과·채주스 규격을 준수하는 배합비를 설계합니다.

배합비 출력 양식:
| No | 원료명 | 원료구분 | 사용량(%) | 누적(%) | 단가(원/kg) | 원가기여(원) | Brix기여 | pH기여 | 산도기여 |

반드시 포함할 사항:
1. 식품공전 규격 준수 여부
2. 목표 Brix, pH, 산도 대비 달성도
3. 원가 합계
4. 핵심 성분의 관능 기여 설명 (쓴맛 마스킹, 향 블렌딩 등)

답변은 한국어로 작성하세요."""
        
        presets = [
            ("포커스 샷 배합비",
             "포커스 샷(L-테아닌 집중력 음료)의 배합비를 도출해줘.\n핵심 과제: L-테아닌 쓴맛 마스킹.\n목표: Brix 10.5 / pH 3.4 / 산도 0.45%\n식품공전 과·채주스 규격 준수."),
            ("포레스트 브레스 배합비",
             "포레스트 브레스(유칼립투스 리프레시 음료)의 배합비를 도출해줘.\n핵심 과제: 유칼립투스의 인공적 느낌 제거.\n목표: Brix 8.0 / pH 3.8 / 산도 0.35%\n식품공전 과·채주스 규격 준수."),
        ]
        
        render_chat_ui("phase_3", system_prompt,
                       "배합비 최적화 명령을 입력하세요...", presets)
    
    with tab2:
        st.markdown("### 🔧 실시간 배합비 시뮬레이터")
        st.markdown("원료별 사용량을 조절하면 Brix, pH, 산도가 실시간으로 변합니다.")
        
        col1, col2 = st.columns([3, 2])
        
        with col1:
            st.markdown("#### 원료 투입량 조절")
            
            fruit_conc = st.slider("과즙농축액 (%)", 0.0, 30.0, 14.0, 0.5, key="sim_fruit")
            water = st.slider("정제수 (%)", 50.0, 95.0, 78.5, 0.5, key="sim_water")
            functional = st.slider("기능성원료 (%)", 0.0, 5.0, 0.67, 0.01, key="sim_func")
            sweetener_sugar = st.slider("당류 (%)", 0.0, 10.0, 3.3, 0.1, key="sim_sugar")
            acid = st.slider("산미료 (%)", 0.0, 1.0, 0.15, 0.01, key="sim_acid")
            flavor = st.slider("향료 (%)", 0.0, 0.5, 0.05, 0.01, key="sim_flavor")
            
            total = fruit_conc + water + functional + sweetener_sugar + acid + flavor
            remaining = 100.0 - total
            
            if remaining < 0:
                st.error(f"⚠️ 합계 초과: {total:.1f}% (잔여: {remaining:.1f}%)")
            else:
                st.info(f"잔여량(기타/조정): {remaining:.1f}%")
        
        with col2:
            # 계산
            brix_est = fruit_conc * 0.65 + sweetener_sugar * 0.9 + functional * 0.05
            ph_est = 7.0 - fruit_conc * 0.2 - acid * 8.0 + sweetener_sugar * 0.02
            ph_est = max(2.5, min(5.0, ph_est))
            acidity_est = fruit_conc * 0.02 + acid * 0.6
            cost_est = (fruit_conc * 35 + water * 0 + functional * 300 + 
                       sweetener_sugar * 32 + acid * 2.7 + flavor * 7.5)
            
            st.markdown("#### 📊 예측 품질 지표")
            
            m1, m2 = st.columns(2)
            m1.metric("Brix", f"{brix_est:.1f}", 
                     delta=f"{brix_est - 10.5:+.1f}" if abs(brix_est-10.5) > 0.3 else "목표 범위")
            m2.metric("pH", f"{ph_est:.2f}",
                     delta=f"{ph_est - 3.4:+.2f}" if abs(ph_est-3.4) > 0.2 else "목표 범위")
            
            m3, m4 = st.columns(2)
            m3.metric("산도 (%)", f"{acidity_est:.3f}",
                     delta=f"{acidity_est - 0.45:+.3f}" if abs(acidity_est-0.45) > 0.05 else "목표 범위")
            m4.metric("추정 원가", f"{cost_est:.0f}원/병")
            
            # 게이지 차트
            fig_gauge = go.Figure()
            for i, (name, val, target, range_max) in enumerate([
                ("Brix", brix_est, 10.5, 20),
                ("pH", ph_est, 3.4, 5),
                ("산도", acidity_est, 0.45, 1.0),
            ]):
                fig_gauge.add_trace(go.Indicator(
                    mode="gauge+number+delta",
                    value=val,
                    delta={"reference": target},
                    title={"text": name, "font": {"size": 13}},
                    gauge={
                        "axis": {"range": [0, range_max]},
                        "bar": {"color": "#1975BC"},
                        "threshold": {
                            "line": {"color": "red", "width": 3},
                            "thickness": 0.8,
                            "value": target
                        }
                    },
                    domain={"row": 0, "column": i}
                ))
            fig_gauge.update_layout(
                grid={"rows": 1, "columns": 3},
                height=200,
                margin=dict(t=30, b=10, l=30, r=30)
            )
            st.plotly_chart(fig_gauge, use_container_width=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 4: 관능 검증
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def page_phase4():
    st.markdown("""
    <div class="main-header">
        <h1>👅 Phase 4: 최종 관능 정밀 검증 (N=200)</h1>
        <p>CLT 블라인드 테스트 → 7점 척도 평가 → 스파이더맵 시각화</p>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["📝 관능 데이터 입력", "🕸️ 스파이더맵", "💬 AI 분석"])
    
    categories = ["단맛", "신맛", "쓴맛(역)", "향", "색상", "전반적 기호도"]
    
    with tab1:
        st.markdown("### 📝 관능 평가 데이터 입력 (7점 척도)")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("#### 🔵 포커스 샷")
            fs_values = []
            for cat in categories:
                val = st.slider(f"{cat}", 1.0, 7.0, 5.5, 0.1, 
                               key=f"fs_{cat}")
                fs_values.append(val)
        
        with col2:
            st.markdown("#### 🟠 포레스트 브레스")
            fb_values = []
            for cat in categories:
                val = st.slider(f"{cat}", 1.0, 7.0, 5.5, 0.1, 
                               key=f"fb_{cat}")
                fb_values.append(val)
        
        with col3:
            st.markdown("#### ⚙️ 설정")
            golden_std = st.slider("골든 스탠다드 기준선", 3.0, 7.0, 5.5, 0.1,
                                   key="golden_std")
            
            if st.button("💾 데이터 저장", type="primary", use_container_width=True):
                st.session_state.sensory_data = {
                    "categories": categories,
                    "포커스 샷": fs_values,
                    "포레스트 브레스": fb_values,
                    "golden_std": golden_std
                }
                st.success("✅ 관능 데이터 저장 완료!")
            
            # 요약 테이블
            if st.session_state.sensory_data:
                st.markdown("---")
                st.markdown("**저장된 데이터:**")
                df = pd.DataFrame({
                    "속성": categories,
                    "포커스 샷": st.session_state.sensory_data["포커스 샷"],
                    "포레스트 브레스": st.session_state.sensory_data["포레스트 브레스"],
                    "골든 스탠다드": [golden_std] * len(categories),
                })
                df["포커스 샷 판정"] = df["포커스 샷"].apply(
                    lambda x: "✅ PASS" if x >= golden_std else "❌ FAIL")
                df["포레스트 판정"] = df["포레스트 브레스"].apply(
                    lambda x: "✅ PASS" if x >= golden_std else "❌ FAIL")
                st.dataframe(df, use_container_width=True, hide_index=True)
    
    with tab2:
        st.markdown("### 🕸️ 관능 평가 스파이더맵")
        
        if st.session_state.sensory_data:
            data = st.session_state.sensory_data
            
            fig = make_spider_chart(
                data["categories"],
                {
                    "포커스 샷": data["포커스 샷"],
                    "포레스트 브레스": data["포레스트 브레스"]
                },
                title="최종 관능 평가 결과 (N=200, 7점 척도)",
                golden_std=data["golden_std"]
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # 통과 여부 요약
            col1, col2 = st.columns(2)
            with col1:
                all_pass_fs = all(v >= data["golden_std"] for v in data["포커스 샷"])
                st.markdown(f"**포커스 샷:** {'✅ 전체 PASS' if all_pass_fs else '⚠️ 일부 미달'}")
                avg_fs = np.mean(data["포커스 샷"])
                st.metric("평균 점수", f"{avg_fs:.2f}")
            with col2:
                all_pass_fb = all(v >= data["golden_std"] for v in data["포레스트 브레스"])
                st.markdown(f"**포레스트 브레스:** {'✅ 전체 PASS' if all_pass_fb else '⚠️ 일부 미달'}")
                avg_fb = np.mean(data["포레스트 브레스"])
                st.metric("평균 점수", f"{avg_fb:.2f}")
        else:
            st.info("📝 먼저 '관능 데이터 입력' 탭에서 데이터를 저장해주세요.")
    
    with tab3:
        system_prompt = """당신은 관능 평가 분석 전문가 AI입니다.
관능 데이터를 분석할 때 다음을 포함하세요:
1. 각 속성별 점수 해석
2. 골든 스탠다드 대비 달성도
3. 제품 간 유의미한 차이 분석
4. JAR(Just About Right) 스케일 해석
5. 개선 권장 사항

전문 용어에는 간략한 괄호 설명을 붙여주세요.
답변은 한국어로 작성하세요."""
        
        # 저장된 데이터가 있으면 자동 프롬프트 생성
        auto_presets = []
        if st.session_state.sensory_data:
            data = st.session_state.sensory_data
            data_summary = "\n".join([
                f"  · {cat}: 포커스 샷 {data['포커스 샷'][i]:.1f} / 포레스트 브레스 {data['포레스트 브레스'][i]:.1f}"
                for i, cat in enumerate(data["categories"])
            ])
            auto_prompt = f"다음 관능 평가 데이터를 분석해줘.\n골든 스탠다드: {data['golden_std']}점\n\n{data_summary}"
            auto_presets.append(("저장된 데이터 분석", auto_prompt))
        
        auto_presets.append(("관능 평가 설계 자문",
            "200인 소비자 패널로 최종 관능 평가를 설계해줘.\n평가 방법: CLT 블라인드 테스트, 7점 척도.\n훈련 패널 30명으로 레퍼런스 캘리브레이션 후 실시."))
        
        render_chat_ui("phase_4", system_prompt,
                       "관능 분석 명령을 입력하세요...", auto_presets)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Phase 5: AI 정합성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def page_phase5():
    st.markdown("""
    <div class="main-header">
        <h1>🎯 Phase 5: AI 예측 vs 실제 소비자 정합성 검증</h1>
        <p>AI 시뮬레이션 예측값 vs 실측값 비교 → 오차 분석 → 모델 신뢰도 판정</p>
    </div>
    """, unsafe_allow_html=True)
    
    tab1, tab2, tab3 = st.tabs(["📊 정합성 차트", "📈 상세 분석", "💬 AI 해석"])
    
    categories = ["단맛", "신맛", "쓴맛(역)", "향", "색상", "전반적 기호도"]
    
    with tab1:
        st.markdown("### 📊 AI 예측 vs 실제 관능 비교")
        
        col_input, col_chart = st.columns([1, 2])
        
        with col_input:
            st.markdown("#### AI 예측값 입력")
            
            st.markdown("**포커스 샷 - AI 예측**")
            ai_fs = []
            for cat in categories:
                val = st.number_input(f"{cat}", 1.0, 7.0, 5.5, 0.1,
                                     key=f"ai_fs_{cat}")
                ai_fs.append(val)
            
            st.markdown("**포레스트 브레스 - AI 예측**")
            ai_fb = []
            for cat in categories:
                val = st.number_input(f"{cat}", 1.0, 7.0, 5.5, 0.1,
                                     key=f"ai_fb_{cat}")
                ai_fb.append(val)
            
            if st.button("📊 정합성 분석 실행", type="primary", use_container_width=True):
                st.session_state.ai_prediction = {
                    "포커스 샷": ai_fs,
                    "포레스트 브레스": ai_fb
                }
                st.success("✅ AI 예측값 저장!")
        
        with col_chart:
            sensory = st.session_state.sensory_data
            ai_pred = st.session_state.ai_prediction
            
            if sensory and ai_pred:
                # 포커스 샷 비교
                fig1 = make_concordance_chart(
                    categories, ai_pred["포커스 샷"], sensory["포커스 샷"],
                    "포커스 샷"
                )
                st.plotly_chart(fig1, use_container_width=True)
                
                # 포레스트 브레스 비교
                fig2 = make_concordance_chart(
                    categories, ai_pred["포레스트 브레스"], sensory["포레스트 브레스"],
                    "포레스트 브레스"
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("📝 Phase 4에서 관능 데이터를 저장하고, AI 예측값을 입력한 후 '정합성 분석 실행'을 클릭하세요.")
    
    with tab2:
        st.markdown("### 📈 정합성 상세 분석")
        
        sensory = st.session_state.sensory_data
        ai_pred = st.session_state.ai_prediction
        
        if sensory and ai_pred:
            # 오차 계산
            errors_fs = [a - r for a, r in zip(ai_pred["포커스 샷"], sensory["포커스 샷"])]
            errors_fb = [a - r for a, r in zip(ai_pred["포레스트 브레스"], sensory["포레스트 브레스"])]
            
            # 정합도 계산
            concordance_fs = [100 - abs(e)/7*100 for e in errors_fs]
            concordance_fb = [100 - abs(e)/7*100 for e in errors_fb]
            
            avg_conc = np.mean(concordance_fs + concordance_fb)
            
            # 상관계수 계산
            all_ai = ai_pred["포커스 샷"] + ai_pred["포레스트 브레스"]
            all_actual = sensory["포커스 샷"] + sensory["포레스트 브레스"]
            correlation = np.corrcoef(all_ai, all_actual)[0, 1]
            
            # 요약 메트릭
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("전체 정합도", f"{avg_conc:.1f}%")
            col2.metric("상관계수 (r)", f"{correlation:.3f}")
            col3.metric("평균 오차", f"±{np.mean(np.abs(errors_fs + errors_fb)):.2f}점")
            col4.metric("최대 오차", f"{max(max(np.abs(errors_fs)), max(np.abs(errors_fb))):.2f}점")
            
            # 오차 히트맵
            fig_hm = make_error_heatmap(
                categories,
                ["포커스 샷", "포레스트 브레스"],
                [errors_fs, errors_fb]
            )
            st.plotly_chart(fig_hm, use_container_width=True)
            
            # 상세 테이블
            df_detail = pd.DataFrame({
                "속성": categories,
                "포커스샷 AI": [f"{v:.1f}" for v in ai_pred["포커스 샷"]],
                "포커스샷 실측": [f"{v:.1f}" for v in sensory["포커스 샷"]],
                "오차": [f"{e:+.2f}" for e in errors_fs],
                "정합도": [f"{c:.1f}%" for c in concordance_fs],
                "포레스트 AI": [f"{v:.1f}" for v in ai_pred["포레스트 브레스"]],
                "포레스트 실측": [f"{v:.1f}" for v in sensory["포레스트 브레스"]],
                "오차 ": [f"{e:+.2f}" for e in errors_fb],
                "정합도 ": [f"{c:.1f}%" for c in concordance_fb],
            })
            st.dataframe(df_detail, use_container_width=True, hide_index=True)
            
            # 스파이더맵 오버레이
            st.markdown("### 🕸️ AI 예측 vs 실측 스파이더맵 오버레이")
            fig_spider = make_spider_chart(
                categories,
                {
                    "포커스 샷 (AI)": ai_pred["포커스 샷"],
                    "포커스 샷 (실측)": sensory["포커스 샷"],
                    "포레스트 (AI)": ai_pred["포레스트 브레스"],
                    "포레스트 (실측)": sensory["포레스트 브레스"],
                },
                title="AI 예측 vs 실제 관능 오버레이 비교"
            )
            st.plotly_chart(fig_spider, use_container_width=True)
            
        else:
            st.info("📝 Phase 4에서 관능 데이터 저장 후, '정합성 차트' 탭에서 AI 예측값을 입력해주세요.")
    
    with tab3:
        system_prompt = """당신은 AI 예측 모델 검증 전문가입니다.
AI 가상 소비자 예측값과 실제 관능 평가 결과를 비교 분석할 때:
1. 전체 정합도(%) 및 상관계수(r) 해석
2. 속성별 오차 원인 분석
3. AI 모델의 강점/약점 진단
4. 모델 개선 방향 제안
5. 비즈니스 의사결정 시사점

통계 용어에 괄호 설명을 붙여주세요.
답변은 한국어로 작성하세요."""
        
        auto_presets = []
        if st.session_state.sensory_data and st.session_state.ai_prediction:
            sensory = st.session_state.sensory_data
            ai_pred = st.session_state.ai_prediction
            
            errors_fs = [a - r for a, r in zip(ai_pred["포커스 샷"], sensory["포커스 샷"])]
            errors_fb = [a - r for a, r in zip(ai_pred["포레스트 브레스"], sensory["포레스트 브레스"])]
            concordance = [100 - abs(e)/7*100 for e in errors_fs + errors_fb]
            
            data_str = "정합성 데이터:\n"
            for i, cat in enumerate(categories):
                data_str += f"  · {cat}: 포커스 샷 AI {ai_pred['포커스 샷'][i]:.1f} vs 실측 {sensory['포커스 샷'][i]:.1f} (오차 {errors_fs[i]:+.2f})\n"
                data_str += f"         포레스트 AI {ai_pred['포레스트 브레스'][i]:.1f} vs 실측 {sensory['포레스트 브레스'][i]:.1f} (오차 {errors_fb[i]:+.2f})\n"
            data_str += f"\n전체 정합도: {np.mean(concordance):.1f}%"
            
            auto_presets.append(("저장된 데이터 분석", 
                f"다음 AI 정합성 데이터를 분석해줘.\n\n{data_str}"))
        
        auto_presets.append(("정합성 검증 방법론 자문",
            "AI 가상 소비자 예측의 신뢰성을 검증하는 방법론을 설명해줘.\n상관계수, RMSE, MAE, 블랜드-알트만 분석 등을 포함해서."))
        
        render_chat_ui("phase_5", system_prompt,
                       "정합성 분석 명령을 입력하세요...", auto_presets)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 페이지 라우팅
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

page_map = {
    "🏠 홈": page_home,
    "👥 Phase 0: 패널 설계": page_phase0,
    "💡 Phase 1: 컨셉 수용도": page_phase1,
    "📊 Phase 2: 시장성 확대": page_phase2,
    "🧪 Phase 3: 배합비 최적화": page_phase3,
    "👅 Phase 4: 관능 검증": page_phase4,
    "🎯 Phase 5: AI 정합성": page_phase5,
}

current = st.session_state.current_page
if current in page_map:
    page_map[current]()
else:
    page_home()
