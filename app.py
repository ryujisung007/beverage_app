"""
🧪 음료개발 AI 플랫폼 v7.1 — 6개 추가 개선
"""
import streamlit as st
import pandas as pd
import numpy as np
import json, os, re, sys, io
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from engine import *
except ImportError as e:
    st.error(f"❌ engine.py 로딩 실패: {e}")
    st.stop()

st.set_page_config(page_title="🧪 음료개발 AI 플랫폼", page_icon="🧪", layout="wide")

# ── 데이터 로드 ──
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "음료개발_데이터베이스_v4-1.xlsx")

@st.cache_data
def load_data(path):
    return {n: pd.read_excel(path, sheet_name=n) for n in pd.ExcelFile(path).sheet_names}

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

# [개선3] 원료 목록에 직접입력 옵션 추가
ING_NAMES = ['(선택)', '✏️ 직접입력'] + df_ing['원료명'].tolist()

# ── 세션 초기화 ──
for k, v in [('slots', init_slots()), ('history', []), ('product_name', ''), ('bev_type', ''),
             ('flavor', ''), ('volume', 500), ('container', 'PET'), ('target_price', 1500),
             ('ai_response', ''), ('generated_image', ''), ('concept_result', None),
             ('edu_slots', init_slots())]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── [개선4] CSS — 헤더 100%↑(24px), 본문 16px ──
st.markdown("""<style>
.sim-header{background:#1a237e;color:white;padding:12px 18px;border-radius:6px;font-weight:bold;font-size:22px;margin-bottom:14px;}
.grp-label{background:#fff9c4;padding:6px 14px;font-weight:bold;font-size:17px;border-left:5px solid #f9a825;margin:10px 0;border-radius:3px;}
.hdr{font-size:14px !important;font-weight:800 !important;color:#1a237e !important;background:#e3f2fd;padding:5px 6px;border-radius:3px;text-align:center;line-height:2.0;}
.cel{font-size:15px !important;color:#212121 !important;font-weight:500 !important;line-height:2.0;}
.cnum{font-size:15px !important;color:#1565c0 !important;font-weight:700 !important;}
.pass{color:#2e7d32;font-weight:bold;font-size:16px;}
.fail{color:#c62828;font-weight:bold;font-size:16px;}
.infot{color:#1565c0;font-weight:bold;font-size:15px;}
.rrow{font-size:17px !important;padding:5px 0;line-height:2.0;}
.edu-step{background:#f3e5f5;border-left:5px solid #9c27b0;padding:14px 18px;border-radius:5px;margin:10px 0;font-size:16px;}
.edu-warn{background:#fff3e0;border-left:5px solid #ff9800;padding:10px 14px;border-radius:4px;margin:6px 0;font-size:15px;}
.concept-box{background:#e8f5e9;border:2px solid #4caf50;border-radius:8px;padding:18px;margin:10px 0;}
div[data-testid="stNumberInput"] input{font-size:15px !important;padding:6px 8px !important;color:#212121 !important;}
div[data-testid="stSelectbox"] > div{font-size:15px !important;color:#212121 !important;}
div[data-testid="stTextInput"] input{font-size:15px !important;}
div[data-testid="stTextArea"] textarea{font-size:15px !important;}
</style>""", unsafe_allow_html=True)

# ── 사이드바 ──
st.sidebar.title("🧪 음료개발 AI 플랫폼")
st.sidebar.markdown("---")
# [개선6] 첫 메뉴 = 컨셉→배합설계
PAGES = ["🎯 컨셉→배합설계", "🧪 배합 시뮬레이터", "🧑‍🔬 AI 연구원 평가", "🎨 제품 이미지 생성",
         "🔄 역설계", "📊 시장분석", "🎓 교육용 실습", "📋 기획서/HACCP",
         "📑 식품표시사항", "🧫 시작 레시피", "📓 배합 히스토리"]
page = st.sidebar.radio("메뉴", PAGES)
st.sidebar.markdown("---")
st.sidebar.caption(f"원료 {len(df_ing)}종 · 제품 {len(df_product)}종")
if st.session_state.product_name:
    st.sidebar.info(f"📦 {st.session_state.product_name}\n{st.session_state.bev_type} / {st.session_state.flavor}")


