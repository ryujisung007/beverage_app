"""
🧪 음료개발 AI 플랫폼 v7 — 8개 개선사항 전체 적용
"""
import streamlit as st
import pandas as pd
import numpy as np
import json, os, re, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from engine import *
except ImportError as e:
    st.error(f"❌ engine.py 로딩 실패: {e}")
    st.stop()

st.set_page_config(page_title="🧪 음료개발 AI 플랫폼", page_icon="🧪", layout="wide")

# ── 데이터 ──
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "음료개발_데이터베이스_v4-1.xlsx")

@st.cache_data
def load_data(path):
    return {name: pd.read_excel(path, sheet_name=name) for name in pd.ExcelFile(path).sheet_names}

try:
    DATA = load_data(DB_PATH)
except:
    st.error("❌ 음료개발_데이터베이스_v4-1.xlsx 파일을 앱 폴더에 넣어주세요.")
    st.stop()

df_type = DATA['음료유형분류']
df_product = DATA['시장제품DB']
df_ing = DATA['원료DB']
df_spec = DATA['음료규격기준']
df_process = DATA['표준제조공정_HACCP']
df_guide = DATA['가이드배합비DB']

for c in ['Brix(°)', 'pH', '산도(%)', '감미도(설탕대비)', '예상단가(원/kg)',
          '1%사용시 Brix기여(°)', '1%사용시 산도기여(%)', '1%사용시 감미기여']:
    df_ing[c] = pd.to_numeric(df_ing[c], errors='coerce').fillna(0)
PH_COL = [c for c in df_ing.columns if 'pH영향' in str(c) or 'ΔpH' in str(c)][0]
df_ing[PH_COL] = pd.to_numeric(df_ing[PH_COL], errors='coerce').fillna(0)

try:
    OPENAI_KEY = st.secrets["openai"]["OPENAI_API_KEY"]
except:
    OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")

ING_NAMES = [''] + df_ing['원료명'].tolist()

# ── 세션 초기화 ──
for k, v in [('slots', init_slots()), ('history', []), ('product_name', ''), ('bev_type', ''),
             ('flavor', ''), ('volume', 500), ('container', 'PET'), ('target_price', 1500),
             ('ai_response', ''), ('generated_image', '')]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── [개선2] 시인성 CSS — 큰 글씨, 진한 색상 ──
st.markdown("""<style>
.sim-header {background:#1a237e;color:white;padding:10px 16px;border-radius:4px;font-weight:bold;font-size:17px;margin-bottom:12px;}
.group-label {background:#fff9c4;padding:4px 10px;font-weight:bold;font-size:14px;border-left:4px solid #f9a825;margin:6px 0;}
.cell {font-size:14px !important;color:#212121 !important;font-weight:500 !important;line-height:1.6;}
.cell-num {font-size:14px !important;color:#1565c0 !important;font-weight:600 !important;}
.cell-head {font-size:12px !important;font-weight:bold !important;color:#37474f !important;background:#e3f2fd;padding:2px 4px;border-radius:2px;}
.pass {color:#2e7d32;font-weight:bold;font-size:14px;}
.fail {color:#c62828;font-weight:bold;font-size:14px;}
.info-tag {color:#1565c0;font-weight:bold;font-size:14px;}
.result-row {font-size:15px !important;padding:3px 0;}
div[data-testid="stNumberInput"] input {font-size:14px !important;padding:4px 8px !important;color:#212121 !important;}
div[data-testid="stSelectbox"] > div {font-size:14px !important;color:#212121 !important;}
</style>""", unsafe_allow_html=True)

# ── 사이드바 ──
st.sidebar.title("🧪 음료개발 AI 플랫폼")
st.sidebar.markdown("---")
PAGES = ["🧪 배합 시뮬레이터", "🧑‍🔬 AI 연구원 평가", "🎨 제품 이미지 생성", "🔄 역설계",
         "📊 시장분석", "🎓 교육용 실습", "📋 신제품 기획서", "📑 식품표시사항",
         "🧫 시작 레시피", "📓 배합 히스토리"]
page = st.sidebar.radio("메뉴", PAGES)
st.sidebar.markdown("---")
st.sidebar.caption(f"원료 {len(df_ing)}종 · 제품 {len(df_product)}종")
if st.session_state.product_name:
    st.sidebar.info(f"📦 {st.session_state.product_name}\n{st.session_state.bev_type} / {st.session_state.flavor}")


