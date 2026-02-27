"""
🧪 음료개발 AI 플랫폼 v5 — 10개 기능 통합
"""
import streamlit as st
import pandas as pd
import numpy as np
import json, os, re
from datetime import datetime
from engine import (
    calc_formulation, get_spec_range, check_compliance,
    reverse_engineer_product, generate_food_label, generate_lab_recipe,
    call_gpt_researcher, call_dalle, build_dalle_prompt, parse_modified_formulation,
    get_color_from_ingredients,
)

# ============================================================
# 0. 설정 & 데이터
# ============================================================
st.set_page_config(page_title="🧪 음료개발 AI 플랫폼", page_icon="🧪", layout="wide")

DB_PATH = os.path.join(os.path.dirname(__file__), "음료개발_데이터베이스_v4-1.xlsx")

@st.cache_data
def load_data(path):
    sheets = {}
    for name in pd.ExcelFile(path).sheet_names:
        sheets[name] = pd.read_excel(path, sheet_name=name)
    return sheets

try:
    DATA = load_data(DB_PATH)
except:
    st.error("❌ `음료개발_데이터베이스_v4-1.xlsx` 파일을 앱 폴더에 넣어주세요.")
    st.stop()

df_type = DATA['음료유형분류']
df_product = DATA['시장제품DB']
df_ing = DATA['원료DB']
df_spec = DATA['음료규격기준']
df_process = DATA['표준제조공정_HACCP']
df_guide = DATA['가이드배합비DB']

# 수치 전처리
NUM_COLS = ['Brix(°)', 'pH', '산도(%)', '감미도(설탕대비)', '예상단가(원/kg)',
            '1%사용시 Brix기여(°)', '1%사용시 산도기여(%)', '1%사용시 감미기여']
for c in NUM_COLS:
    df_ing[c] = pd.to_numeric(df_ing[c], errors='coerce').fillna(0)
PH_COL = [c for c in df_ing.columns if 'pH영향' in str(c) or 'ΔpH' in str(c)][0]
df_ing[PH_COL] = pd.to_numeric(df_ing[PH_COL], errors='coerce').fillna(0)

# OpenAI 키
# secrets 구조 자동 감지: [openai] 섹션 또는 최상위 모두 지원
try:
    OPENAI_KEY = st.secrets["openai"]["OPENAI_API_KEY"]
except (KeyError, TypeError):
    OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")

# ============================================================
# 사이드바
# ============================================================
st.sidebar.title("🧪 음료개발 AI 플랫폼")
st.sidebar.markdown("---")
PAGES = [
    "🧪 배합 시뮬레이터", "🧑‍🔬 AI 연구원 평가", "🎨 제품 이미지 생성",
    "🔄 역설계", "📊 시장분석", "🎓 교육용 실습",
    "📋 신제품 기획서", "📑 식품표시사항", "🧫 시작 레시피",
    "📓 배합 히스토리",
]
page = st.sidebar.radio("메뉴", PAGES)
st.sidebar.markdown("---")
st.sidebar.caption(f"원료 {len(df_ing)}종 · 제품 {len(df_product)}종 · 가이드 {len(df_guide)}건")

# 공통 세션 초기화
if 'formulation' not in st.session_state:
    st.session_state.formulation = []
if 'history' not in st.session_state:
    st.session_state.history = []