# ================================================================
# [개선6] PAGE 0: 마케팅 컨셉 → R&D 배합설계
# ================================================================
def page_concept():
    st.markdown('<div class="sim-header">🎯 마케팅 컨셉 → R&D 배합설계 (AI 음료연구원)</div>', unsafe_allow_html=True)
    st.caption("마케팅 기획자로부터 받은 제품 컨셉을 붙여넣으면, R&D센터 음료연구원 AI가 배합표로 변환합니다.")

    concept = st.text_area("📋 마케팅 컨셉 (복사/붙여넣기)", height=200,
        placeholder="예시: 2030 여성 타겟, 비타민C 풍부한 자몽+레몬 상큼 음료, 저칼로리, 500ml PET, 편의점 유통, 가격대 1,500원, 산뜻한 후미...")

    if st.button("🤖 R&D 음료연구원에게 전달 → 배합설계", type="primary", use_container_width=True):
        if not OPENAI_KEY:
            st.error("OpenAI API 키 필요"); return
        if not concept.strip():
            st.warning("컨셉을 입력해주세요."); return
        with st.spinner("🧑‍🔬 R&D센터 음료연구원이 컨셉을 분석하고 배합표를 설계 중..."):
            sample = ', '.join(df_ing['원료명'].sample(min(30, len(df_ing))).tolist())
            result = call_gpt_marketing_to_rd(OPENAI_KEY, concept, sample)
            st.session_state.concept_result = result

    if st.session_state.concept_result:
        r = st.session_state.concept_result
        st.markdown("---")
        # AI 분석 텍스트
        st.markdown(r.get('text', ''))

        if r.get('formulation'):
            st.markdown("---")
            st.markdown("### 📊 추천 배합표 (배합시뮬레이터 형식)")
            form_df = pd.DataFrame(r['formulation'])
            st.dataframe(form_df, use_container_width=True, hide_index=True)

            # 주요원료 특장점
            if r.get('ingredients_info'):
                with st.expander("🔍 주요원료 및 사용시 특장점", expanded=True):
                    for info in r['ingredients_info']:
                        st.markdown(f"• **{info.get('원료명', '')}**: {info.get('사용이유', '')}")

            # [개선5] 적용/CSV/저장 버튼
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                if st.button("✅ 추천배합비 → 시뮬레이터 적용", type="primary", use_container_width=True):
                    new_slots = init_slots()
                    for item in r['formulation']:
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
                        new_slots[idx]['AI용도특성'] = item.get('용도특성', '')
                        new_slots[idx] = calc_slot_contributions(new_slots[idx])
                    st.session_state.slots = new_slots
                    if r.get('bev_type'):
                        st.session_state.bev_type = r['bev_type']
                    if r.get('flavor'):
                        st.session_state.flavor = r['flavor']
                    st.success("✅ 배합표 적용 완료! 좌측 '배합 시뮬레이터'로 이동하세요.")
            with bc2:
                csv = form_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 CSV 다운로드", csv, "추천배합표.csv", "text/csv", use_container_width=True)
            with bc3:
                if st.button("💾 히스토리에 저장", use_container_width=True):
                    st.session_state.history.append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                        'name': f"컨셉배합_{r.get('flavor', 'AI')}",
                        'type': r.get('bev_type', ''), 'flavor': r.get('flavor', ''),
                        'slots': [s.copy() for s in st.session_state.slots],
                        'result': {}, 'notes': concept[:80]})
                    st.success(f"✅ 히스토리 저장 ({len(st.session_state.history)}건)")


