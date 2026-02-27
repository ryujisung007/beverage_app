"""
🧪 음료개발 AI 플랫폼 v6
엑셀 시뮬레이터 디자인 재현 + 10개 기능 + 전체 데이터 파이프라인
"""
import streamlit as st
import pandas as pd
import numpy as np
import json, os, re, sys
from datetime import datetime

# engine.py 경로 보장 (Streamlit Cloud 호환)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from engine import (
        SLOT_GROUPS, EMPTY_SLOT, init_slots, fill_slot_from_db, calc_slot_contributions,
        calc_formulation_from_slots, get_spec_range, check_compliance,
        load_guide_formulation, reverse_engineer,
        generate_food_label, generate_lab_recipe,
        call_gpt_researcher, call_gpt_estimate_ingredient, call_dalle, build_dalle_prompt,
        parse_modified_formulation,
        generate_haccp_ha_worksheet, generate_haccp_ccp_decision_tree,
        generate_haccp_ccp_plan, generate_haccp_monitoring_log,
        generate_flow_diagram, generate_sop,
    )
except ImportError as e:
    st.error(f"❌ engine.py 로딩 실패: {e}\n\nengine.py 파일이 app.py와 같은 폴더에 있는지 확인하세요.")
    st.stop()

st.set_page_config(page_title="🧪 음료개발 AI 플랫폼", page_icon="🧪", layout="wide")

# ============================================================
# 데이터 로딩
# ============================================================
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

NUM_COLS = ['Brix(°)', 'pH', '산도(%)', '감미도(설탕대비)', '예상단가(원/kg)',
            '1%사용시 Brix기여(°)', '1%사용시 산도기여(%)', '1%사용시 감미기여']
for c in NUM_COLS:
    df_ing[c] = pd.to_numeric(df_ing[c], errors='coerce').fillna(0)
PH_COL = [c for c in df_ing.columns if 'pH영향' in str(c) or 'ΔpH' in str(c)][0]
df_ing[PH_COL] = pd.to_numeric(df_ing[PH_COL], errors='coerce').fillna(0)

try:
    OPENAI_KEY = st.secrets["openai"]["OPENAI_API_KEY"]
except (KeyError, TypeError):
    OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")

ING_NAMES = [''] + df_ing['원료명'].tolist()

# ============================================================
# 세션 초기화 — 전체 파이프라인 공유 데이터
# ============================================================
if 'slots' not in st.session_state:
    st.session_state.slots = init_slots()
if 'history' not in st.session_state:
    st.session_state.history = []
if 'product_name' not in st.session_state:
    st.session_state.product_name = ''
if 'bev_type' not in st.session_state:
    st.session_state.bev_type = ''
if 'flavor' not in st.session_state:
    st.session_state.flavor = ''
if 'volume' not in st.session_state:
    st.session_state.volume = 500
if 'container' not in st.session_state:
    st.session_state.container = 'PET'
if 'target_price' not in st.session_state:
    st.session_state.target_price = 1500
if 'ai_response' not in st.session_state:
    st.session_state.ai_response = ''
if 'generated_image' not in st.session_state:
    st.session_state.generated_image = ''

# ============================================================
# CSS 스타일
# ============================================================
st.markdown("""<style>
.sim-header {background: #1a237e; color: white; padding: 8px 16px; border-radius: 4px; font-weight: bold; font-size: 16px; margin-bottom: 10px;}
.sim-subheader {background: #e8eaf6; padding: 4px 12px; border-radius: 3px; font-weight: bold; font-size: 13px; margin: 6px 0;}
.result-box {background: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 4px; padding: 10px; margin: 4px 0;}
.pass {color: #2e7d32; font-weight: bold;}
.fail {color: #c62828; font-weight: bold;}
.info-tag {color: #1565c0; font-weight: bold;}
.group-label {background: #fff9c4; padding: 2px 8px; font-weight: bold; font-size: 13px; border-left: 3px solid #f9a825; margin: 4px 0;}
.slot-text {font-size: 13px !important; color: #212121 !important; font-weight: 500 !important;}
.slot-num {font-size: 13px !important; color: #1565c0 !important; font-weight: 600 !important;}
.slot-header {font-size: 11px !important; font-weight: bold !important; color: #37474f !important;}
div[data-testid="stNumberInput"] input {font-size: 13px !important; padding: 4px 8px !important; color: #212121 !important;}
div[data-testid="stSelectbox"] > div {font-size: 13px !important; color: #212121 !important;}
</style>""", unsafe_allow_html=True)

# ============================================================
# 사이드바
# ============================================================
st.sidebar.title("🧪 음료개발 AI 플랫폼")
st.sidebar.markdown("---")
PAGES = [
    "🧪 배합 시뮬레이터",
    "🧑‍🔬 AI 연구원 평가",
    "🎨 제품 이미지 생성",
    "🔄 역설계",
    "📊 시장분석",
    "🎓 교육용 실습",
    "📋 신제품 기획서",
    "📑 식품표시사항",
    "🧫 시작 레시피",
    "📓 배합 히스토리",
]
page = st.sidebar.radio("메뉴", PAGES)
st.sidebar.markdown("---")
st.sidebar.caption(f"원료 {len(df_ing)}종 · 제품 {len(df_product)}종 · 가이드 {len(df_guide)}건")

if st.session_state.product_name:
    st.sidebar.info(f"📦 현재 제품: **{st.session_state.product_name}**\n{st.session_state.bev_type} / {st.session_state.flavor}")