# ============================================================
# 공통: 배합표 입력 위젯
# ============================================================
def formulation_editor(key_prefix="main", show_guide=True):
    """재사용 가능한 배합표 편집 UI — 반환: list of dicts"""
    state_key = f'{key_prefix}_form'
    if state_key not in st.session_state:
        st.session_state[state_key] = []

    # 가이드 배합 로딩
    if show_guide:
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            guide_keys = df_guide['키(유형_맛_슬롯)'].dropna().apply(lambda x: '_'.join(x.split('_')[:2])).unique()
            sel_guide = st.selectbox("가이드배합 선택", ['직접입력'] + sorted(guide_keys.tolist()), key=f'{key_prefix}_guide')
        with c2:
            st.markdown("<br>", unsafe_allow_html=True)
            if sel_guide != '직접입력' and st.button("📥 불러오기", key=f'{key_prefix}_load'):
                st.session_state[state_key] = []
                for _, r in df_guide[df_guide['키(유형_맛_슬롯)'].str.startswith(sel_guide + '_', na=False)].iterrows():
                    n, p = r.get('AI추천_원료명'), r.get('AI추천_배합비(%)')
                    if pd.notna(n) and pd.notna(p) and p > 0:
                        st.session_state[state_key].append({'원료명': str(n), '배합비(%)': float(p)})
                st.rerun()
        with c3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 초기화", key=f'{key_prefix}_reset'):
                st.session_state[state_key] = []
                st.rerun()

    # 원료 추가
    a1, a2, a3, a4 = st.columns([1.5, 2.5, 1, 0.8])
    with a1:
        cats = ['전체'] + df_ing['원료대분류'].unique().tolist()
        fcat = st.selectbox("분류", cats, key=f'{key_prefix}_fcat')
    with a2:
        names = df_ing['원료명'].tolist() if fcat == '전체' else df_ing[df_ing['원료대분류'] == fcat]['원료명'].tolist()
        new_name = st.selectbox("원료", names, key=f'{key_prefix}_newname')
    with a3:
        new_pct = st.number_input("%", 0.0, 100.0, 1.0, 0.1, key=f'{key_prefix}_newpct')
    with a4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕", key=f'{key_prefix}_add', use_container_width=True):
            st.session_state[state_key].append({'원료명': new_name, '배합비(%)': new_pct})
            st.rerun()

    # 편집 테이블
    if st.session_state[state_key]:
        df_form = pd.DataFrame(st.session_state[state_key])
        edited = st.data_editor(
            df_form,
            column_config={
                "원료명": st.column_config.SelectboxColumn("원료명", options=df_ing['원료명'].tolist(), width="large"),
                "배합비(%)": st.column_config.NumberColumn("배합비(%)", min_value=0, max_value=100, step=0.01, format="%.2f"),
            },
            num_rows="dynamic", use_container_width=True, key=f'{key_prefix}_editor',
        )
        st.session_state[state_key] = edited.dropna(subset=['원료명']).to_dict('records')

    return st.session_state[state_key]


def show_result_metrics(result, spec=None):
    """결과 메트릭 + 규격판정 표시"""
    m = st.columns(6)
    m[0].metric("Brix(°)", result['총Brix(°)'])
    m[1].metric("예상 pH", result['예상pH'])
    m[2].metric("산도(%)", f"{result['총산도(%)']:.3f}")
    m[3].metric("감미도", f"{result['총감미도']:.3f}")
    m[4].metric("당산비", result['당산비'])
    m[5].metric("원가(원/kg)", f"{result['원재료비(원/kg)']:,.0f}")

    if spec:
        issues = check_compliance(result, spec)
        if not issues:
            st.success(f"✅ 규격 적합 (Brix {spec['Brix_min']}~{spec['Brix_max']}, pH {spec['pH_min']}~{spec['pH_max']}, 산도 {spec['산도_min']}~{spec['산도_max']})")
        else:
            for i in issues:
                st.warning(i)
    st.info(f"💧 정제수 {result['정제수(%)']}% | 원료합계 {result['원료합계(%)']}%")


# ============================================================
# PAGE 1: 🧪 배합 시뮬레이터
# ============================================================
def page_simulator():
    st.title("🧪 배합 시뮬레이터")
    st.caption("원료 선택 → pH / Brix / 산도 / 감미 / 원가 자동 계산")

    bev_type = st.selectbox("음료유형", df_spec['음료유형'].dropna().tolist())
    ingredients = formulation_editor("sim")

    if ingredients:
        result = calc_formulation(df_ing, ingredients, PH_COL)
        st.markdown("---")
        st.subheader("📊 시뮬레이션 결과")
        show_result_metrics(result, get_spec_range(df_spec, bev_type))

        # 기여도 상세
        if result['details']:
            st.markdown("#### 원료별 기여도")
            det_df = pd.DataFrame(result['details'])
            st.dataframe(det_df.style.format({
                '배합비(%)': '{:.2f}', 'Brix기여': '{:.2f}', '산도기여': '{:.4f}',
                '감미기여': '{:.4f}', 'ΔpH기여': '{:+.3f}', '원가기여(원/kg)': '{:.1f}'
            }), use_container_width=True)

            # 차트
            c1, c2 = st.columns(2)
            with c1:
                st.bar_chart(det_df.set_index('원료명')['Brix기여'])
                st.caption("Brix 기여도")
            with c2:
                st.bar_chart(det_df.set_index('원료명')['원가기여(원/kg)'])
                st.caption("원가 기여도")

        # 히스토리 저장 버튼
        st.markdown("---")
        save_name = st.text_input("배합명", f"배합_{datetime.now().strftime('%H%M%S')}", key="sim_save_name")
        if st.button("💾 히스토리에 저장", key="sim_save"):
            st.session_state.history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'name': save_name, 'type': bev_type,
                'ingredients': ingredients.copy(), 'result': result, 'notes': '',
            })
            st.success(f"✅ '{save_name}' 저장됨 (총 {len(st.session_state.history)}건)")

        # 공유: 메인 세션에도 반영 (AI평가/이미지 등에서 사용)
        st.session_state.formulation = ingredients


