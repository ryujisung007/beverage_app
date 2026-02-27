"""
🧪 음료개발 AI 플랫폼 v4
- 배합 시뮬레이터 | 시장분석 대시보드 | 교육용 실습 | 신제품 기획서 자동생성
- 데이터 소스: 음료개발_데이터베이스_v4-1.xlsx
"""
import streamlit as st
import pandas as pd
import numpy as np
import json, io, os, math
from datetime import datetime

# ============================================================
# 0. 페이지 설정 & 데이터 로딩
# ============================================================
st.set_page_config(
    page_title="🧪 음료개발 AI 플랫폼",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_PATH = os.path.join(os.path.dirname(__file__), "음료개발_데이터베이스_v4-1.xlsx")

@st.cache_data
def load_all_data(path):
    sheets = {}
    xls = pd.ExcelFile(path)
    for name in xls.sheet_names:
        sheets[name] = pd.read_excel(xls, sheet_name=name)
    return sheets

try:
    DATA = load_all_data(DB_PATH)
except FileNotFoundError:
    st.error("❌ 데이터베이스 파일을 찾을 수 없습니다. `음료개발_데이터베이스_v4-1.xlsx` 파일을 앱과 같은 폴더에 넣어주세요.")
    st.stop()

df_type = DATA['음료유형분류']
df_product = DATA['시장제품DB']
df_ingredient = DATA['원료DB']
df_spec = DATA['음료규격기준']
df_process = DATA['표준제조공정_HACCP']
df_guide = DATA['가이드배합비DB']

# 원료DB 수치 전처리
for col in ['Brix(°)', 'pH', '산도(%)', '감미도(설탕대비)', '예상단가(원/kg)',
            '1%사용시 Brix기여(°)', '1%사용시 산도기여(%)', '1%사용시 감미기여']:
    df_ingredient[col] = pd.to_numeric(df_ingredient[col], errors='coerce').fillna(0)

# pH영향 컬럼명 자동 감지
ph_impact_col = [c for c in df_ingredient.columns if 'pH영향' in str(c) or 'ΔpH' in str(c)]
PH_COL = ph_impact_col[0] if ph_impact_col else '1%사용시 pH영향'
df_ingredient[PH_COL] = pd.to_numeric(df_ingredient[PH_COL], errors='coerce').fillna(0)

# ============================================================
# 사이드바 네비게이션
# ============================================================
st.sidebar.image("https://img.icons8.com/fluency/96/test-tube.png", width=60)
st.sidebar.title("음료개발 AI 플랫폼")
st.sidebar.markdown("---")

PAGES = {
    "🧪 배합 시뮬레이터": "simulator",
    "📊 시장제품 분석": "market",
    "🎓 교육용 실습도구": "education",
    "📋 신제품 기획서": "planner"
}
page = st.sidebar.radio("메뉴 선택", list(PAGES.keys()))

st.sidebar.markdown("---")
st.sidebar.caption(f"DB: 원료 {len(df_ingredient)}종 | 제품 {len(df_product)}종 | 가이드배합 {len(df_guide)}건")
st.sidebar.caption(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d')}")


# ============================================================
# 공통 유틸리티
# ============================================================
def get_spec_range(beverage_type):
    """음료유형별 규격 범위 반환"""
    row = df_spec[df_spec['음료유형'].str.contains(beverage_type, na=False)]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        'Brix_min': r.get('Brix_min', 0), 'Brix_max': r.get('Brix_max', 20),
        'pH_min': r.get('pH_min', 2.0), 'pH_max': r.get('pH_max', 7.0),
        '산도_min': r.get('산도_min', 0), '산도_max': r.get('산도_max', 2.0),
    }

def calc_formulation(ingredients_list, base_ph=3.5):
    """
    배합 계산 엔진
    ingredients_list: [{'원료명': str, '배합비(%)': float}, ...]
    Returns: dict with 총Brix, pH, 산도, 감미도, 원가 등
    """
    total_brix = 0.0
    total_acidity = 0.0
    total_sweetness = 0.0
    total_delta_ph = 0.0
    total_cost = 0.0
    total_pct = 0.0
    details = []

    for item in ingredients_list:
        name = item['원료명']
        pct = item['배합비(%)']
        if pct <= 0:
            continue

        row = df_ingredient[df_ingredient['원료명'] == name]
        if row.empty:
            continue
        r = row.iloc[0]

        brix_contrib = r['1%사용시 Brix기여(°)'] * pct
        acid_contrib = r['1%사용시 산도기여(%)'] * pct
        sweet_contrib = r['1%사용시 감미기여'] * pct
        delta_ph = r[PH_COL] * pct
        cost_contrib = r['예상단가(원/kg)'] * pct / 100  # 원/kg 제품

        total_brix += brix_contrib
        total_acidity += acid_contrib
        total_sweetness += sweet_contrib
        total_delta_ph += delta_ph
        total_cost += cost_contrib
        total_pct += pct

        details.append({
            '원료명': name,
            '배합비(%)': pct,
            '분류': r['원료대분류'],
            'Brix기여': round(brix_contrib, 2),
            '산도기여': round(acid_contrib, 4),
            '감미기여': round(sweet_contrib, 4),
            'ΔpH기여': round(delta_ph, 3),
            '원가기여(원/kg)': round(cost_contrib, 1),
        })

    est_ph = base_ph + total_delta_ph
    water_pct = max(0, 100 - total_pct)

    return {
        '총Brix(°)': round(total_brix, 2),
        '예상pH': round(est_ph, 2),
        '총산도(%)': round(total_acidity, 4),
        '총감미도': round(total_sweetness, 4),
        '당산비': round(total_brix / total_acidity, 1) if total_acidity > 0 else 0,
        '원재료비(원/kg)': round(total_cost, 1),
        '원재료비(원/500ml)': round(total_cost * 0.5, 1),
        '원재료비(원/1L)': round(total_cost, 1),
        '정제수(%)': round(water_pct, 2),
        '원료합계(%)': round(total_pct, 2),
        'details': details
    }

def check_spec_compliance(result, spec):
    """규격 적합 판정"""
    if spec is None:
        return []
    issues = []
    brix = result['총Brix(°)']
    if brix < spec['Brix_min']:
        issues.append(f"⚠️ Brix {brix}° < 최소 {spec['Brix_min']}°")
    if brix > spec['Brix_max']:
        issues.append(f"⚠️ Brix {brix}° > 최대 {spec['Brix_max']}°")
    ph = result['예상pH']
    if ph < spec['pH_min']:
        issues.append(f"⚠️ pH {ph} < 최소 {spec['pH_min']}")
    if ph > spec['pH_max']:
        issues.append(f"⚠️ pH {ph} > 최대 {spec['pH_max']}")
    acid = result['총산도(%)']
    if spec['산도_min'] > 0 and acid < spec['산도_min']:
        issues.append(f"⚠️ 산도 {acid}% < 최소 {spec['산도_min']}%")
    if spec['산도_max'] > 0 and acid > spec['산도_max']:
        issues.append(f"⚠️ 산도 {acid}% > 최대 {spec['산도_max']}%")
    return issues


# ============================================================
# PAGE 1: 🧪 배합 시뮬레이터
# ============================================================
def page_simulator():
    st.title("🧪 배합 시뮬레이터")
    st.caption("원료를 선택하고 배합비를 입력하면 pH / Brix / 산도 / 감미도 / 원가를 자동 계산합니다")

    # --- 음료유형 & 가이드 배합비 ---
    col_type, col_flavor = st.columns(2)
    with col_type:
        bev_types = df_spec['음료유형'].dropna().tolist()
        selected_type = st.selectbox("음료유형 선택", bev_types)
    with col_flavor:
        # 가이드배합비에서 해당 유형의 맛 추출
        guide_keys = df_guide['키(유형_맛_슬롯)'].dropna().unique()
        flavors = sorted(set(
            k.split('_')[1] for k in guide_keys
            if selected_type.replace('(', '').replace(')', '') in k.split('_')[0]
        ))
        if not flavors:
            flavors = ['직접입력']
        selected_flavor = st.selectbox("맛(Flavor)", flavors)

    # 가이드 배합비 로딩
    guide_key_prefix = f"{selected_type.split('(')[0]}_{selected_flavor}_"
    guide_rows = df_guide[df_guide['키(유형_맛_슬롯)'].str.startswith(guide_key_prefix, na=False)]

    # 초기 배합 설정
    if 'formulation' not in st.session_state:
        st.session_state.formulation = []

    col_guide, col_manual = st.columns(2)
    with col_guide:
        if st.button("📥 AI추천 가이드배합비 불러오기", use_container_width=True):
            st.session_state.formulation = []
            for _, gr in guide_rows.iterrows():
                name = gr.get('AI추천_원료명')
                pct = gr.get('AI추천_배합비(%)')
                if pd.notna(name) and pd.notna(pct) and pct > 0:
                    st.session_state.formulation.append({'원료명': str(name), '배합비(%)': float(pct)})
    with col_manual:
        if st.button("🔄 초기화", use_container_width=True):
            st.session_state.formulation = []

    st.markdown("---")

    # --- 원료 입력 영역 ---
    st.subheader("📝 배합표 입력")

    ingredient_names = df_ingredient['원료명'].tolist()
    categories = df_ingredient['원료대분류'].unique().tolist()

    # 원료 추가
    col_add1, col_add2, col_add3, col_add4 = st.columns([2, 2, 1, 1])
    with col_add1:
        filter_cat = st.selectbox("분류 필터", ['전체'] + categories, key='filter_cat')
    with col_add2:
        if filter_cat == '전체':
            filtered_names = ingredient_names
        else:
            filtered_names = df_ingredient[df_ingredient['원료대분류'] == filter_cat]['원료명'].tolist()
        new_ingredient = st.selectbox("원료 선택", filtered_names, key='new_ing')
    with col_add3:
        new_pct = st.number_input("배합비(%)", min_value=0.0, max_value=100.0, value=1.0, step=0.5, key='new_pct')
    with col_add4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ 추가", use_container_width=True):
            st.session_state.formulation.append({'원료명': new_ingredient, '배합비(%)': new_pct})

    # 현재 배합표 표시 & 편집
    if st.session_state.formulation:
        st.markdown("#### 현재 배합표")

        edited_formulation = []
        cols_header = st.columns([0.5, 3, 1.5, 1.5, 1.5, 1])
        with cols_header[0]:
            st.markdown("**No**")
        with cols_header[1]:
            st.markdown("**원료명**")
        with cols_header[2]:
            st.markdown("**배합비(%)**")
        with cols_header[3]:
            st.markdown("**분류**")
        with cols_header[4]:
            st.markdown("**단가(원/kg)**")
        with cols_header[5]:
            st.markdown("**삭제**")

        for idx, item in enumerate(st.session_state.formulation):
            row_data = df_ingredient[df_ingredient['원료명'] == item['원료명']]
            cat = row_data.iloc[0]['원료대분류'] if not row_data.empty else '-'
            price = row_data.iloc[0]['예상단가(원/kg)'] if not row_data.empty else 0

            cols = st.columns([0.5, 3, 1.5, 1.5, 1.5, 1])
            with cols[0]:
                st.write(idx + 1)
            with cols[1]:
                st.write(item['원료명'])
            with cols[2]:
                new_val = st.number_input(
                    f"pct_{idx}", value=item['배합비(%)'],
                    min_value=0.0, max_value=100.0, step=0.1,
                    label_visibility="collapsed", key=f"pct_{idx}"
                )
                item['배합비(%)'] = new_val
            with cols[3]:
                st.write(cat)
            with cols[4]:
                st.write(f"{price:,.0f}")
            with cols[5]:
                if st.button("🗑️", key=f"del_{idx}"):
                    st.session_state.formulation.pop(idx)
                    st.rerun()

            edited_formulation.append(item)

        st.session_state.formulation = edited_formulation

        # --- 계산 결과 ---
        st.markdown("---")
        result = calc_formulation(st.session_state.formulation)
        spec = get_spec_range(selected_type)

        st.subheader("📊 배합 시뮬레이션 결과")

        # 메인 수치 카드
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("당도 (Brix°)", f"{result['총Brix(°)']}")
        m2.metric("예상 pH", f"{result['예상pH']}")
        m3.metric("산도 (%)", f"{result['총산도(%)']:.3f}")
        m4.metric("감미도", f"{result['총감미도']:.3f}")
        m5.metric("당산비", f"{result['당산비']}")
        m6.metric("원가 (원/kg)", f"{result['원재료비(원/kg)']:,.0f}")

        # 규격 판정
        if spec:
            issues = check_spec_compliance(result, spec)
            if not issues:
                st.success(f"✅ **{selected_type}** 규격 적합! (Brix {spec['Brix_min']}~{spec['Brix_max']}, pH {spec['pH_min']}~{spec['pH_max']})")
            else:
                st.warning("⚠️ 규격 부적합 항목:")
                for issue in issues:
                    st.write(issue)

        # 원료별 기여도 테이블
        st.markdown("#### 원료별 기여도 상세")
        detail_df = pd.DataFrame(result['details'])
        if not detail_df.empty:
            st.dataframe(
                detail_df.style.format({
                    '배합비(%)': '{:.2f}', 'Brix기여': '{:.2f}',
                    '산도기여': '{:.4f}', '감미기여': '{:.4f}',
                    'ΔpH기여': '{:.3f}', '원가기여(원/kg)': '{:.1f}'
                }),
                use_container_width=True
            )

        # 정제수 표시
        st.info(f"💧 정제수: **{result['정제수(%)']}%** (원료합계 {result['원료합계(%)']}%)")

        # 기여도 시각화 (bar chart)
        if not detail_df.empty:
            st.markdown("#### 📈 기여도 시각화")
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.bar_chart(detail_df.set_index('원료명')['Brix기여'], color='#FF6B6B')
                st.caption("Brix 기여도")
            with chart_col2:
                st.bar_chart(detail_df.set_index('원료명')['원가기여(원/kg)'], color='#4ECDC4')
                st.caption("원가 기여도 (원/kg)")

    else:
        st.info("👆 위에서 원료를 추가하거나 가이드배합비를 불러오세요")


# ============================================================
# PAGE 2: 📊 시장제품 분석 대시보드
# ============================================================
def page_market():
    st.title("📊 시장제품 분석 대시보드")
    st.caption(f"국내 시판 음료 {len(df_product)}개 제품 데이터 기반 분석")

    # --- 필터 ---
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        cats = ['전체'] + df_product['대분류'].dropna().unique().tolist()
        sel_cat = st.selectbox("대분류", cats)
    with col_f2:
        if sel_cat == '전체':
            sub_types = ['전체'] + df_product['세부유형'].dropna().unique().tolist()
        else:
            sub_types = ['전체'] + df_product[df_product['대분류'] == sel_cat]['세부유형'].dropna().unique().tolist()
        sel_sub = st.selectbox("세부유형", sub_types)
    with col_f3:
        makers = ['전체'] + sorted(df_product['제조사'].dropna().unique().tolist())
        sel_maker = st.selectbox("제조사", makers)

    filtered = df_product.copy()
    if sel_cat != '전체':
        filtered = filtered[filtered['대분류'] == sel_cat]
    if sel_sub != '전체':
        filtered = filtered[filtered['세부유형'] == sel_sub]
    if sel_maker != '전체':
        filtered = filtered[filtered['제조사'] == sel_maker]

    st.markdown("---")

    # --- 요약 KPI ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("제품 수", f"{len(filtered)}개")
    k2.metric("제조사 수", f"{filtered['제조사'].nunique()}개")
    avg_price = filtered['가격(원)'].dropna().mean()
    k3.metric("평균 가격", f"{avg_price:,.0f}원" if not np.isnan(avg_price) else "-")
    avg_vol = filtered['용량(ml)'].dropna().mean()
    k4.metric("평균 용량", f"{avg_vol:,.0f}ml" if not np.isnan(avg_vol) else "-")

    # --- 탭 분석 ---
    tab1, tab2, tab3, tab4 = st.tabs(["🏢 제조사별", "📦 유형별", "💰 가격분석", "🔬 원재료 패턴"])

    with tab1:
        maker_counts = filtered['제조사'].value_counts().head(15)
        st.bar_chart(maker_counts)
        st.caption("제조사별 제품 수 (상위 15)")

    with tab2:
        type_counts = filtered['세부유형'].value_counts()
        st.bar_chart(type_counts)

        # 유형별 시장규모 (음료유형분류 시트 연동)
        st.markdown("#### 유형별 예상 시장규모")
        market_data = df_type[['세부유형(식품유형)', '국내 예상 연매출(억원)']].dropna()
        market_data.columns = ['유형', '연매출(억원)']
        market_data = market_data.sort_values('연매출(억원)', ascending=False)
        st.bar_chart(market_data.set_index('유형'))

    with tab3:
        # 가격 분포
        price_data = filtered[['세부유형', '가격(원)', '용량(ml)']].dropna()
        if not price_data.empty:
            price_data['ml당가격'] = price_data['가격(원)'] / price_data['용량(ml)']

            st.markdown("#### 유형별 평균 가격")
            avg_by_type = price_data.groupby('세부유형')['가격(원)'].mean().sort_values(ascending=False)
            st.bar_chart(avg_by_type)

            st.markdown("#### ml당 가격 분포")
            ml_by_type = price_data.groupby('세부유형')['ml당가격'].mean().sort_values(ascending=False)
            st.bar_chart(ml_by_type)

            # 용기별 분포
            st.markdown("#### 포장용기별 제품수")
            pkg_counts = filtered['포장용기'].value_counts()
            st.bar_chart(pkg_counts)

    with tab4:
        st.markdown("#### 배합순위 1위 원료 빈도")
        raw1 = filtered['배합순위1(원재료/배합비%/원산지)'].dropna()
        # 원료명만 추출 (/ 앞 부분)
        raw1_names = raw1.apply(lambda x: str(x).split('/')[0].strip())
        top_raw = raw1_names.value_counts().head(20)
        st.bar_chart(top_raw)

        st.markdown("#### 배합순위 2위 원료 빈도")
        raw2 = filtered['배합순위2'].dropna()
        raw2_names = raw2.apply(lambda x: str(x).split('/')[0].strip())
        top_raw2 = raw2_names.value_counts().head(20)
        st.bar_chart(top_raw2)

    # --- 제품 목록 ---
    st.markdown("---")
    st.subheader("📋 제품 목록")
    display_cols = ['No', '대분류', '세부유형', '제품명', '제조사', '용량(ml)', '포장용기', '가격(원)',
                    '배합순위1(원재료/배합비%/원산지)', '배합순위2', '배합순위3']
    st.dataframe(filtered[display_cols], use_container_width=True, height=400)


# ============================================================
# PAGE 3: 🎓 교육용 실습도구
# ============================================================
def page_education():
    st.title("🎓 음료 배합 실습 도구")
    st.caption("AI 기반 음료개발 교육과정 — 수강생 직접 배합 체험")

    # --- 실습 시나리오 선택 ---
    st.subheader("📚 실습 시나리오 선택")

    scenarios = {
        "🍊 과채음료 (사과맛)": {"유형": "과·채음료", "맛": "사과", "목표": "Brix 11, pH 3.5, 산도 0.35%"},
        "🍋 탄산음료 (레몬맛)": {"유형": "탄산음료", "맛": "레몬", "목표": "Brix 10.5, pH 3.2, 산도 0.25%"},
        "🍇 과채주스 (포도)": {"유형": "과·채주스", "맛": "포도", "목표": "Brix 12, pH 3.3, 산도 0.5%"},
        "🥛 유산균음료": {"유형": "유산균음료", "맛": "플레인", "목표": "Brix 13, pH 3.8, 산도 0.8%"},
        "🍑 제로칼로리 복숭아": {"유형": "과·채음료", "맛": "복숭아", "목표": "Brix 0, 감미도 0.10, 산도 0.20%"},
        "🆓 자유 실습": {"유형": "자유선택", "맛": "-", "목표": "자유"}
    }

    selected_scenario = st.selectbox("실습 과제", list(scenarios.keys()))
    scenario = scenarios[selected_scenario]

    st.info(f"🎯 **목표 규격**: {scenario['목표']}")

    # --- 학습 가이드 ---
    with st.expander("📖 배합 설계 가이드 (클릭해서 펼치기)"):
        st.markdown("""
        ### 음료 배합 설계 기본 원리

        **1단계: 원재료 선정** (과즙농축액)
        - 과즙함량 기준 충족이 최우선 (과채음료: 10%이상, 주스: 100%)
        - 농축배수 고려: 65Brix 오렌지 5배농축 → 13% 사용시 원래 과즙 65%

        **2단계: 당류 조절** (Brix 목표 맞추기)
        - 설탕 1% → Brix 약 1° 상승 (가장 직관적)
        - 액상과당: 설탕 대비 저렴, Brix 77이므로 0.77°/1%
        - 제로칼로리: 수크랄로스 0.01~0.02% (감미도 600배)

        **3단계: 산미료 조절** (pH & 산도 목표)
        - 구연산 0.1% 추가 → pH 약 0.1 하락, 산도 약 0.064% 상승
        - 산도 올리되 pH 과도저하 방지: 구연산Na로 완충

        **4단계: 향료·색소·안정제** (관능 최적화)
        - 향료: 보통 0.05~0.15%
        - 안정제: 펙틴 0.1~0.2% (과즙 분리 방지)

        **5단계: 규격 확인** → 미세조정 반복
        """)

    # --- 원료 DB 탐색 ---
    with st.expander("🔍 원료 DB 탐색"):
        search_cat = st.selectbox("원료 분류", df_ingredient['원료대분류'].unique().tolist(), key='edu_cat')
        sub_df = df_ingredient[df_ingredient['원료대분류'] == search_cat]
        display_cols = ['원료명', '원료소분류', 'Brix(°)', 'pH', '산도(%)', '감미도(설탕대비)',
                       '1%사용시 Brix기여(°)', PH_COL, '1%사용시 산도기여(%)', '1%사용시 감미기여', '예상단가(원/kg)']
        available_cols = [c for c in display_cols if c in sub_df.columns]
        st.dataframe(sub_df[available_cols], use_container_width=True)

    st.markdown("---")

    # --- 실습 배합 입력 ---
    st.subheader("🧪 나의 배합표")

    if 'edu_formulation' not in st.session_state:
        st.session_state.edu_formulation = []

    # 간편 원료 추가 (드래그 느낌)
    categories_order = ['과즙농축액', '당류', '감미료', '산미료', '향료', '색소', '안정제/증점제', '기타원료']

    for cat in categories_order:
        cat_ingredients = df_ingredient[df_ingredient['원료대분류'] == cat]['원료명'].tolist()
        if not cat_ingredients:
            continue

        with st.expander(f"{'🟢' if cat == '과즙농축액' else '🔵' if cat == '당류' else '🟡' if cat == '산미료' else '⚪'} {cat} ({len(cat_ingredients)}종)"):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                sel = st.selectbox(f"{cat} 원료", cat_ingredients, key=f"edu_sel_{cat}")
            with c2:
                pct = st.number_input("배합비(%)", 0.0, 100.0, 1.0, 0.1, key=f"edu_pct_{cat}")
            with c3:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("추가", key=f"edu_add_{cat}"):
                    st.session_state.edu_formulation.append({'원료명': sel, '배합비(%)': pct})
                    st.rerun()

    # 현재 배합 표시
    if st.session_state.edu_formulation:
        st.markdown("#### 📋 현재 배합")
        form_df = pd.DataFrame(st.session_state.edu_formulation)

        # 편집 가능 테이블
        edited_df = st.data_editor(
            form_df,
            column_config={
                "원료명": st.column_config.SelectboxColumn("원료명", options=df_ingredient['원료명'].tolist()),
                "배합비(%)": st.column_config.NumberColumn("배합비(%)", min_value=0, max_value=100, step=0.1)
            },
            num_rows="dynamic",
            use_container_width=True
        )
        st.session_state.edu_formulation = edited_df.to_dict('records')

        # 결과 계산
        result = calc_formulation(st.session_state.edu_formulation)

        st.markdown("---")
        st.subheader("📊 실습 결과")

        # 결과 대시보드
        r1, r2, r3 = st.columns(3)
        with r1:
            st.metric("당도 (Brix°)", result['총Brix(°)'])
            st.metric("원가 (원/kg)", f"{result['원재료비(원/kg)']:,.0f}")
        with r2:
            st.metric("예상 pH", result['예상pH'])
            st.metric("감미도", f"{result['총감미도']:.3f}")
        with r3:
            st.metric("산도 (%)", f"{result['총산도(%)']:.4f}")
            st.metric("당산비", result['당산비'])

        # 규격 판정
        if scenario['유형'] != '자유선택':
            spec = get_spec_range(scenario['유형'])
            if spec:
                issues = check_spec_compliance(result, spec)
                if not issues:
                    st.success("🎉 축하합니다! 규격 적합 판정!")
                    st.balloons()
                else:
                    st.warning("규격 미달 항목이 있습니다:")
                    for issue in issues:
                        st.write(issue)
                    st.markdown("💡 **힌트**: 어떤 원료를 조절해야 할까요? 위의 학습 가이드를 참고하세요!")

        # 상세 기여도
        with st.expander("📊 원료별 기여도 상세"):
            if result['details']:
                st.dataframe(pd.DataFrame(result['details']), use_container_width=True)

        # 초기화
        if st.button("🔄 배합 초기화"):
            st.session_state.edu_formulation = []
            st.rerun()


# ============================================================
# PAGE 4: 📋 신제품 기획서 자동생성
# ============================================================
def page_planner():
    st.title("📋 신제품 기획서 자동생성")
    st.caption("배합 → 규격 → 공정 → 원가를 원스톱으로 생성합니다")

    # --- STEP 1: 제품 기본정보 ---
    st.subheader("STEP 1: 제품 기본정보")
    col1, col2, col3 = st.columns(3)
    with col1:
        product_name = st.text_input("제품명", "새로운 음료")
        bev_type = st.selectbox("음료유형", df_spec['음료유형'].dropna().tolist(), key='plan_type')
    with col2:
        volume = st.number_input("용량(ml)", 100, 2000, 500, 50)
        packaging = st.selectbox("포장용기", ['PET', '캔', '유리병', '종이팩', '파우치'])
    with col3:
        target_price = st.number_input("목표 소비자가(원)", 500, 10000, 1500, 100)
        monthly_prod = st.number_input("월생산량(병)", 10000, 10000000, 100000, 10000)

    st.markdown("---")

    # --- STEP 2: 배합 설계 ---
    st.subheader("STEP 2: 배합 설계")

    if 'plan_formulation' not in st.session_state:
        st.session_state.plan_formulation = []

    # 가이드 배합 자동 추천
    guide_types = df_guide['키(유형_맛_슬롯)'].dropna().apply(lambda x: '_'.join(x.split('_')[:2])).unique()
    sel_guide = st.selectbox("가이드 배합 선택", ['직접입력'] + sorted(guide_types.tolist()))

    if sel_guide != '직접입력' and st.button("📥 가이드배합 불러오기", key='plan_load'):
        st.session_state.plan_formulation = []
        prefix = sel_guide + '_'
        rows = df_guide[df_guide['키(유형_맛_슬롯)'].str.startswith(prefix, na=False)]
        for _, r in rows.iterrows():
            name = r.get('AI추천_원료명')
            pct = r.get('AI추천_배합비(%)')
            if pd.notna(name) and pd.notna(pct) and pct > 0:
                st.session_state.plan_formulation.append({'원료명': str(name), '배합비(%)': float(pct)})
        st.rerun()

    # 배합표 편집
    if st.session_state.plan_formulation:
        plan_df = pd.DataFrame(st.session_state.plan_formulation)
        edited = st.data_editor(
            plan_df,
            column_config={
                "원료명": st.column_config.SelectboxColumn("원료명", options=df_ingredient['원료명'].tolist()),
                "배합비(%)": st.column_config.NumberColumn("배합비(%)", min_value=0, max_value=100, step=0.1)
            },
            num_rows="dynamic",
            use_container_width=True
        )
        st.session_state.plan_formulation = edited.dropna(subset=['원료명']).to_dict('records')

        result = calc_formulation(st.session_state.plan_formulation)

        # 결과 요약
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Brix", result['총Brix(°)'])
        m2.metric("pH", result['예상pH'])
        m3.metric("산도", f"{result['총산도(%)']:.3f}%")
        m4.metric("원가", f"{result['원재료비(원/kg)']:,.0f}원/kg")
    else:
        result = None
        st.info("배합표를 입력하거나 가이드배합을 불러오세요")

    st.markdown("---")

    # --- STEP 3: 공정 & HACCP ---
    st.subheader("STEP 3: 표준 제조공정 & HACCP")

    # 음료유형에 맞는 공정 자동 매칭
    bev_type_short = bev_type.split('(')[0].strip()
    matched_process = df_process[df_process['음료유형'].str.contains(bev_type_short, na=False)]

    if not matched_process.empty:
        st.success(f"✅ **{bev_type}** 표준공정 {len(matched_process)}단계 매칭됨")
        with st.expander("📋 표준 제조공정 상세"):
            for _, p in matched_process.iterrows():
                ccp_mark = "🔴 CCP" if str(p.get('CCP여부', '')).startswith('CCP') else ""
                st.markdown(f"**{p['공정단계']}** — {p['세부공정']} {ccp_mark}")
                st.write(f"  방법: {p.get('작업방법(구체적)', '-')}")
                st.write(f"  조건: {p.get('주요조건/파라미터', '-')}")
                if ccp_mark:
                    st.error(f"  한계기준: {p.get('한계기준(CL)', '-')}")
                st.markdown("---")
    else:
        st.warning(f"'{bev_type_short}'에 매칭되는 공정이 없습니다. 유사 유형을 선택해주세요.")

    st.markdown("---")

    # --- STEP 4: 원가 계산 ---
    st.subheader("STEP 4: 원가 계산")

    if result and result['details']:
        # 원재료비
        raw_cost_per_kg = result['원재료비(원/kg)']
        raw_cost_per_bottle = raw_cost_per_kg * volume / 1000

        # 포장재비 (추정)
        pkg_costs = {'PET': 120, '캔': 90, '유리병': 200, '종이팩': 80, '파우치': 60}
        pkg_cost = pkg_costs.get(packaging, 100)

        # 제조비 (추정: 원재료비의 30~50%)
        mfg_cost = raw_cost_per_bottle * 0.4

        # 총제조원가
        total_cost = raw_cost_per_bottle + pkg_cost + mfg_cost

        # 마진 분석
        margin = target_price - total_cost
        margin_rate = margin / target_price * 100 if target_price > 0 else 0

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("#### 💰 원가 구성")
            st.write(f"원재료비: **{raw_cost_per_bottle:,.0f}원**/병")
            st.write(f"포장재비: **{pkg_cost:,.0f}원**/병")
            st.write(f"제조가공비: **{mfg_cost:,.0f}원**/병 (추정)")
            st.write(f"**총제조원가: {total_cost:,.0f}원/병**")
        with c2:
            st.markdown("#### 📊 마진 분석")
            st.write(f"소비자가: {target_price:,.0f}원")
            st.write(f"마진: **{margin:,.0f}원** ({margin_rate:.1f}%)")
            if margin_rate > 50:
                st.success("수익성 우수")
            elif margin_rate > 30:
                st.info("수익성 적정")
            else:
                st.warning("수익성 검토 필요")
        with c3:
            st.markdown("#### 🏭 생산 규모")
            st.write(f"월생산량: {monthly_prod:,}병")
            st.write(f"월원재료비: **{raw_cost_per_bottle * monthly_prod:,.0f}원**")
            st.write(f"연매출(예상): **{target_price * monthly_prod * 12 / 100000000:.1f}억원**")

    st.markdown("---")

    # --- 기획서 생성 버튼 ---
    st.subheader("📄 기획서 다운로드")

    if result and result['details']:
        if st.button("📋 기획서 텍스트 생성", use_container_width=True):
            report = generate_report(
                product_name, bev_type, volume, packaging, target_price,
                monthly_prod, result, matched_process, spec=get_spec_range(bev_type)
            )
            st.text_area("기획서 미리보기", report, height=500)
            st.download_button(
                "💾 기획서 다운로드 (.txt)",
                report,
                file_name=f"신제품기획서_{product_name}_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain"
            )


def generate_report(name, bev_type, volume, pkg, price, prod, result, process_df, spec=None):
    """신제품 기획서 텍스트 생성"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"    신제품 기획서: {name}")
    lines.append(f"    작성일: {datetime.now().strftime('%Y년 %m월 %d일')}")
    lines.append("=" * 60)

    lines.append("\n■ 1. 제품 개요")
    lines.append(f"  제품명: {name}")
    lines.append(f"  음료유형: {bev_type}")
    lines.append(f"  용량: {volume}ml")
    lines.append(f"  포장: {pkg}")
    lines.append(f"  목표가: {price:,}원")

    lines.append("\n■ 2. 배합표")
    lines.append(f"  {'원료명':<25} {'배합비(%)':<10} {'분류':<12} {'원가기여(원/kg)':<15}")
    lines.append("  " + "-" * 65)
    for d in result['details']:
        lines.append(f"  {d['원료명']:<25} {d['배합비(%)']:<10.2f} {d['분류']:<12} {d['원가기여(원/kg)']:<15.1f}")
    lines.append(f"  {'정제수':<25} {result['정제수(%)']:<10.2f} {'기본원료':<12} {'0':>15}")
    lines.append("  " + "-" * 65)
    lines.append(f"  {'합계':<25} {'100.00':<10}")

    lines.append("\n■ 3. 품질 규격")
    lines.append(f"  당도(Brix): {result['총Brix(°)']}°")
    lines.append(f"  예상 pH: {result['예상pH']}")
    lines.append(f"  산도: {result['총산도(%)']:.4f}%")
    lines.append(f"  감미도: {result['총감미도']:.4f}")
    lines.append(f"  당산비: {result['당산비']}")

    if spec:
        lines.append(f"\n  [규격기준] Brix {spec['Brix_min']}~{spec['Brix_max']}° / "
                     f"pH {spec['pH_min']}~{spec['pH_max']} / "
                     f"산도 {spec['산도_min']}~{spec['산도_max']}%")
        issues = check_spec_compliance(result, spec)
        if not issues:
            lines.append("  → ✅ 규격 적합")
        else:
            for issue in issues:
                lines.append(f"  → {issue}")

    lines.append("\n■ 4. 제조공정 (HACCP)")
    if not process_df.empty:
        for _, p in process_df.iterrows():
            ccp = " [CCP]" if str(p.get('CCP여부', '')).startswith('CCP') else ""
            lines.append(f"  {p['공정단계']} - {p['세부공정']}{ccp}")
            if ccp:
                lines.append(f"    한계기준: {p.get('한계기준(CL)', '-')}")

    lines.append("\n■ 5. 원가 분석")
    raw_per_bottle = result['원재료비(원/kg)'] * volume / 1000
    pkg_costs = {'PET': 120, '캔': 90, '유리병': 200, '종이팩': 80, '파우치': 60}
    pkg_cost = pkg_costs.get(pkg, 100)
    mfg_cost = raw_per_bottle * 0.4
    total = raw_per_bottle + pkg_cost + mfg_cost
    margin = price - total

    lines.append(f"  원재료비: {raw_per_bottle:,.0f}원/병 ({result['원재료비(원/kg)']:,.0f}원/kg)")
    lines.append(f"  포장재비: {pkg_cost:,.0f}원/병")
    lines.append(f"  제조가공비: {mfg_cost:,.0f}원/병 (추정)")
    lines.append(f"  총제조원가: {total:,.0f}원/병")
    lines.append(f"  소비자가: {price:,}원")
    lines.append(f"  마진: {margin:,.0f}원 ({margin/price*100:.1f}%)")
    lines.append(f"  월생산량: {prod:,}병")
    lines.append(f"  월매출: {price * prod:,.0f}원")
    lines.append(f"  연매출: {price * prod * 12:,.0f}원 ({price * prod * 12 / 100000000:.1f}억)")

    lines.append("\n" + "=" * 60)
    lines.append("  ※ 본 기획서는 AI 시뮬레이션 기반 추정치입니다.")
    lines.append("  ※ 실제 제조 시 시작(試作) 테스트가 필요합니다.")
    lines.append("=" * 60)

    return "\n".join(lines)


# ============================================================
# 메인 라우팅
# ============================================================
if PAGES[page] == "simulator":
    page_simulator()
elif PAGES[page] == "market":
    page_market()
elif PAGES[page] == "education":
    page_education()
elif PAGES[page] == "planner":
    page_planner()
