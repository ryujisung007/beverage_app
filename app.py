"""
🧪 음료개발 AI 플랫폼 v7.5
- page_image() 함수 구조 수정 (들여쓰기/함수 밖 코드 오류 해결)
- concept_text session_state 저장 추가
- RTD 음료 정교한 DALL-E 프롬프트 (배합표 + 마케팅 컨셉 연동)
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

df_type    = DATA['음료유형분류']
df_product = DATA['시장제품DB']
df_ing     = DATA['원료DB']
df_spec    = DATA['음료규격기준']
df_process = DATA['표준제조공정_HACCP']
df_guide   = DATA['가이드배합비DB']

for c in ['Brix(°)', 'pH', '산도(%)', '감미도(설탕대비)', '예상단가(원/kg)',
          '1%사용시 Brix기여(°)', '1%사용시 산도기여(%)', '1%사용시 감미기여']:
    df_ing[c] = pd.to_numeric(df_ing[c], errors='coerce').fillna(0)
PH_COL = [c for c in df_ing.columns if 'pH영향' in str(c) or 'ΔpH' in str(c)][0]
df_ing[PH_COL] = pd.to_numeric(df_ing[PH_COL], errors='coerce').fillna(0)

try:
    OPENAI_KEY = st.secrets["openai"]["OPENAI_API_KEY"]
except:
    OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")

ING_LIST  = df_ing['원료명'].tolist()
ING_NAMES = ['(선택)', '✏️ 직접입력'] + ING_LIST

# ── session_state 초기화 ──
for k, v in [
    ('slots',           init_slots()),
    ('history',         []),
    ('product_name',    ''),
    ('bev_type',        ''),
    ('flavor',          ''),
    ('volume',          500),
    ('container',       'PET'),
    ('target_price',    1500),
    ('ai_response',     ''),
    ('generated_image', ''),
    ('concept_result',  None),
    ('concept_text',    ''),        # ← 마케팅 컨셉 원문 저장
    ('edu_slots',       init_slots()),
    ('ai_est_results',  []),
]:
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown("""<style>
.sim-hdr{background:#1a237e;color:white;padding:12px 18px;border-radius:6px;font-weight:bold;font-size:22px;margin-bottom:14px}
.grp-lbl{background:#fff9c4;padding:6px 14px;font-weight:bold;font-size:17px;border-left:5px solid #f9a825;margin:10px 0;border-radius:3px}
.t-hdr{font-size:13px!important;font-weight:800!important;color:#1a237e!important;background:#e3f2fd;padding:5px 6px;border-radius:3px;text-align:center;line-height:2.0}
.t-cel{font-size:14px!important;color:#212121!important;font-weight:500!important;line-height:2.0}
.t-num{font-size:14px!important;color:#1565c0!important;font-weight:700!important}
.t-cust{font-size:12px!important;color:#e65100!important;font-weight:bold}
.pass{color:#2e7d32;font-weight:bold;font-size:16px}
.fail{color:#c62828;font-weight:bold;font-size:16px}
.infot{color:#1565c0;font-weight:bold;font-size:15px}
.rrow{font-size:17px!important;padding:5px 0;line-height:2.0}
.edu-step{background:#f3e5f5;border-left:5px solid #9c27b0;padding:14px 18px;border-radius:5px;margin:10px 0;font-size:16px}
.edu-warn{background:#fff3e0;border-left:5px solid #ff9800;padding:10px 14px;border-radius:4px;margin:6px 0;font-size:15px}
.est-box{background:#e3f2fd;border:2px solid #1565c0;border-radius:8px;padding:14px;margin:10px 0}
div[data-testid="stNumberInput"] input{font-size:15px!important;padding:6px 8px!important}
div[data-testid="stSelectbox"] > div{font-size:14px!important}
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
    st.sidebar.info(f"📦 {st.session_state.product_name}\n{st.session_state.bev_type}/{st.session_state.flavor}")


# ============================================================
# 헬퍼
# ============================================================
def clear_slot_widget_keys():
    for i in range(20):
        for prefix in ['i', 'ci', 'pct']:
            st.session_state.pop(f"{prefix}{i}", None)


def load_formulation_with_estimation(formulation_list, auto_estimate=True):
    new_slots = init_slots()
    need_est  = []

    for item in formulation_list:
        i = int(item.get('슬롯', 1)) - 1
        if i < 0 or i >= 19:
            continue
        nm  = str(item.get('원료명', '')).strip()
        pct = safe_float(item.get('배합비', 0))
        if not nm or pct <= 0:
            continue

        new_slots[i] = fill_slot_from_db(EMPTY_SLOT.copy(), nm, df_ing, PH_COL)
        new_slots[i]['배합비(%)']        = pct
        new_slots[i]['AI추천_원료명']    = nm
        new_slots[i]['AI추천_%']         = pct
        new_slots[i]['AI용도특성']       = item.get('용도특성', item.get('구분', ''))
        new_slots[i] = calc_slot_contributions(new_slots[i])

        if new_slots[i].get('is_custom'):
            bx = safe_float(new_slots[i].get('당도(Bx)', 0))
            ac = safe_float(new_slots[i].get('산도(%)', 0))
            sw = safe_float(new_slots[i].get('감미도', 0))
            pr = safe_float(new_slots[i].get('단가(원/kg)', 0))
            if bx == 0 and ac == 0 and sw == 0 and pr == 0:
                need_est.append(i)

    est_results = []
    if auto_estimate and need_est and OPENAI_KEY:
        for idx in need_est:
            nm = new_slots[idx]['원료명']
            try:
                est = call_gpt_estimate_ingredient(OPENAI_KEY, nm)
                new_slots[idx] = apply_estimation_to_slot(new_slots[idx], est)
                est_results.append({'슬롯': idx+1, '원료명': nm, **est})
            except Exception as e:
                est_results.append({'슬롯': idx+1, '원료명': nm, '오류': str(e)})

    return new_slots, est_results


# ============================================================
# PAGE 0: 컨셉 → 배합설계
# ============================================================
def page_concept():
    st.markdown('<div class="sim-hdr">🎯 마케팅 컨셉 → R&D 배합설계</div>', unsafe_allow_html=True)
    st.caption("마케팅 기획자의 컨셉을 붙여넣으면, R&D 음료연구원 AI가 배합표로 변환합니다.")

    concept = st.text_area(
        "📋 마케팅 컨셉 (복사/붙여넣기)", height=200,
        placeholder="예시: 2030 여성 타겟, 비타민C 풍부한 자몽+레몬 상큼 음료, 저칼로리...",
        value=st.session_state.concept_text,
    )
    # ← 컨셉 원문 session_state 저장 (이미지 생성 페이지에서 활용)
    st.session_state.concept_text = concept

    if st.button("🤖 R&D 음료연구원에게 전달", type="primary", use_container_width=True):
        if not OPENAI_KEY:
            st.error("OpenAI API 키 필요")
            return
        if not concept.strip():
            st.warning("컨셉을 입력하세요.")
            return
        with st.spinner("🧑‍🔬 R&D센터: 컨셉분석 → 배합설계 → DB매칭 → 이화학분석 중..."):
            sample = ', '.join(df_ing['원료명'].sample(min(30, len(df_ing))).tolist())
            result = call_gpt_marketing_to_rd(OPENAI_KEY, concept, sample)
            st.session_state.concept_result = result
            if result.get('formulation'):
                new_slots, est_results = load_formulation_with_estimation(
                    result['formulation'], auto_estimate=True)
                st.session_state.slots         = new_slots
                st.session_state.ai_est_results = est_results
                if result.get('bev_type'):
                    st.session_state.bev_type = result['bev_type']
                if result.get('flavor'):
                    st.session_state.flavor   = result['flavor']
                clear_slot_widget_keys()
                st.rerun()

    if st.session_state.concept_result:
        r = st.session_state.concept_result
        st.markdown("---")
        st.markdown(r.get('text', ''))

        rows = []
        for i, s in enumerate(st.session_state.slots[:19]):
            if s.get('원료명') and safe_float(s.get('배합비(%)', 0)) > 0:
                rows.append({
                    'No': i+1, '원료명': s['원료명'],
                    '배합비(%)': round(s['배합비(%)'], 3),
                    'Brix': s.get('당도(Bx)', 0),
                    '산도(%)': round(safe_float(s.get('산도(%)', 0)), 3),
                    '감미도': s.get('감미도', 0),
                    '단가(원/kg)': int(safe_float(s.get('단가(원/kg)', 0))),
                    '당기여': round(s.get('당기여', 0), 2),
                    '출처': '✅DB' if not s.get('is_custom') else '🤖AI추정',
                })
        if rows:
            st.markdown("### 📊 추천 배합표 (이화학분석 반영)")
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if st.session_state.ai_est_results:
            st.markdown('<div class="est-box">🤖 <b>AI 이화학분석 결과</b></div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(st.session_state.ai_est_results), use_container_width=True, hide_index=True)

        if r.get('ingredients_info'):
            with st.expander("🔍 주요원료 특장점"):
                for info in r['ingredients_info']:
                    st.markdown(f"• **{info.get('원료명','')}**: {info.get('사용이유','')}")

        bc1, bc2, bc3 = st.columns(3)
        with bc1:
            st.success("✅ 배합표 자동 적용됨! '배합 시뮬레이터'에서 확인하세요.")
        with bc2:
            if rows:
                csv = pd.DataFrame(rows).to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 CSV", csv, "추천배합표.csv", "text/csv", use_container_width=True)
        with bc3:
            if st.button("💾 히스토리 저장", use_container_width=True):
                st.session_state.history.append({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'name':      f"컨셉_{r.get('flavor','AI')}",
                    'type':      r.get('bev_type', ''),
                    'flavor':    r.get('flavor', ''),
                    'slots':     [s.copy() for s in st.session_state.slots],
                    'result':    calc_formulation(st.session_state.slots, st.session_state.volume),
                    'notes':     '',
                })
                st.success("✅ 저장")


# ============================================================
# PAGE 1: 배합 시뮬레이터
# ============================================================
def page_simulator():
    st.markdown('<div class="sim-hdr">🧪 음료 배합비 시뮬레이터</div>', unsafe_allow_html=True)

    h1, h2, h3, h4 = st.columns([1.5, 2, 1.5, 1.5])
    with h1:
        st.session_state.product_name = st.text_input(
            "📋 제품명", st.session_state.product_name or "사과과채음료_시제1호")
        bev_types = df_spec['음료유형'].dropna().tolist()
        bt_idx    = bev_types.index(st.session_state.bev_type) if st.session_state.bev_type in bev_types else 0
        st.session_state.bev_type = st.selectbox("음료유형", bev_types, index=bt_idx)
    with h2:
        bt_short   = st.session_state.bev_type.split('(')[0].replace('·', '')
        guide_keys = df_guide['키(유형_맛_슬롯)'].dropna().unique()
        flavors    = sorted(set(k.split('_')[1] for k in guide_keys if bt_short in k.split('_')[0].replace('·', '')))
        flavor_opts = flavors + ['직접입력']
        sel = st.selectbox("맛(Flavor)", flavor_opts)
        st.session_state.flavor = (st.text_input("맛 직접입력", st.session_state.flavor)
                                    if sel == '직접입력' else sel)
    with h3:
        st.session_state.volume    = st.number_input("목표용량(ml)", 100, 2000, st.session_state.volume, 50)
        st.session_state.container = st.selectbox("포장용기", ['PET', '캔', '유리병', '종이팩', '파우치'])
    with h4:
        spec = get_spec(df_spec, st.session_state.bev_type)
        if spec:
            st.markdown("**📋 규격기준**")
            st.markdown(f"Bx {spec['Brix_min']}~{spec['Brix_max']}°")
            st.markdown(f"pH {spec['pH_min']}~{spec['pH_max']}")

    st.markdown("---")
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        if st.button("🤖 AI 추천배합비", use_container_width=True, type="primary"):
            if not OPENAI_KEY:
                st.error("OpenAI API 키 필요")
                return
            with st.spinner("🤖 AI 배합설계 + DB매칭 + 이화학분석..."):
                sample  = ', '.join(df_ing['원료명'].sample(min(30, len(df_ing))).tolist())
                ai_form = call_gpt_ai_formulation(OPENAI_KEY, st.session_state.bev_type,
                                                   st.session_state.flavor, sample)
                if ai_form:
                    new_slots, est_results = load_formulation_with_estimation(ai_form, auto_estimate=True)
                    st.session_state.slots          = new_slots
                    st.session_state.ai_est_results = est_results
                    clear_slot_widget_keys()
                    st.rerun()
    with bc2:
        if st.button("📥 가이드배합비", use_container_width=True):
            st.session_state.slots = load_guide(df_guide, st.session_state.bev_type,
                                                 st.session_state.flavor, df_ing, PH_COL)
            clear_slot_widget_keys()
            st.rerun()
    with bc3:
        if st.button("🔄 전체 초기화", use_container_width=True):
            st.session_state.slots          = init_slots()
            st.session_state.ai_est_results = []
            clear_slot_widget_keys()
            st.rerun()

    st.markdown("---")
    hdr = st.columns([0.3, 2.5, 1.0, 0.7, 0.7, 0.7, 0.7, 0.7, 0.6])
    for i, h in enumerate(['No', '원료명', '배합비(%)', 'Bx', '산도', '감미', '단가', '당기여', 'g/kg']):
        hdr[i].markdown(f'<div class="t-hdr">{h}</div>', unsafe_allow_html=True)

    for group_name, group_rows in SLOT_GROUPS:
        if group_name == '정제수':
            continue
        st.markdown(f'<div class="grp-lbl">{group_name}</div>', unsafe_allow_html=True)
        for rn in group_rows:
            idx      = rn - 1
            s        = st.session_state.slots[idx]
            cur      = s.get('원료명', '')
            is_custom = s.get('is_custom', False)

            c = st.columns([0.3, 2.5, 1.0, 0.7, 0.7, 0.7, 0.7, 0.7, 0.6])
            c[0].markdown(f'<span class="t-cel">{rn}</span>', unsafe_allow_html=True)

            with c[1]:
                if cur and cur in ING_LIST:
                    def_idx = ING_NAMES.index(cur)
                elif cur and is_custom:
                    def_idx = 1
                else:
                    def_idx = 0

                picked = st.selectbox("원료", ING_NAMES, index=def_idx,
                                      label_visibility="collapsed", key=f"i{idx}")

                if picked == '✏️ 직접입력':
                    cname = st.text_input("원료명입력", value=cur if is_custom else "",
                                          label_visibility="collapsed", key=f"ci{idx}",
                                          placeholder="원료명 입력 후 Enter")
                    if cname and cname != cur:
                        new_s = fill_slot_from_db(EMPTY_SLOT.copy(), cname, df_ing, PH_COL)
                        new_s['배합비(%)']   = safe_float(s.get('배합비(%)', 0))
                        new_s['AI용도특성'] = s.get('AI용도특성', '')
                        st.session_state.slots[idx] = new_s
                        s = new_s
                    elif not cname and cur:
                        st.session_state.slots[idx] = EMPTY_SLOT.copy()
                        s = st.session_state.slots[idx]

                elif picked == '(선택)':
                    if cur:
                        st.session_state.slots[idx] = EMPTY_SLOT.copy()
                        s = st.session_state.slots[idx]

                elif picked != cur:
                    old_pct = safe_float(s.get('배합비(%)', 0))
                    st.session_state.slots[idx] = fill_slot_from_db(EMPTY_SLOT.copy(), picked, df_ing, PH_COL)
                    st.session_state.slots[idx]['배합비(%)'] = old_pct
                    s = st.session_state.slots[idx]

            with c[2]:
                new_pct = st.number_input("pct", 0.0, 100.0, float(s.get('배합비(%)', 0)),
                                          0.1, format="%.3f", label_visibility="collapsed", key=f"pct{idx}")
                st.session_state.slots[idx]['배합비(%)'] = new_pct

            st.session_state.slots[idx] = calc_slot_contributions(st.session_state.slots[idx])
            s = st.session_state.slots[idx]

            css = 't-cust' if s.get('is_custom') and s.get('원료명') else 't-cel'
            c[3].markdown(f'<span class="{css}">{s.get("당도(Bx)", 0)}</span>',    unsafe_allow_html=True)
            c[4].markdown(f'<span class="{css}">{s.get("산도(%)", 0)}</span>',      unsafe_allow_html=True)
            c[5].markdown(f'<span class="{css}">{s.get("감미도", 0)}</span>',       unsafe_allow_html=True)
            c[6].markdown(f'<span class="{css}">{safe_float(s.get("단가(원/kg)", 0)):,.0f}</span>', unsafe_allow_html=True)
            c[7].markdown(f'<span class="t-num">{s.get("당기여", 0):.2f}</span>',   unsafe_allow_html=True)
            c[8].markdown(f'<span class="t-num">{s.get("배합량(g/kg)", 0):.1f}</span>', unsafe_allow_html=True)

    # 정제수
    ing_total = round(sum(safe_float(st.session_state.slots[j].get('배합비(%)', 0)) for j in range(19)), 3)
    water_pct = round(max(0, 100 - ing_total), 3)
    st.session_state.slots[19]['원료명']       = '정제수'
    st.session_state.slots[19]['배합비(%)']    = water_pct
    st.session_state.slots[19]['배합량(g/kg)'] = round(water_pct * 10, 1)

    wc = st.columns([0.3, 2.5, 1.0, 0.7, 0.7, 0.7, 0.7, 0.7, 0.6])
    wc[0].markdown('<span class="t-cel">20</span>', unsafe_allow_html=True)
    wc[1].markdown('**💧 정제수**')
    wc[2].markdown(f'<span class="t-num">{water_pct:.3f}%</span>', unsafe_allow_html=True)
    wc[8].markdown(f'<span class="t-num">{water_pct*10:.1f}</span>', unsafe_allow_html=True)

    st.markdown("---")

    custom_zero = [i for i in range(19)
                   if st.session_state.slots[i].get('is_custom')
                   and st.session_state.slots[i].get('원료명')
                   and safe_float(st.session_state.slots[i].get('배합비(%)', 0)) > 0
                   and safe_float(st.session_state.slots[i].get('당도(Bx)', 0)) == 0
                   and safe_float(st.session_state.slots[i].get('산도(%)', 0)) == 0
                   and safe_float(st.session_state.slots[i].get('감미도', 0)) == 0
                   and safe_float(st.session_state.slots[i].get('단가(원/kg)', 0)) == 0]

    custom_all = [i for i in range(19)
                  if st.session_state.slots[i].get('is_custom')
                  and st.session_state.slots[i].get('원료명')
                  and safe_float(st.session_state.slots[i].get('배합비(%)', 0)) > 0]

    if custom_zero and OPENAI_KEY:
        names = ', '.join([st.session_state.slots[i]['원료명'] for i in custom_zero])
        st.warning(f"⚠️ 이화학데이터 없음: **{names}**")
        if st.button(f"🤖 AI 이화학분석 실행 ({len(custom_zero)}종)", type="primary", use_container_width=True):
            bar         = st.progress(0)
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

    if st.session_state.ai_est_results:
        st.markdown('<div class="est-box">🤖 <b>AI 이화학분석 결과</b></div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(st.session_state.ai_est_results), use_container_width=True, hide_index=True)

    st.markdown("---")
    if ing_total > 100:
        st.error(f"⚠️ 원료합계 **{ing_total:.3f}%** > 100%")
        if st.button("💧 정제수 0%로 설정", type="primary", use_container_width=True):
            st.session_state.slots[19]['배합비(%)'] = 0
            st.rerun()
    elif ing_total < 100:
        st.info(f"원료합계 **{ing_total:.3f}%** — 정제수 **{water_pct:.3f}%**")
        if abs(water_pct - safe_float(st.session_state.slots[19].get('배합비(%)', 0))) > 0.001:
            if st.button(f"💧 정제수 → {water_pct:.3f}% 조정", type="primary", use_container_width=True):
                st.session_state.slots[19]['배합비(%)'] = water_pct
                st.rerun()
    else:
        st.success(f"✅ 합계 100.000%")

    if custom_all:
        with st.expander(f"✏️ 직접입력 원료 상세편집 ({len(custom_all)}종)", expanded=False):
            st.caption("AI추정값이 부정확하면 여기서 직접 수정하세요.")
            for ci in custom_all:
                s = st.session_state.slots[ci]
                st.markdown(f"**슬롯{ci+1}: {s['원료명']}** ({s['배합비(%)']:.3f}%)")
                ec = st.columns(5)
                with ec[0]:
                    bx = st.number_input("Brix", 0.0, 100.0, float(s.get('당도(Bx)', 0)), 0.1, key=f"cbx{ci}")
                    st.session_state.slots[ci]['당도(Bx)'] = bx
                    st.session_state.slots[ci]['Brix(°)']  = bx
                    st.session_state.slots[ci]['1%Brix기여'] = round(bx/100, 4) if bx else 0
                with ec[1]:
                    ac = st.number_input("산도(%)", 0.0, 50.0, float(s.get('산도(%)', 0)), 0.01, key=f"cac{ci}")
                    st.session_state.slots[ci]['산도(%)']    = ac
                    st.session_state.slots[ci]['1%산도기여'] = round(ac/100, 4) if ac else 0
                with ec[2]:
                    sw = st.number_input("감미도", 0.0, 50000.0, float(s.get('감미도', 0)), 0.1, key=f"csw{ci}")
                    st.session_state.slots[ci]['감미도']    = sw
                    st.session_state.slots[ci]['1%감미기여'] = round(sw/100, 4) if sw else 0
                with ec[3]:
                    pr = st.number_input("단가", 0, 500000, int(s.get('단가(원/kg)', 0)), 100, key=f"cpr{ci}")
                    st.session_state.slots[ci]['단가(원/kg)'] = pr
                with ec[4]:
                    if OPENAI_KEY and st.button("🤖재추정", key=f"cai{ci}"):
                        try:
                            est = call_gpt_estimate_ingredient(OPENAI_KEY, s['원료명'])
                            st.session_state.slots[ci] = apply_estimation_to_slot(st.session_state.slots[ci], est)
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                st.session_state.slots[ci] = calc_slot_contributions(st.session_state.slots[ci])

    active_idxs = [i for i in range(19)
                   if st.session_state.slots[i].get('원료명')
                   and safe_float(st.session_state.slots[i].get('배합비(%)', 0)) > 0]
    no_info = [i for i in active_idxs if not st.session_state.slots[i].get('AI용도특성')]
    if OPENAI_KEY and no_info:
        if st.button(f"🔍 AI 원료 용도/특성 조회 ({len(no_info)}종)", use_container_width=True):
            bar = st.progress(0)
            for pi, i in enumerate(no_info):
                try:
                    st.session_state.slots[i]['AI용도특성'] = call_gpt_ingredient_info(
                        OPENAI_KEY, st.session_state.slots[i]['원료명'])
                except:
                    pass
                bar.progress((pi+1)/len(no_info))
            st.rerun()

    st.markdown("---")
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    st.markdown('<div class="sim-hdr">▶ 시뮬레이션 결과</div>', unsafe_allow_html=True)
    spec  = get_spec(df_spec, st.session_state.bev_type)
    comp  = check_compliance(result, spec) if spec else {}

    r1, r2 = st.columns(2)
    with r1:
        for label, val, status in [
            ("배합비 합계",  f"{result['배합비합계(%)']:.3f}%",
             "✅ 100%" if abs(result['배합비합계(%)']-100) < 0.01 else f"⚠️ {result['배합비합계(%)']:.3f}%"),
            ("예상 당도(Bx)", f"{result['예상당도(Bx)']:.2f}°", comp.get('당도', ('',))[0]),
            ("예상 산도",     f"{result['예상산도(%)']:.4f}%",   comp.get('산도', ('',))[0]),
            ("예상 감미도",   f"{result['예상감미도']:.4f}",      ""),
            ("원가(원/kg)",   f"{result['원재료비(원/kg)']:,.0f}", ""),
            ("원가(원/병)",   f"{result['원재료비(원/병)']:,.0f}", ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'infot')
            st.markdown(f'<div class="rrow"><b>{label}</b> <code>{val}</code> <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)
    with r2:
        for label, val, status in [
            ("정제수",   f"{result['정제수비율(%)']:.1f}%",  ""),
            ("pH(참고)", f"{result['예상pH']:.2f}",          comp.get('pH', ('ℹ️ 실측필요',))[0]),
            ("당산비",   f"{result['당산비']}",               ""),
            ("과즙함량", f"{result['과즙함량(%)']:.1f}%",    ""),
        ]:
            cls = 'pass' if '✅' in str(status) else ('fail' if '⚠️' in str(status) else 'infot')
            st.markdown(f'<div class="rrow"><b>{label}</b> <code>{val}</code> <span class="{cls}">{status}</span></div>', unsafe_allow_html=True)

    st.markdown("---")
    b1, b2, b3 = st.columns(3)
    with b1:
        sn = st.text_input("저장명", f"{st.session_state.product_name}_{datetime.now().strftime('%H%M')}")
        if st.button("💾 히스토리 저장", use_container_width=True):
            st.session_state.history.append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'name': sn,
                'type':      st.session_state.bev_type,
                'flavor':    st.session_state.flavor,
                'slots':     [s.copy() for s in st.session_state.slots],
                'result':    result.copy(), 'notes': '',
            })
            st.success(f"✅ 저장 ({len(st.session_state.history)}건)")
    with b2:
        st.markdown("<br>", unsafe_allow_html=True)
        out_rows = [{'No': i+1, '원료명': s['원료명'], '배합비(%)': round(s['배합비(%)'], 3),
                     'Brix': s.get('당도(Bx)', 0), '산도': s.get('산도(%)', 0),
                     '감미도': s.get('감미도', 0), '단가': s.get('단가(원/kg)', 0),
                     'g/kg': s.get('배합량(g/kg)', 0)}
                    for i, s in enumerate(st.session_state.slots)
                    if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
        if out_rows:
            st.download_button("📥 CSV",
                               pd.DataFrame(out_rows).to_csv(index=False).encode('utf-8-sig'),
                               f"배합표_{st.session_state.product_name}.csv", "text/csv",
                               use_container_width=True)
    with b3:
        st.markdown("<br>", unsafe_allow_html=True)
        if out_rows and st.button("📋 배합표 출력", use_container_width=True):
            st.dataframe(pd.DataFrame(out_rows), use_container_width=True, hide_index=True)


# ============================================================
# PAGE 2: AI 연구원
# ============================================================
def page_ai_researcher():
    st.title("🧑‍🔬 AI 음료개발연구원 평가")
    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요")
        return
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다.")
        return
    with st.expander("📋 현재 배합표", expanded=True):
        st.dataframe(pd.DataFrame(active, columns=['원료명', '배합비(%)']), use_container_width=True)
        st.markdown(f"**Brix {result['예상당도(Bx)']}° | pH {result['예상pH']} | 산도 {result['예상산도(%)']:.4f}%**")
    target = st.text_input("목표 컨셉", "과즙감 강조, 상큼한 산미밸런스")
    if st.button("🧑‍🔬 평가 요청", type="primary", use_container_width=True):
        form_text  = '\n'.join([f"{n}: {p:.3f}%" for n, p in active])
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
                    [{'슬롯': i+1, '원료명': m['원료명'], '배합비': safe_float(m.get('배합비(%)', 0))}
                     for i, m in enumerate(mod) if i < 19], auto_estimate=True)
                st.session_state.slots          = new
                st.session_state.ai_est_results = est
                clear_slot_widget_keys()
                st.rerun()


# ============================================================
# PAGE 3: 제품 이미지 생성
# ============================================================
def page_image():
    st.markdown('<div class="sim-hdr">🎨 AI 제품 이미지 생성</div>', unsafe_allow_html=True)

    if not OPENAI_KEY:
        st.error("⚠️ OpenAI API 키 필요")
        st.stop()

    # ──────────────────────────────────────────────────────
    # RTD 음료 DALL-E 프롬프트 자동 빌더
    # ──────────────────────────────────────────────────────
    def build_rtd_prompt(product_name, bev_type, slots, container, volume, concept_text=""):
        """
        배합표 원료명 + 마케팅 컨셉 텍스트 →
        실제 RTD 음료 제품사진 느낌의 정교한 DALL-E 프롬프트.
        """
        active_ings = [
            s.get('원료명', '').lower()
            for s in slots
            if s.get('원료명') and safe_float(s.get('배합비(%)', 0)) > 0
        ]

        # ── 플레이버/색상/가니쉬 매핑 ──
        FLAVOR_MAP = {
            '자몽':    ('grapefruit',    '#FF6B4A', 'fresh grapefruit halves with zest'),
            '레몬':    ('lemon',         '#FFF176', 'bright lemon slices and zest ribbons'),
            '라임':    ('lime',          '#A5D6A7', 'lime wedges with crushed mint'),
            '오렌지':  ('orange',        '#FF9800', 'orange slices with peel curl'),
            '사과':    ('apple',         '#C8E6C9', 'crisp green apple slices'),
            '복숭아':  ('peach',         '#FFCCBC', 'ripe peach slices showing texture'),
            '딸기':    ('strawberry',    '#EF9A9A', 'halved fresh strawberries with seeds'),
            '포도':    ('grape',         '#CE93D8', 'purple grape clusters glistening'),
            '망고':    ('mango',         '#FFE082', 'tropical mango cubes with leaf'),
            '유자':    ('yuzu',          '#FFF9C4', 'yuzu citrus with white blossom'),
            '키위':    ('kiwi',          '#DCEDC8', 'kiwi cross-section showing seeds'),
            '파인애플':('pineapple',     '#FFF176', 'golden pineapple chunks with core'),
            '블루베리':('blueberry',     '#9FA8DA', 'plump fresh blueberries'),
            '석류':    ('pomegranate',   '#EF9A9A', 'pomegranate seeds glistening red'),
            '매실':    ('plum',          '#B39DDB', 'green-tinted plum halved'),
            '녹차':    ('green tea',     '#C8E6C9', 'unfurled green tea leaves'),
            '홍차':    ('black tea',     '#D7CCC8', 'rolled black tea leaves with steam'),
            '커피':    ('coffee',        '#8D6E63', 'roasted coffee beans and crema'),
            '아사이':  ('acai',          '#7B1FA2', 'dark acai berries'),
            '히비스커스':('hibiscus',    '#E91E63', 'dried hibiscus petals'),
        }

        detected_flavors  = []
        garnish_elements  = []
        liquid_color_hint = 'light cyan'

        for ing in active_ings:
            for kr, (en, color_hex, garnish) in FLAVOR_MAP.items():
                if kr in ing:
                    detected_flavors.append(en)
                    liquid_color_hint = en
                    if garnish:
                        garnish_elements.append(garnish)

        detected_flavors = list(dict.fromkeys(detected_flavors))
        garnish_elements = list(dict.fromkeys(garnish_elements))

        # ── 용기 묘사 ──
        CONTAINER_MAP = {
            'PET':   (f'{volume}ml transparent PET bottle, ergonomic curved shape, '
                      'moisture condensation droplets on surface, '
                      'slim waist design, frosted label area'),
            '캔':    (f'{volume}ml slim aluminum can, metallic sheen with embossed ridges, '
                      'pull-tab and lid visible from slight angle, '
                      'printed wrap-around label'),
            '유리병': (f'{volume}ml premium glass bottle, thick heavy base, '
                       'crystal clarity showing liquid color, metal crown cap, '
                       'embossed brand mark on glass'),
            '종이팩': (f'{volume}ml Tetra Pak carton, geometric folded edges, '
                       'glossy lamination, straw hole on top'),
            '파우치': (f'{volume}ml stand-up flexible pouch, resealable zip top, '
                       'matte finish with metallic foil accents'),
        }
        container_desc = CONTAINER_MAP.get(container, f'{volume}ml {container} container')

        # ── 음료유형별 액체 묘사 ──
        BEV_LIQUID = {
            '탄산': ('sparkling carbonated liquid with rising micro-bubbles, '
                     'effervescent surface, CO2 streams clearly visible'),
            '과즙': ('slightly cloudy fruit juice, natural pulp opacity, '
                     'rich layered fruit pigmentation'),
            '차':   ('translucent amber tea liquid, delicate tannin golden hue, '
                     'clean bright appearance'),
            '기능': ('crystal-clear functional beverage, '
                     'clean transparent appearance with slight tint'),
        }
        liquid_desc = 'refreshing translucent beverage'
        for key, desc in BEV_LIQUID.items():
            if key in (bev_type or ''):
                liquid_desc = desc
                break
        if any('탄산' in i or 'soda' in i for i in active_ings):
            liquid_desc = BEV_LIQUID['탄산']

        # ── 기능성 포지셔닝 ──
        functional_tags = []
        if any(x in ' '.join(active_ings) for x in ['제로', '에리스', '수크랄', '스테비']):
            functional_tags.append('zero sugar clean-label positioning')
        if any(x in ' '.join(active_ings) for x in ['비타민', '아스코르']):
            functional_tags.append('vitamin-enriched wellness')
        if any(x in ' '.join(active_ings) for x in ['콜라겐', 'collagen']):
            functional_tags.append('beauty collagen drink')
        if any(x in ' '.join(active_ings) for x in ['유산균', '프로바이']):
            functional_tags.append('probiotic health drink')
        if any(x in ' '.join(active_ings) for x in ['홍삼', '인삼']):
            functional_tags.append('Korean red ginseng health drink')

        # ── 마케팅 컨셉에서 분위기 키워드 추출 ──
        mood_tags = []
        concept_low = (concept_text or '').lower()
        if any(x in concept_low for x in ['프리미엄', 'premium', '고급']):
            mood_tags.append('luxury premium feel')
        if any(x in concept_low for x in ['여성', '우먼', 'woman', '2030']):
            mood_tags.append('feminine elegant aesthetic, soft pastel tones')
        if any(x in concept_low for x in ['건강', 'health', '웰니스', 'wellness']):
            mood_tags.append('healthy clean wellness vibe')
        if any(x in concept_low for x in ['청량', '상큼', 'refresh', '시원']):
            mood_tags.append('ultra-refreshing cool atmosphere')
        if any(x in concept_low for x in ['어린이', '키즈', 'kids', '아동']):
            mood_tags.append('playful colorful fun design')
        if any(x in concept_low for x in ['스포츠', 'sport', '에너지', 'energy']):
            mood_tags.append('dynamic energetic sporty mood')

        # ── 프롬프트 조립 ──
        flavor_str   = ' and '.join(detected_flavors[:3]) if detected_flavors else 'natural'
        garnish_str  = ', '.join(garnish_elements[:2])    if garnish_elements else ''
        func_str     = ', '.join(functional_tags)          if functional_tags else ''
        mood_str     = ', '.join(mood_tags)                if mood_tags else 'clean modern commercial'

        parts = [
            # 스타일/카메라
            "Professional commercial beverage product photography,",
            "hyperrealistic 8K render,",
            "studio three-point lighting: soft key light from upper-left,",
            "fill light eliminating harsh shadows, rim light for container edge definition,",

            # 배경
            f"gradient background from pure white to very light {liquid_color_hint} at edges,",

            # 용기
            f"{container_desc},",

            # 액체
            f"containing {flavor_str} flavored {liquid_desc},",

            # 가니쉬
            (f"artfully arranged {garnish_str} beside and partially submerged in foreground,"
             if garnish_str else ""),

            # 수분/청량감
            "photorealistic water condensation droplets covering container exterior,",
            "3-4 ice cubes with internal reflections in foreground,",
            "small water splash droplets frozen in motion near base,",

            # 라벨
            f"product label displaying '{product_name}' in clean modern sans-serif typography,",
            "label features brand color block, subtle barcode, and nutrition facts panel,",

            # 기능성/컨셉 분위기
            (f"packaging design communicates {func_str}," if func_str else ""),
            (f"overall mood: {mood_str}," if mood_str else ""),

            # 구도
            "three-quarter angle view, slight upward camera tilt 15 degrees,",
            "product center-frame with rule-of-thirds balance,",
            "sharp focus on container, subtle background depth-of-field bokeh,",

            # 품질
            "Pantone color accurate, photorealistic rendering,",
            "commercial advertisement quality, no text artifacts, no watermark,",
        ]

        return ' '.join(p for p in parts if p.strip())

    # ──────────────────────────────────────────────────────
    # GPT로 마케팅 컨셉 → 영문 분위기 보완 (선택적)
    # ──────────────────────────────────────────────────────
    def translate_concept_to_style(concept_text):
        """마케팅 컨셉 한국어 → 영문 스타일 키워드 (GPT 호출)"""
        if not concept_text.strip() or not OPENAI_KEY:
            return ""
        try:
            import requests as _req
            resp = _req.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system",
                         "content": (
                             "You are a creative director specializing in beverage product photography. "
                             "Convert Korean beverage marketing concepts into concise English "
                             "visual style keywords for DALL-E prompts. "
                             "Output: 1 sentence, max 30 words, English only, "
                             "focus on visual atmosphere, lighting, and color palette."
                         )},
                        {"role": "user",
                         "content": f"Korean concept: {concept_text}\nConvert to visual style keywords:"}
                    ],
                    "max_tokens": 60,
                    "temperature": 0.7,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        return ""

    # ──────────────────────────────────────────────────────
    # UI 시작
    # ──────────────────────────────────────────────────────

    # 현재 배합표 요약
    active = [(s.get('원료명', ''), round(safe_float(s.get('배합비(%)', 0)), 2))
              for s in st.session_state.slots
              if s.get('원료명') and safe_float(s.get('배합비(%)', 0)) > 0]
    if active:
        with st.expander("📋 현재 배합표 (프롬프트 자동 생성 기준)", expanded=False):
            st.dataframe(pd.DataFrame(active, columns=['원료명', '배합비(%)']),
                         use_container_width=True, hide_index=True)
    else:
        st.info("💡 배합 시뮬레이터에서 원료를 입력하면 더 정교한 이미지 프롬프트가 자동 생성됩니다.")

    # 마케팅 컨셉 표시 (page_concept에서 저장된 값)
    concept_text = st.session_state.get('concept_text', '')
    if concept_text:
        with st.expander("📋 적용된 마케팅 컨셉", expanded=False):
            st.markdown(concept_text)
            st.caption("🎯 컨셉→배합설계 페이지에서 입력한 내용이 이미지 프롬프트에 반영됩니다.")
    else:
        st.caption("💡 '🎯 컨셉→배합설계' 페이지에서 마케팅 컨셉을 입력하면 이미지 스타일에 반영됩니다.")

    # GPT 컨셉 번역 옵션
    gpt_style = ""
    if concept_text and OPENAI_KEY:
        if st.button("✨ 마케팅 컨셉 → 영문 스타일 변환 (GPT)", use_container_width=False,
                     key="concept_translate"):
            with st.spinner("GPT로 컨셉 스타일 변환 중..."):
                gpt_style = translate_concept_to_style(concept_text)
                st.session_state['_gpt_style_cache'] = gpt_style
        gpt_style = st.session_state.get('_gpt_style_cache', '')
        if gpt_style:
            st.success(f"🎨 변환된 스타일: _{gpt_style}_")

    st.markdown("---")

    # 프롬프트 자동 생성
    auto_prompt = build_rtd_prompt(
        product_name  = st.session_state.get('product_name', 'RTD Beverage'),
        bev_type      = st.session_state.get('bev_type', ''),
        slots         = st.session_state.get('slots', []),
        container     = st.session_state.get('container', 'PET'),
        volume        = st.session_state.get('volume', 500),
        concept_text  = concept_text,
    )
    # GPT 스타일 키워드 추가
    if gpt_style:
        auto_prompt = auto_prompt.rstrip(',') + f", {gpt_style},"

    st.markdown("#### ✏️ 이미지 생성 프롬프트")
    st.caption("배합표와 마케팅 컨셉에서 자동 생성됩니다. 직접 수정도 가능합니다.")
    prompt = st.text_area("프롬프트", auto_prompt, height=220, key="dalle_prompt_area")

    # 옵션
    col_a, col_b = st.columns(2)
    with col_a:
        img_size = st.selectbox(
            "이미지 사이즈",
            ["1024x1024", "1024x1792", "1792x1024"],
            index=1, key="dalle_size",
        )
    with col_b:
        img_quality = st.selectbox(
            "품질",
            ["standard", "hd"],
            index=1, key="dalle_quality",
        )

    # 생성 버튼
    if st.button("🎨 이미지 생성", type="primary", use_container_width=True, key="dalle_run"):
        if not prompt.strip():
            st.warning("프롬프트를 입력하세요.")
            st.stop()
        with st.spinner("🎨 DALL-E 3 생성 중… (15~30초 소요)"):
            try:
                # call_dalle 시그니처에 따라 파라미터 조정
                try:
                    st.session_state.generated_image = call_dalle(
                        OPENAI_KEY, prompt, size=img_size, quality=img_quality)
                except TypeError:
                    # engine.py의 call_dalle가 size/quality 미지원 시 fallback
                    st.session_state.generated_image = call_dalle(OPENAI_KEY, prompt)
                st.success("✅ 이미지 생성 완료!")
            except Exception as e:
                st.error(f"❌ 생성 실패: {e}")

    # 결과
    if st.session_state.get('generated_image'):
        st.markdown("---")
        st.markdown("#### 🖼️ 생성 결과")
        st.image(st.session_state.generated_image, use_container_width=True)

        dl_col, reset_col = st.columns(2)
        with dl_col:
            try:
                import requests as _req
                img_bytes = _req.get(st.session_state.generated_image, timeout=15).content
                st.download_button(
                    "📥 이미지 다운로드", img_bytes,
                    file_name=f"{st.session_state.get('product_name','beverage')}_image.png",
                    mime="image/png", use_container_width=True,
                )
            except Exception:
                st.caption("URL로 직접 저장하세요.")
        with reset_col:
            if st.button("🔄 이미지 초기화", use_container_width=True, key="dalle_reset"):
                st.session_state.generated_image = ''
                st.session_state.pop('_gpt_style_cache', None)
                st.rerun()


# ============================================================
# PAGE 4: 역설계
# ============================================================
def page_reverse():
    st.title("🔄 시판제품 역설계")
    cats    = ['전체'] + df_product['대분류'].dropna().unique().tolist()
    sel_cat = st.selectbox("대분류", cats)
    f       = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
    sel     = st.selectbox("제품", f['제품명'].dropna().tolist())
    if sel:
        prod = df_product[df_product['제품명'] == sel].iloc[0]
        st.markdown(f"**{sel}** — {prod.get('제조사','')} | {prod.get('세부유형','')}")
        if st.button("🔄 역설계 → 시뮬레이터", type="primary"):
            st.session_state.slots        = reverse_engineer(prod, df_ing, PH_COL)
            st.session_state.product_name = f"{sel}_역설계"
            clear_slot_widget_keys()
            st.success("✅")


# ============================================================
# PAGE 5: 시장분석
# ============================================================
def page_market():
    st.title("📊 시장제품 분석")
    sel_cat = st.selectbox("대분류", ['전체'] + df_product['대분류'].dropna().unique().tolist())
    f = df_product if sel_cat == '전체' else df_product[df_product['대분류'] == sel_cat]
    k1, k2, k3 = st.columns(3)
    k1.metric("제품수",   len(f))
    k2.metric("제조사",   f['제조사'].nunique())
    k3.metric("평균가격", f"{f['가격(원)'].dropna().mean():,.0f}원")
    st.dataframe(f[['No','대분류','세부유형','제품명','제조사','용량(ml)','가격(원)']],
                 use_container_width=True, height=300)


# ============================================================
# PAGE 6: 교육용
# ============================================================
def page_education():
    st.markdown('<div class="sim-hdr">🎓 교육용 배합 실습</div>', unsafe_allow_html=True)
    bev = st.selectbox("실습 음료유형", df_spec['음료유형'].dropna().tolist(), key="edu_bev")
    step_slot_map = {
        '1단계_원재료': list(range(0,4)), '2단계_당류':   list(range(4,8)),
        '3단계_산미료': [12,13],          '4단계_안정제': list(range(8,12)),
        '5단계_기타':   [14,15,16,17,18],
    }
    for step_key, step_info in EDUCATION_STEPS.items():
        slot_idxs = step_slot_map.get(step_key, [])
        st.markdown(f'<div class="edu-step">{step_info["icon"]} <b>{step_info["title"]}</b> — {step_info["items"]}</div>', unsafe_allow_html=True)
        st.markdown(f'📖 {step_info["guide"]}')
        st.markdown(f'<div class="edu-warn">{step_info["warning"]}</div>', unsafe_allow_html=True)
        for si in slot_idxs:
            ec  = st.columns([0.3, 2.5, 1.2, 1.0])
            ec[0].markdown(f'<span class="t-cel">{si+1}</span>', unsafe_allow_html=True)
            s   = st.session_state.edu_slots[si]
            with ec[1]:
                opts = [''] + ING_LIST
                cur  = s.get('원료명', '')
                ci   = opts.index(cur) if cur in opts else 0
                p    = st.selectbox("원료", opts, index=ci, label_visibility="collapsed",
                                    key=f"ei{si}", format_func=lambda x: "(선택)" if x == '' else x)
                if p and p != cur:
                    st.session_state.edu_slots[si] = fill_slot_from_db(EMPTY_SLOT.copy(), p, df_ing, PH_COL)
            with ec[2]:
                pct = st.number_input("pct", 0.0, 100.0, float(s.get('배합비(%)', 0)), 0.1,
                                      format="%.2f", label_visibility="collapsed", key=f"ep{si}")
                st.session_state.edu_slots[si]['배합비(%)'] = pct
            st.session_state.edu_slots[si] = calc_slot_contributions(st.session_state.edu_slots[si])
            ec[3].markdown(f'<span class="t-num">Bx: {st.session_state.edu_slots[si].get("당기여",0):.2f}</span>', unsafe_allow_html=True)
        st.markdown("---")
    er = calc_formulation(st.session_state.edu_slots, 500)
    mc = st.columns(5)
    mc[0].metric("Brix",  f"{er['예상당도(Bx)']:.2f}°")
    mc[1].metric("pH",    f"{er['예상pH']:.2f}")
    mc[2].metric("산도",  f"{er['예상산도(%)']:.4f}%")
    mc[3].metric("정제수",f"{er['정제수비율(%)']:.1f}%")
    mc[4].metric("원가",  f"{er['원재료비(원/kg)']:,.0f}원/kg")
    es = get_spec(df_spec, bev)
    if es:
        for k, (msg, ok) in check_compliance(er, es).items():
            (st.success if ok is True else st.error if ok is False else st.info)(f"{k}: {msg}")
    if st.button("🔄 초기화"):
        st.session_state.edu_slots = init_slots()
        st.rerun()


# ============================================================
# PAGE 7: HACCP
# ============================================================
def page_planner():
    st.title("📋 기획서 + 공정시방서 + HACCP")
    result = calc_formulation(st.session_state.slots, st.session_state.volume)
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다.")
        return
    st.markdown(f"**{st.session_state.product_name}** | {st.session_state.bev_type} | {st.session_state.volume}ml")
    mc = st.columns(6)
    mc[0].metric("Brix",  result['예상당도(Bx)'])
    mc[1].metric("pH",    result['예상pH'])
    mc[2].metric("산도",  f"{result['예상산도(%)']:.4f}%")
    mc[3].metric("감미도",f"{result['예상감미도']:.4f}")
    mc[4].metric("당산비",result['당산비'])
    mc[5].metric("원가",  f"{result['원재료비(원/kg)']:,.0f}")
    tabs = st.tabs(["📋 기획서", "🏭 SOP", "📄 HACCP (6종)", "🤖 AI 보고서"])
    with tabs[0]:
        raw_b = result['원재료비(원/병)']
        pkg   = {'PET':120,'캔':90,'유리병':200,'종이팩':80,'파우치':60}.get(st.session_state.container,100)
        mfg   = raw_b * 0.4
        total = raw_b + pkg + mfg
        price = st.session_state.target_price
        margin = price - total
        st.dataframe(pd.DataFrame({
            '항목':    ['원재료비','포장재비','제조비','총원가','판매가','마진'],
            '금액(원/병)':[f'{raw_b:,.0f}',f'{pkg:,.0f}',f'{mfg:,.0f}',
                          f'{total:,.0f}',f'{price:,.0f}',f'{margin:,.0f}'],
        }), use_container_width=True, hide_index=True)
    with tabs[1]:
        matched = match_process(st.session_state.bev_type, df_process)
        if not matched.empty:
            for _, p in matched.iterrows():
                step    = str(p.get('세부공정', ''))
                icon    = '⚙️'
                for kw, ic in HACCP_ICONS.items():
                    if kw in step: icon = ic; break
                ccp_raw = str(p.get('CCP여부', ''))
                ccp_tag = f" 🔴 **{ccp_raw}**" if ccp_raw.startswith('CCP') else ""
                with st.expander(f"{icon} {p.get('공정단계','')} — {step}{ccp_tag}"):
                    st.markdown(f"**작업방법**: {p.get('작업방법(구체적)','-')}")
                    st.markdown(f"**조건**: {p.get('주요조건/파라미터','-')}")
                    if ccp_raw.startswith('CCP'):
                        st.error(f"🔴 {ccp_raw} | CL: {p.get('한계기준(CL)','-')} | 모니터링: {p.get('모니터링방법','-')}")
            st.download_button("💾 SOP",
                               haccp_sop(st.session_state.bev_type, df_process,
                                         st.session_state.product_name, st.session_state.slots),
                               "SOP.txt")
    with tabs[2]:
        matched = match_process(st.session_state.bev_type, df_process)
        if not matched.empty:
            docs = {
                "① 위해분석표":  haccp_ha_worksheet(st.session_state.bev_type, df_process),
                "② CCP결정도":   haccp_ccp_decision_tree(st.session_state.bev_type, df_process),
                "③ CCP관리계획서":haccp_ccp_plan(st.session_state.bev_type, df_process),
                "④ 모니터링일지": haccp_monitoring_log(st.session_state.bev_type, df_process),
                "⑤ 공정흐름도":  haccp_flow_diagram(st.session_state.bev_type, df_process),
                "⑥ SOP":         haccp_sop(st.session_state.bev_type, df_process,
                                            st.session_state.product_name, st.session_state.slots),
            }
            for t, d in docs.items():
                with st.expander(t):
                    st.code(d, language=None)
                    st.download_button("💾", d, f"HACCP_{t[:4]}.txt", key=f"dl_{t}")
            st.download_button("📦 6종 일괄",
                               '\n\n'.join([f"{'='*60}\n{t}\n{'='*60}\n{d}" for t,d in docs.items()]),
                               "HACCP_전체.txt", type="primary")
    with tabs[3]:
        if not OPENAI_KEY:
            st.error("API 키 필요")
            return
        rtype   = st.selectbox("관점", ["🧑‍🔬 R&D", "🏭 생산관리자", "📄 품질전문가"])
        persona = {"🧑‍🔬 R&D": PERSONA_PLANNER,
                   "🏭 생산관리자": PERSONA_PRODUCTION,
                   "📄 품질전문가": PERSONA_QA}[rtype]
        if st.button("📝 보고서", type="primary"):
            ft = '\n'.join([f"{n}:{p:.3f}%" for n, p in active])
            with st.spinner("AI..."):
                r = call_gpt(OPENAI_KEY, persona,
                             f"제품:{st.session_state.product_name}\n배합:\n{ft}\n종합 분석보고서")
                st.markdown(r)


# ============================================================
# PAGE 8~10
# ============================================================
def page_labeling():
    st.title("📑 식품표시사항")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("배합표가 비어있습니다.")
        return
    label = generate_food_label(st.session_state.slots, st.session_state.product_name,
                                st.session_state.volume, st.session_state.bev_type)
    items = []
    for k, v in label.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                items.append({'항목': f'  {sk}', '내용': str(sv)})
        else:
            items.append({'항목': k, '내용': str(v)})
    st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)


def page_lab_recipe():
    st.title("🧫 시작 레시피")
    active = [(s['원료명'], s['배합비(%)']) for s in st.session_state.slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    if not active:
        st.warning("비어있음")
        return
    scales = st.multiselect("스케일", [1, 5, 10, 20, 50, 100], default=[1, 5, 20])
    if scales:
        for sc, items in generate_lab_recipe(st.session_state.slots, scales).items():
            st.subheader(f"📋 {sc}")
            st.dataframe(pd.DataFrame(items), use_container_width=True, hide_index=True)


def page_history():
    st.title("📓 히스토리")
    if not st.session_state.history:
        st.info("시뮬레이터에서 저장하세요.")
        return
    for idx, h in enumerate(st.session_state.history):
        with st.expander(f"**{h['name']}** — {h['timestamp']}"):
            r  = h.get('result', {})
            cc = st.columns(5)
            cc[0].metric("Brix",  r.get('예상당도(Bx)', '-'))
            cc[1].metric("pH",    r.get('예상pH', '-'))
            cc[2].metric("산도",  f"{r.get('예상산도(%)', 0):.4f}%")
            cc[3].metric("당산비",r.get('당산비', '-'))
            cc[4].metric("원가",  f"{r.get('원재료비(원/kg)', 0):,.0f}")
            if st.button("📤 로드", key=f"ld{idx}"):
                st.session_state.slots = [s.copy() for s in h['slots']]
                clear_slot_widget_keys()
                st.success("✅")
            if st.button("🗑️", key=f"rm{idx}"):
                st.session_state.history.pop(idx)
                st.rerun()


# ============================================================
# 라우팅
# ============================================================
{
    "🎯 컨셉→배합설계":  page_concept,
    "🧪 배합 시뮬레이터": page_simulator,
    "🧑‍🔬 AI 연구원 평가": page_ai_researcher,
    "🎨 제품 이미지 생성": page_image,
    "🔄 역설계":          page_reverse,
    "📊 시장분석":        page_market,
    "🎓 교육용 실습":     page_education,
    "📋 기획서/HACCP":    page_planner,
    "📑 식품표시사항":    page_labeling,
    "🧫 시작 레시피":     page_lab_recipe,
    "📓 배합 히스토리":   page_history,
}[page]()