# ============================================================
# PAGE 2: 🧑‍🔬 AI 연구원 평가
# ============================================================
def page_ai_researcher():
    st.title("🧑‍🔬 AI 음료개발연구원 평가")
    st.caption("20년 경력 수석 연구원 'Dr. 이음료'가 배합표를 평가하고 개선안을 제시합니다")

    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키가 설정되지 않았습니다. Streamlit secrets에 `OPENAI_API_KEY`를 등록하세요.")
        return

    bev_type = st.selectbox("음료유형", df_spec['음료유형'].dropna().tolist(), key="ai_type")
    target = st.text_input("목표 컨셉", "과즙감 강조, 상큼한 산미, 원가 500원/kg 이하", key="ai_target")

    st.markdown("---")
    st.subheader("📝 평가할 배합표")
    ingredients = formulation_editor("ai")

    if ingredients:
        result = calc_formulation(df_ing, ingredients, PH_COL)
        show_result_metrics(result, get_spec_range(df_spec, bev_type))

        st.markdown("---")
        if st.button("🧑‍🔬 AI 연구원에게 평가 요청", type="primary", use_container_width=True):
            # 배합표 텍스트 생성
            lines = [f"{'원료명':<25} {'배합비':>6}  {'분류':<10}"]
            lines.append("-" * 45)
            for d in result['details']:
                lines.append(f"{d['원료명']:<25} {d['배합비(%)']:>5.2f}%  {d['분류']:<10}")
            lines.append(f"{'정제수':<25} {result['정제수(%)']:>5.2f}%  {'기본원료':<10}")
            lines.append(f"\n총Brix: {result['총Brix(°)']}° | pH: {result['예상pH']} | 산도: {result['총산도(%)']:.4f}%")
            lines.append(f"감미도: {result['총감미도']:.4f} | 당산비: {result['당산비']} | 원가: {result['원재료비(원/kg)']:.0f}원/kg")
            form_text = '\n'.join(lines)

            spec = get_spec_range(df_spec, bev_type)
            spec_text = f"Brix {spec['Brix_min']}~{spec['Brix_max']}, pH {spec['pH_min']}~{spec['pH_max']}, 산도 {spec['산도_min']}~{spec['산도_max']}%" if spec else ""

            with st.spinner("🧑‍🔬 Dr. 이음료가 분석 중..."):
                try:
                    response = call_gpt_researcher(OPENAI_KEY, form_text, bev_type, f"{spec_text}\n목표: {target}")
                    st.session_state['ai_response'] = response
                except Exception as e:
                    st.error(f"API 호출 실패: {e}")
                    return

        # 결과 표시
        if 'ai_response' in st.session_state:
            st.markdown("---")
            st.subheader("🧑‍🔬 Dr. 이음료의 평가")
            st.markdown(st.session_state['ai_response'])

            # 수정 배합표 추출 & 적용
            modified = parse_modified_formulation(st.session_state['ai_response'])
            if modified:
                st.markdown("---")
                st.subheader("📋 제안된 수정 배합표")
                mod_df = pd.DataFrame(modified)
                st.dataframe(mod_df, use_container_width=True)

                if st.button("✅ 수정 배합표를 시뮬레이터에 적용", type="primary"):
                    st.session_state['ai_form'] = modified
                    st.session_state.formulation = modified
                    st.success("✅ 시뮬레이터에 반영되었습니다. '배합 시뮬레이터' 탭에서 확인하세요.")


