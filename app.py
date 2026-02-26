"""
🧪 음료 배합비 시뮬레이터 (Beverage Formulation Simulator)
Streamlit App - 음료개발_데이터베이스_v3 기반
"""
import streamlit as st
import json, os
import pandas as pd

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="음료 배합비 시뮬레이터",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# LOAD DATA
# ============================================================
@st.cache_data
def load_data():
    data_path = os.path.join(os.path.dirname(__file__), "beverage_data.json")
    with open(data_path, "r", encoding="utf-8") as f:
        return json.load(f)

data = load_data()
raw_materials = data["raw_materials"]
standards = data["standards"]
guides = data["guides"]

# Build lookup dicts
mat_dict = {m["name"]: m for m in raw_materials}
mat_names = [""] + [m["name"] for m in raw_materials]
mat_by_cat = {}
for m in raw_materials:
    cat = m["cat"]
    if cat not in mat_by_cat:
        mat_by_cat[cat] = []
    mat_by_cat[cat].append(m["name"])

std_dict = {s["type"]: s for s in standards}
std_types = [s["type"] for s in standards]

guide_combos = list(guides.keys())
flavors_all = sorted(set(k.split("_")[1] for k in guide_combos if "_" in k))

# ============================================================
# CUSTOM CSS
# ============================================================
st.markdown("""
<style>
    .main-title {
        background: linear-gradient(135deg, #305496 0%, #4472C4 100%);
        color: white; padding: 20px 30px; border-radius: 12px;
        margin-bottom: 20px; text-align: center;
    }
    .main-title h1 { margin: 0; font-size: 2em; }
    .main-title p { margin: 5px 0 0 0; opacity: 0.85; font-size: 0.95em; }
    .guide-match {
        background: #92D050 !important; color: #1a5c1a !important;
        padding: 6px 14px; border-radius: 20px; font-weight: 700;
        display: inline-block; font-size: 0.85em;
    }
    .guide-no-match {
        background: #FFC000 !important; color: #7a5d00 !important;
        padding: 6px 14px; border-radius: 20px; font-weight: 600;
        display: inline-block; font-size: 0.85em;
    }
    .metric-card {
        background: white; border-radius: 10px; padding: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center;
        border-left: 4px solid #4472C4;
    }
    .metric-card.pass { border-left-color: #70AD47; }
    .metric-card.warn { border-left-color: #FFC000; }
    .metric-card.fail { border-left-color: #FF4444; }
    .metric-card .label { font-size: 0.8em; color: #666; margin-bottom: 4px; }
    .metric-card .value { font-size: 1.6em; font-weight: 700; color: #333; }
    .metric-card .status { font-size: 0.8em; margin-top: 4px; }
    .std-badge {
        background: #E2EFDA; color: #375623; padding: 4px 10px;
        border-radius: 6px; font-size: 0.85em; display: inline-block; margin: 2px;
    }
    .cat-header {
        background: #D6DCE4; padding: 6px 12px; border-radius: 6px;
        font-weight: 700; font-size: 0.9em; margin: 8px 0 4px 0;
    }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; }
    .cost-total {
        background: linear-gradient(135deg, #FCE4D6, #F4B084);
        padding: 20px; border-radius: 10px; text-align: center;
    }
    .cost-total .big { font-size: 2.2em; font-weight: 800; color: #C00000; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# HEADER
# ============================================================
st.markdown("""
<div class="main-title">
    <h1>🧪 음료 배합비 시뮬레이터</h1>
    <p>음료유형 + 맛 선택 → AI추천 & 실제사례 가이드 참조 → 배합비 입력(100%기준) → 규격판정 자동확인</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR: Product Setup
# ============================================================
with st.sidebar:
    st.markdown("### 📋 제품 기본설정")
    product_name = st.text_input("제품명", value="신제품_사과음료", key="pname")
    target_volume = st.number_input("목표용량 (ml)", value=500, min_value=100, max_value=5000, step=50)

    st.markdown("---")
    st.markdown("### 🎯 음료유형 & 맛 선택")

    bev_type = st.selectbox("음료유형", std_types, index=1, key="btype")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        flavor_dropdown = st.selectbox("맛 (드롭다운)", [""] + flavors_all, index=flavors_all.index("사과")+1 if "사과" in flavors_all else 0)
    with col_f2:
        flavor_custom = st.text_input("또는 직접입력", value="", key="fcustom")

    effective_flavor = flavor_custom.strip() if flavor_custom.strip() else flavor_dropdown
    combo_key = f"{bev_type}_{effective_flavor}"
    has_guide = combo_key in guides

    if effective_flavor:
        if has_guide:
            st.markdown(f'<span class="guide-match">🟢 가이드 매칭: {combo_key}</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="guide-no-match">🟡 가이드 없음: {combo_key}</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📏 규격기준 (자동참조)")
    if bev_type in std_dict:
        s = std_dict[bev_type]
        cols = st.columns(2)
        badges = [
            f"당도: {s['brix_text']}", f"pH: {s['ph_text']}",
            f"산도: {s['acid_text']}", f"과즙: {s['juice_text']}",
        ]
        for i, b in enumerate(badges):
            if b.split(": ")[1]:
                cols[i%2].markdown(f'<span class="std-badge">{b}</span>', unsafe_allow_html=True)
        if s['note']:
            st.caption(f"📌 {s['note']}")

    st.markdown("---")
    st.markdown("### 🎯 품질목표")
    target_brix = st.number_input("목표 당도 (Bx)", value=11.0, step=0.5, format="%.1f")
    target_acid = st.number_input("목표 산도 (%)", value=0.35, step=0.05, format="%.2f")
    target_cost = st.number_input("목표 원재료비 (원/kg)", value=1500, step=100)

# ============================================================
# GUIDE DATA
# ============================================================
guide_data = guides.get(combo_key, [])
guide_by_slot = {g["slot"]: g for g in guide_data}

# ============================================================
# FORMULATION TABLE
# ============================================================
categories = [
    ("🍎 원재료", list(range(1, 5))),
    ("🍬 당류/감미료", list(range(5, 9))),
    ("🧴 안정제/호료", list(range(9, 13))),
    ("⚗️ 기타자재", list(range(13, 20))),
]

if "formulation" not in st.session_state:
    st.session_state.formulation = {}
    for cat_name, slots in categories:
        for slot in slots:
            st.session_state.formulation[slot] = {"name": "", "pct": 0.0}

# Pre-fill from AI guide if first load and guide exists
if "initialized_combo" not in st.session_state:
    st.session_state.initialized_combo = ""

if has_guide and st.session_state.initialized_combo != combo_key:
    for slot, g in guide_by_slot.items():
        if slot <= 19 and g["ai_name"]:
            st.session_state.formulation[slot] = {
                "name": g["ai_name"],
                "pct": float(g["ai_pct"]) if g["ai_pct"] else 0.0
            }
    st.session_state.initialized_combo = combo_key

st.markdown("## 📝 배합비 입력 (100% 기준)")

# Button to copy from AI guide
col_btn1, col_btn2, col_btn3 = st.columns(3)
with col_btn1:
    if has_guide and st.button("📋 AI추천 배합비 복사", use_container_width=True):
        for slot, g in guide_by_slot.items():
            if slot <= 19:
                st.session_state.formulation[slot] = {
                    "name": g["ai_name"] if g["ai_name"] else "",
                    "pct": float(g["ai_pct"]) if g["ai_pct"] else 0.0
                }
        st.rerun()
with col_btn2:
    if has_guide and st.button("📋 실제사례 배합비 복사", use_container_width=True):
        for slot, g in guide_by_slot.items():
            if slot <= 19:
                st.session_state.formulation[slot] = {
                    "name": g["case_name"] if g["case_name"] else "",
                    "pct": float(g["case_pct"]) if g["case_pct"] else 0.0
                }
        st.rerun()
with col_btn3:
    if st.button("🗑️ 전체 초기화", use_container_width=True):
        for slot in st.session_state.formulation:
            st.session_state.formulation[slot] = {"name": "", "pct": 0.0}
        st.session_state.initialized_combo = ""
        st.rerun()

# Render formulation table
results = []

for cat_name, slots in categories:
    st.markdown(f'<div class="cat-header">{cat_name}</div>', unsafe_allow_html=True)

    for slot in slots:
        g = guide_by_slot.get(slot, {})
        ai_name = g.get("ai_name", "")
        ai_pct = g.get("ai_pct", 0)
        case_name = g.get("case_name", "")
        case_pct = g.get("case_pct", 0)

        cols = st.columns([0.5, 3, 1.2, 2.5, 0.8, 2.5, 0.8])

        with cols[0]:
            st.markdown(f"**{slot}**")

        # Filter material names by category
        cat_key = cat_name.split(" ")[1] if " " in cat_name else cat_name
        relevant_names = mat_names  # show all for flexibility

        with cols[1]:
            current_name = st.session_state.formulation[slot]["name"]
            idx = 0
            if current_name in relevant_names:
                idx = relevant_names.index(current_name)
            selected = st.selectbox(
                f"원료_{slot}", relevant_names, index=idx,
                key=f"mat_{slot}", label_visibility="collapsed"
            )
            st.session_state.formulation[slot]["name"] = selected

        with cols[2]:
            pct = st.number_input(
                f"배합비_{slot}", value=st.session_state.formulation[slot]["pct"],
                min_value=0.0, max_value=100.0, step=0.1, format="%.3f",
                key=f"pct_{slot}", label_visibility="collapsed"
            )
            st.session_state.formulation[slot]["pct"] = pct

        # Guide columns
        with cols[3]:
            if ai_name and str(ai_name) != '0':
                st.markdown(f'<span style="color:#7B2D8E;font-size:0.82em;">🟣 {ai_name}</span>', unsafe_allow_html=True)
        with cols[4]:
            if ai_pct and float(ai_pct) > 0:
                st.markdown(f'<span style="color:#7B2D8E;font-size:0.85em;font-weight:600;">{float(ai_pct):.2f}%</span>', unsafe_allow_html=True)
        with cols[5]:
            if case_name and str(case_name) != '0':
                st.markdown(f'<span style="color:#2E7D32;font-size:0.82em;">🟢 {case_name}</span>', unsafe_allow_html=True)
        with cols[6]:
            if case_pct and float(case_pct) > 0:
                st.markdown(f'<span style="color:#2E7D32;font-size:0.85em;font-weight:600;">{float(case_pct):.2f}%</span>', unsafe_allow_html=True)

        # Calculate contributions
        mat = mat_dict.get(selected, {})
        brix = float(mat.get("brix", 0) or 0)
        acidity = float(mat.get("acidity", 0) or 0)
        sweetness = float(mat.get("sweetness", 0) or 0)
        price = float(mat.get("price", 0) or 0)

        results.append({
            "slot": slot, "name": selected, "pct": pct,
            "brix": brix, "acidity": acidity, "sweetness": sweetness, "price": price,
            "brix_contrib": pct / 100 * brix,
            "acid_contrib": pct / 100 * acidity,
            "sweet_contrib": pct / 100 * sweetness,
            "cost_contrib": pct / 100 * price,
            "cat": cat_name,
        })

# ============================================================
# 정제수 (auto-calculated)
# ============================================================
total_pct = sum(r["pct"] for r in results)
water_pct = 100.0 - total_pct
water_cost = water_pct / 100 * 2  # 정제수 2원/kg

st.markdown(f'<div class="cat-header">💧 정제수 (자동계산)</div>', unsafe_allow_html=True)

g_water = guide_by_slot.get(20, {})
cols_w = st.columns([0.5, 3, 1.2, 2.5, 0.8, 2.5, 0.8])
with cols_w[0]:
    st.markdown("**20**")
with cols_w[1]:
    st.markdown("정제수")
with cols_w[2]:
    color = "green" if water_pct >= 0 else "red"
    st.markdown(f'<span style="color:{color};font-weight:700;font-size:1.1em;">{water_pct:.3f}%</span>', unsafe_allow_html=True)
with cols_w[3]:
    ai_w = g_water.get("ai_pct", "")
    if ai_w:
        st.markdown(f'<span style="color:#7B2D8E;font-size:0.82em;">🟣 정제수</span>', unsafe_allow_html=True)
with cols_w[4]:
    if ai_w:
        st.markdown(f'<span style="color:#7B2D8E;font-size:0.85em;font-weight:600;">{float(ai_w):.2f}%</span>', unsafe_allow_html=True)
with cols_w[5]:
    case_w = g_water.get("case_pct", "")
    if case_w:
        st.markdown(f'<span style="color:#2E7D32;font-size:0.82em;">🟢 정제수</span>', unsafe_allow_html=True)
with cols_w[6]:
    if case_w:
        st.markdown(f'<span style="color:#2E7D32;font-size:0.85em;font-weight:600;">{float(case_w):.2f}%</span>', unsafe_allow_html=True)

# ============================================================
# TOTALS
# ============================================================
total_all = total_pct + water_pct  # should be 100
total_brix = sum(r["brix_contrib"] for r in results)
total_acid = sum(r["acid_contrib"] for r in results)
total_sweet = sum(r["sweet_contrib"] for r in results)
total_cost = sum(r["cost_contrib"] for r in results) + water_cost
raw_mat_pct = sum(r["pct"] for r in results if "원재료" in r["cat"])

st.markdown("---")

# ============================================================
# RESULTS SUMMARY
# ============================================================
st.markdown("## 📊 시뮬레이션 결과")

# Get standards for comparison
std = std_dict.get(bev_type, {})
brix_min = float(std.get("brix_min") or 0)
brix_max = float(std.get("brix_max") or 999)
acid_min = float(std.get("acid_min") or 0)
acid_max = float(std.get("acid_max") or 999)

def judge(val, vmin, vmax, has_std=True):
    if not has_std or vmin == 0 and vmax >= 999:
        return "ℹ️ 규격없음", "metric-card"
    if vmin <= val <= vmax:
        return "✅ 규격 이내", "metric-card pass"
    elif val < vmin:
        return f"⚠️ 하한미달 ({vmin})", "metric-card fail"
    else:
        return f"⚠️ 상한초과 ({vmax})", "metric-card fail"

# Total check
total_status = "✅ 100%" if abs(total_all - 100) < 0.1 else f"⚠️ {total_all:.1f}%"
total_class = "metric-card pass" if abs(total_all - 100) < 0.1 else "metric-card fail"

brix_status, brix_class = judge(total_brix, brix_min, brix_max, bool(std.get("brix_min")))
acid_has = bool(std.get("acid_min"))
acid_status, acid_class = judge(total_acid, acid_min, acid_max, acid_has)
cost_status = "✅ 목표이내" if total_cost <= target_cost else f"⚠️ +{total_cost - target_cost:,.0f}원"
cost_class = "metric-card pass" if total_cost <= target_cost else "metric-card warn"

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.markdown(f"""<div class="{total_class}">
        <div class="label">배합비 합계</div>
        <div class="value">{total_all:.1f}%</div>
        <div class="status">{total_status}</div>
    </div>""", unsafe_allow_html=True)

with c2:
    st.markdown(f"""<div class="{brix_class}">
        <div class="label">예상 당도 (Bx)</div>
        <div class="value">{total_brix:.2f}</div>
        <div class="status">{brix_status}</div>
    </div>""", unsafe_allow_html=True)

with c3:
    st.markdown(f"""<div class="{acid_class}">
        <div class="label">예상 산도 (%)</div>
        <div class="value">{total_acid:.3f}</div>
        <div class="status">{acid_status}</div>
    </div>""", unsafe_allow_html=True)

with c4:
    st.markdown(f"""<div class="metric-card">
        <div class="label">예상 감미도</div>
        <div class="value">{total_sweet:.3f}</div>
        <div class="status">ℹ️ 참고값</div>
    </div>""", unsafe_allow_html=True)

with c5:
    st.markdown(f"""<div class="{cost_class}">
        <div class="label">원재료비 (원/kg)</div>
        <div class="value">{total_cost:,.0f}</div>
        <div class="status">{cost_status}</div>
    </div>""", unsafe_allow_html=True)

# Second row of metrics
st.markdown("")
c6, c7, c8, c9, c10 = st.columns(5)

with c6:
    cost_bottle = total_cost * target_volume / 1000
    st.markdown(f"""<div class="metric-card">
        <div class="label">원재료비 (원/병)</div>
        <div class="value">{cost_bottle:,.0f}</div>
        <div class="status">{target_volume}ml 기준</div>
    </div>""", unsafe_allow_html=True)

with c7:
    used_count = sum(1 for r in results if r["name"])
    st.markdown(f"""<div class="metric-card">
        <div class="label">원료 사용 종류</div>
        <div class="value">{used_count}개</div>
        <div class="status">정제수 제외</div>
    </div>""", unsafe_allow_html=True)

with c8:
    w_class = "metric-card pass" if water_pct >= 50 else ("metric-card warn" if water_pct >= 30 else "metric-card fail")
    st.markdown(f"""<div class="{w_class}">
        <div class="label">정제수 비율</div>
        <div class="value">{water_pct:.1f}%</div>
        <div class="status">{"✅ 적정" if water_pct >= 50 else "⚠️ 낮음"}</div>
    </div>""", unsafe_allow_html=True)

with c9:
    ph_text = std.get("ph_text", "—") if std else "—"
    st.markdown(f"""<div class="metric-card">
        <div class="label">pH 규격 (참고)</div>
        <div class="value" style="font-size:1.1em;">{ph_text}</div>
        <div class="status">ℹ️ 실측 필요</div>
    </div>""", unsafe_allow_html=True)

with c10:
    juice_text = std.get("juice_text", "—") if std else "—"
    st.markdown(f"""<div class="metric-card">
        <div class="label">과즙기준 vs 원재료</div>
        <div class="value" style="font-size:1em;">{raw_mat_pct:.1f}%</div>
        <div class="status">ℹ️ 기준: {juice_text}</div>
    </div>""", unsafe_allow_html=True)

# ============================================================
# DETAILED TABLE
# ============================================================
with st.expander("📋 배합 상세 내역표", expanded=False):
    detail_rows = []
    for r in results:
        if r["name"]:
            mat = mat_dict.get(r["name"], {})
            detail_rows.append({
                "No": r["slot"], "구분": r["cat"].split(" ")[1],
                "원료명": r["name"], "배합비(%)": round(r["pct"], 3),
                "당도(Bx)": r["brix"], "산도(%)": r["acidity"],
                "감미도": r["sweetness"], "단가(원/kg)": int(r["price"]),
                "당기여": round(r["brix_contrib"], 2),
                "산기여": round(r["acid_contrib"], 3),
                "감미기여": round(r["sweet_contrib"], 3),
                "단가기여": round(r["cost_contrib"], 0),
                "배합량(g/kg)": round(r["pct"] * 10, 1),
            })
    detail_rows.append({
        "No": 20, "구분": "정제수", "원료명": "정제수",
        "배합비(%)": round(water_pct, 3), "당도(Bx)": 0, "산도(%)": 0,
        "감미도": 0, "단가(원/kg)": 2, "당기여": 0, "산기여": 0,
        "감미기여": 0, "단가기여": round(water_cost, 0),
        "배합량(g/kg)": round(water_pct * 10, 1),
    })
    if detail_rows:
        df = pd.DataFrame(detail_rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

# ============================================================
# COST CALCULATION
# ============================================================
st.markdown("---")
st.markdown("## 💰 원가계산서")

col_cost1, col_cost2 = st.columns([2, 1])

with col_cost1:
    st.markdown("### ① 원재료비")
    st.markdown(f"**{total_cost:,.0f} 원/kg** (= {cost_bottle:,.0f} 원/병)")

    st.markdown("### ② 포장재비")
    pack_items = [
        ("PET 용기", 45), ("PE 캡 (28mm)", 8), ("수축라벨", 12),
        ("카톤박스 (24입→1병)", 50), ("쉬링크랩", 5),
    ]
    pack_total = sum(p for _, p in pack_items)
    for name, cost in pack_items:
        st.caption(f"  {name}: {cost:,}원/병")
    st.markdown(f"**소계: {pack_total:,} 원/병**")

    st.markdown("### ③ 제조경비")
    mfg_items = [
        ("인건비(직접+간접)", 20), ("전력/용수/스팀", 15),
        ("CIP/품질검사", 5), ("설비감가+건물", 15), ("기타", 5),
    ]
    mfg_total = sum(c for _, c in mfg_items)
    for name, cost in mfg_items:
        st.caption(f"  {name}: {cost:,}원/병")
    st.markdown(f"**소계: {mfg_total:,} 원/병**")

with col_cost2:
    grand_total = cost_bottle + pack_total + mfg_total
    retail_price = st.number_input("소비자가 (원)", value=1500, step=100, key="retail")
    cost_ratio = (grand_total / retail_price * 100) if retail_price > 0 else 0

    st.markdown(f"""<div class="cost-total">
        <div style="font-size:0.9em;color:#666;">★ 제조원가 합계</div>
        <div class="big">{grand_total:,.0f}원</div>
        <div style="font-size:0.85em;margin-top:8px;">
            원재료비: {cost_bottle:,.0f} + 포장재: {pack_total:,} + 제조경비: {mfg_total:,}
        </div>
    </div>""", unsafe_allow_html=True)

    st.markdown("")
    ratio_color = "#70AD47" if cost_ratio < 40 else ("#FFC000" if cost_ratio < 50 else "#FF4444")
    ratio_status = "✅ 양호" if cost_ratio < 40 else ("ℹ️ 보통" if cost_ratio < 50 else "⚠️ 높음")
    st.markdown(f"""<div style="text-align:center;padding:16px;background:white;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
        <div style="font-size:0.85em;color:#666;">원가율</div>
        <div style="font-size:2.5em;font-weight:800;color:{ratio_color};">{cost_ratio:.1f}%</div>
        <div style="font-size:0.85em;">{ratio_status}</div>
    </div>""", unsafe_allow_html=True)

# ============================================================
# REFERENCE DATA VIEWER
# ============================================================
st.markdown("---")
with st.expander("📚 원료DB 조회", expanded=False):
    search = st.text_input("원료 검색", key="mat_search")
    cat_filter = st.multiselect("분류 필터", sorted(mat_by_cat.keys()))

    filtered = raw_materials
    if search:
        filtered = [m for m in filtered if search.lower() in m["name"].lower() or search in (m.get("component") or "")]
    if cat_filter:
        filtered = [m for m in filtered if m["cat"] in cat_filter]

    if filtered:
        df_mat = pd.DataFrame(filtered)[["name","cat","subcat","brix","ph","acidity","sweetness","price","note"]]
        df_mat.columns = ["원료명","대분류","소분류","Brix","pH","산도(%)","감미도","단가(원/kg)","비고"]
        st.dataframe(df_mat, use_container_width=True, hide_index=True)
    else:
        st.info("검색 결과가 없습니다.")

with st.expander("📏 음료규격기준", expanded=False):
    df_std = pd.DataFrame(standards)[["type","brix_text","ph_text","acid_text","juice_text","solid_text","note"]]
    df_std.columns = ["음료유형","당도(Bx)","pH범위","산도(%)","과즙함량","고형분","비고"]
    st.dataframe(df_std, use_container_width=True, hide_index=True)

with st.expander("📖 가이드배합비 DB", expanded=False):
    if has_guide:
        st.markdown(f"**현재 선택: {combo_key}**")
        gdf = pd.DataFrame(guide_data)
        gdf.columns = ["슬롯","구분","AI추천원료","AI(%)","사례원료","사례(%)"]
        st.dataframe(gdf, use_container_width=True, hide_index=True)
    else:
        st.info(f"'{combo_key}' 조합의 가이드 데이터가 없습니다.")
        st.markdown("**등록된 조합:**")
        for k in sorted(guide_combos):
            st.caption(f"  • {k}")

# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption("🧪 음료 배합비 시뮬레이터 v3 | 음료개발_데이터베이스 기반 | 교육훈련용")
