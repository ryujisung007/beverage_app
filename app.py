import streamlit as st
import pandas as pd
import json, os

st.set_page_config(page_title="🥤 음료개발 데이터베이스 v3", layout="wide", initial_sidebar_state="expanded")

# ============================================================
# DATA LOADING
# ============================================================
@st.cache_data
def load_data():
    xlsx = "음료개발_데이터베이스_v3.xlsx"
    if not os.path.exists(xlsx):
        st.error(f"❌ '{xlsx}' 파일을 앱과 같은 폴더에 넣어주세요.")
        st.stop()
    
    sheets = {}
    xls = pd.ExcelFile(xlsx)
    
    sheets['음료유형분류'] = pd.read_excel(xls, '음료유형분류')
    sheets['시장제품DB'] = pd.read_excel(xls, '시장제품DB')
    sheets['원료DB'] = pd.read_excel(xls, '원료DB')
    sheets['음료규격기준'] = pd.read_excel(xls, '음료규격기준')
    sheets['HACCP'] = pd.read_excel(xls, '표준제조공정_HACCP')
    sheets['자재SPEC'] = pd.read_excel(xls, '자재SPEC참조', header=None)
    sheets['과일Brix'] = pd.read_excel(xls, '과일Brix참조', header=None)
    sheets['가이드배합비'] = pd.read_excel(xls, '가이드배합비DB')
    
    return sheets

data = load_data()

# ============================================================
# SIDEBAR NAVIGATION
# ============================================================
st.sidebar.image("https://img.icons8.com/fluency/96/cocktail.png", width=60)
st.sidebar.title("🥤 음료개발 DB v3")
st.sidebar.markdown("---")