# ============================================================
# PAGE 3: 🎨 제품 이미지 생성
# ============================================================
def page_image_gen():
    st.title("🎨 AI 제품 이미지 생성")
    st.caption("배합표 기반으로 DALL-E가 제품 패키지 디자인을 생성합니다")

    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키가 필요합니다.")
        return

    c1, c2 = st.columns(2)
    with c1:
        product_name = st.text_input("제품명", "풋사과톡", key="img_name")
        bev_type = st.selectbox("음료유형", df_spec['음료유형'].dropna().tolist(), key="img_type")
    with c2:
        container = st.selectbox("포장용기", ['PET', '캔', '유리병', '종이팩', '파우치'], key="img_pkg")
        volume = st.number_input("용량(ml)", 100, 2000, 500, key="img_vol")

    st.markdown("---")
    st.subheader("배합표 (이미지 참조용)")
    ingredients = formulation_editor("img", show_guide=True)

    if ingredients:
        # 프롬프트 미리보기
        prompt = build_dalle_prompt(product_name, bev_type, ingredients, df_ing, container, volume)
        with st.expander("🔍 생성 프롬프트 미리보기"):
            st.text(prompt)

        # 프롬프트 직접 수정 가능
        custom_prompt = st.text_area("프롬프트 수정 (선택)", prompt, height=120, key="img_prompt")

        if st.button("🎨 이미지 생성", type="primary", use_container_width=True):
            with st.spinner("🎨 DALL-E가 디자인 중... (약 15~30초)"):
                try:
                    img_url = call_dalle(OPENAI_KEY, custom_prompt)
                    st.session_state['generated_image'] = img_url
                except Exception as e:
                    st.error(f"이미지 생성 실패: {e}")

        if 'generated_image' in st.session_state:
            st.markdown("---")
            st.subheader(f"🎨 {product_name} 디자인 시안")
            st.image(st.session_state['generated_image'], use_container_width=True)
            st.markdown(f"[📥 이미지 다운로드]({st.session_state['generated_image']})")


# ============================================================
# PAGE 4: 🔄 역설계
# ============================================================
def page_reverse():
    st.title("🔄 시판제품 역설계")
    st.caption("시장제품DB에서 제품을 선택하면 배합비를 추정합니다")

    # 제품 필터
    c1, c2 = st.columns(2)
    with c1:
        cats = ['전체'] + df_product['대분류'].dropna().unique().tolist()
        sel_cat = st.selectbox("대분류", cats, key="rev_cat")
    with c2:
        filtered = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
        products = filtered['제품명'].dropna().tolist()
        sel_product = st.selectbox("제품 선택", products, key="rev_product")

    if sel_product:
        prod_row = df_product[df_product['제품명'] == sel_product].iloc[0]

        # 제품 정보
        st.markdown("---")
        st.subheader(f"📦 {sel_product}")
        i1, i2, i3, i4 = st.columns(4)
        i1.write(f"**제조사**: {prod_row.get('제조사', '-')}")
        i2.write(f"**유형**: {prod_row.get('세부유형', '-')}")
        i3.write(f"**용량**: {prod_row.get('용량(ml)', '-')}ml")
        i4.write(f"**가격**: {prod_row.get('가격(원)', '-')}원")

        # 원재료 표시
        st.markdown("#### 📋 제품 원재료 표시")
        for i in range(1, 8):
            col = f'배합순위{i}' if i > 1 else '배합순위1(원재료/배합비%/원산지)'
            val = prod_row.get(col)
            if pd.notna(val) and str(val).strip() not in ['—', '-', '0', '']:
                st.write(f"  {i}순위: **{val}**")

        # 역설계
        st.markdown("---")
        if st.button("🔄 배합비 추정 실행", type="primary", use_container_width=True):
            estimated = reverse_engineer_product(prod_row, df_ing)
            if estimated:
                st.subheader("📊 추정 배합표")
                est_df = pd.DataFrame(estimated)
                st.dataframe(est_df, use_container_width=True)

                # 시뮬레이션
                sim_ready = [{'원료명': e['원료명'], '배합비(%)': e['배합비(%)']} for e in estimated if e.get('DB매칭')]
                if sim_ready:
                    result = calc_formulation(df_ing, sim_ready, PH_COL)
                    st.markdown("#### 추정 품질 규격")
                    show_result_metrics(result)

                # 시뮬레이터로 보내기
                if st.button("📤 이 배합표를 시뮬레이터로 보내기"):
                    st.session_state['sim_form'] = sim_ready
                    st.session_state.formulation = sim_ready
                    st.success("✅ 시뮬레이터에 반영됨")
            else:
                st.warning("배합비 정보를 추출할 수 없습니다.")