# ============================================================
# PAGE 1: 🧪 배합 시뮬레이터 (엑셀 디자인)
# ============================================================
def page_simulator():
    st.markdown('<div class="sim-header">🧪 음료 배합비 시뮬레이터 (Formulation Simulator)</div>', unsafe_allow_html=True)
    st.caption("▶ 음료유형+맛 선택 → 가이드배합비 참조 → 배합비 입력(100%기준) → 규격판정 자동확인")

    # ── 헤더 영역: 제품정보 ──
    h1, h2, h3, h4 = st.columns([1.5, 2, 1.5, 1.5])
    with h1:
        st.session_state.product_name = st.text_input("제품명", st.session_state.product_name or "사과과채음료_시제1호", key="sim_pname")
        bev_types = df_spec['음료유형'].dropna().tolist()
        st.session_state.bev_type = st.selectbox("음료유형", bev_types, index=bev_types.index(st.session_state.bev_type) if st.session_state.bev_type in bev_types else 0, key="sim_btype")
    with h2:
        # 맛(Flavor) — 가이드DB에서 추출 + 직접입력
        guide_keys = df_guide['키(유형_맛_슬롯)'].dropna().unique()
        bt_short = st.session_state.bev_type.split('(')[0].replace('·', '')
        flavors = sorted(set(k.split('_')[1] for k in guide_keys if bt_short in k.split('_')[0].replace('·', '')))
        flavor_options = flavors + ['직접입력']
        sel_flavor = st.selectbox("맛(Flavor)", flavor_options, key="sim_flavor")
        if sel_flavor == '직접입력':
            st.session_state.flavor = st.text_input("맛 직접입력", st.session_state.flavor, key="sim_flavor_custom")
        else:
            st.session_state.flavor = sel_flavor

        use_custom = st.checkbox("직접입력▶", help="드롭다운에 없는 맛은 직접입력하세요", key="sim_custom_toggle")
    with h3:
        st.session_state.volume = st.number_input("목표용량(ml)", 100, 2000, st.session_state.volume, 50, key="sim_vol")
        st.session_state.container = st.selectbox("포장용기", ['PET', '캔', '유리병', '종이팩', '파우치'], key="sim_pkg")
    with h4:
        spec = get_spec_range(df_spec, st.session_state.bev_type)
        if spec:
            st.markdown(f"""<div class="sim-subheader">📋 규격</div>
Bx: {spec.get('Brix_min',0)}~{spec.get('Brix_max',0)} · pH: {spec.get('pH_min',0)}~{spec.get('pH_max',0)} · 산도: {spec.get('산도_min',0)}~{spec.get('산도_max',0)}%""", unsafe_allow_html=True)
        target_cost = st.number_input("목표단가(원/kg)", 100, 10000, 1500, 100, key="sim_tcost")

    # ── 가이드 배합 로딩 ──
    gc1, gc2, gc3 = st.columns([2, 1, 1])
    with gc1:
        if st.session_state.flavor and st.session_state.flavor != '직접입력':
            st.caption(f"🔹 직접입력(F4) 우선적용 | 🟢=가이드DB 매칭됨 | 🟡=노랑=직접입력미매칭")
    with gc2:
        if st.button("📥 가이드배합비 불러오기", use_container_width=True, key="sim_load_guide"):
            if st.session_state.flavor and st.session_state.flavor not in ['직접입력', '']:
                st.session_state.slots = load_guide_formulation(
                    df_guide, st.session_state.bev_type.split('(')[0].replace('·', ''),
                    st.session_state.flavor, df_ing, PH_COL
                )
                st.rerun()
    with gc3:
        if st.button("🔄 전체 초기화", use_container_width=True, key="sim_reset"):
            st.session_state.slots = init_slots()
            st.rerun()

    st.markdown("---")

    # ── 20행 배합표 입력 ──
    # 헤더
    cols_h = st.columns([0.4, 1, 2.5, 1, 1.5, 1, 1.5, 1, 0.8, 0.8, 0.8, 1, 1, 1, 1])
    headers = ['No', '구분', '원료명(드롭다운)', '배합비(%)', 'AI추천 원료명', 'AI추천%',
               '실제사례 원료명', '사례%', '당도(Bx)', '산도(%)', '감미도',
               '단가(원/kg)', '당기여', '산기여', '배합량(g/kg)']
    for i, h in enumerate(headers):
        cols_h[i].markdown(f"<span class='slot-header'>{h}</span>", unsafe_allow_html=True)

    # 행 그룹별 렌더링
    slot_idx = 0
    for group_name, group_rows in SLOT_GROUPS:
        if group_name != '정제수':
            st.markdown(f'<div class="group-label">{group_name}</div>', unsafe_allow_html=True)

        for row_num in group_rows:
            idx = row_num - 1
            s = st.session_state.slots[idx]

            if group_name == '정제수':
                # 정제수 자동 계산
                total_pct = sum(st.session_state.slots[j].get('배합비(%)', 0) for j in range(19))
                water = round(max(0, 100 - total_pct), 3)
                st.session_state.slots[idx]['원료명'] = '정제수'
                st.session_state.slots[idx]['배합비(%)'] = water
                st.session_state.slots[idx]['배합량(g/kg)'] = round(water * 10, 1)
                cols = st.columns([0.4, 1, 2.5, 1, 1.5, 1, 1.5, 1, 0.8, 0.8, 0.8, 1, 1, 1, 1])
                cols[0].markdown(f"<span class='slot-text'>{row_num}</span>", unsafe_allow_html=True)
                cols[1].markdown(f"<span class='slot-text'>정제수</span>", unsafe_allow_html=True)
                cols[2].markdown(f"**정제수**")
                cols[3].markdown(f"**{water:.3f}**")
                cols[14].markdown(f"**{water*10:.1f}**")
                continue

            cols = st.columns([0.4, 1, 2.5, 1, 1.5, 1, 1.5, 1, 0.8, 0.8, 0.8, 1, 1, 1, 1])
            cols[0].markdown(f"<span class='slot-text'>{row_num}</span>", unsafe_allow_html=True)
            cols[1].markdown(f"<span class='slot-text'>{group_name[:4]}</span>", unsafe_allow_html=True)

            # 원료 선택 (드롭다운 + 직접입력)
            with cols[2]:
                current_name = s.get('원료명', '')
                if current_name and current_name in ING_NAMES:
                    default_idx = ING_NAMES.index(current_name)
                else:
                    default_idx = 0

                selected = st.selectbox("원료", ING_NAMES, index=default_idx,
                                       label_visibility="collapsed", key=f"ing_{idx}")

                # 선택 변경 시 DB에서 채우기
                if selected and selected != s.get('원료명', ''):
                    st.session_state.slots[idx] = fill_slot_from_db(
                        st.session_state.slots[idx], selected, df_ing, PH_COL)
                    s = st.session_state.slots[idx]

            # 직접입력 (DB에 없는 원료)
            if not selected and use_custom:
                with cols[2]:
                    custom_name = st.text_input("직접입력", s.get('원료명', ''),
                                                label_visibility="collapsed", key=f"cust_{idx}")
                    if custom_name and custom_name != s.get('원료명', ''):
                        st.session_state.slots[idx]['원료명'] = custom_name
                        st.session_state.slots[idx]['is_custom'] = True
                        s = st.session_state.slots[idx]

            # 배합비
            with cols[3]:
                pct = st.number_input("배합비", 0.0, 100.0, float(s.get('배합비(%)', 0)),
                                     step=0.1, format="%.3f",
                                     label_visibility="collapsed", key=f"pct_{idx}")
                st.session_state.slots[idx]['배합비(%)'] = pct

            # AI추천/실사례 (읽기전용)
            cols[4].markdown(f"<span class='slot-text'>{s.get('AI추천_원료명','')[:10]}</span>", unsafe_allow_html=True)
            cols[5].markdown(f"<span class='slot-text'>{s.get('AI추천_%', 0)}</span>", unsafe_allow_html=True)
            cols[6].markdown(f"<span class='slot-text'>{s.get('실제사례_원료명','')[:10]}</span>", unsafe_allow_html=True)
            cols[7].markdown(f"<span class='slot-text'>{s.get('실제사례_%', 0)}</span>", unsafe_allow_html=True)

            # 직접입력 원료인 경우: 이화학 규격 편집 가능
            if s.get('is_custom'):
                with cols[8]:
                    bx = st.number_input("Bx", 0.0, 100.0, float(s.get('당도(Bx)', 0)), 0.1,
                                        label_visibility="collapsed", key=f"bx_{idx}")
                    st.session_state.slots[idx]['당도(Bx)'] = bx
                    st.session_state.slots[idx]['Brix(°)'] = bx
                    st.session_state.slots[idx]['1%Brix기여'] = round(bx / 100, 4) if bx else 0
                with cols[9]:
                    ac = st.number_input("산도", 0.0, 50.0, float(s.get('산도(%)', 0)), 0.01,
                                        label_visibility="collapsed", key=f"ac_{idx}")
                    st.session_state.slots[idx]['산도(%)'] = ac
                    st.session_state.slots[idx]['1%산도기여'] = round(ac / 100, 4) if ac else 0
                with cols[10]:
                    sw = st.number_input("감미", 0.0, 50000.0, float(s.get('감미도', 0)), 0.1,
                                        label_visibility="collapsed", key=f"sw_{idx}")
                    st.session_state.slots[idx]['감미도'] = sw
                    st.session_state.slots[idx]['감미도(설탕대비)'] = sw
                    st.session_state.slots[idx]['1%감미기여'] = round(sw / 100, 4) if sw else 0
                with cols[11]:
                    pr = st.number_input("단가", 0, 500000, int(s.get('단가(원/kg)', 0)), 100,
                                        label_visibility="collapsed", key=f"pr_{idx}")
                    st.session_state.slots[idx]['단가(원/kg)'] = pr
            else:
                cols[8].markdown(f"<span class='slot-text'>{s.get('당도(Bx)',0)}</span>", unsafe_allow_html=True)
                cols[9].markdown(f"<span class='slot-text'>{s.get('산도(%)',0)}</span>", unsafe_allow_html=True)
                cols[10].markdown(f"<span class='slot-text'>{s.get('감미도',0)}</span>", unsafe_allow_html=True)
                cols[11].markdown(f"<span class='slot-text'>{s.get('단가(원/kg)',0):,.0f}</span>", unsafe_allow_html=True)

            # 기여도 계산
            st.session_state.slots[idx] = calc_slot_contributions(st.session_state.slots[idx])
            s = st.session_state.slots[idx]

            cols[12].markdown(f"<span class='slot-text'>{s.get('당기여',0):.2f}</span>", unsafe_allow_html=True)
            cols[13].markdown(f"<span class='slot-text'>{s.get('산기여',0):.4f}</span>", unsafe_allow_html=True)
            cols[14].markdown(f"<span class='slot-text'>{s.get('배합량(g/kg)',0):.1f}</span>", unsafe_allow_html=True)

    # ── AI 원료 추정 버튼 (직접입력 원료용) ──
    custom_slots = [i for i, s in enumerate(st.session_state.slots)
                    if s.get('is_custom') and s.get('원료명')]
    if custom_slots and OPENAI_KEY:
        st.markdown("---")
        if st.button("🤖 직접입력 원료 → AI 이화학규격 추정", key="sim_ai_estimate"):
            estimation_results = []
            for idx in custom_slots:
                s = st.session_state.slots[idx]
                with st.spinner(f"'{s['원료명']}' AI 추정 중..."):
                    try:
                        est = call_gpt_estimate_ingredient(OPENAI_KEY, s['원료명'])
                        st.session_state.slots[idx]['당도(Bx)'] = est.get('Brix', 0)
                        st.session_state.slots[idx]['Brix(°)'] = est.get('Brix', 0)
                        st.session_state.slots[idx]['산도(%)'] = est.get('산도_pct', 0)
                        st.session_state.slots[idx]['감미도'] = est.get('감미도_설탕대비', 0)
                        st.session_state.slots[idx]['감미도(설탕대비)'] = est.get('감미도_설탕대비', 0)
                        st.session_state.slots[idx]['단가(원/kg)'] = est.get('예상단가_원kg', 0)
                        st.session_state.slots[idx]['1%Brix기여'] = est.get('1pct_Brix기여', 0)
                        st.session_state.slots[idx]['1%pH영향'] = est.get('1pct_pH영향', 0)
                        st.session_state.slots[idx]['1%산도기여'] = est.get('1pct_산도기여', 0)
                        st.session_state.slots[idx]['1%감미기여'] = est.get('1pct_감미기여', 0)
                        st.session_state.slots[idx] = calc_slot_contributions(st.session_state.slots[idx])
                        estimation_results.append({
                            '원료명': s['원료명'],
                            'Brix(°)': est.get('Brix', 0),
                            'pH': est.get('pH', 0),
                            '산도(%)': est.get('산도_pct', 0),
                            '감미도': est.get('감미도_설탕대비', 0),
                            '단가(원/kg)': est.get('예상단가_원kg', 0),
                            '1%Brix기여': est.get('1pct_Brix기여', 0),
                            '1%pH영향': est.get('1pct_pH영향', 0),
                            '1%산도기여': est.get('1pct_산도기여', 0),
                            '1%감미기여': est.get('1pct_감미기여', 0),
                        })
                    except Exception as e:
                        st.error(f"'{s['원료명']}' 추정 실패: {e}")

            if estimation_results:
                st.markdown("#### 🤖 AI 추정 결과")
                est_df = pd.DataFrame(estimation_results)
                st.dataframe(est_df, use_container_width=True)
                st.caption("※ AI 추정값입니다. 배합표에 자동 반영되었으며, 직접 수정도 가능합니다.")
                st.rerun()

    # ── 합계 행 ──
    st.markdown("---")

    # 정제수 비율 직접 계산 (calc 함수와 별도로, 렌더링 시점의 정확한 값)
    _total_ing_pct = sum(st.session_state.slots[j].get('배합비(%)', 0) for j in range(19))
    _water_pct = round(max(0, 100 - _total_ing_pct), 2)

    result = calc_formulation_from_slots(st.session_state.slots)
    # 정제수비율 강제 동기화
    result['정제수비율(%)'] = _water_pct
    # 원재료비(원/병) = 원/kg × 용량(L)
    result['원재료비(원/병)'] = round(result['원재료비(원/kg)'] * st.session_state.volume / 1000, 1)

    tc = st.columns([0.4, 1, 2.5, 1, 1.5, 1, 1.5, 1, 0.8, 0.8, 0.8, 1, 1, 1, 1])
    tc[0].markdown("**합계**")
    tc[3].markdown(f"**{result['배합비합계(%)']:.3f}**")
    sum_brix = sum(s.get('당기여', 0) for s in st.session_state.slots)
    sum_acid = sum(s.get('산기여', 0) for s in st.session_state.slots)
    sum_cost = sum(s.get('단가기여(원/kg)', 0) for s in st.session_state.slots)
    tc[12].markdown(f"**{sum_brix:.2f}**")
    tc[13].markdown(f"**{sum_acid:.4f}**")
    tc[14].markdown(f"**{result['배합비합계(%)']*10:.1f}**")

    # ── 시뮬레이션 결과 요약 ──
    st.markdown("---")
    st.markdown('<div class="sim-header">▶ 시뮬레이션 결과 요약</div>', unsafe_allow_html=True)

    spec = get_spec_range(df_spec, st.session_state.bev_type)
    compliance = check_compliance(result, spec) if spec else {}

    r1, r2 = st.columns(2)
    with r1:
        # 배합비 합계 체크 + 정제수 자동조정
        pct_status = "✅ 100% 충족"
        if abs(result['배합비합계(%)']-100) >= 0.01:
            pct_status = f"⚠️ 합계 {result['배합비합계(%)']:.3f}% (100%가 아님)"

        items = [
            ("배합비 합계(%)", f"{result['배합비합계(%)']:.3f}", pct_status),
            ("예상 당도(Bx)", f"{result['예상당도(Bx)']:.2f}", compliance.get('당도', ('', True))[0]),
            ("예상 산도(%)", f"{result['예상산도(%)']:.3f}", compliance.get('산도', ('', True))[0]),
            ("예상 감미도", f"{result['예상감미도']:.3f}", ""),
            ("원재료비(원/kg)", f"{result['원재료비(원/kg)']:,.0f}", compliance.get('원재료비', ('', True))[0]),
            ("원재료비(원/병)", f"{result['원재료비(원/병)']:,.0f}", ""),
        ]
        for label, val, status in items:
            is_pass = '✅' in status if status else True
            cls = 'pass' if is_pass else ('fail' if '⚠️' in status else 'info-tag')
            st.markdown(f"**{label}** &nbsp;&nbsp; `{val}` &nbsp;&nbsp; <span class='{cls}'>{status}</span>", unsafe_allow_html=True)
    with r2:
        items2 = [
            ("원료 사용 종류(개)", f"{result['원료종류(개)']}", ""),
            ("정제수 비율(%)", f"{result['정제수비율(%)']:.1f}", compliance.get('정제수비율', ('', True))[0]),
            ("pH 규격 (참고)", f"{result['예상pH']:.2f}", compliance.get('pH', ('', None))[0] if 'pH' in compliance else "ℹ️ pH규격: 실측 필요"),
            ("과즙함량(%)", f"{result['과즙함량(%)']:.1f}", ""),
            ("당산비", f"{result['당산비']}", ""),
        ]
        for label, val, status in items2:
            cls = 'pass' if '✅' in status else ('fail' if '⚠️' in status else 'info-tag')
            st.markdown(f"**{label}** &nbsp;&nbsp; `{val}` &nbsp;&nbsp; <span class='{cls}'>{status}</span>", unsafe_allow_html=True)

    # ── 정제수 자동조정 ──
    if abs(result['배합비합계(%)']-100) >= 0.01:
        if st.button("💧 정제수 자동조정 (100% 맞추기)", use_container_width=True, key="sim_water_adj"):
            # 원료합계(정제수 제외) 기준으로 정제수 재계산
            ing_total = sum(st.session_state.slots[j].get('배합비(%)', 0) for j in range(19))
            if ing_total <= 100:
                st.session_state.slots[19]['배합비(%)'] = round(100 - ing_total, 3)
                st.session_state.slots[19]['배합량(g/kg)'] = round((100 - ing_total) * 10, 1)
                st.success(f"✅ 정제수 {100 - ing_total:.3f}%로 조정, 합계 100%")
                st.rerun()
            else:
                st.warning(f"⚠️ 원료합계가 {ing_total:.3f}%로 100%를 초과합니다. 원료 배합비를 줄여주세요.")

    # ── 하단 버튼들 ──
    st.markdown("---")
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        save_name = st.text_input("배합명", f"{st.session_state.product_name}_{datetime.now().strftime('%H%M')}", key="sim_savename")
        if st.button("💾 히스토리에 저장", use_container_width=True):
            st.session_state.history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'name': save_name, 'type': st.session_state.bev_type,
                'flavor': st.session_state.flavor,
                'slots': [s.copy() for s in st.session_state.slots],
                'result': result.copy(), 'notes': '',
            })
            st.success(f"✅ '{save_name}' 저장 (총 {len(st.session_state.history)}건)")
    with b2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🧑‍🔬 AI 연구원에게 넘기기 →", use_container_width=True, type="primary"):
            st.session_state['goto_ai'] = True
            st.success("✅ 배합표가 AI 연구원에게 전달됩니다. 좌측 메뉴에서 'AI 연구원 평가'를 선택하세요.")
    with b3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🎨 이미지 생성 →", use_container_width=True):
            st.success("좌측 메뉴에서 '제품 이미지 생성'을 선택하세요.")
    with b4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📋 기획서 생성 →", use_container_width=True):
            st.success("좌측 메뉴에서 '신제품 기획서'를 선택하세요.")


