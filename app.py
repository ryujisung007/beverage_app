"""
🧪 음료개발 AI 플랫폼 v7.3 — AI이화학분석 자동화 + 정제수조정 수정
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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "음료개발_데이터베이스_v4-1.xlsx")

@st.cache_data
def load_data(path):
    return {n: pd.read_excel(path, sheet_name=n) for n in pd.ExcelFile(path).sheet_names}

try:
    DATA = load_data(DB_PATH)
except:
    st.error("❌ 음료개발_데이터베이스_v4-1.xlsx 파일을 앱 폴더에 넣어주세요.")
    st.stop()

df_type = DATA['음료유형분류']; df_product = DATA['시장제품DB']; df_ing = DATA['원료DB']
df_spec = DATA['음료규격기준']; df_process = DATA['표준제조공정_HACCP']; df_guide = DATA['가이드배합비DB']

for c in ['Brix(°)', 'pH', '산도(%)', '감미도(설탕대비)', '예상단가(원/kg)',
          '1%사용시 Brix기여(°)', '1%사용시 산도기여(%)', '1%사용시 감미기여']:
    df_ing[c] = pd.to_numeric(df_ing[c], errors='coerce').fillna(0)
PH_COL = [c for c in df_ing.columns if 'pH영향' in str(c) or 'ΔpH' in str(c)][0]
df_ing[PH_COL] = pd.to_numeric(df_ing[PH_COL], errors='coerce').fillna(0)

try:
    OPENAI_KEY = st.secrets["openai"]["OPENAI_API_KEY"]
except:
    OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")

ING_LIST = df_ing['원료명'].tolist()

for k, v in [('slots', init_slots()), ('history', []), ('product_name', ''), ('bev_type', ''),
             ('flavor', ''), ('volume', 500), ('container', 'PET'), ('target_price', 1500),
             ('ai_response', ''), ('generated_image', ''), ('concept_result', None),
             ('edu_slots', init_slots()), ('ai_est_results', [])]:
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown("""<style>
.sim-hdr{background:#1a237e;color:white;padding:12px 18px;border-radius:6px;font-weight:bold;font-size:22px;margin-bottom:14px}
.grp-lbl{background:#fff9c4;padding:6px 14px;font-weight:bold;font-size:17px;border-left:5px solid #f9a825;margin:10px 0;border-radius:3px}
.t-hdr{font-size:13px!important;font-weight:800!important;color:#1a237e!important;background:#e3f2fd;padding:5px 6px;border-radius:3px;text-align:center;line-height:2.0}
.t-cel{font-size:14px!important;color:#212121!important;font-weight:500!important;line-height:2.0}
.t-num{font-size:14px!important;color:#1565c0!important;font-weight:700!important}
.t-cust{font-size:12px!important;color:#e65100!important;font-style:italic}
.pass{color:#2e7d32;font-weight:bold;font-size:16px}
.fail{color:#c62828;font-weight:bold;font-size:16px}
.infot{color:#1565c0;font-weight:bold;font-size:15px}
.rrow{font-size:17px!important;padding:5px 0;line-height:2.0}
.edu-step{background:#f3e5f5;border-left:5px solid #9c27b0;padding:14px 18px;border-radius:5px;margin:10px 0;font-size:16px}
.edu-warn{background:#fff3e0;border-left:5px solid #ff9800;padding:10px 14px;border-radius:4px;margin:6px 0;font-size:15px}
.est-box{background:#e3f2fd;border:2px solid #1565c0;border-radius:8px;padding:14px;margin:10px 0}
div[data-testid="stNumberInput"] input{font-size:15px!important;padding:6px 8px!important;color:#212121!important}
div[data-testid="stSelectbox"] > div{font-size:14px!important;color:#212121!important}
div[data-testid="stTextInput"] input{font-size:15px!important}
div[data-testid="stTextArea"] textarea{font-size:15px!important}
</style>""", unsafe_allow_html=True)

st.sidebar.title("🧪 음료개발 AI 플랫폼")
st.sidebar.markdown("---")
PAGES = ["🎯 컨셉→배합설계", "🧪 배합 시뮬레이터", "🧑‍🔬 AI 연구원 평가", "🎨 제품 이미지 생성",
         "🔄 역설계", "📊 시장분석", "🎓 교육용 실습", "📋 기획서/HACCP",
         "📑 식품표시사항", "🧫 시작 레시피", "📓 배합 히스토리"]
page = st.sidebar.radio("메뉴", PAGES)
st.sidebar.markdown("---")
st.sidebar.caption(f"원료 {len(df_ing)}종 · 제품 {len(df_product)}종")
if st.session_state.product_name:
    st.sidebar.info(f"📦 {st.session_state.product_name}\n{st.session_state.bev_type} / {st.session_state.flavor}")


# ============================================================
# 헬퍼: 안전한 원료 selectbox
# ============================================================
def safe_ingredient_picker(slot, idx, prefix="s"):
    cur = slot.get('원료명', '')
    is_custom = slot.get('is_custom', False)
    if cur and cur in ING_LIST:
        mode = 'db'
    elif cur:
        mode = 'custom'
        slot['is_custom'] = True
    else:
        mode = 'none'
    input_mode = st.radio("입력", ["DB검색", "직접입력"], index=1 if mode == 'custom' else 0,
                          horizontal=True, label_visibility="collapsed", key=f"{prefix}m{idx}")
    if input_mode == "DB검색":
        options = [''] + ING_LIST
        cur_idx = options.index(cur) if cur in options else 0
        picked = st.selectbox("원료선택", options, index=cur_idx, label_visibility="collapsed",
                              key=f"{prefix}sel{idx}", format_func=lambda x: "(원료 선택)" if x == '' else x)
        if picked and picked != cur:
            new_slot = fill_slot_from_db(EMPTY_SLOT.copy(), picked, df_ing, PH_COL)
            new_slot['배합비(%)'] = slot.get('배합비(%)', 0)
            new_slot['AI추천_원료명'] = slot.get('AI추천_원료명', '')
            new_slot['AI추천_%'] = slot.get('AI추천_%', 0)
            new_slot['AI용도특성'] = slot.get('AI용도특성', '')
            return new_slot, True
        elif not picked and cur:
            return EMPTY_SLOT.copy(), True
        return slot, False
    else:
        cname = st.text_input("원료명", cur if mode in ('custom', 'db') else "",
                              label_visibility="collapsed", key=f"{prefix}txt{idx}", placeholder="원료명 직접 입력")
        if cname and cname != cur:
            new_slot = fill_slot_from_db(EMPTY_SLOT.copy(), cname, df_ing, PH_COL)
            new_slot['배합비(%)'] = slot.get('배합비(%)', 0)
            return new_slot, True
        elif not cname and cur:
            return EMPTY_SLOT.copy(), True
        return slot, False


# ============================================================
# 헬퍼: 배합비 로딩 + 자동 이화학추정 (핵심!)
# ============================================================
def load_formulation_with_estimation(formulation_list, auto_estimate=True):
    """AI/컨셉 배합비 리스트 → 슬롯 적용 + DB유사매칭 + 이화학 자동추정"""
    new_slots = init_slots()
    need_est = []  # AI추정 필요한 슬롯

    for item in formulation_list:
        i = int(item.get('슬롯', 1)) - 1
        if i < 0 or i >= 19:
            continue
        nm = item.get('원료명', '')
        pct = safe_float(item.get('배합비', 0))

        # DB 유사매칭 시도
        new_slots[i] = fill_slot_from_db(new_slots[i], nm, df_ing, PH_COL)
        new_slots[i]['배합비(%)'] = pct
        new_slots[i]['AI추천_원료명'] = nm
        new_slots[i]['AI추천_%'] = pct
        new_slots[i]['AI용도특성'] = item.get('용도특성', item.get('구분', ''))
        new_slots[i] = calc_slot_contributions(new_slots[i])

        # 이화학 전부 0이면 추정 대상
        if new_slots[i].get('is_custom') and pct > 0:
            bx = safe_float(new_slots[i].get('당도(Bx)', 0))
            ac = safe_float(new_slots[i].get('산도(%)', 0))
            sw = safe_float(new_slots[i].get('감미도', 0))
            pr = safe_float(new_slots[i].get('단가(원/kg)', 0))
            if bx == 0 and ac == 0 and sw == 0 and pr == 0:
                need_est.append(i)

    # 자동 AI 이화학추정
    est_results = []
    if auto_estimate and need_est and OPENAI_KEY:
        for idx in need_est:
            nm = new_slots[idx]['원료명']
            try:
                est = call_gpt_estimate_ingredient(OPENAI_KEY, nm)
                new_slots[idx] = apply_estimation_to_slot(new_slots[idx], est)
                est_results.append({'슬롯': idx+1, '원료명': nm, **est})
            except:
                pass

    return new_slots, est_results


# ============================================================
# PAGE 0: 마케팅 컨셉 → R&D 배합설계
# ============================================================
def page_concept():
    st.markdown('<div class="sim-hdr">🎯 마케팅 컨셉 → R&D 배합설계</div>', unsafe_allow_html=True)
    st.caption("마케팅 기획자의 컨셉을 붙여넣으면, R&D 음료연구원 AI가 배합표로 변환합니다.")
    concept = st.text_area("📋 마케팅 컨셉 (복사/붙여넣기)", height=200,
        placeholder="예시: 2030 여성 타겟, 비타민C 풍부한 자몽+레몬 상큼 음료, 저칼로리...")
    if st.button("🤖 R&D 음료연구원에게 전달", type="primary", use_container_width=True):
        if not OPENAI_KEY: st.error("OpenAI API 키 필요"); return
        if not concept.strip(): st.warning("컨셉을 입력하세요."); return
        with st.spinner("🧑‍🔬 R&D센터 음료연구원이 컨셉 분석 + 배합설계 + 이화학분석 중..."):
            sample = ', '.join(df_ing['원료명'].sample(min(30, len(df_ing))).tolist())
            result = call_gpt_marketing_to_rd(OPENAI_KEY, concept, sample)
            st.session_state.concept_result = result

            # ★ 배합비 + 자동 이화학추정
            if result.get('formulation'):
                new_slots, est_results = load_formulation_with_estimation(
                    result['formulation'], auto_estimate=True)
                st.session_state.slots = new_slots
                st.session_state.ai_est_results = est_results
                if result.get('bev_type'): st.session_state.bev_type = result['bev_type']
                if result.get('flavor'): st.session_state.flavor = result['flavor']

    if st.session_state.concept_result:
        r = st.session_state.concept_result
        st.markdown("---")
        st.markdown(r.get('text', ''))

        if r.get('formulation'):
            st.markdown("### 📊 추천 배합표 (이화학분석 반영)")
            # 현재 슬롯에서 활성 원료 표시
            rows = []
            for i, s in enumerate(st.session_state.slots[:19]):
                if s.get('원료명') and safe_float(s.get('배합비(%)', 0)) > 0:
                    rows.append({'No': i+1, '원료명': s['원료명'], '배합비(%)': round(s['배합비(%)'], 3),
                                'Brix': s.get('당도(Bx)', 0), '산도(%)': s.get('산도(%)', 0),
                                '감미도': s.get('감미도', 0), '단가(원/kg)': safe_float(s.get('단가(원/kg)', 0)),
                                '당기여': round(s.get('당기여', 0), 2), 'DB매칭': '✅DB' if not s.get('is_custom') else '🤖AI추정'})
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # AI 이화학 추정 결과 표시
            if st.session_state.ai_est_results:
                st.markdown('<div class="est-box">🤖 <b>AI 이화학분석 결과</b> (DB에 없는 원료 자동추정)</div>', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(st.session_state.ai_est_results), use_container_width=True, hide_index=True)

            if r.get('ingredients_info'):
                with st.expander("🔍 주요원료 특장점"):
                    for info in r['ingredients_info']:
                        st.markdown(f"• **{info.get('원료명','')}**: {info.get('사용이유','')}")

            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                st.success("✅ 배합표 자동 적용됨! '배합 시뮬레이터'에서 확인하세요.")
            with bc2:
                form_df = pd.DataFrame(rows) if rows else pd.DataFrame()
                if not form_df.empty:
                    csv = form_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 CSV", csv, "추천배합표.csv", "text/csv", use_container_width=True)
            with bc3:
                if st.button("💾 히스토리 저장", use_container_width=True):
                    st.session_state.history.append({
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                        'name': f"컨셉_{r.get('flavor','AI')}", 'type': r.get('bev_type',''),
                        'flavor': r.get('flavor',''), 'slots': [s.copy() for s in st.session_state.slots],
                        'result': calc_formulation(st.session_state.slots, st.session_state.volume),
                        'notes': concept[:80] if concept else ''})
                    st.success("✅ 저장")


# ============================================================
# PAGE 1: 배합 시뮬레이터
# ============================================================
def page_simulator():
    st.markdown('<div class="sim-hdr">🧪 음료 배합비 시뮬레이터</div>', unsafe_allow_html=True)

    # 헤더 설정
    h1, h2, h3, h4 = st.columns([1.5, 2, 1.5, 1.5])
    with h1:
        st.session_state.product_name = st.text_input("📋 제품명",
            st.session_state.product_name or "사과과채음료_시제1호")
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
            st.markdown(f"Bx {spec['Brix_min']}~{spec['Brix_max']}° · pH {spec['pH_min']}~{spec['pH_max']}")

    # 버튼
    st.markdown("---")
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        if st.button("🤖 AI 추천배합비 생성", use_container_width=True, type="primary"):
            if not OPENAI_KEY: st.error("OpenAI API 키 필요"); return
            with st.spinner("🤖 AI 배합설계 + 이화학분석 중..."):
                sample = ', '.join(df_ing['원료명'].sample(min(30, len(df_ing))).tolist())
                ai_form = call_gpt_ai_formulation(OPENAI_KEY, st.session_state.bev_type,
                                                   st.session_state.flavor, sample)
                if ai_form:
                    new_slots, est_results = load_formulation_with_estimation(ai_form, auto_estimate=True)
                    st.session_state.slots = new_slots
                    st.session_state.ai_est_results = est_results
                    st.rerun()
    with bc2:
        if st.button("📥 가이드배합비 불러오기", use_container_width=True):
            st.session_state.slots = load_guide(df_guide, st.session_state.bev_type,
                                                 st.session_state.flavor, df_ing, PH_COL)
            st.rerun()
    with bc3:
        if st.button("🔄 전체 초기화", use_container_width=True):
            st.session_state.slots = init_slots()
            st.session_state.ai_est_results = []
            st.rerun()

    # ── 배합표 ──
    st.markdown("---")
    hdr = st.columns([0.4, 2.8, 1.0, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6])
    for i, h in enumerate(['No', '원료명', '배합비(%)', 'Bx', '산도', '감미', '단가', '당기여', 'g/kg']):
        hdr[i].markdown(f'<div class="t-hdr">{h}</div>', unsafe_allow_html=True)

    for group_name, group_rows in SLOT_GROUPS:
        if group_name == '정제수':
            ing_total = sum(safe_float(st.session_state.slots[j].get('배합비(%)', 0)) for j in range(19))
            wp = round(max(0, 100 - ing_total), 3)
            st.session_state.slots[19]['원료명'] = '정제수'
            st.session_state.slots[19]['배합비(%)'] = wp
            st.session_state.slots[19]['배합량(g/kg)'] = round(wp * 10, 1)
            c = st.columns([0.4, 2.8, 1.0, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6])
            c[0].markdown(f'<span class="t-cel">20</span>', unsafe_allow_html=True)
            c[1].markdown(f'**💧 정제수**')
            c[2].markdown(f'<span class="t-num">{wp:.3f}%</span>', unsafe_allow_html=True)
            c[8].markdown(f'<span class="t-num">{wp*10:.1f}</span>', unsafe_allow_html=True)
            continue

        st.markdown(f'<div class="grp-lbl">{group_name}</div>', unsafe_allow_html=True)
        for rn in group_rows:
            idx = rn - 1
            s = st.session_state.slots[idx]

            c = st.columns([0.4, 2.8, 1.0, 0.6, 0.6, 0.6, 0.6, 0.6, 0.6])
            c[0].markdown(f'<span class="t-cel">{rn}</span>', unsafe_allow_html=True)

            # 원료명
            with c[1]:
                new_slot, changed = safe_ingredient_picker(s, idx, prefix="s")
                if changed:
                    if new_slot.get('원료명') and not safe_float(new_slot.get('배합비(%)', 0)):
                        new_slot['배합비(%)'] = safe_float(s.get('배합비(%)', 0))
                    st.session_state.slots[idx] = new_slot
                    s = new_slot

            # 배합비
            with c[2]:
                new_pct = st.number_input("pct", 0.0, 100.0, float(s.get('배합비(%)', 0)),
                                          0.1, format="%.3f", label_visibility="collapsed", key=f"pct{idx}")
                st.session_state.slots[idx]['배합비(%)'] = new_pct

            st.session_state.slots[idx] = calc_slot_contributions(st.session_state.slots[idx])
            s = st.session_state.slots[idx]

            bx = s.get('당도(Bx)', 0); ac = s.get('산도(%)', 0)
            sw = s.get('감미도', 0); pr = safe_float(s.get('단가(원/kg)', 0))
            css = 't-cust' if s.get('is_custom') else 't-cel'

            c[3].markdown(f'<span class="{css}">{bx}</span>', unsafe_allow_html=True)
            c[4].markdown(f'<span class="{css}">{ac}</span>', unsafe_allow_html=True)
            c[5].markdown(f'<span class="{css}">{sw}</span>', unsafe_allow_html=True)
            c[6].markdown(f'<span class="{css}">{pr:,.0f}</span>', unsafe_allow_html=True)
            c[7].markdown(f'<span class="t-num">{s.get("당기여",0):.2f}</span>', unsafe_allow_html=True)
            c[8].markdown(f'<span class="t-num">{s.get("배합량(g/kg)",0):.1f}</span>', unsafe_allow_html=True)

    # ── [핵심] AI 이화학분석 + 결과 출력 + 정제수 조정 ──
    st.markdown("---")
    custom_zero = [i for i in range(19) if st.session_state.slots[i].get('is_custom')
                   and st.session_state.slots[i].get('원료명')
                   and safe_float(st.session_state.slots[i].get('배합비(%)', 0)) > 0
                   and safe_float(st.session_state.slots[i].get('당도(Bx)', 0)) == 0
                   and safe_float(st.session_state.slots[i].get('산도(%)', 0)) == 0
                   and safe_float(st.session_state.slots[i].get('감미도', 0)) == 0
                   and safe_float(st.session_state.slots[i].get('단가(원/kg)', 0)) == 0]

    custom_all = [i for i in range(19) if st.session_state.slots[i].get('is_custom')
                  and st.session_state.slots[i].get('원료명')
                  and safe_float(st.session_state.slots[i].get('배합비(%)', 0)) > 0]

    col_ai, col_water = st.columns(2)

    # AI 이화학분석 버튼
    with col_ai:
        if custom_zero and OPENAI_KEY:
            names = ', '.join([st.session_state.slots[i]['원료명'] for i in custom_zero])
            st.warning(f"⚠️ 이화학데이터 없음: {names}")
            if st.button(f"🤖 AI 이화학분석 실행 ({len(custom_zero)}종)", type="primary", use_container_width=True):
                bar = st.progress(0)
                est_results = []
                for pi, ci in enumerate(custom_zero):
                    nm = st.session_state.slots[ci]['원료명']
                    try:
                        est = call_gpt_estimate_ingredient(OPENAI_KEY, nm)
                        st.session_state.slots[ci] = apply_estimation_to_slot(st.session_state.slots[ci], est)
                        est_results.append({'슬롯': ci+1, '원료명': nm, **est})
                    except Exception as e:
                        est_results.append({'슬롯': ci+1, '원료명': nm, '오류': str(e)})
                    bar.progress((pi+1) / len(custom_zero))
                st.session_state.ai_est_results = est_results
                st.rerun()
        elif custom_all:
            st.info(f"✅ 직접입력 원료 {len(custom_all)}종 이화학 반영됨")
        else:
            st.info("✅ 전체 원료 DB 매칭 완료")

    # [문제3,5] 정제수 조정 버튼 — 합계 100 초과/미만 모두 대응
    with col_water:
        ing_tot = sum(safe_float(st.session_state.slots[j].get('배합비(%)', 0)) for j in range(19))
        total_with_water = ing_tot + safe_float(st.session_state.slots[19].get('배합비(%)', 0))

        if abs(total_with_water - 100) > 0.01:
            water_target = round(max(0, 100 - ing_tot), 3)
            if ing_tot > 100:
                st.error(f"⚠️ 원료합계 {ing_tot:.3f}% > 100%. 정제수=0으로 조정 필요")
                if st.button("💧 정제수 0% 설정 (원료 초과)", type="primary", use_container_width=True):
                    st.session_state.slots[19]['배합비(%)'] = 0
                    st.rerun()
            else:
                st.warning(f"정제수 {water_target:.3f}%로 조정 필요 (현재 합계 {total_with_water:.3f}%)")
                if st.button(f"💧 정제수 → {water_target:.3f}% (합계 100%)", type="primary", use_container_width=True):
                    st.session_state.slots[19]['배합비(%)'] = water_target
                    st.rerun()
        else:
            st.success(f"✅ 배합비 합계 100.000%")

    # AI 이화학분석 결과 테이블 (있으면 표시)
    if st.session_state.ai_est_results:
        st.markdown('<div class="est-box">🤖 <b>AI 이화학분석 결과</b> — 배합표에 자동 반영됨</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(st.session_state.ai_est_results), use_container_width=True, hide_index=True)
        st.caption("※ AI 추정값은 참고용입니다. 수정이 필요하면 아래 편집 섹션에서 직접 수정하세요.")

    # 직접입력 원료 상세편집
    if custom_all:
        with st.expander(f"✏️ 직접입력 원료 상세편집 ({len(custom_all)}종)"):
            for ci in custom_all:
                s = st.session_state.slots[ci]
                st.markdown(f"**슬롯{ci+1}: {s['원료명']}** ({s['배합비(%)']:.3f}%)")
                ec = st.columns(5)
                with ec[0]:
                    bx = st.number_input("Brix", 0.0, 100.0, float(s.get('당도(Bx)', 0)), 0.1, key=f"cbx{ci}")
                    st.session_state.slots[ci]['당도(Bx)'] = bx
                    st.session_state.slots[ci]['Brix(°)'] = bx
                    st.session_state.slots[ci]['1%Brix기여'] = round(bx/100, 4) if bx else 0
                with ec[1]:
                    ac = st.number_input("산도(%)", 0.0, 50.0, float(s.get('산도(%)', 0)), 0.01, key=f"cac{ci}")
                    st.session_state.slots[ci]['산도(%)'] = ac
                    st.session_state.slots[ci]['1%산도기여'] = round(ac/100, 4) if ac else 0
                with ec[2]:
                    sw = st.number_input("감미도", 0.0, 50000.0, float(s.get('감미도', 0)), 0.1, key=f"csw{ci}")
                    st.session_state.slots[ci]['감미도'] = sw
                    st.session_state.slots[ci]['1%감미기여'] = round(sw/100, 4) if sw else 0
                with ec[3]:
                    pr = st.number_input("단가(원/kg)", 0, 500000, int(s.get('단가(원/kg)', 0)), 100, key=f"cpr{ci}")
                    st.session_state.slots[ci]['단가(원/kg)'] = pr
                with ec[4]:
                    if OPENAI_KEY and st.button("🤖 재추정", key=f"cai{ci}"):
                        try:
                            est = call_gpt_estimate_ingredient(OPENAI_KEY, s['원료명'])
                            st.session_state.slots[ci] = apply_estimation_to_slot(st.session_state.slots[ci], est)
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                st.session_state.slots[ci] = calc_slot_contributions(st.session_state.slots[ci])

    # ── 결과 요약 ──
    st.markdown("---")
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    st.markdown('<div class="sim-hdr">▶ 시뮬레이션 결과</div>', unsafe_allow_html=True)
    spec = get_spec(df_spec, st.session_state.bev_type)
    comp = check_compliance(result, spec) if spec else {}
    pct_ok = abs(result['배합비합계(%)'] - 100) < 0.01

    r1, r2 = st.columns(2)
    with r1:
        for label, val, status in [
            ("배합비 합계", f"{result['배합비합계(%)']:.3f}%", "✅ 100%" if pct_ok else f"⚠️ {result['배합비합계(%)']:.3f}%"),
            ("예상 당도(Bx)", f"{result['예상당도(Bx)']:.2f}°", comp.get('당도', ('',))[0]),
            ("예상 산도", f"{result['예상산도(%)']:.4f}%", comp.get('산도', ('',))[0]),
            ("예상 감미도", f"{result['예상감미도']:.4f}", ""),
            ("원가(원/kg)", f"{result['원재료비(원/kg)']:,.0f}", ""),
            ("원가(원/병)", f"{result['원재료비(원/병)']:,.0f}", ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'infot')
            st.markdown(f'<div class="rrow"><b>{label}</b> <code>{val}</code> <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)
    with r2:
        for label, val, status in [
            ("정제수", f"{result['정제수비율(%)']:.1f}%", ""),
            ("pH(참고)", f"{result['예상pH']:.2f}", comp.get('pH', ('ℹ️ 실측필요',))[0]),
            ("당산비", f"{result['당산비']}", ""),
            ("과즙함량", f"{result['과즙함량(%)']:.1f}%", ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'infot')
            st.markdown(f'<div class="rrow"><b>{label}</b> <code>{val}</code> <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)

    # 하단 버튼
    st.markdown("---")
    b1, b2, b3 = st.columns(3)
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
        out_rows = [{'No': i+1, '원료명': s['원료명'], '배합비(%)': round(s['배합비(%)'], 3),
                     'Brix': s.get('당도(Bx)', 0), '산도': s.get('산도(%)', 0),
                     '감미도': s.get('감미도', 0), '단가': s.get('단가(원/kg)', 0),
                     '배합량(g/kg)': s.get('배합량(g/kg)', 0)}
                    for i, s in enumerate(st.session_state.slots)
                    if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
        if out_rows:
            csv_data = pd.DataFrame(out_rows).to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 배합표 CSV", csv_data,
                              f"배합표_{st.session_state.product_name}.csv", "text/csv", use_container_width=True)
    with b3:
        st.markdown("<br>", unsafe_allow_html=True)
        if out_rows and st.button("📋 배합표 출력", use_container_width=True):
            st.dataframe(pd.DataFrame(out_rows), use_container_width=True, hide_index=True)


# ============================================================
# PAGE 2: AI 연구원
# ============================================================
def page_ai_researcher():
    st.title("🧑‍🔬 AI 음료개발연구원 평가")
    if not OPENAI_KEY: st.error("⚠️ OpenAI API 키 필요"); return
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active: st.warning("배합표가 비어있습니다."); return
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
                new, est = load_formulation_with_estimation(
                    [{'슬롯': i+1, '원료명': m['원료명'], '배합비': safe_float(m.get('배합비(%)',0))}
                     for i, m in enumerate(mod) if i < 19], auto_estimate=True)
                st.session_state.slots = new
                st.session_state.ai_est_results = est
                st.rerun()


# ============================================================
# PAGE 3~5
# ============================================================
def page_image():
    st.title("🎨 AI 제품 이미지 생성")
    if not OPENAI_KEY: st.error("⚠️ OpenAI API 키 필요"); return
    prompt = build_dalle_prompt(st.session_state.product_name, st.session_state.bev_type,
                                st.session_state.slots, st.session_state.container, st.session_state.volume)
    prompt = st.text_area("프롬프트", prompt, height=100)
    if st.button("🎨 이미지 생성", type="primary"):
        with st.spinner("생성 중..."):
            try: st.session_state.generated_image = call_dalle(OPENAI_KEY, prompt)
            except Exception as e: st.error(f"실패: {e}")
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
        st.markdown(f"**{sel}** — {prod.get('제조사','')} | {prod.get('세부유형','')}")
        if st.button("🔄 역설계 → 시뮬레이터", type="primary"):
            st.session_state.slots = reverse_engineer(prod, df_ing, PH_COL)
            st.session_state.product_name = f"{sel}_역설계"; st.success("✅")

def page_market():
    st.title("📊 시장제품 분석")
    sel_cat = st.selectbox("대분류", ['전체'] + df_product['대분류'].dropna().unique().tolist())
    f = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
    k1, k2, k3 = st.columns(3)
    k1.metric("제품수", len(f)); k2.metric("제조사", f['제조사'].nunique())
    k3.metric("평균가격", f"{f['가격(원)'].dropna().mean():,.0f}원")
    st.dataframe(f[['No','대분류','세부유형','제품명','제조사','용량(ml)','가격(원)']],
                 use_container_width=True, height=300)


# ============================================================
# PAGE 6: 교육용 실습
# ============================================================
def page_education():
    st.markdown('<div class="sim-hdr">🎓 교육용 배합 실습</div>', unsafe_allow_html=True)
    bev = st.selectbox("실습 음료유형", df_spec['음료유형'].dropna().tolist(), key="edu_bev")
    step_slot_map = {'1단계_원재료': list(range(0,4)), '2단계_당류': list(range(4,8)),
                     '3단계_산미료': [12,13], '4단계_안정제': list(range(8,12)),
                     '5단계_기타': [14,15,16,17,18]}
    for step_key, step_info in EDUCATION_STEPS.items():
        slot_idxs = step_slot_map.get(step_key, [])
        st.markdown(f'<div class="edu-step">{step_info["icon"]} <b>{step_info["title"]}</b> — {step_info["items"]}</div>', unsafe_allow_html=True)
        st.markdown(f'📖 {step_info["guide"]}')
        st.markdown(f'<div class="edu-warn">{step_info["warning"]}</div>', unsafe_allow_html=True)
        for si in slot_idxs:
            ec = st.columns([0.3, 2.5, 1.2, 1.0])
            ec[0].markdown(f'<span class="t-cel">{si+1}</span>', unsafe_allow_html=True)
            s = st.session_state.edu_slots[si]
            with ec[1]:
                opts = [''] + ING_LIST
                cur = s.get('원료명', '')
                ci = opts.index(cur) if cur in opts else 0
                p = st.selectbox("원료", opts, index=ci, label_visibility="collapsed",
                                 key=f"ei{si}", format_func=lambda x: "(선택)" if x=='' else x)
                if p and p != cur:
                    st.session_state.edu_slots[si] = fill_slot_from_db(EMPTY_SLOT.copy(), p, df_ing, PH_COL)
            with ec[2]:
                pct = st.number_input("pct", 0.0, 100.0, float(s.get('배합비(%)',0)), 0.1,
                                      format="%.2f", label_visibility="collapsed", key=f"ep{si}")
                st.session_state.edu_slots[si]['배합비(%)'] = pct
            st.session_state.edu_slots[si] = calc_slot_contributions(st.session_state.edu_slots[si])
            ec[3].markdown(f'<span class="t-num">Bx: {st.session_state.edu_slots[si].get("당기여",0):.2f}</span>', unsafe_allow_html=True)
        st.markdown("---")
    er = calc_formulation(st.session_state.edu_slots, 500)
    mc = st.columns(5)
    mc[0].metric("Brix", f"{er['예상당도(Bx)']:.2f}°"); mc[1].metric("pH", f"{er['예상pH']:.2f}")
    mc[2].metric("산도", f"{er['예상산도(%)']:.4f}%"); mc[3].metric("정제수", f"{er['정제수비율(%)']:.1f}%")
    mc[4].metric("원가", f"{er['원재료비(원/kg)']:,.0f}원/kg")
    es = get_spec(df_spec, bev)
    if es:
        for k, (msg, ok) in check_compliance(er, es).items():
            (st.success if ok is True else st.error if ok is False else st.info)(f"{k}: {msg}")
    if st.button("🔄 초기화"): st.session_state.edu_slots = init_slots(); st.rerun()


# ============================================================
# PAGE 7: HACCP
# ============================================================
def page_planner():
    st.title("📋 기획서 + 공정시방서 + HACCP")
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)',0)) > 0 and s.get('원료명')]
    if not active: st.warning("배합표가 비어있습니다."); return
    st.markdown(f"**{st.session_state.product_name}** | {st.session_state.bev_type} | {st.session_state.volume}ml")
    mc = st.columns(6)
    mc[0].metric("Brix", result['예상당도(Bx)']); mc[1].metric("pH", result['예상pH'])
    mc[2].metric("산도", f"{result['예상산도(%)']:.4f}%"); mc[3].metric("감미도", f"{result['예상감미도']:.4f}")
    mc[4].metric("당산비", result['당산비']); mc[5].metric("원가", f"{result['원재료비(원/kg)']:,.0f}")
    tabs = st.tabs(["📋 기획서", "🏭 SOP", "📄 HACCP (6종)", "🤖 AI 보고서"])
    with tabs[0]:
        raw_b = result['원재료비(원/병)']
        pkg = {'PET':120,'캔':90,'유리병':200,'종이팩':80,'파우치':60}.get(st.session_state.container,100)
        mfg = raw_b*0.4; total = raw_b+pkg+mfg; price = st.session_state.target_price; margin = price-total
        st.dataframe(pd.DataFrame({'항목':['원재료비','포장재비','제조비','총원가','판매가','마진'],
            '금액(원/병)':[f'{raw_b:,.0f}',f'{pkg:,.0f}',f'{mfg:,.0f}',f'{total:,.0f}',f'{price:,.0f}',f'{margin:,.0f}']}),
            use_container_width=True, hide_index=True)
    with tabs[1]:
        matched = match_process(st.session_state.bev_type, df_process)
        if not matched.empty:
            for _, p in matched.iterrows():
                step = str(p.get('세부공정',''))
                icon = '⚙️'
                for kw, ic in HACCP_ICONS.items():
                    if kw in step: icon = ic; break
                ccp_raw = str(p.get('CCP여부',''))
                ccp_tag = f" 🔴 **{ccp_raw}**" if ccp_raw.startswith('CCP') else ""
                with st.expander(f"{icon} {p.get('공정단계','')} — {step}{ccp_tag}"):
                    st.markdown(f"**작업방법**: {p.get('작업방법(구체적)','-')}")
                    st.markdown(f"**조건**: {p.get('주요조건/파라미터','-')}")
                    if ccp_raw.startswith('CCP'):
                        st.error(f"🔴 {ccp_raw} | CL: {p.get('한계기준(CL)','-')} | 모니터링: {p.get('모니터링방법','-')}")
            st.download_button("💾 SOP", haccp_sop(st.session_state.bev_type, df_process,
                st.session_state.product_name, st.session_state.slots), f"SOP.txt")
    with tabs[2]:
        matched = match_process(st.session_state.bev_type, df_process)
        if not matched.empty:
            docs = {"① 위해분석표": haccp_ha_worksheet(st.session_state.bev_type, df_process),
                    "② CCP결정도": haccp_ccp_decision_tree(st.session_state.bev_type, df_process),
                    "③ CCP관리계획서": haccp_ccp_plan(st.session_state.bev_type, df_process),
                    "④ 모니터링일지": haccp_monitoring_log(st.session_state.bev_type, df_process),
                    "⑤ 공정흐름도": haccp_flow_diagram(st.session_state.bev_type, df_process),
                    "⑥ SOP": haccp_sop(st.session_state.bev_type, df_process,
                        st.session_state.product_name, st.session_state.slots)}
            for t, d in docs.items():
                with st.expander(t): st.code(d, language=None); st.download_button("💾", d, f"HACCP_{t[:4]}.txt", key=f"dl_{t}")
            st.download_button("📦 6종 일괄", '\n\n'.join([f"{'='*60}\n{t}\n{'='*60}\n{d}" for t,d in docs.items()]),
                              "HACCP_전체.txt", type="primary")
    with tabs[3]:
        if not OPENAI_KEY: st.error("API 키 필요"); return
        rtype = st.selectbox("관점", ["🧑‍🔬 R&D", "🏭 생산관리자", "📄 품질전문가"])
        persona = {"🧑‍🔬 R&D": PERSONA_PLANNER, "🏭 생산관리자": PERSONA_PRODUCTION, "📄 품질전문가": PERSONA_QA}[rtype]
        if st.button("📝 보고서", type="primary"):
            ft = '\n'.join([f"{n}:{p:.3f}%" for n,p in active])
            with st.spinner("AI..."): r = call_gpt(OPENAI_KEY, persona, f"제품:{st.session_state.product_name}\n배합:\n{ft}\n종합 분석보고서"); st.markdown(r)


# ============================================================
# PAGE 8~10
# ============================================================
def page_labeling():
    st.title("📑 식품표시사항")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots if safe_float(s.get('배합비(%)',0)) > 0 and s.get('원료명')]
    if not active: st.warning("배합표가 비어있습니다."); return
    label = generate_food_label(st.session_state.slots, st.session_state.product_name, st.session_state.volume, st.session_state.bev_type)
    items = []
    for k,v in label.items():
        if isinstance(v,dict):
            for sk,sv in v.items(): items.append({'항목':f'  {sk}','내용':str(sv)})
        else: items.append({'항목':k,'내용':str(v)})
    st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)

def page_lab_recipe():
    st.title("🧫 시작 레시피")
    active = [(s['원료명'],s['배합비(%)']) for s in st.session_state.slots if safe_float(s.get('배합비(%)',0))>0 and s.get('원료명')]
    if not active: st.warning("비어있음"); return
    scales = st.multiselect("스케일", [1,5,10,20,50,100], default=[1,5,20])
    if scales:
        for sc, items in generate_lab_recipe(st.session_state.slots, scales).items():
            st.subheader(f"📋 {sc}"); st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)

def page_history():
    st.title("📓 히스토리")
    if not st.session_state.history: st.info("시뮬레이터에서 저장하세요."); return
    for idx, h in enumerate(st.session_state.history):
        with st.expander(f"**{h['name']}** — {h['timestamp']}"):
            r = h.get('result', {})
            cc = st.columns(5)
            cc[0].metric("Brix", r.get('예상당도(Bx)','-')); cc[1].metric("pH", r.get('예상pH','-'))
            cc[2].metric("산도", f"{r.get('예상산도(%)',0):.4f}%")
            cc[3].metric("당산비", r.get('당산비','-')); cc[4].metric("원가", f"{r.get('원재료비(원/kg)',0):,.0f}")
            if st.button("📤 로드", key=f"ld{idx}"): st.session_state.slots = [s.copy() for s in h['slots']]; st.success("✅")
            if st.button("🗑️", key=f"rm{idx}"): st.session_state.history.pop(idx); st.rerun()


{"🎯 컨셉→배합설계": page_concept, "🧪 배합 시뮬레이터": page_simulator,
 "🧑‍🔬 AI 연구원 평가": page_ai_researcher, "🎨 제품 이미지 생성": page_image,
 "🔄 역설계": page_reverse, "📊 시장분석": page_market,
 "🎓 교육용 실습": page_education, "📋 기획서/HACCP": page_planner,
 "📑 식품표시사항": page_labeling, "🧫 시작 레시피": page_lab_recipe,
 "📓 배합 히스토리": page_history}[page]()