# ============================================================
# PAGE 5: 📊 시장분석
# ============================================================
def page_market():
    st.title("📊 시장제품 분석 대시보드")
    st.caption(f"국내 시판 음료 {len(df_product)}개 제품 분석")

    c1, c2, c3 = st.columns(3)
    with c1:
        sel_cat = st.selectbox("대분류", ['전체'] + df_product['대분류'].dropna().unique().tolist())
    with c2:
        if sel_cat == '전체':
            subs = ['전체'] + df_product['세부유형'].dropna().unique().tolist()
        else:
            subs = ['전체'] + df_product[df_product['대분류'] == sel_cat]['세부유형'].dropna().unique().tolist()
        sel_sub = st.selectbox("세부유형", subs)
    with c3:
        sel_maker = st.selectbox("제조사", ['전체'] + sorted(df_product['제조사'].dropna().unique().tolist()))

    f = df_product.copy()
    if sel_cat != '전체': f = f[f['대분류'] == sel_cat]
    if sel_sub != '전체': f = f[f['세부유형'] == sel_sub]
    if sel_maker != '전체': f = f[f['제조사'] == sel_maker]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("제품수", f"{len(f)}개")
    k2.metric("제조사", f"{f['제조사'].nunique()}개")
    avg_p = f['가격(원)'].dropna().mean()
    k3.metric("평균가격", f"{avg_p:,.0f}원" if not np.isnan(avg_p) else "-")
    avg_v = f['용량(ml)'].dropna().mean()
    k4.metric("평균용량", f"{avg_v:,.0f}ml" if not np.isnan(avg_v) else "-")

    tab1, tab2, tab3, tab4 = st.tabs(["🏢 제조사", "📦 유형", "💰 가격", "🔬 원재료"])
    with tab1:
        st.bar_chart(f['제조사'].value_counts().head(15))
    with tab2:
        st.bar_chart(f['세부유형'].value_counts())
        st.markdown("#### 유형별 시장규모")
        mkt = df_type[['세부유형(식품유형)', '국내 예상 연매출(억원)']].dropna()
        mkt.columns = ['유형', '연매출(억)']
        st.bar_chart(mkt.set_index('유형').sort_values('연매출(억)', ascending=False))
    with tab3:
        pd_price = f[['세부유형', '가격(원)', '용량(ml)']].dropna()
        if not pd_price.empty:
            st.bar_chart(pd_price.groupby('세부유형')['가격(원)'].mean().sort_values(ascending=False))
            st.bar_chart(f['포장용기'].value_counts())
    with tab4:
        raw1 = f['배합순위1(원재료/배합비%/원산지)'].dropna().apply(lambda x: str(x).split('/')[0].strip())
        st.bar_chart(raw1.value_counts().head(20))

    st.markdown("---")
    st.dataframe(f[['No', '대분류', '세부유형', '제품명', '제조사', '용량(ml)', '가격(원)',
                     '배합순위1(원재료/배합비%/원산지)', '배합순위2']],
                 use_container_width=True, height=350)


# ============================================================
# PAGE 6: 🎓 교육용 실습
# ============================================================
def page_education():
    st.title("🎓 음료 배합 실습 도구")
    st.caption("AI 음료개발 교육 — 직접 배합하고 규격 달성에 도전하세요!")

    scenarios = {
        "🍊 과채음료(사과)": ("과·채음료", "Brix 11, pH 3.5, 산도 0.35%"),
        "🍋 탄산음료(레몬)": ("탄산음료", "Brix 10.5, pH 3.2, 산도 0.25%"),
        "🍇 과채주스(포도)": ("과·채주스", "Brix 12, pH 3.3, 산도 0.5%"),
        "🥛 유산균음료": ("유산균음료", "Brix 13, pH 3.8, 산도 0.8%"),
        "🍑 제로칼로리": ("과·채음료", "감미도 0.10, 산도 0.20%"),
        "🆓 자유실습": ("자유", "자유"),
    }
    sel = st.selectbox("실습 시나리오", list(scenarios.keys()))
    btype, target = scenarios[sel]
    st.info(f"🎯 목표: {target}")

    with st.expander("📖 배합 설계 가이드"):
        st.markdown("""
**1단계 원재료**: 과즙함량 기준 충족 (과채음료 ≥10%, 주스 100%)
**2단계 당류**: 설탕 1% ≈ Brix 1° / 액상과당 1% ≈ 0.77° / 제로 → 수크랄로스 0.01~0.02%
**3단계 산미료**: 구연산 0.1% → pH ~0.1↓, 산도 ~0.064%↑ / 구연산Na로 완충
**4단계 향료·안정제**: 향료 0.05~0.15% / 펙틴 0.1~0.2%
**5단계 규격확인** → 미세조정 반복
        """)

    with st.expander("🔍 원료 DB 탐색"):
        scat = st.selectbox("분류", df_ing['원료대분류'].unique(), key="edu_scat")
        show_cols = ['원료명', '원료소분류', 'Brix(°)', '감미도(설탕대비)',
                     '1%사용시 Brix기여(°)', PH_COL, '1%사용시 산도기여(%)', '1%사용시 감미기여', '예상단가(원/kg)']
        st.dataframe(df_ing[df_ing['원료대분류'] == scat][[c for c in show_cols if c in df_ing.columns]], use_container_width=True)

    st.markdown("---")
    ingredients = formulation_editor("edu")

    if ingredients:
        result = calc_formulation(df_ing, ingredients, PH_COL)
        st.markdown("---")
        st.subheader("📊 실습 결과")
        spec = get_spec_range(df_spec, btype) if btype != '자유' else None
        show_result_metrics(result, spec)

        if spec and not check_compliance(result, spec):
            st.balloons()
            st.success("🎉 축하합니다! 규격 적합 달성!")