# ============================================================
# PAGE 2: 🧑‍🔬 AI 연구원 평가
# ============================================================
def page_ai_researcher():
    st.title("🧑‍🔬 AI 음료개발연구원 평가")
    st.caption("20년 경력 수석 연구원 'Dr. 이음료'가 현재 배합표를 평가합니다")

    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요 (.streamlit/secrets.toml)")
        return

    # 현재 배합 표시
    result = calc_formulation_from_slots(st.session_state.slots)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if s.get('배합비(%)', 0) > 0 and s['원료명']]

    if not active:
        st.warning("배합표가 비어있습니다. 시뮬레이터에서 먼저 배합을 입력하세요.")
        return

    st.markdown(f"**제품**: {st.session_state.product_name} | **유형**: {st.session_state.bev_type} | **맛**: {st.session_state.flavor}")

    with st.expander("📋 현재 배합표 확인", expanded=True):
        for name, pct in active:
            st.write(f"  {name}: {pct:.3f}%")
        st.write(f"  정제수: {result['정제수비율(%)']:.1f}%")
        st.markdown(f"**Brix {result['예상당도(Bx)']}° | pH {result['예상pH']} | 산도 {result['예상산도(%)']:.3f}% | 원가 {result['원재료비(원/kg)']:,.0f}원/kg**")

    target = st.text_input("목표 컨셉", "과즙감 강조, 상큼한 산미밸런스", key="ai_target")

    if st.button("🧑‍🔬 평가 요청", type="primary", use_container_width=True):
        form_text = '\n'.join([f"{name}: {pct:.3f}%" for name, pct in active])
        form_text += f"\n정제수: {result['정제수비율(%)']:.1f}%"
        form_text += f"\n\nBrix: {result['예상당도(Bx)']}° | pH: {result['예상pH']} | 산도: {result['예상산도(%)']:.4f}% | 감미도: {result['예상감미도']:.4f} | 당산비: {result['당산비']} | 원가: {result['원재료비(원/kg)']:.0f}원/kg"

        spec = get_spec_range(df_spec, st.session_state.bev_type)
        spec_text = f"Brix {spec['Brix_min']}~{spec['Brix_max']}, pH {spec['pH_min']}~{spec['pH_max']}, 산도 {spec['산도_min']}~{spec['산도_max']}%" if spec else ""

        with st.spinner("🧑‍🔬 Dr. 이음료 분석 중..."):
            try:
                st.session_state.ai_response = call_gpt_researcher(OPENAI_KEY, form_text, st.session_state.bev_type, f"{spec_text}\n목표: {target}")
            except Exception as e:
                st.error(f"API 오류: {e}")
                return

    if st.session_state.ai_response:
        st.markdown("---")
        st.subheader("🧑‍🔬 Dr. 이음료의 평가")
        st.markdown(st.session_state.ai_response)

        modified = parse_modified_formulation(st.session_state.ai_response)
        if modified:
            st.markdown("---")
            st.subheader("📋 제안된 수정 배합표")
            st.dataframe(pd.DataFrame(modified), use_container_width=True)
            if st.button("✅ 수정배합표를 시뮬레이터에 적용", type="primary"):
                new_slots = init_slots()
                for i, m in enumerate(modified):
                    if i >= 19:
                        break
                    new_slots[i] = fill_slot_from_db(new_slots[i], m['원료명'], df_ing, PH_COL)
                    new_slots[i]['배합비(%)'] = m['배합비(%)']
                    new_slots[i] = calc_slot_contributions(new_slots[i])
                st.session_state.slots = new_slots
                st.success("✅ 시뮬레이터에 반영됨!")
                st.rerun()