page = st.sidebar.radio("📂 메뉴 선택", [
    "🏠 대시보드",
    "🧪 배합시뮬레이터",
    "💰 원가계산서",
    "📋 음료유형분류",
    "🏪 시장제품DB",
    "🧬 원료DB",
    "📏 음료규격기준",
    "🏭 표준제조공정/HACCP",
    "📊 자재SPEC참조",
    "🍎 과일Brix참조",
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
    matches = df_guide[df_guide.iloc[:,0].str.startswith(prefix, na=False)]
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
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🧬 등록 원료", f"{len(data['원료DB'])}종")
    c2.metric("🏪 시장 제품", f"{len(data['시장제품DB'])}건")
    c3.metric("📏 규격 유형", f"{len(data['음료규격기준'])}종")
    c4.metric("📖 가이드 배합", f"{len(data['가이드배합비'])}건")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📂 시트 구성")
        sheet_info = {
            "음료유형분류": f"{len(data['음료유형분류'])}행 — 음료 대분류/세부유형/정의",
            "시장제품DB": f"{len(data['시장제품DB'])}행 — 시장제품 배합/규격 DB",
            "원료DB": f"{len(data['원료DB'])}행 — 원료 SPEC(Brix/pH/산도/감미도/단가)",
            "음료규격기준": f"{len(data['음료규격기준'])}행 — 유형별 규격범위",
            "표준제조공정/HACCP": f"{len(data['HACCP'])}행 — 공정/CCP 관리기준",
            "자재SPEC참조": "당류/감미료/안정제 SPEC 참조표",
            "과일Brix참조": "60종 과일 한국/FDA Brix 기준",
            "가이드배합비DB": f"{len(data['가이드배합비'])}행 — AI추천+실제사례 가이드",
        }
        for k, v in sheet_info.items():
            st.markdown(f"- **{k}**: {v}")
    
    with col2:
        st.subheader("🧬 원료 대분류 분포")
        cat_counts = data['원료DB']['원료대분류'].value_counts()
        st.bar_chart(cat_counts)
    
    st.markdown("---")
    st.subheader("🏪 시장제품 유형 분포")
    if '대분류' in data['시장제품DB'].columns:
        prod_counts = data['시장제품DB']['대분류'].value_counts()
        st.bar_chart(prod_counts)

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
        bev_type = st.selectbox("음료유형", bev_types, index=1)
    
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
        ("📦 기타자재", 7, "etc"),
    ]
    
    # Build guide lookup dict
    guide_dict = {}
    if has_guide:
        for _, row in guide_matches.iterrows():
            slot = safe_float(row.iloc[1], 0)
            ai_name = row.iloc[3] if pd.notna(row.iloc[3]) else ''
            ai_pct = safe_float(row.iloc[4])
            case_name = row.iloc[5] if pd.notna(row.iloc[5]) else ''
            case_pct = safe_float(row.iloc[6])
            # Skip if name is '0' or 0
            if str(ai_name) == '0': ai_name = ''
            if str(case_name) == '0': case_name = ''
            guide_dict[int(slot)] = {
                'AI원료': str(ai_name) if ai_name else '',
                'AI%': ai_pct if ai_pct > 0 else 0,
                '사례원료': str(case_name) if case_name else '',
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
            'slot': 20, '구분': '정제수', '원료명': '정제수',
            '배합비(%)': water_pct, 'Brix': 0, '산도': 0, '감미도': 0, '단가': 2,
        })
    
    # --- 시뮬레이션 결과 ---
    st.markdown("---")
    st.markdown("### 📊 시뮬레이션 결과")
    
    if ingredients:
        # Calculate contributions
        total_brix = sum(i['배합비(%)'] / 100 * i['Brix'] for i in ingredients)
        total_acid = sum(i['배합비(%)'] / 100 * i['산도'] for i in ingredients)
        total_sweet = sum(i['배합비(%)'] / 100 * i['감미도'] for i in ingredients)
        total_cost = sum(i['배합비(%)'] / 100 * i['단가'] for i in ingredients)
        total_pct_final = sum(i['배합비(%)'] for i in ingredients)
        raw_material_pct = sum(i['배합비(%)'] for i in ingredients if i['slot'] <= 4) / 100
        num_ingredients = len([i for i in ingredients if i['원료명'] != '정제수'])
        
        # Results with standards check
        rc1, rc2, rc3, rc4 = st.columns(4)
        
        # 배합비 합계
        with rc1:
            if abs(total_pct_final - 100) < 0.1:
                st.success(f"**배합비 합계**: {total_pct_final:.1f}%\n✅ 100% 충족")
            else:
                st.error(f"**배합비 합계**: {total_pct_final:.1f}%\n⚠️ 조정필요")
        
        # 당도 vs 규격
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
        
        # 산도 vs 규격
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
        
        # 원가
        with rc4:
            cost_status = "✅ 목표이내" if total_cost <= target_cost else f"⚠️ 초과 +{total_cost-target_cost:.0f}원"
            st.metric("원재료비(원/kg)", f"{total_cost:,.0f}")
            st.caption(cost_status)
        
        # Additional info
        rc5, rc6, rc7, rc8 = st.columns(4)
        rc5.metric("원재료비(원/병)", f"{total_cost*volume/1000:,.0f}")
        rc6.metric("원료 종류", f"{num_ingredients}종")
        rc7.metric("정제수 비율", f"{water_pct:.1f}%")
        rc8.metric("원재료함량", f"{raw_material_pct*100:.1f}%")
        
        # pH/과즙 참조
        if std is not None:
            ph_range = str(std.get('pH 범위', '—')) if pd.notna(std.get('pH 범위')) else '—'
            juice_std = str(std.get('과즙함량(%)', '—')) if pd.notna(std.get('과즙함량(%)')) else '—'
            st.info(f"ℹ️ **pH 규격**: {ph_range} → 배합후 실측 필요 | **과즙함량 기준**: {juice_std} | 현재 원재료함량: {raw_material_pct*100:.1f}%")
        
        # Detailed table
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
        
        # Store in session state for cost sheet
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
    
    # ① 원재료비
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
    
    # ② 포장재비
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
    
    # ③ 제조경비
    st.markdown("### ③ 제조경비")
    mc1, mc2, mc3 = st.columns(3)
    mfg_labor = mc1.number_input("인건비(직접+간접)", value=20, key="mf1")
    mfg_utility = mc2.number_input("전력+용수+스팀+냉각", value=18, key="mf2")
    mfg_other = mc3.number_input("CIP+검사+감가+임차", value=22, key="mf3")
    total_mfg = mfg_labor + mfg_utility + mfg_other
    st.metric("제조경비 소계(원/병)", f"{total_mfg:,.0f}")
    
    # ④ 총괄 원가 요약
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
# PAGE: 음료유형분류
# ============================================================
elif page == "📋 음료유형분류":
    st.title("📋 음료유형분류")
    df = data['음료유형분류']
    
    search = st.text_input("🔍 검색 (유형명, 정의, 제품명)", "")
    if search:
        mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
        df = df[mask]
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f"총 {len(df)}개 유형")