# ============================================================
# PAGE 7: 📋 신제품 기획서
# ============================================================
def page_planner():
    st.title("📋 신제품 기획서 자동생성")

    c1, c2, c3 = st.columns(3)
    with c1:
        pname = st.text_input("제품명", "새로운 음료")
        btype = st.selectbox("음료유형", df_spec['음료유형'].dropna().tolist(), key="plan_type")
    with c2:
        volume = st.number_input("용량(ml)", 100, 2000, 500, 50)
        pkg = st.selectbox("포장", ['PET', '캔', '유리병', '종이팩', '파우치'])
    with c3:
        price = st.number_input("목표가(원)", 500, 10000, 1500, 100)
        prod = st.number_input("월생산량(병)", 10000, 10000000, 100000, 10000)

    st.markdown("---")
    ingredients = formulation_editor("plan")

    if ingredients:
        result = calc_formulation(df_ing, ingredients, PH_COL)
        spec = get_spec_range(df_spec, btype)
        show_result_metrics(result, spec)

        # 공정 매칭
        st.markdown("---")
        st.subheader("🏭 표준 제조공정")
        matched = df_process[df_process['음료유형'].str.contains(btype.split('(')[0], na=False)]
        if not matched.empty:
            for _, p in matched.iterrows():
                ccp = " 🔴CCP" if str(p.get('CCP여부', '')).startswith('CCP') else ""
                st.markdown(f"**{p['공정단계']}** — {p['세부공정']}{ccp}")
                if ccp:
                    st.error(f"한계기준: {p.get('한계기준(CL)', '-')}")

        # 원가
        st.markdown("---")
        st.subheader("💰 원가 분석")
        raw_bottle = result['원재료비(원/kg)'] * volume / 1000
        pkg_cost = {'PET': 120, '캔': 90, '유리병': 200, '종이팩': 80, '파우치': 60}.get(pkg, 100)
        mfg = raw_bottle * 0.4
        total = raw_bottle + pkg_cost + mfg
        margin = price - total

        o1, o2, o3 = st.columns(3)
        with o1:
            st.write(f"원재료비: **{raw_bottle:,.0f}원**/병")
            st.write(f"포장재비: **{pkg_cost}원**/병")
            st.write(f"제조비(추정): **{mfg:,.0f}원**/병")
            st.write(f"**총원가: {total:,.0f}원/병**")
        with o2:
            st.write(f"마진: **{margin:,.0f}원** ({margin/price*100:.1f}%)")
            if margin / price > 0.5: st.success("수익성 우수")
            elif margin / price > 0.3: st.info("수익성 적정")
            else: st.warning("수익성 검토 필요")
        with o3:
            st.write(f"월매출: **{price * prod:,.0f}원**")
            st.write(f"연매출: **{price * prod * 12 / 1e8:.1f}억원**")

        # 기획서 다운로드
        st.markdown("---")
        if st.button("📄 기획서 생성", use_container_width=True):
            lines = [
                "=" * 60, f"  신제품 기획서: {pname}", f"  {datetime.now().strftime('%Y-%m-%d')}", "=" * 60,
                f"\n■ 제품: {pname} | {btype} | {volume}ml | {pkg} | {price:,}원",
                "\n■ 배합표"
            ]
            for d in result['details']:
                lines.append(f"  {d['원료명']:<25} {d['배합비(%)']:>6.2f}%  {d['원가기여(원/kg)']:>8.1f}원/kg")
            lines.append(f"  {'정제수':<25} {result['정제수(%)']:>6.2f}%")
            lines.append(f"\n■ 규격: Brix {result['총Brix(°)']}° | pH {result['예상pH']} | 산도 {result['총산도(%)']:.4f}% | 당산비 {result['당산비']}")
            lines.append(f"\n■ 원가: 원재료 {raw_bottle:.0f} + 포장 {pkg_cost} + 제조 {mfg:.0f} = {total:.0f}원/병 | 마진 {margin:.0f}원({margin/price*100:.1f}%)")
            report = '\n'.join(lines)
            st.download_button("💾 다운로드", report, f"기획서_{pname}.txt", "text/plain")