# ============================================================
# PAGE 3: 🎨 제품 이미지 생성
# ============================================================
def page_image():
    st.title("🎨 AI 제품 이미지 생성")
    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요")
        return

    st.markdown(f"**제품**: {st.session_state.product_name} | **유형**: {st.session_state.bev_type}")
    prompt = build_dalle_prompt(st.session_state.product_name, st.session_state.bev_type,
                                st.session_state.slots, st.session_state.container, st.session_state.volume)

    with st.expander("🔍 프롬프트 확인/수정"):
        prompt = st.text_area("프롬프트", prompt, height=100, key="img_prompt")

    if st.button("🎨 이미지 생성 (DALL-E 3)", type="primary", use_container_width=True):
        with st.spinner("🎨 디자인 생성 중... (15~30초)"):
            try:
                st.session_state.generated_image = call_dalle(OPENAI_KEY, prompt)
            except Exception as e:
                st.error(f"생성 실패: {e}")

    if st.session_state.generated_image:
        st.image(st.session_state.generated_image, use_container_width=True)
        st.markdown(f"[📥 이미지 다운로드]({st.session_state.generated_image})")


# ============================================================
# PAGE 4: 🔄 역설계
# ============================================================
def page_reverse():
    st.title("🔄 시판제품 역설계")

    c1, c2 = st.columns(2)
    with c1:
        cats = ['전체'] + df_product['대분류'].dropna().unique().tolist()
        sel_cat = st.selectbox("대분류", cats, key="rev_cat")
    with c2:
        filtered = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
        sel = st.selectbox("제품 선택", filtered['제품명'].dropna().tolist(), key="rev_sel")

    if sel:
        prod = df_product[df_product['제품명'] == sel].iloc[0]
        st.markdown(f"**{sel}** — {prod.get('제조사', '')} | {prod.get('세부유형', '')} | {prod.get('용량(ml)', '')}ml | {prod.get('가격(원)', '')}원")

        for i in range(1, 6):
            col = f'배합순위{i}' if i > 1 else '배합순위1(원재료/배합비%/원산지)'
            v = prod.get(col)
            if pd.notna(v) and str(v).strip() not in ['—', '-', '0', '']:
                st.write(f"  {i}순위: {v}")

        if st.button("🔄 역설계 → 시뮬레이터에 반영", type="primary", use_container_width=True):
            st.session_state.slots = reverse_engineer(prod, df_ing, PH_COL)
            st.session_state.product_name = f"{sel}_역설계"
            st.session_state.bev_type = str(prod.get('세부유형', ''))
            st.success("✅ 시뮬레이터에 반영됨! '배합 시뮬레이터' 메뉴에서 확인하세요.")