# ============================================================
# PAGE: 시장제품DB
# ============================================================
elif page == "🏪 시장제품DB":
    st.title("🏪 시장제품 데이터베이스")
    df = data['시장제품DB']
    
    col1, col2, col3 = st.columns(3)
    with col1:
        cat_filter = st.multiselect("대분류 필터", df['대분류'].dropna().unique().tolist())
    with col2:
        sub_filter = st.multiselect("세부유형 필터", df['세부유형'].dropna().unique().tolist() if '세부유형' in df.columns else [])
    with col3:
        search = st.text_input("🔍 제품명 검색", "", key="prod_search")
    
    if cat_filter:
        df = df[df['대분류'].isin(cat_filter)]
    if sub_filter:
        df = df[df['세부유형'].isin(sub_filter)]
    if search:
        mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
        df = df[mask]
    
    st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    st.caption(f"총 {len(df)}건")

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
    
    # Detail view
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
    
    display_cols = [c for c in df.columns if 'min' not in c.lower() and 'max' not in c.lower()]
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
# PAGE: HACCP
# ============================================================
elif page == "🏭 표준제조공정/HACCP":
    st.title("🏭 표준제조공정 / HACCP")
    df = data['HACCP']
    
    if '음료유형' in df.columns:
        type_filter = st.multiselect("음료유형 필터", df['음료유형'].dropna().unique().tolist())
        if type_filter:
            df = df[df['음료유형'].isin(type_filter)]
    
    if '공정단계' in df.columns:
        step_filter = st.multiselect("공정단계 필터", df['공정단계'].dropna().unique().tolist())
        if step_filter:
            df = df[df['공정단계'].isin(step_filter)]
    
    ccp_only = st.checkbox("CCP만 보기")
    if ccp_only and 'CCP여부' in df.columns:
        df = df[df['CCP여부'] != 'N']
    
    st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    st.caption(f"총 {len(df)}건")

# ============================================================
# PAGE: 자재SPEC참조
# ============================================================
elif page == "📊 자재SPEC참조":
    st.title("📊 자재SPEC 참조표")
    st.markdown("당류 Brix/감미도, 고감미료 감미배수, 안정제/부자재 SPEC")
    
    df = data['자재SPEC']
    st.dataframe(df, use_container_width=True, hide_index=True)

# ============================================================
# PAGE: 과일Brix참조
# ============================================================
elif page == "🍎 과일Brix참조":
    st.title("🍎 과일별 기준 Brix (한국/FDA)")
    
    df = data['과일Brix']
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("약 60종 과일의 Single Strength Brix 기준값")

# ============================================================
# PAGE: 가이드배합비DB
# ============================================================
elif page == "📖 가이드배합비DB":
    st.title("📖 가이드 배합비 데이터베이스")
    df = data['가이드배합비']
    
    st.markdown("AI추천 배합비와 실제 사례 배합비 가이드 데이터")
    
    # Parse keys to get unique combos
    if len(df) > 0:
        keys = df.iloc[:,0].dropna().tolist()
        combos = set()
        for k in keys:
            parts = k.rsplit('_', 1)
            if len(parts) == 2:
                combos.add(parts[0])
        
        combo_list = sorted(combos)
        selected_combo = st.selectbox("유형+맛 조합 선택", combo_list)
        
        if selected_combo:
            filtered = df[df.iloc[:,0].str.startswith(selected_combo + "_", na=False)]
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 🟣 AI 추천 배합비")
                ai_data = filtered.copy()
                if len(ai_data) > 0:
                    for _, row in ai_data.iterrows():
                        name = row.iloc[3]
                        pct = safe_float(row.iloc[4])
                        cat = row.iloc[2]
                        if name and str(name) not in ('0','nan','') and pct > 0:
                            st.markdown(f"- **{name}**: {pct}% ({cat})")
            
            with col2:
                st.markdown("#### 🟢 실제 사례 배합비")
                case_data = filtered.copy()
                if len(case_data) > 0:
                    for _, row in case_data.iterrows():
                        name = row.iloc[5]
                        pct = safe_float(row.iloc[6])
                        cat = row.iloc[2]
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