# ============================================================
# PAGE 8: 📑 식품표시사항
# ============================================================
def page_labeling():
    st.title("📑 식품표시사항 자동생성")
    st.caption("배합표 → 원재료명 표시순서 + 영양성분표")

    c1, c2 = st.columns(2)
    with c1:
        pname = st.text_input("제품명", "제품명", key="lab_name")
    with c2:
        volume = st.number_input("내용량(ml)", 100, 2000, 500, key="lab_vol")

    ingredients = formulation_editor("lab")

    if ingredients:
        result = calc_formulation(df_ing, ingredients, PH_COL)
        label = generate_food_label(ingredients, df_ing, pname, volume)

        st.markdown("---")
        st.subheader("📋 원재료명")
        st.info(label['원재료명'])
        st.caption("※ 식품공전 기준: 많이 사용한 순서대로 표시")

        st.subheader("📊 영양성분표")
        nut = label['영양성분']
        n1, n2 = st.columns(2)
        with n1:
            st.markdown("**1회 제공량 기준**")
            st.write(f"내용량: {volume}ml")
            st.write(f"열량: **{nut.get(f'열량(kcal/{volume}ml)', 0)}kcal**")
            st.write(f"당류: **{nut.get(f'당류(g/{volume}ml)', 0)}g**")
        with n2:
            st.markdown("**100ml 기준**")
            for k, v in nut.items():
                if '100ml' in k:
                    st.write(f"{k}: {v}")

        st.caption("※ 추정치입니다. 정확한 영양성분은 공인기관 분석이 필요합니다.")


# ============================================================
# PAGE 9: 🧫 시작 레시피 시트
# ============================================================
def page_lab_recipe():
    st.title("🧫 시작(試作) 레시피 시트")
    st.caption("배합표 → 실험실 스케일(1L/5L/20L) 칭량표 자동 생성")

    ingredients = formulation_editor("recipe")

    if ingredients:
        result = calc_formulation(df_ing, ingredients, PH_COL)
        st.markdown("---")
        show_result_metrics(result)

        # 스케일 선택
        scales = st.multiselect("제조 스케일", [1, 5, 10, 20, 50, 100], default=[1, 5, 20], key="recipe_scales")

        if scales:
            recipes = generate_lab_recipe(ingredients, df_ing, scales)

            for scale, items in recipes.items():
                st.subheader(f"📋 {scale} 칭량표")
                rdf = pd.DataFrame(items)
                st.dataframe(rdf.style.format({
                    '배합비(%)': '{:.2f}',
                    f'칭량({scale})_g': '{:.2f}',
                }), use_container_width=True)

            # 투입순서 가이드
            st.markdown("---")
            st.subheader("🔄 투입 순서 가이드")
            order = [
                ("1️⃣", "정제수 투입 (총량의 60~70%)", "배합탱크, 교반기 100~200rpm"),
                ("2️⃣", "과즙농축액 투입", "교반하며 서서히 투입"),
                ("3️⃣", "당류 투입 (설탕/액상과당 등)", "완전 용해 확인, 10분 교반"),
                ("4️⃣", "산미료 투입 (구연산 등)", "투입 후 pH 즉시 측정"),
                ("5️⃣", "안정제 투입 (펙틴 등)", "사전 분산 후 투입"),
                ("6️⃣", "향료·색소 투입", "마지막 투입, 5분 교반"),
                ("7️⃣", "잔량 정제수로 볼륨업", "최종 Brix/pH 확인"),
            ]
            for emoji, step, note in order:
                st.write(f"{emoji} **{step}** — {note}")

            # 다운로드
            st.markdown("---")
            recipe_text = f"시작 레시피 시트\n생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            for scale, items in recipes.items():
                recipe_text += f"\n{'='*40}\n{scale} 칭량표\n{'='*40}\n"
                recipe_text += f"{'투입순서':>6}  {'원료명':<25} {'배합비':>7}  {'칭량(g)':>10}\n"
                recipe_text += "-" * 55 + "\n"
                for item in items:
                    g_col = [k for k in item.keys() if '칭량' in k][0]
                    recipe_text += f"{item['투입순서']:>6}  {item['원료명']:<25} {item['배합비(%)']:>6.2f}%  {item[g_col]:>9.2f}g\n"
            st.download_button("💾 레시피시트 다운로드", recipe_text, "시작레시피.txt", "text/plain")