# ============================================================
# PAGE 1: 배합 시뮬레이터 [개선1,2,7,8 적용]
# ============================================================
def page_simulator():
    st.markdown('<div class="sim-header">🧪 음료 배합비 시뮬레이터 (Formulation Simulator)</div>', unsafe_allow_html=True)
    st.caption("▶ 음료유형+맛 선택 → 가이드/AI배합비 참조 → 배합비 입력 → 규격판정 자동확인")

    # ── 헤더 ──
    h1, h2, h3, h4 = st.columns([1.5, 2, 1.5, 1.5])
    with h1:
        st.session_state.product_name = st.text_input("📋 제품명", st.session_state.product_name or "사과과채음료_시제1호")
        bev_types = df_spec['음료유형'].dropna().tolist()
        idx = bev_types.index(st.session_state.bev_type) if st.session_state.bev_type in bev_types else 0
        st.session_state.bev_type = st.selectbox("음료유형", bev_types, index=idx)
    with h2:
        bt_short = st.session_state.bev_type.split('(')[0].replace('·', '')
        guide_keys = df_guide['키(유형_맛_슬롯)'].dropna().unique()
        flavors = sorted(set(k.split('_')[1] for k in guide_keys if bt_short in k.split('_')[0].replace('·', '')))
        flavor_opts = flavors + ['직접입력']
        sel = st.selectbox("맛(Flavor)", flavor_opts)
        st.session_state.flavor = st.text_input("맛 직접입력", st.session_state.flavor) if sel == '직접입력' else sel
        use_custom = st.checkbox("✏️ 직접입력 모드 (DB에 없는 원료 입력)", key="sim_custom")
    with h3:
        st.session_state.volume = st.number_input("목표용량(ml)", 100, 2000, st.session_state.volume, 50)
        st.session_state.container = st.selectbox("포장용기", ['PET', '캔', '유리병', '종이팩', '파우치'])
    with h4:
        spec = get_spec(df_spec, st.session_state.bev_type)
        if spec:
            st.markdown(f"**📋 규격기준**")
            st.markdown(f"Bx: {spec['Brix_min']}~{spec['Brix_max']} · pH: {spec['pH_min']}~{spec['pH_max']} · 산도: {spec['산도_min']}~{spec['산도_max']}%")

    # ── [개선1a] 기존표준배합비 + [개선1b] AI추천배합비 버튼 ──
    st.markdown("---")
    bc1, bc2, bc3, bc4 = st.columns(4)
    with bc1:
        if st.button("📥 기존표준배합비 불러오기", use_container_width=True):
            if st.session_state.flavor and st.session_state.flavor != '직접입력':
                st.session_state.slots = load_guide(df_guide, st.session_state.bev_type, st.session_state.flavor, df_ing, PH_COL)
                st.rerun()
            else:
                st.warning("맛(Flavor)을 선택하세요.")
    with bc2:
        if st.button("🤖 AI 추천배합비 생성", use_container_width=True, type="primary"):
            if OPENAI_KEY:
                with st.spinner("🤖 AI가 배합비를 설계하고 있습니다..."):
                    sample = ', '.join(df_ing['원료명'].sample(min(30, len(df_ing))).tolist())
                    ai_form = call_gpt_ai_formulation(OPENAI_KEY, st.session_state.bev_type, st.session_state.flavor, sample)
                    if ai_form:
                        new_slots = init_slots()
                        for item in ai_form:
                            idx = int(item.get('슬롯', 1)) - 1
                            if idx < 0 or idx >= 19:
                                continue
                            name = item.get('원료명', '')
                            pct = safe_float(item.get('배합비', 0))
                            new_slots[idx] = fill_slot_from_db(new_slots[idx], name, df_ing, PH_COL)
                            if not new_slots[idx]['원료명']:
                                new_slots[idx]['원료명'] = name
                                new_slots[idx]['is_custom'] = True
                            new_slots[idx]['배합비(%)'] = pct
                            new_slots[idx]['AI추천_원료명'] = name
                            new_slots[idx]['AI추천_%'] = pct
                            new_slots[idx] = calc_slot_contributions(new_slots[idx])
                        st.session_state.slots = new_slots
                        st.success(f"✅ AI 추천배합 적용 ({len(ai_form)}종 원료)")
                        st.rerun()
                    else:
                        st.error("AI 배합 생성 실패. 다시 시도해주세요.")
            else:
                st.error("OpenAI API 키가 필요합니다.")
    with bc3:
        if st.button("🔄 전체 초기화", use_container_width=True):
            st.session_state.slots = init_slots()
            st.rerun()
    with bc4:
        pass

    # ── 배합표 헤더 [개선2: 큰 글씨] ──
    st.markdown("---")
    hdr_cols = st.columns([0.3, 0.8, 2.5, 1, 1.2, 0.8, 1.2, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8])
    for i, h in enumerate(['No', '구분', '원료명', '배합비(%)', 'AI추천', 'AI%', '기존표준', '표준%',
                           'Bx', '산도', '감미', '단가', '당기여', '배합량']):
        hdr_cols[i].markdown(f'<span class="cell-head">{h}</span>', unsafe_allow_html=True)

    # ── 20행 배합표 ──
    for group_name, group_rows in SLOT_GROUPS:
        if group_name != '정제수':
            st.markdown(f'<div class="group-label">{group_name}</div>', unsafe_allow_html=True)

        for rn in group_rows:
            idx = rn - 1
            s = st.session_state.slots[idx]

            if group_name == '정제수':
                ing_total = sum(safe_float(st.session_state.slots[j].get('배합비(%)', 0)) for j in range(19))
                wp = round(max(0, 100 - ing_total), 3)
                st.session_state.slots[idx]['원료명'] = '정제수'
                st.session_state.slots[idx]['배합비(%)'] = wp
                st.session_state.slots[idx]['배합량(g/kg)'] = round(wp * 10, 1)
                c = st.columns([0.3, 0.8, 2.5, 1, 1.2, 0.8, 1.2, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8])
                c[0].markdown(f'<span class="cell">{rn}</span>', unsafe_allow_html=True)
                c[1].markdown(f'<span class="cell">정제수</span>', unsafe_allow_html=True)
                c[2].markdown(f'**정제수**')
                c[3].markdown(f'<span class="cell-num">{wp:.3f}</span>', unsafe_allow_html=True)
                c[13].markdown(f'<span class="cell-num">{wp*10:.1f}</span>', unsafe_allow_html=True)
                continue

            c = st.columns([0.3, 0.8, 2.5, 1, 1.2, 0.8, 1.2, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8])
            c[0].markdown(f'<span class="cell">{rn}</span>', unsafe_allow_html=True)
            c[1].markdown(f'<span class="cell">{group_name[:3]}</span>', unsafe_allow_html=True)

            # 원료 선택
            with c[2]:
                cur = s.get('원료명', '')
                def_idx = ING_NAMES.index(cur) if cur in ING_NAMES else 0
                picked = st.selectbox("원료", ING_NAMES, index=def_idx, label_visibility="collapsed", key=f"i{idx}")
                if picked and picked != cur:
                    st.session_state.slots[idx] = fill_slot_from_db(st.session_state.slots[idx], picked, df_ing, PH_COL)
                    s = st.session_state.slots[idx]
                # 직접입력
                if not picked and use_custom:
                    cname = st.text_input("입력", s.get('원료명', ''), label_visibility="collapsed", key=f"c{idx}")
                    if cname:
                        st.session_state.slots[idx]['원료명'] = cname
                        st.session_state.slots[idx]['is_custom'] = True
                        s = st.session_state.slots[idx]

            # 배합비
            with c[3]:
                pct = st.number_input("pct", 0.0, 100.0, float(s.get('배합비(%)', 0)), 0.1,
                                     format="%.3f", label_visibility="collapsed", key=f"p{idx}")
                st.session_state.slots[idx]['배합비(%)'] = pct

            # [개선1] AI추천 + 기존표준 표시
            c[4].markdown(f'<span class="cell">{s.get("AI추천_원료명","")[:8]}</span>', unsafe_allow_html=True)
            c[5].markdown(f'<span class="cell-num">{s.get("AI추천_%",0)}</span>', unsafe_allow_html=True)
            c[6].markdown(f'<span class="cell">{s.get("기존표준_원료명","")[:8]}</span>', unsafe_allow_html=True)
            c[7].markdown(f'<span class="cell-num">{s.get("기존표준_%",0)}</span>', unsafe_allow_html=True)

            # 직접입력 편집 가능
            if s.get('is_custom'):
                with c[8]:
                    bx = st.number_input("Bx", 0.0, 100.0, float(s.get('당도(Bx)', 0)), 0.1, label_visibility="collapsed", key=f"bx{idx}")
                    st.session_state.slots[idx]['당도(Bx)'] = bx
                    st.session_state.slots[idx]['Brix(°)'] = bx
                    st.session_state.slots[idx]['1%Brix기여'] = round(bx / 100, 4) if bx else 0
                with c[9]:
                    ac = st.number_input("ac", 0.0, 50.0, float(s.get('산도(%)', 0)), 0.01, label_visibility="collapsed", key=f"ac{idx}")
                    st.session_state.slots[idx]['산도(%)'] = ac
                    st.session_state.slots[idx]['1%산도기여'] = round(ac / 100, 4) if ac else 0
                with c[10]:
                    sw = st.number_input("sw", 0.0, 50000.0, float(s.get('감미도', 0)), 0.1, label_visibility="collapsed", key=f"sw{idx}")
                    st.session_state.slots[idx]['감미도'] = sw
                    st.session_state.slots[idx]['1%감미기여'] = round(sw / 100, 4) if sw else 0
                with c[11]:
                    pr = st.number_input("pr", 0, 500000, int(s.get('단가(원/kg)', 0)), 100, label_visibility="collapsed", key=f"pr{idx}")
                    st.session_state.slots[idx]['단가(원/kg)'] = pr
            else:
                c[8].markdown(f'<span class="cell">{s.get("당도(Bx)",0)}</span>', unsafe_allow_html=True)
                c[9].markdown(f'<span class="cell">{s.get("산도(%)",0)}</span>', unsafe_allow_html=True)
                c[10].markdown(f'<span class="cell">{s.get("감미도",0)}</span>', unsafe_allow_html=True)
                c[11].markdown(f'<span class="cell">{safe_float(s.get("단가(원/kg)",0)):,.0f}</span>', unsafe_allow_html=True)

            st.session_state.slots[idx] = calc_slot_contributions(st.session_state.slots[idx])
            s = st.session_state.slots[idx]
            c[12].markdown(f'<span class="cell-num">{s.get("당기여",0):.2f}</span>', unsafe_allow_html=True)
            c[13].markdown(f'<span class="cell-num">{s.get("배합량(g/kg)",0):.1f}</span>', unsafe_allow_html=True)

    # ── [개선8] AI 직접입력 추정 ──
    custom_idxs = [i for i, s in enumerate(st.session_state.slots) if s.get('is_custom') and s.get('원료명')]
    if custom_idxs and OPENAI_KEY:
        st.markdown("---")
        if st.button("🤖 직접입력 원료 → AI 이화학규격 추정 (결과 출력)", key="ai_est", use_container_width=True):
            results = []
            for idx in custom_idxs:
                s = st.session_state.slots[idx]
                with st.spinner(f"'{s['원료명']}' 추정 중..."):
                    try:
                        est = call_gpt_estimate_ingredient(OPENAI_KEY, s['원료명'])
                        for k_from, k_to in [('Brix','당도(Bx)'), ('Brix','Brix(°)'), ('산도_pct','산도(%)'),
                                              ('감미도_설탕대비','감미도'), ('감미도_설탕대비','감미도(설탕대비)'),
                                              ('예상단가_원kg','단가(원/kg)'), ('1pct_Brix기여','1%Brix기여'),
                                              ('1pct_pH영향','1%pH영향'), ('1pct_산도기여','1%산도기여'),
                                              ('1pct_감미기여','1%감미기여')]:
                            st.session_state.slots[idx][k_to] = safe_float(est.get(k_from, 0))
                        st.session_state.slots[idx] = calc_slot_contributions(st.session_state.slots[idx])
                        results.append({'원료명': s['원료명'], **est})
                    except Exception as e:
                        st.error(f"'{s['원료명']}' 실패: {e}")
            if results:
                st.markdown("### 🤖 AI 추정 결과")
                st.dataframe(pd.DataFrame(results), use_container_width=True)
                st.caption("※ 추정값은 배합표에 자동 반영됨. 직접 수정 가능.")
                st.rerun()

    # ── 합계 + 결과요약 ──
    st.markdown("---")
    result = calc_formulation(st.session_state.slots, st.session_state.volume)

    st.markdown('<div class="sim-header">▶ 시뮬레이션 결과 요약</div>', unsafe_allow_html=True)
    spec = get_spec(df_spec, st.session_state.bev_type)
    comp = check_compliance(result, spec) if spec else {}

    # [개선7] 정제수비율 정확 표시 + [개선8] 규격이탈 표현
    r1, r2 = st.columns(2)
    with r1:
        pct_ok = abs(result['배합비합계(%)']-100) < 0.01
        for label, val, status in [
            ("배합비 합계(%)", f"{result['배합비합계(%)']:.3f}", "✅ 100% 충족" if pct_ok else f"⚠️ {result['배합비합계(%)']:.3f}%"),
            ("예상 당도(Bx)", f"{result['예상당도(Bx)']:.2f}", comp.get('당도', ('',))[0]),
            ("예상 산도(%)", f"{result['예상산도(%)']:.4f}", comp.get('산도', ('',))[0]),
            ("예상 감미도", f"{result['예상감미도']:.4f}", ""),
            ("원재료비(원/kg)", f"{result['원재료비(원/kg)']:,.0f}", ""),
            ("원재료비(원/병)", f"{result['원재료비(원/병)']:,.0f}", ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'info-tag')
            st.markdown(f'<div class="result-row"><b>{label}</b> &nbsp; <code>{val}</code> &nbsp; <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)
    with r2:
        for label, val, status in [
            ("원료 종류(개)", f"{result['원료종류(개)']}", ""),
            ("정제수 비율(%)", f"{result['정제수비율(%)']:.1f}", comp.get('정제수비율', ('',))[0]),
            ("pH 규격(참고)", f"{result['예상pH']:.2f}", comp.get('pH', ('',))[0] if 'pH' in comp else "ℹ️ 실측 필요"),
            ("과즙함량(%)", f"{result['과즙함량(%)']:.1f}", ""),
            ("당산비", f"{result['당산비']}", ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'info-tag')
            st.markdown(f'<div class="result-row"><b>{label}</b> &nbsp; <code>{val}</code> &nbsp; <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)

    # [개선8] 정제수 자동조정
    if not pct_ok:
        ing_tot = sum(safe_float(st.session_state.slots[j].get('배합비(%)', 0)) for j in range(19))
        if ing_tot <= 100:
            if st.button("💧 정제수 자동조정 (100% 맞추기)", use_container_width=True, type="primary"):
                st.session_state.slots[19]['배합비(%)'] = round(100 - ing_tot, 3)
                st.session_state.slots[19]['배합량(g/kg)'] = round((100 - ing_tot) * 10, 1)
                st.rerun()
        else:
            st.warning(f"⚠️ 원료합계 {ing_tot:.3f}% > 100%. 원료 배합비를 줄여주세요.")

    # ── 하단 버튼 ──
    st.markdown("---")
    b1, b2, b3 = st.columns(3)
    with b1:
        sn = st.text_input("저장명", f"{st.session_state.product_name}_{datetime.now().strftime('%H%M')}")
        if st.button("💾 히스토리에 저장", use_container_width=True):
            st.session_state.history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'name': sn,
                'type': st.session_state.bev_type, 'flavor': st.session_state.flavor,
                'slots': [s.copy() for s in st.session_state.slots], 'result': result.copy(), 'notes': ''})
            st.success(f"✅ 저장 (총 {len(st.session_state.history)}건)")
    with b2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🧑‍🔬 AI 연구원에게 넘기기 →", use_container_width=True, type="primary"):
            st.success("좌측 메뉴 'AI 연구원 평가' 선택")
    with b3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📋 기획서/HACCP →", use_container_width=True):
            st.success("좌측 메뉴 '신제품 기획서' 선택")


# ============================================================
# PAGE 2: AI 연구원 [개선6: 전용 페르소나]
# ============================================================
def page_ai_researcher():
    st.title("🧑‍🔬 AI 음료개발연구원 평가")
    st.caption("20년 경력 수석 연구원 'Dr. 이음료' 페르소나")
    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요"); return

    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return

    st.markdown(f"**{st.session_state.product_name}** | {st.session_state.bev_type} | {st.session_state.flavor}")
    with st.expander("📋 현재 배합표", expanded=True):
        st.dataframe(pd.DataFrame(active, columns=['원료명', '배합비(%)']), use_container_width=True)
        st.markdown(f"**Brix {result['예상당도(Bx)']}° | pH {result['예상pH']} | 산도 {result['예상산도(%)']:.4f}% | 원가 {result['원재료비(원/kg)']:,.0f}원/kg**")

    target = st.text_input("목표 컨셉", "과즙감 강조, 상큼한 산미밸런스")
    if st.button("🧑‍🔬 평가 요청", type="primary", use_container_width=True):
        form_text = '\n'.join([f"{n}: {p:.3f}%" for n, p in active])
        form_text += f"\n정제수: {result['정제수비율(%)']:.1f}%"
        form_text += f"\nBrix:{result['예상당도(Bx)']}° pH:{result['예상pH']} 산도:{result['예상산도(%)']:.4f}% 감미도:{result['예상감미도']:.4f} 당산비:{result['당산비']} 원가:{result['원재료비(원/kg)']:.0f}원/kg"
        with st.spinner("🧑‍🔬 Dr. 이음료 분석 중..."):
            try:
                st.session_state.ai_response = call_gpt(OPENAI_KEY, PERSONA_RESEARCHER, form_text + f"\n\n목표: {target}")
            except Exception as e:
                st.error(f"API 오류: {e}"); return

    if st.session_state.ai_response:
        st.markdown("---")
        st.markdown(st.session_state.ai_response)
        mod = parse_modified_formulation(st.session_state.ai_response)
        if mod:
            st.markdown("---")
            st.dataframe(pd.DataFrame(mod), use_container_width=True)
            if st.button("✅ 수정배합 적용", type="primary"):
                new = init_slots()
                for i, m in enumerate(mod):
                    if i >= 19: break
                    new[i] = fill_slot_from_db(new[i], m['원료명'], df_ing, PH_COL)
                    new[i]['배합비(%)'] = safe_float(m.get('배합비(%)', 0))
                    new[i] = calc_slot_contributions(new[i])
                st.session_state.slots = new
                st.rerun()


# ============================================================
# PAGE 3: 이미지 생성
# ============================================================
def page_image():
    st.title("🎨 AI 제품 이미지 생성")
    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요"); return
    prompt = build_dalle_prompt(st.session_state.product_name, st.session_state.bev_type,
                                st.session_state.slots, st.session_state.container, st.session_state.volume)
    with st.expander("프롬프트"):
        prompt = st.text_area("프롬프트", prompt, height=100)
    if st.button("🎨 이미지 생성", type="primary", use_container_width=True):
        with st.spinner("생성 중..."):
            try:
                st.session_state.generated_image = call_dalle(OPENAI_KEY, prompt)
            except Exception as e:
                st.error(f"실패: {e}")
    if st.session_state.generated_image:
        st.image(st.session_state.generated_image, use_container_width=True)


# ============================================================
# PAGE 4: 역설계
# ============================================================
def page_reverse():
    st.title("🔄 시판제품 역설계")
    cats = ['전체'] + df_product['대분류'].dropna().unique().tolist()
    sel_cat = st.selectbox("대분류", cats)
    f = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
    sel = st.selectbox("제품", f['제품명'].dropna().tolist())
    if sel:
        prod = df_product[df_product['제품명'] == sel].iloc[0]
        st.markdown(f"**{sel}** — {prod.get('제조사','')} | {prod.get('세부유형','')} | {prod.get('용량(ml)','')}ml")
        if st.button("🔄 역설계 → 시뮬레이터 반영", type="primary", use_container_width=True):
            st.session_state.slots = reverse_engineer(prod, df_ing, PH_COL)
            st.session_state.product_name = f"{sel}_역설계"
            st.success("✅ 반영됨")


# ============================================================
# PAGE 5: 시장분석
# ============================================================
def page_market():
    st.title("📊 시장제품 분석")
    c1, c2 = st.columns(2)
    sel_cat = c1.selectbox("대분류", ['전체'] + df_product['대분류'].dropna().unique().tolist())
    f = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
    k1, k2, k3 = st.columns(3)
    k1.metric("제품수", len(f)); k2.metric("제조사", f['제조사'].nunique()); k3.metric("평균가격", f"{f['가격(원)'].dropna().mean():,.0f}원")
    st.bar_chart(f['제조사'].value_counts().head(15))
    st.dataframe(f[['No', '대분류', '세부유형', '제품명', '제조사', '용량(ml)', '가격(원)']], use_container_width=True, height=300)


# ============================================================
# PAGE 6: 교육
# ============================================================
def page_education():
    st.title("🎓 음료 배합 실습 도구")
    with st.expander("📖 배합 설계 가이드", expanded=True):
        st.markdown("""
**1단계**: 원재료 (과즙함량 충족)\n**2단계**: 당류 (설탕 1% ≈ Brix 1°)\n**3단계**: 산미료 (구연산 0.1% → pH↓0.1)\n**4단계**: 향료·안정제\n**5단계**: 규격확인""")
    with st.expander("🔍 원료 DB 탐색"):
        scat = st.selectbox("분류", df_ing['원료대분류'].unique())
        st.dataframe(df_ing[df_ing['원료대분류'] == scat][['원료명', '원료소분류', 'Brix(°)', '감미도(설탕대비)', PH_COL, '예상단가(원/kg)']], use_container_width=True)


# ============================================================
# PAGE 7: 기획서 + HACCP [개선3,4,6 적용]
# ============================================================
def page_planner():
    st.title("📋 신제품 기획서 + 공정시방서 + HACCP")

    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return

    st.markdown(f"**{st.session_state.product_name}** | {st.session_state.bev_type} | {st.session_state.volume}ml {st.session_state.container}")

    # 규격 요약 [개선4: 테이블식 정렬]
    mc = st.columns(6)
    mc[0].metric("Brix", result['예상당도(Bx)']); mc[1].metric("pH", result['예상pH'])
    mc[2].metric("산도", f"{result['예상산도(%)']:.4f}%"); mc[3].metric("감미도", f"{result['예상감미도']:.4f}")
    mc[4].metric("당산비", result['당산비']); mc[5].metric("원가(원/kg)", f"{result['원재료비(원/kg)']:,.0f}")

    tabs = st.tabs(["📋 기획서", "🏭 공정시방서(SOP)", "📄 HACCP 서류 (6종)", "🤖 AI 분석보고서"])

    # ── TAB 1: 기획서 [개선4: 테이블 정렬] ──
    with tabs[0]:
        st.subheader("신제품 기획서")
        vol = st.session_state.volume
        raw_bottle = result['원재료비(원/병)']
        pkg_cost = {'PET':120, '캔':90, '유리병':200, '종이팩':80, '파우치':60}.get(st.session_state.container, 100)
        mfg = raw_bottle * 0.4
        total = raw_bottle + pkg_cost + mfg
        price = st.session_state.target_price
        margin = price - total

        cost_data = pd.DataFrame({
            '항목': ['원재료비', '포장재비', '제조비(추정)', '총원가', '판매가', '마진'],
            '금액(원/병)': [f'{raw_bottle:,.0f}', f'{pkg_cost:,.0f}', f'{mfg:,.0f}',
                          f'{total:,.0f}', f'{price:,.0f}', f'{margin:,.0f}'],
            '비율(%)': [f'{raw_bottle/price*100:.1f}', f'{pkg_cost/price*100:.1f}', f'{mfg/price*100:.1f}',
                       f'{total/price*100:.1f}', '100.0', f'{margin/price*100:.1f}'],
        })
        st.dataframe(cost_data, use_container_width=True, hide_index=True)

    # ── TAB 2: 공정시방서 [개선3,6: 생산관리자 페르소나] ──
    with tabs[1]:
        st.subheader("🏭 공정시방서 / 작업지시서 (SOP)")
        matched = match_process(st.session_state.bev_type, df_process)

        if not matched.empty:
            sop_text = haccp_sop(st.session_state.bev_type, df_process, st.session_state.product_name, st.session_state.slots)
            st.code(sop_text, language=None)
            st.download_button("💾 SOP 다운로드", sop_text, f"SOP_{st.session_state.product_name}.txt")

            if OPENAI_KEY:
                if st.button("🤖 AI 생산관리자 공정분석", key="ai_sop"):
                    form_text = '\n'.join([f"{n}:{p:.3f}%" for n, p in active])
                    with st.spinner("🏭 생산관리자 AI 분석 중..."):
                        resp = call_gpt(OPENAI_KEY, PERSONA_PRODUCTION, f"제품: {st.session_state.product_name}\n유형: {st.session_state.bev_type}\n배합:\n{form_text}")
                        st.markdown(resp)
        else:
            st.warning("매칭 공정 없음")

    # ── TAB 3: HACCP 6종 [개선3: 식약처 양식] ──
    with tabs[2]:
        st.subheader("📄 HACCP 서류 (식약처 표준양식)")
        matched = match_process(st.session_state.bev_type, df_process)

        if not matched.empty:
            docs = {
                "① 위해분석표 (HA Worksheet)": haccp_ha_worksheet(st.session_state.bev_type, df_process),
                "② CCP 결정도 (Decision Tree)": haccp_ccp_decision_tree(st.session_state.bev_type, df_process),
                "③ CCP 관리계획서 (HACCP Plan)": haccp_ccp_plan(st.session_state.bev_type, df_process),
                "④ CCP 모니터링 일지 (빈 양식)": haccp_monitoring_log(st.session_state.bev_type, df_process),
                "⑤ 공정흐름도 (Flow Diagram)": haccp_flow_diagram(st.session_state.bev_type, df_process),
                "⑥ 작업표준서 (SOP)": haccp_sop(st.session_state.bev_type, df_process, st.session_state.product_name, st.session_state.slots),
            }
            for title, doc in docs.items():
                with st.expander(title, expanded=False):
                    st.code(doc, language=None)
                    st.download_button(f"💾 다운로드", doc, f"HACCP_{title[:10]}_{st.session_state.product_name}.txt", key=f"dl_{title}")

            all_docs = '\n\n\n'.join([f"{'='*70}\n{t}\n{'='*70}\n{d}" for t, d in docs.items()])
            st.download_button("📦 HACCP 6종 일괄 다운로드", all_docs, f"HACCP_전체_{st.session_state.product_name}.txt", type="primary")

            # [개선6] AI 품질전문가 분석
            if OPENAI_KEY:
                if st.button("🤖 AI 품질전문가 HACCP 분석", key="ai_haccp"):
                    form_text = '\n'.join([f"{n}:{p:.3f}%" for n, p in active])
                    with st.spinner("📄 HACCP 전문가 AI 분석 중..."):
                        resp = call_gpt(OPENAI_KEY, PERSONA_QA, f"제품: {st.session_state.product_name}\n유형: {st.session_state.bev_type}\n배합:\n{form_text}")
                        st.markdown(resp)
        else:
            st.warning("매칭 공정 없음")

    # ── TAB 4: AI 분석보고서 [개선4,6] ──
    with tabs[3]:
        st.subheader("🤖 AI 분석보고서")
        if not OPENAI_KEY:
            st.error("OpenAI API 키 필요"); return
        report_type = st.selectbox("보고서 유형", ["🧑‍🔬 R&D 연구원 관점", "🏭 생산관리자 관점", "📄 품질전문가 관점"])
        persona = {"🧑‍🔬 R&D 연구원 관점": PERSONA_PLANNER, "🏭 생산관리자 관점": PERSONA_PRODUCTION, "📄 품질전문가 관점": PERSONA_QA}[report_type]
        if st.button("📝 AI 보고서 생성", type="primary", use_container_width=True):
            form_text = '\n'.join([f"{n}:{p:.3f}%" for n, p in active])
            spec_info = f"Brix:{result['예상당도(Bx)']} pH:{result['예상pH']} 산도:{result['예상산도(%)']:.4f}%"
            with st.spinner("AI 보고서 작성 중..."):
                resp = call_gpt(OPENAI_KEY, persona, f"제품: {st.session_state.product_name}\n유형: {st.session_state.bev_type}\n규격: {spec_info}\n배합:\n{form_text}\n\n종합 분석보고서를 작성하세요.")
                st.markdown(resp)
                st.download_button("💾 보고서 다운로드", resp, f"AI보고서_{st.session_state.product_name}.txt")


# ============================================================
# PAGE 8: 식품표시사항 [개선5: 식약처 기준 적용]
# ============================================================
def page_labeling():
    st.title("📑 식품표시사항 자동생성")
    st.caption("식품등의 표시기준 (식약처 고시) 기반")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return

    label = generate_food_label(st.session_state.slots, st.session_state.product_name,
                                st.session_state.volume, st.session_state.bev_type)

    # 전체 표시사항 테이블
    label_items = []
    for k, v in label.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                label_items.append({'표시항목': f'  {sk}', '내용': str(sv)})
        else:
            label_items.append({'표시항목': k, '내용': str(v)})
    st.dataframe(pd.DataFrame(label_items), use_container_width=True, hide_index=True)

    # 상세 분석
    st.markdown("---")
    with st.expander("📋 원재료명 상세 (식품공전 기준)"):
        st.markdown(f"**원재료명 표시순서** (많이 사용한 순): 원재료명은 일괄표시면에 7포인트 이상으로 표시")
        for i, (n, p) in enumerate(sorted(active, key=lambda x: x[1], reverse=True), 1):
            marker = "🔴" if p >= 2 else "⚪"
            st.markdown(f"{marker} {i}. **{n}** — {p:.3f}% {'(2%이상: 함량표시 대상)' if p >= 2 else '(2%미만)'}")

    with st.expander("⚠️ 알레르기 유발물질 분석"):
        st.markdown(f"**검출 결과**: {label['⑧ 알레르기 유발물질']}")
        st.caption("※ 식약처 고시 21종 알레르기 유발물질 기준: 난류, 우유, 메밀, 땅콩, 대두, 밀, 고등어, 게, 새우, 돼지고기, 복숭아, 토마토, 호두, 닭고기, 쇠고기, 오징어, 조개류, 잣, 아황산류")

    with st.expander("📊 영양성분표 (의무표시 9종)"):
        nut = label['⑦ 영양성분']
        nut_df = pd.DataFrame([{'영양성분': k, '함량': v} for k, v in nut.items()])
        st.dataframe(nut_df, use_container_width=True, hide_index=True)
        st.caption("※ 추정치. 정확한 수치는 공인시험기관 분석 필요. 1일 영양성분 기준치 대비 % 별도 산출 필요.")

    # 다운로드
    label_text = '\n'.join([f"{item['표시항목']}: {item['내용']}" for item in label_items])
    st.download_button("💾 표시사항 다운로드", label_text, f"식품표시_{st.session_state.product_name}.txt")


# ============================================================
# PAGE 9: 시작 레시피
# ============================================================
def page_lab_recipe():
    st.title("🧫 시작(試作) 레시피 시트")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return
    scales = st.multiselect("제조 스케일", [1, 5, 10, 20, 50, 100], default=[1, 5, 20])
    if scales:
        recipes = generate_lab_recipe(st.session_state.slots, scales)
        for scale, items in recipes.items():
            st.subheader(f"📋 {scale} 칭량표")
            st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)


# ============================================================
# PAGE 10: 히스토리
# ============================================================
def page_history():
    st.title("📓 배합 히스토리")
    if not st.session_state.history:
        st.info("시뮬레이터에서 '히스토리에 저장'으로 추가하세요."); return
    for idx, h in enumerate(st.session_state.history):
        with st.expander(f"**{h['name']}** — {h['timestamp']}"):
            r = h.get('result', {})
            c = st.columns(5)
            c[0].metric("Brix", r.get('예상당도(Bx)', '-'))
            c[1].metric("pH", r.get('예상pH', '-'))
            c[2].metric("산도", f"{r.get('예상산도(%)', 0):.4f}%")
            c[3].metric("당산비", r.get('당산비', '-'))
            c[4].metric("원가", f"{r.get('원재료비(원/kg)', 0):,.0f}")
            if st.button("📤 시뮬레이터 로드", key=f"ld{idx}"):
                st.session_state.slots = [s.copy() for s in h['slots']]
                st.success("✅ 반영됨")
            if st.button("🗑️ 삭제", key=f"rm{idx}"):
                st.session_state.history.pop(idx)
                st.rerun()


# ── 라우팅 ──
{"🧪 배합 시뮬레이터": page_simulator, "🧑‍🔬 AI 연구원 평가": page_ai_researcher,
 "🎨 제품 이미지 생성": page_image, "🔄 역설계": page_reverse,
 "📊 시장분석": page_market, "🎓 교육용 실습": page_education,
 "📋 신제품 기획서": page_planner, "📑 식품표시사항": page_labeling,
 "🧫 시작 레시피": page_lab_recipe, "📓 배합 히스토리": page_history}[page]()