# ============================================================
# PAGE 5: 📊 시장분석
# ============================================================
def page_market():
    st.title("📊 시장제품 분석 대시보드")
    c1, c2, c3 = st.columns(3)
    with c1:
        sel_cat = st.selectbox("대분류", ['전체'] + df_product['대분류'].dropna().unique().tolist())
    with c2:
        f = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
        subs = ['전체'] + f['세부유형'].dropna().unique().tolist()
        sel_sub = st.selectbox("세부유형", subs)
    with c3:
        sel_mk = st.selectbox("제조사", ['전체'] + sorted(df_product['제조사'].dropna().unique().tolist()))

    f = df_product.copy()
    if sel_cat != '전체': f = f[f['대분류'] == sel_cat]
    if sel_sub != '전체': f = f[f['세부유형'] == sel_sub]
    if sel_mk != '전체': f = f[f['제조사'] == sel_mk]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("제품수", len(f))
    k2.metric("제조사", f['제조사'].nunique())
    k3.metric("평균가격", f"{f['가격(원)'].dropna().mean():,.0f}원")
    k4.metric("평균용량", f"{f['용량(ml)'].dropna().mean():,.0f}ml")

    tab1, tab2, tab3 = st.tabs(["🏢 제조사", "💰 가격", "🔬 원재료"])
    with tab1:
        st.bar_chart(f['제조사'].value_counts().head(15))
    with tab2:
        st.bar_chart(f.groupby('세부유형')['가격(원)'].mean().dropna().sort_values(ascending=False))
    with tab3:
        raw1 = f['배합순위1(원재료/배합비%/원산지)'].dropna().apply(lambda x: str(x).split('/')[0].strip())
        st.bar_chart(raw1.value_counts().head(20))
    st.dataframe(f[['No', '대분류', '세부유형', '제품명', '제조사', '용량(ml)', '가격(원)']], use_container_width=True, height=300)