# ============================================================
# PAGE 10: 📓 배합 히스토리
# ============================================================
def page_history():
    st.title("📓 배합 히스토리 & 실험노트")
    st.caption("저장된 배합 기록을 확인하고 비교합니다")

    if not st.session_state.history:
        st.info("💡 배합 시뮬레이터에서 '히스토리에 저장' 버튼을 눌러 기록을 추가하세요.")

        # 데모 데이터 추가 옵션
        if st.button("📥 데모 데이터 추가"):
            st.session_state.history.append({
                'timestamp': '2026-02-27 10:00', 'name': '사과음료 v1', 'type': '과·채음료',
                'ingredients': [
                    {'원료명': '사과농축과즙(70Brix)', '배합비(%)': 8},
                    {'원료명': '액상과당(HFCS55)', '배합비(%)': 7},
                    {'원료명': '구연산(무수)', '배합비(%)': 0.08},
                ],
                'result': {'총Brix(°)': 10.99, '예상pH': 2.72, '총산도(%)': 0.3312, '당산비': 33.2, '원재료비(원/kg)': 352.0},
                'notes': '산미가 너무 강함. 구연산 줄여야.',
            })
            st.rerun()
        return

    # 히스토리 목록
    st.subheader(f"📋 저장된 배합 ({len(st.session_state.history)}건)")
    for idx, h in enumerate(st.session_state.history):
        with st.expander(f"**{h['name']}** — {h['timestamp']} | {h['type']}"):
            # 결과 요약
            r = h.get('result', {})
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Brix", r.get('총Brix(°)', '-'))
            c2.metric("pH", r.get('예상pH', '-'))
            c3.metric("산도", f"{r.get('총산도(%)', 0):.3f}%")
            c4.metric("당산비", r.get('당산비', '-'))
            c5.metric("원가", f"{r.get('원재료비(원/kg)', 0):,.0f}")

            # 배합표
            if h.get('ingredients'):
                st.dataframe(pd.DataFrame(h['ingredients']), use_container_width=True)

            # 메모
            note = st.text_area("실험 메모", h.get('notes', ''), key=f"note_{idx}")
            st.session_state.history[idx]['notes'] = note

            # 액션 버튼
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                if st.button("📤 시뮬레이터로 로드", key=f"load_{idx}"):
                    st.session_state['sim_form'] = h['ingredients']
                    st.session_state.formulation = h['ingredients']
                    st.success("✅ 시뮬레이터에 반영됨")
            with bc2:
                if st.button("🧑‍🔬 AI 평가 요청", key=f"ai_{idx}"):
                    st.session_state['ai_form'] = h['ingredients']
                    st.info("AI 연구원 평가 탭으로 이동하세요")
            with bc3:
                if st.button("🗑️ 삭제", key=f"del_{idx}"):
                    st.session_state.history.pop(idx)
                    st.rerun()

    # 버전 비교
    if len(st.session_state.history) >= 2:
        st.markdown("---")
        st.subheader("🔀 버전 비교")
        names = [h['name'] for h in st.session_state.history]
        v1, v2 = st.columns(2)
        with v1:
            sel1 = st.selectbox("버전 A", names, key="cmp1")
        with v2:
            sel2 = st.selectbox("버전 B", names, index=min(1, len(names)-1), key="cmp2")

        h1 = next(h for h in st.session_state.history if h['name'] == sel1)
        h2 = next(h for h in st.session_state.history if h['name'] == sel2)
        r1, r2 = h1.get('result', {}), h2.get('result', {})

        compare_keys = ['총Brix(°)', '예상pH', '총산도(%)', '당산비', '원재료비(원/kg)']
        cmp_data = {'항목': compare_keys, sel1: [], sel2: [], '변화': []}
        for k in compare_keys:
            v1_val = r1.get(k, 0)
            v2_val = r2.get(k, 0)
            cmp_data[sel1].append(v1_val)
            cmp_data[sel2].append(v2_val)
            try:
                diff = float(v2_val) - float(v1_val)
                cmp_data['변화'].append(f"{diff:+.3f}")
            except:
                cmp_data['변화'].append('-')
        st.dataframe(pd.DataFrame(cmp_data), use_container_width=True)


# ============================================================
# 메인 라우팅
# ============================================================
page_map = {
    "🧪 배합 시뮬레이터": page_simulator,
    "🧑‍🔬 AI 연구원 평가": page_ai_researcher,
    "🎨 제품 이미지 생성": page_image_gen,
    "🔄 역설계": page_reverse,
    "📊 시장분석": page_market,
    "🎓 교육용 실습": page_education,
    "📋 신제품 기획서": page_planner,
    "📑 식품표시사항": page_labeling,
    "🧫 시작 레시피": page_lab_recipe,
    "📓 배합 히스토리": page_history,
}
page_map[page]()