# ================================================================
# PAGE 1: 배합 시뮬레이터 [개선2,3,4,5 모두 적용]
# ================================================================
def page_simulator():
    st.markdown('<div class="sim-header">🧪 음료 배합비 시뮬레이터</div>', unsafe_allow_html=True)

    # ── 헤더 설정 ──
    h1, h2, h3, h4 = st.columns([1.5, 2, 1.5, 1.5])
    with h1:
        st.session_state.product_name = st.text_input("📋 제품명", st.session_state.product_name or "사과과채음료_시제1호")
        bev_types = df_spec['음료유형'].dropna().tolist()
        bt_idx = bev_types.index(st.session_state.bev_type) if st.session_state.bev_type in bev_types else 0
        st.session_state.bev_type = st.selectbox("음료유형", bev_types, index=bt_idx)
    with h2:
        bt_short = st.session_state.bev_type.split('(')[0].replace('·', '')
        guide_keys = df_guide['키(유형_맛_슬롯)'].dropna().unique()
        flavors = sorted(set(k.split('_')[1] for k in guide_keys if bt_short in k.split('_')[0].replace('·', '')))
        flavor_opts = flavors + ['직접입력']
        sel = st.selectbox("맛(Flavor)", flavor_opts)
        st.session_state.flavor = st.text_input("맛 직접입력", st.session_state.flavor) if sel == '직접입력' else sel
    with h3:
        st.session_state.volume = st.number_input("목표용량(ml)", 100, 2000, st.session_state.volume, 50)
        st.session_state.container = st.selectbox("포장용기", ['PET', '캔', '유리병', '종이팩', '파우치'])
    with h4:
        spec = get_spec(df_spec, st.session_state.bev_type)
        if spec:
            st.markdown("**📋 규격기준**")
            st.markdown(f"Bx: {spec['Brix_min']}~{spec['Brix_max']}° · pH: {spec['pH_min']}~{spec['pH_max']}")

    # ── 버튼 ──
    st.markdown("---")
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        if st.button("🤖 AI 추천배합비 생성", use_container_width=True, type="primary"):
            if not OPENAI_KEY:
                st.error("OpenAI API 키 필요"); return
            with st.spinner("🤖 AI 배합설계 중..."):
                sample = ', '.join(df_ing['원료명'].sample(min(30, len(df_ing))).tolist())
                ai_form = call_gpt_ai_formulation(OPENAI_KEY, st.session_state.bev_type, st.session_state.flavor, sample)
                if ai_form:
                    new = init_slots()
                    for item in ai_form:
                        i = int(item.get('슬롯', 1)) - 1
                        if i < 0 or i >= 19:
                            continue
                        nm = item.get('원료명', '')
                        new[i] = fill_slot_from_db(new[i], nm, df_ing, PH_COL)
                        if not new[i]['원료명']:
                            new[i]['원료명'] = nm
                            new[i]['is_custom'] = True
                        new[i]['배합비(%)'] = safe_float(item.get('배합비', 0))
                        new[i]['AI추천_원료명'] = nm
                        new[i]['AI추천_%'] = safe_float(item.get('배합비', 0))
                        new[i] = calc_slot_contributions(new[i])
                    st.session_state.slots = new
                    st.success(f"✅ AI 추천배합 {len(ai_form)}종 적용")
                    st.rerun()
    with bc2:
        if st.button("📥 가이드배합비 불러오기", use_container_width=True):
            st.session_state.slots = load_guide(df_guide, st.session_state.bev_type, st.session_state.flavor, df_ing, PH_COL)
            st.rerun()
    with bc3:
        if st.button("🔄 전체 초기화", use_container_width=True):
            st.session_state.slots = init_slots()
            st.rerun()

    # ── [개선4] 배합표 헤더 (확대) + [개선2] 기존표준→AI용도특성 ──
    st.markdown("---")
    hdr = st.columns([0.3, 2.2, 1.0, 0.7, 0.7, 2.0, 0.8, 0.7, 0.7, 0.7, 0.7])
    for i, h in enumerate(['No', '원료명', '배합비(%)', 'AI%', 'Bx', '🤖 용도/특성', '산도', '감미', '단가', '당기여', 'g/kg']):
        hdr[i].markdown(f'<div class="hdr">{h}</div>', unsafe_allow_html=True)

    # ── 20행 배합표 ──
    for group_name, group_rows in SLOT_GROUPS:
        if group_name != '정제수':
            st.markdown(f'<div class="grp-label">{group_name}</div>', unsafe_allow_html=True)

        for rn in group_rows:
            idx = rn - 1
            s = st.session_state.slots[idx]

            # 정제수 행 (20행)
            if group_name == '정제수':
                ing_total = sum(safe_float(st.session_state.slots[j].get('배합비(%)', 0)) for j in range(19))
                wp = round(max(0, 100 - ing_total), 3)
                st.session_state.slots[idx]['원료명'] = '정제수'
                st.session_state.slots[idx]['배합비(%)'] = wp
                st.session_state.slots[idx]['배합량(g/kg)'] = round(wp * 10, 1)
                c = st.columns([0.3, 2.2, 1.0, 0.7, 0.7, 2.0, 0.8, 0.7, 0.7, 0.7, 0.7])
                c[0].markdown(f'<span class="cel">{rn}</span>', unsafe_allow_html=True)
                c[1].markdown(f'**💧 정제수**')
                c[2].markdown(f'<span class="cnum">{wp:.3f}%</span>', unsafe_allow_html=True)
                c[10].markdown(f'<span class="cnum">{wp*10:.1f}</span>', unsafe_allow_html=True)
                continue

            c = st.columns([0.3, 2.2, 1.0, 0.7, 0.7, 2.0, 0.8, 0.7, 0.7, 0.7, 0.7])
            c[0].markdown(f'<span class="cel">{rn}</span>', unsafe_allow_html=True)

            # ── [개선3] 원료 선택 + 직접입력 통합 ──
            with c[1]:
                cur = s.get('원료명', '')
                if cur and cur in df_ing['원료명'].values:
                    def_idx = ING_NAMES.index(cur)
                elif cur and s.get('is_custom'):
                    def_idx = 1  # ✏️ 직접입력
                else:
                    def_idx = 0  # (선택)

                picked = st.selectbox("원료", ING_NAMES, index=def_idx,
                                      label_visibility="collapsed", key=f"i{idx}")

                if picked == '✏️ 직접입력':
                    cname = st.text_input("원료명", cur if s.get('is_custom') else "",
                                          label_visibility="collapsed", key=f"ci{idx}",
                                          placeholder="원료명 입력")
                    if cname:
                        st.session_state.slots[idx]['원료명'] = cname
                        st.session_state.slots[idx]['is_custom'] = True
                        s = st.session_state.slots[idx]
                elif picked == '(선택)':
                    # 공란 선택 → 슬롯 초기화 (사용자가 지울 수 있도록)
                    if cur:
                        st.session_state.slots[idx] = EMPTY_SLOT.copy()
                        s = st.session_state.slots[idx]
                elif picked != cur:
                    st.session_state.slots[idx] = fill_slot_from_db(EMPTY_SLOT.copy(), picked, df_ing, PH_COL)
                    s = st.session_state.slots[idx]

            # 배합비(%)
            with c[2]:
                pct = st.number_input("pct", 0.0, 100.0, float(s.get('배합비(%)', 0)), 0.1,
                                      format="%.3f", label_visibility="collapsed", key=f"p{idx}")
                st.session_state.slots[idx]['배합비(%)'] = pct

            # AI추천%
            ai_pct = s.get('AI추천_%', 0)
            c[3].markdown(f'<span class="cnum">{ai_pct if ai_pct else ""}</span>', unsafe_allow_html=True)

            # [개선3] 직접입력 원료 → 편집 가능 필드
            if s.get('is_custom') and s.get('원료명'):
                with c[4]:
                    bx = st.number_input("Bx", 0.0, 100.0, float(s.get('당도(Bx)', 0)), 0.1,
                                         label_visibility="collapsed", key=f"bx{idx}")
                    st.session_state.slots[idx]['당도(Bx)'] = bx
                    st.session_state.slots[idx]['Brix(°)'] = bx
                    st.session_state.slots[idx]['1%Brix기여'] = round(bx / 100, 4) if bx else 0
                # [개선2] AI 용도특성
                c[5].markdown(f'<span class="cel">{s.get("AI용도특성", "")}</span>', unsafe_allow_html=True)
                with c[6]:
                    ac = st.number_input("ac", 0.0, 50.0, float(s.get('산도(%)', 0)), 0.01,
                                         label_visibility="collapsed", key=f"ac{idx}")
                    st.session_state.slots[idx]['산도(%)'] = ac
                    st.session_state.slots[idx]['1%산도기여'] = round(ac / 100, 4) if ac else 0
                with c[7]:
                    sw = st.number_input("sw", 0.0, 50000.0, float(s.get('감미도', 0)), 0.1,
                                         label_visibility="collapsed", key=f"sw{idx}")
                    st.session_state.slots[idx]['감미도'] = sw
                    st.session_state.slots[idx]['1%감미기여'] = round(sw / 100, 4) if sw else 0
                with c[8]:
                    pr = st.number_input("단가", 0, 500000, int(s.get('단가(원/kg)', 0)), 100,
                                         label_visibility="collapsed", key=f"pr{idx}")
                    st.session_state.slots[idx]['단가(원/kg)'] = pr
            else:
                c[4].markdown(f'<span class="cel">{s.get("당도(Bx)", 0)}</span>', unsafe_allow_html=True)
                c[5].markdown(f'<span class="cel">{s.get("AI용도특성", "")}</span>', unsafe_allow_html=True)
                c[6].markdown(f'<span class="cel">{s.get("산도(%)", 0)}</span>', unsafe_allow_html=True)
                c[7].markdown(f'<span class="cel">{s.get("감미도", 0)}</span>', unsafe_allow_html=True)
                c[8].markdown(f'<span class="cel">{safe_float(s.get("단가(원/kg)", 0)):,.0f}</span>', unsafe_allow_html=True)

            st.session_state.slots[idx] = calc_slot_contributions(st.session_state.slots[idx])
            s = st.session_state.slots[idx]
            c[9].markdown(f'<span class="cnum">{s.get("당기여", 0):.2f}</span>', unsafe_allow_html=True)
            c[10].markdown(f'<span class="cnum">{s.get("배합량(g/kg)", 0):.1f}</span>', unsafe_allow_html=True)

    # ── [개선2] AI 용도특성 일괄조회 + [개선3] AI 이화학추정 ──
    custom_idxs = [i for i, s in enumerate(st.session_state.slots) if s.get('is_custom') and s.get('원료명')]
    active_idxs = [i for i, s in enumerate(st.session_state.slots[:19]) if s.get('원료명') and safe_float(s.get('배합비(%)', 0)) > 0]

    if OPENAI_KEY:
        ab1, ab2 = st.columns(2)
        with ab1:
            if active_idxs and st.button("🔍 AI 원료 용도/특성 일괄조회", use_container_width=True):
                prog = st.progress(0)
                for pi, i in enumerate(active_idxs):
                    nm = st.session_state.slots[i].get('원료명', '')
                    if nm and not st.session_state.slots[i].get('AI용도특성'):
                        try:
                            info = call_gpt_ingredient_info(OPENAI_KEY, nm)
                            st.session_state.slots[i]['AI용도특성'] = info
                        except:
                            pass
                    prog.progress((pi + 1) / len(active_idxs))
                st.rerun()
        with ab2:
            if custom_idxs and st.button("🤖 직접입력 원료 → AI 이화학추정", use_container_width=True):
                results = []
                for ci in custom_idxs:
                    s = st.session_state.slots[ci]
                    with st.spinner(f"'{s['원료명']}' 추정 중..."):
                        try:
                            est = call_gpt_estimate_ingredient(OPENAI_KEY, s['원료명'])
                            for k_from, k_to in [
                                ('Brix', '당도(Bx)'), ('Brix', 'Brix(°)'), ('산도_pct', '산도(%)'),
                                ('감미도_설탕대비', '감미도'), ('감미도_설탕대비', '감미도(설탕대비)'),
                                ('예상단가_원kg', '단가(원/kg)'), ('1pct_Brix기여', '1%Brix기여'),
                                ('1pct_pH영향', '1%pH영향'), ('1pct_산도기여', '1%산도기여'),
                                ('1pct_감미기여', '1%감미기여')
                            ]:
                                st.session_state.slots[ci][k_to] = safe_float(est.get(k_from, 0))
                            st.session_state.slots[ci] = calc_slot_contributions(st.session_state.slots[ci])
                            results.append({'원료명': s['원료명'], **est})
                        except Exception as e:
                            st.error(f"'{s['원료명']}' 실패: {e}")
                if results:
                    st.markdown("### 🤖 AI 이화학추정 결과")
                    st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
                    st.caption("※ 추정값이 배합표에 자동 반영됨. 직접 수정 가능.")
                    st.rerun()

    # ── 결과 요약 ──
    st.markdown("---")
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    st.markdown('<div class="sim-header">▶ 시뮬레이션 결과 요약</div>', unsafe_allow_html=True)
    spec = get_spec(df_spec, st.session_state.bev_type)
    comp = check_compliance(result, spec) if spec else {}
    pct_ok = abs(result['배합비합계(%)'] - 100) < 0.01

    r1, r2 = st.columns(2)
    with r1:
        for label, val, status in [
            ("배합비 합계(%)", f"{result['배합비합계(%)']:.3f}", "✅ 100%" if pct_ok else f"⚠️ {result['배합비합계(%)']:.3f}%"),
            ("예상 당도(Bx)", f"{result['예상당도(Bx)']:.2f}", comp.get('당도', ('',))[0]),
            ("예상 산도(%)", f"{result['예상산도(%)']:.4f}", comp.get('산도', ('',))[0]),
            ("예상 감미도", f"{result['예상감미도']:.4f}", ""),
            ("원재료비(원/kg)", f"{result['원재료비(원/kg)']:,.0f}", ""),
            ("원재료비(원/병)", f"{result['원재료비(원/병)']:,.0f}", ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'infot')
            st.markdown(f'<div class="rrow"><b>{label}</b> &nbsp; <code>{val}</code> &nbsp; <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)
    with r2:
        for label, val, status in [
            ("정제수 비율(%)", f"{result['정제수비율(%)']:.1f}", comp.get('정제수비율', ('',))[0]),
            ("pH(참고)", f"{result['예상pH']:.2f}", comp.get('pH', ('ℹ️ 실측필요',))[0]),
            ("당산비", f"{result['당산비']}", ""),
            ("과즙함량(%)", f"{result['과즙함량(%)']:.1f}", ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'infot')
            st.markdown(f'<div class="rrow"><b>{label}</b> &nbsp; <code>{val}</code> &nbsp; <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)

    # 정제수 자동조정
    if not pct_ok:
        ing_tot = sum(safe_float(st.session_state.slots[j].get('배합비(%)', 0)) for j in range(19))
        if ing_tot <= 100:
            if st.button("💧 정제수 자동조정 (100% 맞추기)", type="primary", use_container_width=True):
                st.session_state.slots[19]['배합비(%)'] = round(100 - ing_tot, 3)
                st.rerun()
        else:
            st.warning(f"⚠️ 원료합계 {ing_tot:.3f}% > 100%. 원료 배합비를 줄여주세요.")

    # ── [개선5] 하단: 저장 / 출력 / CSV ──
    st.markdown("---")
    b1, b2, b3, b4 = st.columns(4)
    with b1:
        sn = st.text_input("저장명", f"{st.session_state.product_name}_{datetime.now().strftime('%H%M')}")
        if st.button("💾 히스토리 저장", use_container_width=True):
            st.session_state.history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'name': sn,
                'type': st.session_state.bev_type, 'flavor': st.session_state.flavor,
                'slots': [s.copy() for s in st.session_state.slots], 'result': result.copy(), 'notes': ''})
            st.success(f"✅ 저장 ({len(st.session_state.history)}건)")
    with b2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("📋 배합표 출력 (공란 제외)", use_container_width=True):
            rows = []
            for i, s in enumerate(st.session_state.slots):
                if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명'):
                    rows.append({'No': i+1, '원료명': s['원료명'], '배합비(%)': round(s['배합비(%)'], 3),
                                'AI용도특성': s.get('AI용도특성', ''), 'Brix': s.get('당도(Bx)', 0),
                                '단가(원/kg)': s.get('단가(원/kg)', 0), '배합량(g/kg)': s.get('배합량(g/kg)', 0)})
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with b3:
        st.markdown("<br>", unsafe_allow_html=True)
        out_rows = [{'No': i+1, '원료명': s['원료명'], '배합비(%)': round(s['배합비(%)'], 3),
                     '당도(Bx)': s.get('당도(Bx)', 0), '산도(%)': s.get('산도(%)', 0),
                     '감미도': s.get('감미도', 0), '단가(원/kg)': s.get('단가(원/kg)', 0),
                     '배합량(g/kg)': s.get('배합량(g/kg)', 0)}
                    for i, s in enumerate(st.session_state.slots)
                    if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
        if out_rows:
            csv_data = pd.DataFrame(out_rows).to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 CSV 다운로드", csv_data,
                              f"배합표_{st.session_state.product_name}.csv", "text/csv", use_container_width=True)
    with b4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🧑‍🔬 AI 연구원에게 →", use_container_width=True, type="primary"):
            st.success("좌측 '🧑‍🔬 AI 연구원 평가' 선택")


# ================================================================
# PAGE 2: AI 연구원
# ================================================================
def page_ai_researcher():
    st.title("🧑‍🔬 AI 음료개발연구원 평가")
    st.caption("20년 경력 수석 연구원 'Dr. 이음료' 페르소나")
    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요"); return
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return
    with st.expander("📋 현재 배합표", expanded=True):
        st.dataframe(pd.DataFrame(active, columns=['원료명', '배합비(%)']), use_container_width=True)
        st.markdown(f"**Brix {result['예상당도(Bx)']}° | pH {result['예상pH']} | 산도 {result['예상산도(%)']:.4f}%**")
    target = st.text_input("목표 컨셉", "과즙감 강조, 상큼한 산미밸런스")
    if st.button("🧑‍🔬 평가 요청", type="primary", use_container_width=True):
        form_text = '\n'.join([f"{n}: {p:.3f}%" for n, p in active])
        form_text += f"\nBrix:{result['예상당도(Bx)']}° pH:{result['예상pH']} 산도:{result['예상산도(%)']:.4f}%"
        with st.spinner("🧑‍🔬 분석 중..."):
            st.session_state.ai_response = call_gpt(OPENAI_KEY, PERSONA_RESEARCHER,
                                                     form_text + f"\n목표: {target}")
    if st.session_state.ai_response:
        st.markdown("---")
        st.markdown(st.session_state.ai_response)
        mod = parse_modified_formulation(st.session_state.ai_response)
        if mod:
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


# ================================================================
# PAGE 3~5: 이미지, 역설계, 시장분석
# ================================================================
def page_image():
    st.title("🎨 AI 제품 이미지 생성")
    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요"); return
    prompt = build_dalle_prompt(st.session_state.product_name, st.session_state.bev_type,
                                st.session_state.slots, st.session_state.container, st.session_state.volume)
    prompt = st.text_area("프롬프트", prompt, height=100)
    if st.button("🎨 이미지 생성", type="primary"):
        with st.spinner("생성 중..."):
            try:
                st.session_state.generated_image = call_dalle(OPENAI_KEY, prompt)
            except Exception as e:
                st.error(f"실패: {e}")
    if st.session_state.generated_image:
        st.image(st.session_state.generated_image, use_container_width=True)


def page_reverse():
    st.title("🔄 시판제품 역설계")
    cats = ['전체'] + df_product['대분류'].dropna().unique().tolist()
    sel_cat = st.selectbox("대분류", cats)
    f = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
    sel = st.selectbox("제품", f['제품명'].dropna().tolist())
    if sel:
        prod = df_product[df_product['제품명'] == sel].iloc[0]
        st.markdown(f"**{sel}** — {prod.get('제조사', '')} | {prod.get('세부유형', '')}")
        if st.button("🔄 역설계 → 시뮬레이터", type="primary"):
            st.session_state.slots = reverse_engineer(prod, df_ing, PH_COL)
            st.session_state.product_name = f"{sel}_역설계"
            st.success("✅ 시뮬레이터에 반영됨")


def page_market():
    st.title("📊 시장제품 분석")
    sel_cat = st.selectbox("대분류", ['전체'] + df_product['대분류'].dropna().unique().tolist())
    f = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
    k1, k2, k3 = st.columns(3)
    k1.metric("제품수", len(f))
    k2.metric("제조사", f['제조사'].nunique())
    k3.metric("평균가격", f"{f['가격(원)'].dropna().mean():,.0f}원")
    st.dataframe(f[['No', '대분류', '세부유형', '제품명', '제조사', '용량(ml)', '가격(원)']],
                 use_container_width=True, height=300)


# ================================================================
# [개선1] PAGE 6: 교육용 실습 — 단계별 배합연습 + 주의사항
# ================================================================
def page_education():
    st.markdown('<div class="sim-header">🎓 교육용 배합 실습 도구</div>', unsafe_allow_html=True)
    st.caption("단계별로 원료를 투입하며 배합을 연습합니다. 각 단계마다 식품유형별 주의사항이 표시됩니다.")

    bev_types = df_spec['음료유형'].dropna().tolist()
    bev = st.selectbox("실습 음료유형", bev_types, key="edu_bev")

    step_slot_map = {
        '1단계_원재료': list(range(0, 4)),
        '2단계_당류': list(range(4, 8)),
        '3단계_산미료': [12, 13],
        '4단계_안정제': list(range(8, 12)),
        '5단계_기타': [14, 15, 16, 17, 18],
    }

    for step_key, step_info in EDUCATION_STEPS.items():
        slot_idxs = step_slot_map.get(step_key, [])
        st.markdown(f'<div class="edu-step">{step_info["icon"]} <b>── {step_info["title"]} ──</b> ({step_info["items"]})</div>', unsafe_allow_html=True)
        st.markdown(f'📖 **가이드**: {step_info["guide"]}')
        st.markdown(f'<div class="edu-warn">{step_info["warning"]}</div>', unsafe_allow_html=True)

        # 해당 단계의 간소화 배합표
        for slot_idx in slot_idxs:
            ec = st.columns([0.3, 2.5, 1.2, 1.0, 2.0])
            ec[0].markdown(f'<span class="cel">{slot_idx+1}</span>', unsafe_allow_html=True)
            s = st.session_state.edu_slots[slot_idx]
            with ec[1]:
                cur = s.get('원료명', '')
                def_idx = ING_NAMES.index(cur) if cur in ING_NAMES else 0
                picked = st.selectbox("원료", ING_NAMES, index=def_idx,
                                      label_visibility="collapsed", key=f"ei{slot_idx}")
                if picked not in ['(선택)', '✏️ 직접입력'] and picked != cur:
                    st.session_state.edu_slots[slot_idx] = fill_slot_from_db(EMPTY_SLOT.copy(), picked, df_ing, PH_COL)
                    s = st.session_state.edu_slots[slot_idx]
            with ec[2]:
                pct = st.number_input("배합비(%)", 0.0, 100.0, float(s.get('배합비(%)', 0)), 0.1,
                                      format="%.2f", label_visibility="collapsed", key=f"ep{slot_idx}")
                st.session_state.edu_slots[slot_idx]['배합비(%)'] = pct
            st.session_state.edu_slots[slot_idx] = calc_slot_contributions(st.session_state.edu_slots[slot_idx])
            s = st.session_state.edu_slots[slot_idx]
            ec[3].markdown(f'<span class="cnum">Bx기여: {s.get("당기여", 0):.2f}</span>', unsafe_allow_html=True)
            # [개선2] 용도특성
            ec[4].markdown(f'<span class="cel">{s.get("AI용도특성", "")}</span>', unsafe_allow_html=True)

        st.markdown("---")

    # 실습 결과
    edu_result = calc_formulation(st.session_state.edu_slots, 500)
    st.markdown('<div class="sim-header">📊 실습 결과</div>', unsafe_allow_html=True)
    mc = st.columns(5)
    mc[0].metric("Brix", f"{edu_result['예상당도(Bx)']:.2f}°")
    mc[1].metric("pH(추정)", f"{edu_result['예상pH']:.2f}")
    mc[2].metric("산도", f"{edu_result['예상산도(%)']:.4f}%")
    mc[3].metric("정제수", f"{edu_result['정제수비율(%)']:.1f}%")
    mc[4].metric("원가", f"{edu_result['원재료비(원/kg)']:,.0f}원/kg")

    edu_spec = get_spec(df_spec, bev)
    if edu_spec:
        edu_comp = check_compliance(edu_result, edu_spec)
        for k, (msg, ok) in edu_comp.items():
            if ok is True:
                st.success(f"{k}: {msg}")
            elif ok is False:
                st.error(f"{k}: {msg}")
            else:
                st.info(f"{k}: {msg}")

    if st.button("🔄 실습 초기화"):
        st.session_state.edu_slots = init_slots()
        st.rerun()


# ================================================================
# [개선5] PAGE 7: 기획서 + HACCP — 아이콘 추가
# ================================================================
def page_planner():
    st.title("📋 신제품 기획서 + 공정시방서 + HACCP")
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return

    st.markdown(f"**{st.session_state.product_name}** | {st.session_state.bev_type} | {st.session_state.volume}ml")
    mc = st.columns(6)
    mc[0].metric("Brix", result['예상당도(Bx)'])
    mc[1].metric("pH", result['예상pH'])
    mc[2].metric("산도", f"{result['예상산도(%)']:.4f}%")
    mc[3].metric("감미도", f"{result['예상감미도']:.4f}")
    mc[4].metric("당산비", result['당산비'])
    mc[5].metric("원가", f"{result['원재료비(원/kg)']:,.0f}")

    tabs = st.tabs(["📋 기획서", "🏭 공정시방서(SOP)", "📄 HACCP 서류 (6종)", "🤖 AI 분석보고서"])

    # TAB 1: 기획서
    with tabs[0]:
        st.subheader("신제품 기획서")
        raw_b = result['원재료비(원/병)']
        pkg = {'PET': 120, '캔': 90, '유리병': 200, '종이팩': 80, '파우치': 60}.get(st.session_state.container, 100)
        mfg = raw_b * 0.4
        total = raw_b + pkg + mfg
        price = st.session_state.target_price
        margin = price - total
        st.dataframe(pd.DataFrame({
            '항목': ['원재료비', '포장재비', '제조비', '총원가', '판매가', '마진'],
            '금액(원/병)': [f'{raw_b:,.0f}', f'{pkg:,.0f}', f'{mfg:,.0f}', f'{total:,.0f}', f'{price:,.0f}', f'{margin:,.0f}'],
        }), use_container_width=True, hide_index=True)

    # TAB 2: 공정시방서 [개선5: 아이콘]
    with tabs[1]:
        st.subheader("🏭 공정시방서 / 작업지시서")
        matched = match_process(st.session_state.bev_type, df_process)
        if not matched.empty:
            for _, p in matched.iterrows():
                step = str(p.get('세부공정', ''))
                icon = '⚙️'
                for kw, ic in HACCP_ICONS.items():
                    if kw in step:
                        icon = ic; break
                ccp_raw = str(p.get('CCP여부', ''))
                ccp_tag = f" 🔴 **{ccp_raw}**" if ccp_raw.startswith('CCP') else ""
                with st.expander(f"{icon} {p.get('공정단계', '')} — {step}{ccp_tag}"):
                    st.markdown(f"**작업방법**: {p.get('작업방법(구체적)', '-')}")
                    st.markdown(f"**조건**: {p.get('주요조건/파라미터', '-')}")
                    st.markdown(f"**품질관리**: {p.get('품질관리포인트', '-')}")
                    if ccp_raw.startswith('CCP'):
                        st.error(f"🔴 **{ccp_raw}** | CL: {p.get('한계기준(CL)', '-')} | 모니터링: {p.get('모니터링방법', '-')} | 개선조치: {p.get('개선조치', '-')}")
            sop_text = haccp_sop(st.session_state.bev_type, df_process, st.session_state.product_name, st.session_state.slots)
            st.download_button("💾 SOP 다운로드", sop_text, f"SOP_{st.session_state.product_name}.txt")
            if OPENAI_KEY and st.button("🤖 AI 생산관리자 공정분석", key="ai_sop"):
                form_text = '\n'.join([f"{n}:{p:.3f}%" for n, p in active])
                with st.spinner("🏭 AI 분석 중..."):
                    resp = call_gpt(OPENAI_KEY, PERSONA_PRODUCTION,
                                    f"제품:{st.session_state.product_name}\n유형:{st.session_state.bev_type}\n배합:\n{form_text}")
                    st.markdown(resp)
        else:
            st.warning("매칭 공정 없음")

    # TAB 3: HACCP 6종
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
                "⑥ 작업표준서 (SOP)": haccp_sop(st.session_state.bev_type, df_process,
                                              st.session_state.product_name, st.session_state.slots),
            }
            for title, doc in docs.items():
                with st.expander(title):
                    st.code(doc, language=None)
                    st.download_button(f"💾 다운로드", doc, f"HACCP_{title[:6]}.txt", key=f"dl_{title}")
            all_docs = '\n\n\n'.join([f"{'=' * 70}\n{t}\n{'=' * 70}\n{d}" for t, d in docs.items()])
            st.download_button("📦 HACCP 6종 일괄 다운로드", all_docs, "HACCP_전체.txt", type="primary")
            if OPENAI_KEY and st.button("🤖 AI 품질전문가 HACCP 분석", key="ai_haccp"):
                form_text = '\n'.join([f"{n}:{p:.3f}%" for n, p in active])
                with st.spinner("📄 AI 분석 중..."):
                    resp = call_gpt(OPENAI_KEY, PERSONA_QA,
                                    f"제품:{st.session_state.product_name}\n유형:{st.session_state.bev_type}\n배합:\n{form_text}")
                    st.markdown(resp)
        else:
            st.warning("매칭 공정 없음")

    # TAB 4: AI 분석보고서
    with tabs[3]:
        st.subheader("🤖 AI 분석보고서")
        if not OPENAI_KEY:
            st.error("API 키 필요"); return
        rtype = st.selectbox("관점", ["🧑‍🔬 R&D 연구원", "🏭 생산관리자", "📄 품질전문가"])
        persona = {"🧑‍🔬 R&D 연구원": PERSONA_PLANNER, "🏭 생산관리자": PERSONA_PRODUCTION, "📄 품질전문가": PERSONA_QA}[rtype]
        if st.button("📝 보고서 생성", type="primary"):
            form_text = '\n'.join([f"{n}:{p:.3f}%" for n, p in active])
            with st.spinner("AI 작성 중..."):
                resp = call_gpt(OPENAI_KEY, persona,
                                f"제품:{st.session_state.product_name}\n유형:{st.session_state.bev_type}\nBrix:{result['예상당도(Bx)']} pH:{result['예상pH']}\n배합:\n{form_text}\n\n종합 분석보고서")
                st.markdown(resp)
                st.download_button("💾 다운로드", resp, "AI보고서.txt")


# ================================================================
# PAGE 8~10: 표시사항, 시작레시피, 히스토리
# ================================================================
def page_labeling():
    st.title("📑 식품표시사항 자동생성")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return
    label = generate_food_label(st.session_state.slots, st.session_state.product_name,
                                st.session_state.volume, st.session_state.bev_type)
    items = []
    for k, v in label.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                items.append({'표시항목': f'  {sk}', '내용': str(sv)})
        else:
            items.append({'표시항목': k, '내용': str(v)})
    st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)
    with st.expander("⚠️ 알레르기 유발물질"):
        st.markdown(f"**검출**: {label['⑧ 알레르기 유발물질']}")
    with st.expander("📊 영양성분표"):
        st.dataframe(pd.DataFrame([{'영양성분': k, '함량': v} for k, v in label['⑦ 영양성분'].items()]),
                     use_container_width=True, hide_index=True)


