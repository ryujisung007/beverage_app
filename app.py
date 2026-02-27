import streamlit as st
import pandas as pd
import json, os

st.set_page_config(page_title="🥤 음료개발 데이터베이스 v3", layout="wide", initial_sidebar_state="expanded")

# ============================================================
# DATA LOADING — JSON 기반
# ============================================================
@st.cache_data
def load_data():
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beverage_data.json")
    if not os.path.exists(json_path):
        st.error("❌ 'beverage_data.json' 파일을 앱과 같은 폴더에 넣어주세요.")
        st.stop()
    
    with open(json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    sheets = {}
    
    # ── 원료DB ──
    df_raw = pd.DataFrame(raw['raw_materials'])
    df_raw.rename(columns={
        'cat': '원료대분류', 'subcat': '원료소분류', 'name': '원료명',
        'brix': 'Brix(°)', 'ph': 'pH', 'acidity': '산도(%)',
        'sweetness': '감미도(설탕대비)', 'component': '주요성분',
        'form': '공급형태', 'storage': '보관조건', 'price': '예상단가(원/kg)',
        'brix_1pct': '1%당Brix기여', 'ph_1pct': '1%당pH영향',
        'acid_1pct': '1%당산도기여', 'sweet_1pct': '1%당감미도기여',
        'note': '비고',
    }, inplace=True)
    sheets['원료DB'] = df_raw
    
    # ── 음료규격기준 ──
    df_std = pd.DataFrame(raw['standards'])
    df_std.rename(columns={
        'type': '음료유형',
        'brix_text': '당도(Brix,°)', 'ph_text': 'pH 범위',
        'acid_text': '산도(%)', 'juice_text': '과즙함량(%)',
        'solid_text': '고형분(%)', 'co2_text': '탄산가스(vol)',
        'note': '비고',
        'brix_min': 'Brix_min', 'brix_max': 'Brix_max',
        'ph_min': 'pH_min', 'ph_max': 'pH_max',
        'acid_min': '산도_min', 'acid_max': '산도_max',
    }, inplace=True)
    sheets['음료규격기준'] = df_std
    
    # ── 가이드배합비 ──
    guide_rows = []
    for combo_key, items in raw['guides'].items():
        for item in items:
            guide_rows.append({
                'key': f"{combo_key}_{item['slot']:02d}",
                'slot': item['slot'],
                'cat': item.get('cat', ''),
                'AI원료명': item.get('ai_name', ''),
                'AI배합비(%)': item.get('ai_pct', 0),
                '사례원료명': item.get('case_name', ''),
                '사례배합비(%)': item.get('case_pct', 0),
            })
    df_guide = pd.DataFrame(guide_rows)
    sheets['가이드배합비'] = df_guide
    
    return sheets

data = load_data()

# ============================================================
# SIDEBAR NAVIGATION
# ============================================================
st.sidebar.title("🥤 음료개발 DB v3")
st.sidebar.markdown("---")

page = st.sidebar.radio("📂 메뉴 선택", [
    "🏠 대시보드",
    "🧪 배합시뮬레이터",
    "💰 원가계산서",
    "🧬 원료DB",
    "📏 음료규격기준",
    "📖 가이드배합비DB",
])

# ============================================================
# HELPER FUNCTIONS
# ============================================================
def safe_float(val, default=0.0):
    """Safely convert any value to float, handling '—', NaN, None, strings."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if pd.notna(val):
            return float(val)
        return default
    s = str(val).strip().replace(',', '')
    if not s or s in ('—', '-', 'nan', 'None', '', '0'):
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default

def get_raw_material(name, df_raw):
    match = df_raw[df_raw['원료명'] == name]
    if len(match) > 0:
        return match.iloc[0]
    return None

def get_standard(bev_type, df_std):
    match = df_std[df_std['음료유형'] == bev_type]
    if len(match) > 0:
        return match.iloc[0]
    return None

def get_guide(bev_type, flavor, df_guide):
    prefix = f"{bev_type}_{flavor}_"
    matches = df_guide[df_guide['key'].str.startswith(prefix, na=False)]
    return matches

def get_mat_value(mat, col):
    """Safely get a float value from a material Series."""
    if mat is None:
        return 0.0
    try:
        return safe_float(mat.get(col))
    except Exception:
        return 0.0

# ============================================================
# PAGE: 대시보드
# ============================================================
if page == "🏠 대시보드":
    st.title("🥤 음료개발 데이터베이스 v3")
    st.markdown("**FoodWell 음료 R&D 통합 데이터베이스 — Streamlit 인터랙티브 버전**")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("🧬 등록 원료", f"{len(data['원료DB'])}종")
    c2.metric("📏 규격 유형", f"{len(data['음료규격기준'])}종")
    c3.metric("📖 가이드 배합", f"{len(data['가이드배합비'])}건")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📂 데이터 구성")
        sheet_info = {
            "원료DB": f"{len(data['원료DB'])}행 — 원료 SPEC(Brix/pH/산도/감미도/단가)",
            "음료규격기준": f"{len(data['음료규격기준'])}행 — 유형별 규격범위",
            "가이드배합비DB": f"{len(data['가이드배합비'])}행 — AI추천+실제사례 가이드",
        }
        for k, v in sheet_info.items():
            st.markdown(f"- **{k}**: {v}")
    
    with col2:
        st.subheader("🧬 원료 대분류 분포")
        cat_counts = data['원료DB']['원료대분류'].value_counts()
        st.bar_chart(cat_counts)

# ============================================================
# PAGE: 배합시뮬레이터
# ============================================================
elif page == "🧪 배합시뮬레이터":
    st.title("🧪 음료 배합비 시뮬레이터")
    
    df_raw = data['원료DB']
    df_std = data['음료규격기준']
    df_guide = data['가이드배합비']
    
    # --- Product Info ---
    st.markdown("### 📝 제품 기본정보")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        product_name = st.text_input("제품명", "사과과채음료_시제1호")
    with col2:
        volume = st.number_input("목표용량(ml)", value=1000, step=50)
    
    # --- Type + Flavor Selection ---
    st.markdown("### 🎯 음료유형 + 맛 선택")
    col1, col2, col3 = st.columns(3)
    
    bev_types = df_std['음료유형'].dropna().tolist()
    with col1:
        bev_type = st.selectbox("음료유형", bev_types, index=min(1, len(bev_types)-1))
    
    flavors = ["사과","딸기","포도","오렌지","복숭아","망고","레몬","자몽","블루베리","감귤","유자","키위"]
    with col2:
        flavor = st.selectbox("맛(Flavor)", flavors, index=0)
    with col3:
        custom_flavor = st.text_input("또는 직접입력", "", placeholder="드롭다운에 없는 맛 입력")
    
    effective_flavor = custom_flavor if custom_flavor else flavor
    
    # Check if guide exists
    guide_matches = get_guide(bev_type, effective_flavor, df_guide)
    has_guide = len(guide_matches) > 0
    
    if has_guide:
        st.success(f"✅ **가이드 배합비 있음**: {bev_type} + {effective_flavor} ({len(guide_matches)}건)")
    else:
        st.warning(f"⚠️ 가이드 배합비 없음: {bev_type} + {effective_flavor} — 자유 입력하세요")
    
    # --- Standards Display ---
    std = get_standard(bev_type, df_std)
    if std is not None:
        st.markdown("### 📏 규격기준 (자동참조)")
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        sc1.info(f"**당도**: {std.get('당도(Brix,°)','—') if pd.notna(std.get('당도(Brix,°)')) else '—'}")
        sc2.info(f"**pH**: {std.get('pH 범위','—') if pd.notna(std.get('pH 범위')) else '—'}")
        sc3.info(f"**산도**: {std.get('산도(%)','—') if pd.notna(std.get('산도(%)')) else '—'}")
        sc4.info(f"**과즙**: {std.get('과즙함량(%)','—') if pd.notna(std.get('과즙함량(%)')) else '—'}")
        sc5.info(f"**비고**: {std.get('비고','—') if pd.notna(std.get('비고')) else '—'}")
    
    # --- Quality Targets ---
    st.markdown("### 🎯 품질목표")
    tc1, tc2, tc3, tc4 = st.columns(4)
    with tc1:
        target_brix = st.number_input("목표 당도(Bx)", value=11.0, step=0.5)
    with tc2:
        target_acid = st.number_input("목표 산도(%)", value=0.35, step=0.05, format="%.3f")
    with tc3:
        target_sweet = st.text_input("목표 감미도", "—")
    with tc4:
        target_cost = st.number_input("목표 단가(원/kg)", value=1500, step=100)
    
    # --- Formulation Input ---
    st.markdown("### 🧪 배합비 입력 (100% 기준)")
    
    raw_names = [""] + df_raw['원료명'].dropna().tolist()
    categories = [
        ("🍎 원재료", 4, "raw"),
        ("🍬 당류/감미료", 4, "sugar"),
        ("🧊 안정제/호료", 4, "stabilizer"),
        ("📦 기타자재", 8, "etc"),
    ]
    
    # Build guide lookup dict
    guide_dict = {}
    if has_guide:
        for _, row in guide_matches.iterrows():
            slot = int(row['slot'])
            ai_name = str(row['AI원료명']) if pd.notna(row['AI원료명']) else ''
            ai_pct = safe_float(row['AI배합비(%)'])
            case_name = str(row['사례원료명']) if pd.notna(row['사례원료명']) else ''
            case_pct = safe_float(row['사례배합비(%)'])
            if ai_name == '0': ai_name = ''
            if case_name == '0': case_name = ''
            guide_dict[slot] = {
                'AI원료': ai_name if ai_name else '',
                'AI%': ai_pct if ai_pct > 0 else 0,
                '사례원료': case_name if case_name else '',
                '사례%': case_pct if case_pct > 0 else 0,
            }
    
    ingredients = []
    slot_num = 0
    
    for cat_name, num_rows, cat_key in categories:
        st.markdown(f"**{cat_name}**")
        
        for i in range(num_rows):
            slot_num += 1
            guide = guide_dict.get(slot_num, {'AI원료':'','AI%':0,'사례원료':'','사례%':0})
            
            cols = st.columns([0.5, 3, 1.5, 2.5, 1, 2.5, 1])
            with cols[0]:
                st.markdown(f"<div style='padding-top:30px;text-align:center;color:#888;'>{slot_num}</div>", unsafe_allow_html=True)
            with cols[1]:
                name = st.selectbox(f"원료명", raw_names, key=f"raw_{slot_num}", label_visibility="collapsed")
            with cols[2]:
                pct = st.number_input(f"배합비%", value=0.0, min_value=0.0, max_value=100.0,
                                       step=0.1, format="%.3f", key=f"pct_{slot_num}", label_visibility="collapsed")
            with cols[3]:
                ai_txt = f"🟣 {guide['AI원료']}" if guide['AI원료'] else ""
                st.markdown(f"<div style='padding-top:8px;font-size:12px;color:#7B68EE;background:#F3E8FF;border-radius:4px;padding:6px;min-height:36px;'>{ai_txt}</div>", unsafe_allow_html=True)
            with cols[4]:
                ai_pct = f"{guide['AI%']}%" if guide['AI%'] else ""
                st.markdown(f"<div style='padding-top:8px;font-size:12px;color:#7B68EE;text-align:center;background:#F3E8FF;border-radius:4px;padding:6px;min-height:36px;'>{ai_pct}</div>", unsafe_allow_html=True)
            with cols[5]:
                case_txt = f"🟢 {guide['사례원료']}" if guide['사례원료'] else ""
                st.markdown(f"<div style='padding-top:8px;font-size:12px;color:#2E8B57;background:#E8FFE8;border-radius:4px;padding:6px;min-height:36px;'>{case_txt}</div>", unsafe_allow_html=True)
            with cols[6]:
                case_pct = f"{guide['사례%']}%" if guide['사례%'] else ""
                st.markdown(f"<div style='padding-top:8px;font-size:12px;color:#2E8B57;text-align:center;background:#E8FFE8;border-radius:4px;padding:6px;min-height:36px;'>{case_pct}</div>", unsafe_allow_html=True)
            
            if name and pct > 0:
                mat = get_raw_material(name, df_raw)
                ingredients.append({
                    'slot': slot_num, '구분': cat_name.split(' ')[1] if ' ' in cat_name else cat_name,
                    '원료명': name, '배합비(%)': pct,
                    'Brix': get_mat_value(mat, 'Brix(°)'),
                    '산도': get_mat_value(mat, '산도(%)'),
                    '감미도': get_mat_value(mat, '감미도(설탕대비)'),
                    '단가': get_mat_value(mat, '예상단가(원/kg)'),
                })
    
    # --- 정제수 자동계산 ---
    total_pct = sum(i['배합비(%)'] for i in ingredients)
    water_pct = 100.0 - total_pct
    
    st.markdown("**💧 정제수**")
    wc1, wc2 = st.columns([4, 6])
    with wc1:
        if water_pct >= 0:
            st.metric("정제수 배합비", f"{water_pct:.3f}%")
        else:
            st.error(f"⚠️ 배합비 초과! {total_pct:.1f}% > 100%")
    
    if water_pct > 0:
        ingredients.append({
            'slot': 21, '구분': '정제수', '원료명': '정제수',
            '배합비(%)': water_pct, 'Brix': 0, '산도': 0, '감미도': 0, '단가': 2,
        })
    
    # --- 시뮬레이션 결과 ---
    st.markdown("---")
    st.markdown("### 📊 시뮬레이션 결과")
    
    if ingredients:
        total_brix = sum(i['배합비(%)'] / 100 * i['Brix'] for i in ingredients)
        total_acid = sum(i['배합비(%)'] / 100 * i['산도'] for i in ingredients)
        total_sweet = sum(i['배합비(%)'] / 100 * i['감미도'] for i in ingredients)
        total_cost = sum(i['배합비(%)'] / 100 * i['단가'] for i in ingredients)
        total_pct_final = sum(i['배합비(%)'] for i in ingredients)
        raw_material_pct = sum(i['배합비(%)'] for i in ingredients if i['slot'] <= 4) / 100
        num_ingredients = len([i for i in ingredients if i['원료명'] != '정제수'])
        
        rc1, rc2, rc3, rc4 = st.columns(4)
        
        with rc1:
            if abs(total_pct_final - 100) < 0.1:
                st.success(f"**배합비 합계**: {total_pct_final:.1f}%\n✅ 100% 충족")
            else:
                st.error(f"**배합비 합계**: {total_pct_final:.1f}%\n⚠️ 조정필요")
        
        with rc2:
            brix_status = ""
            if std is not None:
                bmin = safe_float(std.get('Brix_min'))
                bmax = safe_float(std.get('Brix_max'))
                if bmin > 0 and bmax > 0:
                    if bmin <= total_brix <= bmax:
                        brix_status = f"✅ 규격이내({std.get('당도(Brix,°)','—')}°)"
                    elif total_brix < bmin:
                        brix_status = f"⚠️ 하한미달({std.get('당도(Brix,°)','—')}°)"
                    else:
                        brix_status = f"⚠️ 상한초과({std.get('당도(Brix,°)','—')}°)"
            st.metric("예상 당도(Bx)", f"{total_brix:.2f}")
            st.caption(brix_status)
        
        with rc3:
            acid_status = ""
            if std is not None:
                amin = safe_float(std.get('산도_min'))
                amax = safe_float(std.get('산도_max'))
                if amin > 0 or amax > 0:
                    if amin <= total_acid <= amax:
                        acid_status = f"✅ 규격이내({std.get('산도(%)','—')}%)"
                    else:
                        acid_status = f"⚠️ 규격벗어남({std.get('산도(%)','—')}%)"
                else:
                    acid_status = "ℹ️ 산도규격 없음"
            st.metric("예상 산도(%)", f"{total_acid:.4f}")
            st.caption(acid_status)
        
        with rc4:
            cost_status = "✅ 목표이내" if total_cost <= target_cost else f"⚠️ 초과 +{total_cost-target_cost:.0f}원"
            st.metric("원재료비(원/kg)", f"{total_cost:,.0f}")
            st.caption(cost_status)
        
        rc5, rc6, rc7, rc8 = st.columns(4)
        rc5.metric("원재료비(원/병)", f"{total_cost*volume/1000:,.0f}")
        rc6.metric("원료 종류", f"{num_ingredients}종")
        rc7.metric("정제수 비율", f"{water_pct:.1f}%")
        rc8.metric("원재료함량", f"{raw_material_pct*100:.1f}%")
        
        if std is not None:
            ph_range = str(std.get('pH 범위', '—')) if pd.notna(std.get('pH 범위')) else '—'
            juice_std = str(std.get('과즙함량(%)', '—')) if pd.notna(std.get('과즙함량(%)')) else '—'
            st.info(f"ℹ️ **pH 규격**: {ph_range} → 배합후 실측 필요 | **과즙함량 기준**: {juice_std} | 현재 원재료함량: {raw_material_pct*100:.1f}%")
        
        st.markdown("#### 📋 배합 상세표")
        df_result = pd.DataFrame(ingredients)
        df_result['당기여(Bx)'] = df_result['배합비(%)'] / 100 * df_result['Brix']
        df_result['산기여(%)'] = df_result['배합비(%)'] / 100 * df_result['산도']
        df_result['감미기여'] = df_result['배합비(%)'] / 100 * df_result['감미도']
        df_result['단가기여(원/kg)'] = df_result['배합비(%)'] / 100 * df_result['단가']
        df_result['배합량(g/kg)'] = df_result['배합비(%)'] * 10
        
        display_cols = ['구분','원료명','배합비(%)','당기여(Bx)','산기여(%)','감미기여','단가기여(원/kg)','배합량(g/kg)']
        st.dataframe(df_result[display_cols].style.format({
            '배합비(%)': '{:.3f}', '당기여(Bx)': '{:.2f}', '산기여(%)': '{:.4f}',
            '감미기여': '{:.4f}', '단가기여(원/kg)': '{:,.0f}', '배합량(g/kg)': '{:.1f}'
        }), use_container_width=True, hide_index=True)
        
        st.session_state['ingredients'] = ingredients
        st.session_state['total_cost'] = total_cost
        st.session_state['volume'] = volume
        st.session_state['product_name'] = product_name

# ============================================================
# PAGE: 원가계산서
# ============================================================
elif page == "💰 원가계산서":
    st.title("💰 음료 제품 원가계산서")
    
    ingredients = st.session_state.get('ingredients', [])
    volume = st.session_state.get('volume', 1000)
    product_name = st.session_state.get('product_name', '(배합시뮬레이터에서 먼저 입력)')
    
    st.markdown(f"**제품명**: {product_name} | **용량**: {volume}ml")
    
    if not ingredients:
        st.warning("⚠️ 배합시뮬레이터에서 먼저 배합비를 입력해주세요.")
        st.stop()
    
    st.markdown("### ① 원재료비 (배합시뮬레이터 연동)")
    raw_cost_data = []
    for i in ingredients:
        unit_price = safe_float(i.get('단가'))
        pct = safe_float(i.get('배합비(%)'))
        cost_per_bottle = unit_price * (pct / 100) * volume / 1000
        raw_cost_data.append({
            '항목': i['원료명'], '배합비': f"{pct:.2f}%",
            '단가(원/kg)': f"{unit_price:,.0f}", 
            '사용량(kg/병)': f"{pct/100 * volume/1000:.5f}",
            '비용(원/병)': f"{cost_per_bottle:,.1f}",
            '비용(원/kg)': f"{unit_price*pct/100:,.0f}",
        })
    
    df_raw_cost = pd.DataFrame(raw_cost_data)
    st.dataframe(df_raw_cost, use_container_width=True, hide_index=True)
    
    total_raw_per_kg = sum(safe_float(i.get('단가')) * safe_float(i.get('배합비(%)')) / 100 for i in ingredients)
    total_raw_per_bottle = total_raw_per_kg * volume / 1000
    st.metric("원재료비 소계(원/병)", f"{total_raw_per_bottle:,.0f}")
    
    st.markdown("### ② 포장재비")
    pc1, pc2, pc3, pc4, pc5, pc6 = st.columns(6)
    pack_bottle = pc1.number_input("PET용기", value=45, key="pk1")
    pack_cap = pc2.number_input("PE캡", value=8, key="pk2")
    pack_label = pc3.number_input("라벨", value=12, key="pk3")
    pack_box = pc4.number_input("박스(원/병)", value=50, key="pk4")
    pack_straw = pc5.number_input("빨대", value=0, key="pk5")
    pack_shrink = pc6.number_input("쉬링크", value=5, key="pk6")
    total_pack = pack_bottle + pack_cap + pack_label + pack_box + pack_straw + pack_shrink
    st.metric("포장재비 소계(원/병)", f"{total_pack:,.0f}")
    
    st.markdown("### ③ 제조경비")
    mc1, mc2, mc3 = st.columns(3)
    mfg_labor = mc1.number_input("인건비(직접+간접)", value=20, key="mf1")
    mfg_utility = mc2.number_input("전력+용수+스팀+냉각", value=18, key="mf2")
    mfg_other = mc3.number_input("CIP+검사+감가+임차", value=22, key="mf3")
    total_mfg = mfg_labor + mfg_utility + mfg_other
    st.metric("제조경비 소계(원/병)", f"{total_mfg:,.0f}")
    
    st.markdown("---")
    st.markdown("### ④ 총괄 원가 요약")
    total_all = total_raw_per_bottle + total_pack + total_mfg
    
    tc1, tc2, tc3, tc4 = st.columns(4)
    tc1.metric("원재료비", f"{total_raw_per_bottle:,.0f}원/병")
    tc2.metric("포장재비", f"{total_pack:,.0f}원/병")
    tc3.metric("제조경비", f"{total_mfg:,.0f}원/병")
    tc4.metric("★ 제조원가 합계", f"{total_all:,.0f}원/병", delta=f"{total_all*1000/volume:,.0f}원/kg")
    
    selling_price = st.number_input("소비자가(원)", value=1500, step=100)
    if selling_price > 0:
        cost_ratio = total_all / selling_price * 100
        status = "양호" if cost_ratio < 40 else ("보통" if cost_ratio < 50 else "높음")
        st.metric("원가율", f"{cost_ratio:.1f}%", delta=status)

# ============================================================
# PAGE: 원료DB
# ============================================================
elif page == "🧬 원료DB":
    st.title("🧬 원료 데이터베이스")
    df = data['원료DB']
    
    col1, col2, col3 = st.columns(3)
    with col1:
        cat_filter = st.multiselect("대분류", df['원료대분류'].dropna().unique().tolist())
    with col2:
        sub_filter = st.multiselect("소분류", df['원료소분류'].dropna().unique().tolist())
    with col3:
        search = st.text_input("🔍 원료명 검색", "", key="raw_search")
    
    if cat_filter:
        df = df[df['원료대분류'].isin(cat_filter)]
    if sub_filter:
        df = df[df['원료소분류'].isin(sub_filter)]
    if search:
        mask = df['원료명'].astype(str).str.contains(search, case=False, na=False)
        df = df[mask]
    
    st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    st.caption(f"총 {len(df)}종")
    
    if len(df) > 0:
        st.markdown("---")
        selected = st.selectbox("📋 상세 조회", df['원료명'].tolist())
        if selected:
            detail = df[df['원료명'] == selected].iloc[0]
            dc1, dc2, dc3, dc4 = st.columns(4)
            dc1.metric("Brix(°)", safe_float(detail.get('Brix(°)'), '—'))
            dc2.metric("pH", safe_float(detail.get('pH'), '—'))
            dc3.metric("산도(%)", safe_float(detail.get('산도(%)'), '—'))
            dc4.metric("단가(원/kg)", f"{safe_float(detail.get('예상단가(원/kg)')):,.0f}")
            
            dc5, dc6, dc7, dc8 = st.columns(4)
            dc5.metric("감미도", str(detail.get('감미도(설탕대비)', '—')))
            dc6.metric("공급형태", str(detail.get('공급형태', '—')))
            dc7.metric("보관조건", str(detail.get('보관조건', '—')))
            dc8.metric("비고", str(detail.get('비고', '—')))

# ============================================================
# PAGE: 음료규격기준
# ============================================================
elif page == "📏 음료규격기준":
    st.title("📏 음료규격기준")
    df = data['음료규격기준']
    
    display_cols = [c for c in df.columns if '_min' not in c and '_max' not in c and c not in ('Brix_min','Brix_max','pH_min','pH_max','산도_min','산도_max')]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
    
    st.markdown("---")
    selected = st.selectbox("유형 선택", df['음료유형'].tolist())
    if selected:
        row = df[df['음료유형'] == selected].iloc[0]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.info(f"**당도**: {row.get('당도(Brix,°)','—') if pd.notna(row.get('당도(Brix,°)')) else '—'}")
        c2.info(f"**pH**: {row.get('pH 범위','—') if pd.notna(row.get('pH 범위')) else '—'}")
        c3.info(f"**산도**: {row.get('산도(%)','—') if pd.notna(row.get('산도(%)')) else '—'}")
        c4.info(f"**과즙함량**: {row.get('과즙함량(%)','—') if pd.notna(row.get('과즙함량(%)')) else '—'}")
        c5.info(f"**비고**: {row.get('비고','—') if pd.notna(row.get('비고')) else '—'}")

# ============================================================
# PAGE: 가이드배합비DB
# ============================================================
elif page == "📖 가이드배합비DB":
    st.title("📖 가이드 배합비 데이터베이스")
    df = data['가이드배합비']
    
    st.markdown("AI추천 배합비와 실제 사례 배합비 가이드 데이터")
    
    if len(df) > 0:
        keys = df['key'].dropna().tolist()
        combos = set()
        for k in keys:
            parts = k.rsplit('_', 1)
            if len(parts) == 2:
                combos.add(parts[0])
        
        combo_list = sorted(combos)
        selected_combo = st.selectbox("유형+맛 조합 선택", combo_list)
        
        if selected_combo:
            filtered = df[df['key'].str.startswith(selected_combo + "_", na=False)]
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 🟣 AI 추천 배합비")
                for _, row in filtered.iterrows():
                    name = row['AI원료명']
                    pct = safe_float(row['AI배합비(%)'])
                    cat = row['cat']
                    if name and str(name) not in ('0','nan','') and pct > 0:
                        st.markdown(f"- **{name}**: {pct}% ({cat})")
            
            with col2:
                st.markdown("#### 🟢 실제 사례 배합비")
                for _, row in filtered.iterrows():
                    name = row['사례원료명']
                    pct = safe_float(row['사례배합비(%)'])
                    cat = row['cat']
                    if name and str(name) not in ('0','nan','') and pct > 0:
                        st.markdown(f"- **{name}**: {pct}% ({cat})")
            
            st.markdown("---")
            st.markdown("#### 📋 전체 데이터")
            st.dataframe(filtered, use_container_width=True, hide_index=True)

# ============================================================
# FOOTER
# ============================================================
st.sidebar.markdown("---")
st.sidebar.caption("© FoodWell R&D Training\n음료개발 데이터베이스 v3\nPowered by Streamlit")