# ============================================================
# PAGE 6: 🎓 교육용 실습
# ============================================================
def page_education():
    st.title("🎓 음료 배합 실습 도구")
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
**1단계 원재료**: 과즙함량 충족 (과채음료≥10%, 주스 100%)
**2단계 당류**: 설탕 1%≈Brix 1° / 제로→수크랄로스 0.01~0.02%
**3단계 산미료**: 구연산 0.1%→pH~0.1↓, 산도~0.064%↑
**4단계 향료·안정제**: 향료 0.05~0.15% / 펙틴 0.1~0.2%
**5단계 규격확인** → 미세조정""")

    with st.expander("🔍 원료 DB 탐색"):
        scat = st.selectbox("분류", df_ing['원료대분류'].unique(), key="edu_scat")
        cols = ['원료명', '원료소분류', 'Brix(°)', '감미도(설탕대비)', PH_COL, '1%사용시 산도기여(%)', '예상단가(원/kg)']
        st.dataframe(df_ing[df_ing['원료대분류'] == scat][[c for c in cols if c in df_ing.columns]], use_container_width=True)

    st.caption("💡 시뮬레이터에서 직접 배합을 입력해서 도전하세요!")
    if st.button("🧪 시뮬레이터로 이동", use_container_width=True):
        if btype != '자유':
            st.session_state.bev_type = btype
        st.success("좌측 메뉴에서 '배합 시뮬레이터'를 선택하세요.")


# ============================================================
# PAGE 7: 📋 신제품 기획서 + 공정시방서/작업지시서 + HACCP 6종
# ============================================================
def page_planner():
    st.title("📋 신제품 기획서 + 공정시방서/작업지시서")

    result = calc_formulation_from_slots(st.session_state.slots)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if s.get('배합비(%)', 0) > 0 and s['원료명']]

    if not active:
        st.warning("배합표가 비어있습니다. 시뮬레이터에서 먼저 배합을 입력하세요.")
        return

    st.markdown(f"**{st.session_state.product_name}** | {st.session_state.bev_type} | {st.session_state.volume}ml {st.session_state.container}")

    # 규격 요약
    with st.expander("📊 품질규격 요약", expanded=True):
        m = st.columns(6)
        m[0].metric("Brix", result['예상당도(Bx)'])
        m[1].metric("pH", result['예상pH'])
        m[2].metric("산도", f"{result['예상산도(%)']:.3f}%")
        m[3].metric("감미도", f"{result['예상감미도']:.3f}")
        m[4].metric("당산비", result['당산비'])
        m[5].metric("원가", f"{result['원재료비(원/kg)']:,.0f}")

    # 공정 매칭
    st.markdown("---")
    btype = st.session_state.bev_type.split('(')[0]
    matched = df_process[df_process['음료유형'].str.contains(btype, na=False)]

    tabs = st.tabs(["📋 기획서", "🏭 공정시방서/작업지시서", "📄 HACCP 서류 (6종)"])

    with tabs[0]:
        st.subheader("신제품 기획서")
        price = st.session_state.target_price
        vol = st.session_state.volume
        raw_bottle = result['원재료비(원/kg)'] * vol / 1000
        pkg_cost = {'PET': 120, '캔': 90, '유리병': 200, '종이팩': 80, '파우치': 60}.get(st.session_state.container, 100)
        mfg = raw_bottle * 0.4
        total = raw_bottle + pkg_cost + mfg
        margin = price - total

        c1, c2 = st.columns(2)
        with c1:
            st.write(f"원재료비: **{raw_bottle:,.0f}원**/병")
            st.write(f"포장재비: **{pkg_cost:,.0f}원**/병")
            st.write(f"제조비(추정): **{mfg:,.0f}원**/병")
            st.write(f"**총원가: {total:,.0f}원/병**")
        with c2:
            st.write(f"마진: **{margin:,.0f}원** ({margin/price*100:.1f}%)")

        if st.button("📄 기획서 텍스트 다운로드"):
            lines = [f"신제품 기획서: {st.session_state.product_name}", f"유형: {st.session_state.bev_type}", f"용량: {vol}ml {st.session_state.container}", ""]
            lines.append("■ 배합표")
            for name, pct in active:
                lines.append(f"  {name}: {pct:.3f}%")
            lines.append(f"  정제수: {result['정제수비율(%)']:.1f}%")
            lines.append(f"\n■ 규격: Brix {result['예상당도(Bx)']}° | pH {result['예상pH']} | 산도 {result['예상산도(%)']:.4f}%")
            lines.append(f"\n■ 원가: {total:,.0f}원/병 (마진 {margin:,.0f}원, {margin/price*100:.1f}%)")
            st.download_button("💾 다운로드", '\n'.join(lines), f"기획서_{st.session_state.product_name}.txt")

    with tabs[1]:
        st.subheader("🏭 공정시방서 / 작업지시서 (SOP)")
        if not matched.empty:
            sop_text = generate_sop(st.session_state.bev_type, df_process, st.session_state.product_name, st.session_state.slots)
            st.text(sop_text)
            st.download_button("💾 SOP 다운로드", sop_text, f"SOP_{st.session_state.product_name}.txt")
        else:
            st.warning("매칭되는 공정이 없습니다.")

    with tabs[2]:
        st.subheader("📄 HACCP 서류 (식약처 표준양식)")
        if not matched.empty:
            haccp_docs = {
                "1. 위해분석표 (HA Worksheet)": generate_haccp_ha_worksheet(st.session_state.bev_type, df_process),
                "2. CCP 결정도 (Decision Tree)": generate_haccp_ccp_decision_tree(st.session_state.bev_type, df_process),
                "3. CCP 관리계획서 (HACCP Plan)": generate_haccp_ccp_plan(st.session_state.bev_type, df_process),
                "4. CCP 모니터링 일지": generate_haccp_monitoring_log(st.session_state.bev_type, df_process),
                "5. 공정흐름도 (Flow Diagram)": generate_flow_diagram(st.session_state.bev_type, df_process),
                "6. 작업표준서 (SOP)": generate_sop(st.session_state.bev_type, df_process, st.session_state.product_name, st.session_state.slots),
            }
            for title, doc_text in haccp_docs.items():
                with st.expander(title):
                    st.text(doc_text)
                    st.download_button(f"💾 {title} 다운로드", doc_text,
                                      f"HACCP_{title.split('.')[0].strip()}_{st.session_state.product_name}.txt",
                                      key=f"dl_{title}")

            # 전체 다운로드
            all_docs = '\n\n\n'.join([f"{'='*80}\n{t}\n{'='*80}\n{d}" for t, d in haccp_docs.items()])
            st.download_button("📦 HACCP 6종 일괄 다운로드", all_docs,
                              f"HACCP_전체_{st.session_state.product_name}.txt", type="primary")


# ============================================================
# PAGE 8: 📑 식품표시사항
# ============================================================
def page_labeling():
    st.title("📑 식품표시사항 자동생성")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if s.get('배합비(%)', 0) > 0 and s['원료명']]
    if not active:
        st.warning("배합표가 비어있습니다.")
        return

    label = generate_food_label(st.session_state.slots, st.session_state.product_name, st.session_state.volume)

    st.subheader("📋 원재료명")
    st.info(label['원재료명'])
    st.caption("※ 식품공전: 많이 사용한 순서대로 표시")

    st.subheader("📊 영양성분표")
    nut = label['영양성분']
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{st.session_state.volume}ml 기준**")
        for k, v in nut.items():
            if str(st.session_state.volume) in k:
                st.write(f"{k}: **{v}**")
    with c2:
        st.markdown("**100ml 기준**")
        for k, v in nut.items():
            if '100ml' in k:
                st.write(f"{k}: {v}")
    st.caption("※ 추정치. 정확한 수치는 공인기관 분석 필요.")


# ============================================================
# PAGE 9: 🧫 시작 레시피
# ============================================================
def page_lab_recipe():
    st.title("🧫 시작(試作) 레시피 시트")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if s.get('배합비(%)', 0) > 0 and s['원료명']]
    if not active:
        st.warning("배합표가 비어있습니다.")
        return

    scales = st.multiselect("제조 스케일", [1, 5, 10, 20, 50, 100], default=[1, 5, 20])
    if scales:
        recipes = generate_lab_recipe(st.session_state.slots, scales)
        for scale, items in recipes.items():
            st.subheader(f"📋 {scale} 칭량표")
            st.dataframe(pd.DataFrame(items), use_container_width=True)

        st.markdown("---")
        st.subheader("🔄 투입 순서 가이드")
        for e, s, n in [
            ("1️⃣", "정제수 투입 (60~70%)", "교반기 100~200rpm"),
            ("2️⃣", "과즙농축액", "교반하며 서서히"),
            ("3️⃣", "당류", "완전용해 확인, 10분 교반"),
            ("4️⃣", "산미료", "pH 즉시 측정"),
            ("5️⃣", "안정제", "사전분산 후 투입"),
            ("6️⃣", "향료·색소", "마지막, 5분 교반"),
            ("7️⃣", "잔량 정제수로 볼륨업", "최종 Brix/pH 확인"),
        ]:
            st.write(f"{e} **{s}** — {n}")

        recipe_text = '\n'.join([f"{scale} 칭량표\n" + pd.DataFrame(items).to_string() for scale, items in recipes.items()])
        st.download_button("💾 레시피 다운로드", recipe_text, "시작레시피.txt")


# ============================================================
# PAGE 10: 📓 배합 히스토리
# ============================================================
def page_history():
    st.title("📓 배합 히스토리 & 실험노트")

    if not st.session_state.history:
        st.info("💡 시뮬레이터에서 '히스토리에 저장'으로 기록을 추가하세요.")
        return

    for idx, h in enumerate(st.session_state.history):
        with st.expander(f"**{h['name']}** — {h['timestamp']} | {h.get('type', '')} {h.get('flavor', '')}"):
            r = h.get('result', {})
            c = st.columns(5)
            c[0].metric("Brix", r.get('예상당도(Bx)', '-'))
            c[1].metric("pH", r.get('예상pH', '-'))
            c[2].metric("산도", f"{r.get('예상산도(%)', 0):.3f}%")
            c[3].metric("당산비", r.get('당산비', '-'))
            c[4].metric("원가", f"{r.get('원재료비(원/kg)', 0):,.0f}")

            if h.get('slots'):
                active = [(s['원료명'], s['배합비(%)']) for s in h['slots'] if s.get('배합비(%)', 0) > 0 and s['원료명']]
                st.dataframe(pd.DataFrame(active, columns=['원료명', '배합비(%)']), use_container_width=True)

            note = st.text_area("실험메모", h.get('notes', ''), key=f"note_{idx}")
            st.session_state.history[idx]['notes'] = note

            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("📤 시뮬레이터로 로드", key=f"load_{idx}"):
                    if h.get('slots'):
                        st.session_state.slots = [s.copy() for s in h['slots']]
                        st.success("✅ 반영됨")
            with b2:
                if st.button("🧑‍🔬 AI평가 요청", key=f"ai_{idx}"):
                    if h.get('slots'):
                        st.session_state.slots = [s.copy() for s in h['slots']]
                    st.info("'AI 연구원 평가' 메뉴로 이동하세요")
            with b3:
                if st.button("🗑️ 삭제", key=f"del_{idx}"):
                    st.session_state.history.pop(idx)
                    st.rerun()

    if len(st.session_state.history) >= 2:
        st.markdown("---")
        st.subheader("🔀 버전 비교")
        names = [h['name'] for h in st.session_state.history]
        c1, c2 = st.columns(2)
        sel1 = c1.selectbox("A", names, key="cmp1")
        sel2 = c2.selectbox("B", names, index=min(1, len(names)-1), key="cmp2")
        h1 = next(h for h in st.session_state.history if h['name'] == sel1)
        h2 = next(h for h in st.session_state.history if h['name'] == sel2)
        r1, r2 = h1.get('result', {}), h2.get('result', {})
        keys = ['예상당도(Bx)', '예상pH', '예상산도(%)', '당산비', '원재료비(원/kg)']
        data = {'항목': keys, sel1: [r1.get(k, 0) for k in keys], sel2: [r2.get(k, 0) for k in keys]}
        st.dataframe(pd.DataFrame(data), use_container_width=True)


# ============================================================
# 메인 라우팅
# ============================================================
{
    "🧪 배합 시뮬레이터": page_simulator,
    "🧑‍🔬 AI 연구원 평가": page_ai_researcher,
    "🎨 제품 이미지 생성": page_image,
    "🔄 역설계": page_reverse,
    "📊 시장분석": page_market,
    "🎓 교육용 실습": page_education,
    "📋 신제품 기획서": page_planner,
    "📑 식품표시사항": page_labeling,
    "🧫 시작 레시피": page_lab_recipe,
    "📓 배합 히스토리": page_history,
}[page]()