def page_lab_recipe():
    st.title("🧫 시작 레시피")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다."); return
    scales = st.multiselect("스케일", [1, 5, 10, 20, 50, 100], default=[1, 5, 20])
    if scales:
        recipes = generate_lab_recipe(st.session_state.slots, scales)
        for scale, items in recipes.items():
            st.subheader(f"📋 {scale} 칭량표")
            st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)


def page_history():
    st.title("📓 배합 히스토리")
    if not st.session_state.history:
        st.info("시뮬레이터에서 '히스토리 저장'으로 추가하세요."); return
    for idx, h in enumerate(st.session_state.history):
        with st.expander(f"**{h['name']}** — {h['timestamp']}"):
            r = h.get('result', {})
            cc = st.columns(5)
            cc[0].metric("Brix", r.get('예상당도(Bx)', '-'))
            cc[1].metric("pH", r.get('예상pH', '-'))
            cc[2].metric("산도", f"{r.get('예상산도(%)', 0):.4f}%")
            cc[3].metric("당산비", r.get('당산비', '-'))
            cc[4].metric("원가", f"{r.get('원재료비(원/kg)', 0):,.0f}")
            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("📤 시뮬레이터 로드", key=f"ld{idx}"):
                    st.session_state.slots = [s.copy() for s in h['slots']]
                    st.success("✅ 반영")
            with bc2:
                if st.button("🗑️ 삭제", key=f"rm{idx}"):
                    st.session_state.history.pop(idx)
                    st.rerun()


# ── 라우팅 ──
{
    "🎯 컨셉→배합설계": page_concept,
    "🧪 배합 시뮬레이터": page_simulator,
    "🧑‍🔬 AI 연구원 평가": page_ai_researcher,
    "🎨 제품 이미지 생성": page_image,
    "🔄 역설계": page_reverse,
    "📊 시장분석": page_market,
    "🎓 교육용 실습": page_education,
    "📋 기획서/HACCP": page_planner,
    "📑 식품표시사항": page_labeling,
    "🧫 시작 레시피": page_lab_recipe,
    "📓 배합 히스토리": page_history,
}[page]()
