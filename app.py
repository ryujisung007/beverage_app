import streamlit as st
import pandas as pd
import json, os, re, math, io, base64
from datetime import datetime

st.set_page_config(page_title="🥤 음료개발 데이터베이스 v3", layout="wide", initial_sidebar_state="expanded")

# ============================================================
# SESSION STATE 초기화
# ============================================================
DEFAULTS = {
    'product_name': '사과과채음료_시제1호',
    'volume': 1000,
    'bev_type_idx': 1,
    'flavor_idx': 0,
    'custom_flavor': '',
    'target_brix': 11.0,
    'target_acid': 0.35,
    'target_sweet': '—',
    'target_cost': 1500,
    'ingredients': [],
    'total_cost': 0,
    'ai_recommendation': {},
    'ai_meta': {},
    'pack_vals': [45, 8, 12, 50, 0, 5],
    'mfg_vals': [20, 18, 22],
    'selling_price': 1500,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# DATA LOADING
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
    df_raw = pd.DataFrame(raw['raw_materials'])
    df_raw.rename(columns={
        'cat':'원료대분류','subcat':'원료소분류','name':'원료명',
        'brix':'Brix(°)','ph':'pH','acidity':'산도(%)',
        'sweetness':'감미도(설탕대비)','component':'주요성분',
        'form':'공급형태','storage':'보관조건','price':'예상단가(원/kg)',
        'brix_1pct':'1%당Brix기여','ph_1pct':'1%당pH(1%용액)',
        'acid_1pct':'1%당산도기여','sweet_1pct':'1%당감미도기여','note':'비고',
    }, inplace=True)
    sheets['원료DB'] = df_raw
    df_std = pd.DataFrame(raw['standards'])
    df_std.rename(columns={
        'type':'음료유형','brix_text':'당도(Brix,°)','ph_text':'pH 범위',
        'acid_text':'산도(%)','juice_text':'과즙함량(%)','solid_text':'고형분(%)',
        'co2_text':'탄산가스(vol)','note':'비고',
        'brix_min':'Brix_min','brix_max':'Brix_max',
        'ph_min':'pH_min','ph_max':'pH_max',
        'acid_min':'산도_min','acid_max':'산도_max',
    }, inplace=True)
    sheets['음료규격기준'] = df_std
    guide_rows = []
    for combo_key, items in raw['guides'].items():
        for item in items:
            guide_rows.append({
                'key': f"{combo_key}_{item['slot']:02d}",
                'combo': combo_key,
                'slot': item['slot'], 'cat': item.get('cat',''),
                'AI원료명': item.get('ai_name',''), 'AI배합비(%)': item.get('ai_pct',0),
                '사례원료명': item.get('case_name',''), '사례배합비(%)': item.get('case_pct',0),
            })
    sheets['가이드배합비'] = pd.DataFrame(guide_rows)
    return sheets

data = load_data()

# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.title("🥤 음료개발 DB v3")
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔑 Gemini API")
gemini_api_key = st.sidebar.text_input("API Key", type="password", placeholder="AIza...",
    help="Google AI Studio에서 발급 (텍스트 추천 + 이미지 생성 공용)")
if gemini_api_key:
    st.sidebar.success("✅ Key 입력됨")
st.sidebar.markdown("---")
page = st.sidebar.radio("📂 메뉴", [
    "🏠 대시보드","🧪 배합시뮬레이터","💰 원가계산서",
    "🧬 원료DB","📏 음료규격기준","📖 가이드배합비DB",
])

# ============================================================
# HELPERS
# ============================================================
def sf(val, default=0.0):
    """Safe float conversion."""
    if val is None: return default
    if isinstance(val,(int,float)):
        return float(val) if pd.notna(val) else default
    s = str(val).strip().replace(',','')
    if not s or s in ('—','-','nan','None',''): return default
    try: return float(s)
    except: return default

def get_raw(name, df): 
    m = df[df['원료명']==name]
    return m.iloc[0] if len(m)>0 else None

def get_std(btype, df):
    m = df[df['음료유형']==btype]
    return m.iloc[0] if len(m)>0 else None

def get_guide(btype, flv, df):
    return df[df['key'].str.startswith(f"{btype}_{flv}_", na=False)]

def matv(mat, col):
    if mat is None: return 0.0
    try: return sf(mat.get(col))
    except: return 0.0

# ============================================================
# pH 계산 엔진 (H+ 농도 가중평균)
# ============================================================
def estimate_ph(ingredients, df_raw):
    """배합비 기반 pH 추정 — [H+] 가중합산 모델"""
    total_H = 0.0
    total_OH = 0.0
    for ing in ingredients:
        pct = ing['배합비(%)'] / 100
        if pct <= 0: continue
        mat = get_raw(ing['원료명'], df_raw)
        if mat is None:
            total_H += pct * 1e-7  # 중성 가정
            continue
        ph_val = sf(mat.get('1%당pH(1%용액)'))
        if ph_val <= 0:
            ph_val = sf(mat.get('pH'))
        if ph_val <= 0:
            ph_val = 7.0
        if ph_val < 7:
            total_H += pct * (10 ** (-ph_val))
        elif ph_val > 7:
            total_OH += pct * (10 ** (ph_val - 14))
        else:
            total_H += pct * 1e-7
    net = total_H - total_OH
    if net > 1e-14:
        return round(-math.log10(net), 2)
    elif net < -1e-14:
        return round(14 + math.log10(-net), 2)
    return 7.0

# ============================================================
# 원료명 기반 스펙 유추 (이름 규칙 파싱)
# ============================================================
def infer_from_name(name):
    """원료명에서 Brix/pH/산도 유추. 유추 불가 시 None 반환."""
    result = {}
    # Brix 추출: "○○(65Brix)" 또는 "○○농축과즙(70Brix)"
    brix_match = re.search(r'(\d+)\s*[Bb]rix', name)
    if brix_match:
        result['brix'] = float(brix_match.group(1))
    # 농축배수: "5배농축" 
    conc_match = re.search(r'(\d+)배농축', name)
    if conc_match and 'brix' not in result:
        result['brix'] = float(conc_match.group(1)) * 12  # 과즙 평균 ~12Brix
    # 산미료 키워드
    acid_keywords = {
        '구연산': {'ph':2.2,'acidity':100,'acid_1pct':1.0},
        '사과산': {'ph':2.3,'acidity':95.5,'acid_1pct':0.955},
        '말산': {'ph':2.3,'acidity':95.5,'acid_1pct':0.955},
        '주석산': {'ph':2.0,'acidity':85.3,'acid_1pct':0.853},
        '젖산': {'ph':2.4,'acidity':71.1,'acid_1pct':0.711},
        '인산': {'ph':1.6,'acidity':196.1,'acid_1pct':1.961},
        '아스코르빈': {'ph':2.7,'acidity':36.4,'acid_1pct':0.364},
    }
    for kw, vals in acid_keywords.items():
        if kw in name:
            result.update(vals)
            break
    # 당류 키워드
    sugar_keywords = {
        '설탕': {'brix':99.9,'sweetness':1.0},
        '과당': {'brix':77,'sweetness':1.7},
        '포도당': {'brix':91,'sweetness':0.7},
        '올리고당': {'brix':75,'sweetness':0.5},
        '물엿': {'brix':75,'sweetness':0.4},
        '꿀': {'brix':80,'sweetness':1.0},
        '스테비아': {'brix':0,'sweetness':300},
        '수크랄로스': {'brix':0,'sweetness':600},
        '아스파탐': {'brix':0,'sweetness':200},
        '에리스리톨': {'brix':0,'sweetness':0.7},
        '자일리톨': {'brix':0,'sweetness':1.0},
        '알룰로스': {'brix':70,'sweetness':0.7},
    }
    for kw, vals in sugar_keywords.items():
        if kw in name:
            result.update(vals)
            break
    return result if result else None

# ============================================================
# GEMINI API 호출 (텍스트 / 이미지)
# ============================================================
def build_raw_context(df_raw):
    lines = []
    for cat in df_raw['원료대분류'].unique():
        sub = df_raw[df_raw['원료대분류']==cat]
        lines.append(f"\n【{cat}】")
        for _, r in sub.iterrows():
            lines.append(f"  - {r['원료명']} | Brix:{sf(r.get('Brix(°)')):.0f} | pH:{sf(r.get('pH')):.1f} | 산도:{sf(r.get('산도(%)'))}% | 감미도:{sf(r.get('감미도(설탕대비)'))} | 단가:{sf(r.get('예상단가(원/kg)')):,.0f}원/kg")
    return "\n".join(lines)

def build_rec_prompt(bev_type, flavor, std, t_brix, t_acid, t_cost, raw_ctx, extra=""):
    std_text = "규격 없음"
    if std is not None:
        std_text = f"당도:{std.get('당도(Brix,°)','—')} | pH:{std.get('pH 범위','—')} | 산도:{std.get('산도(%)','—')} | 과즙:{std.get('과즙함량(%)','—')} | 비고:{std.get('비고','—')}"
    return f"""당신은 대한민국 식품음료 R&D 수석 연구원(경력 20년)입니다.

【전문분야】관능평가 전문가, 혼합음료·기능성음료 개발, 원가-품질 밸런스 설계, 식품공전 규격 준수
【철학】"맛있는 음료는 과학과 감각의 교차점에서 탄생한다"

【개발 요청】 음료유형:{bev_type} | 맛:{flavor} | 목표당도:{t_brix}Bx | 목표산도:{t_acid}% | 목표원가:{t_cost:,.0f}원/kg이하
【규격기준】{std_text}
【추가요청】{extra or '없음'}

【사용가능 원료DB (반드시 이 목록에서만 선택)】
{raw_ctx}

【배합설계 규칙】
1. 위 원료DB 목록의 원료명을 정확히 사용 (오타 불가)
2. 정제수 제외 원료 합계 15~35% (나머지 정제수)
3. 식품공전 규격 충족 필수
4. 관능(당산비, 향미조화) 최우선
5. 원료 3~12종 이내

【슬롯구조】 1~4:원재료 | 5~8:당류/감미료 | 9~12:안정제/호료 | 13~20:기타

【응답 — 아래 JSON만 출력, 다른 텍스트 없이】
```json
{{"recommendation":[{{"slot":1,"name":"원료명","pct":8.0,"reason":"이유"}},...],
"expected_brix":11.2,"expected_acidity":0.35,"expected_ph":3.5,
"expected_cost_per_kg":1350,
"design_concept":"컨셉 2~3문장","sensory_note":"관능특성","tips":"실무팁"}}
```"""

def call_gemini(api_key, prompt, model="gemini-2.0-flash"):
    import urllib.request, urllib.error
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = json.dumps({"contents":[{"parts":[{"text":prompt}]}],
        "generationConfig":{"temperature":0.7,"topP":0.9,"maxOutputTokens":4096}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            r = json.loads(resp.read().decode())
            return r['candidates'][0]['content']['parts'][0]['text'], None
    except urllib.error.HTTPError as e:
        return None, f"API오류({e.code}): {e.read().decode()[:200] if e.fp else str(e)}"
    except Exception as e:
        return None, f"연결오류: {str(e)}"

def call_gemini_image(api_key, prompt):
    """나노바나나 (gemini-2.5-flash) 이미지 생성"""
    import urllib.request, urllib.error
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp-image-generation:generateContent?key={api_key}"
    body = json.dumps({
        "contents":[{"parts":[{"text": prompt}]}],
        "generationConfig":{"responseModalities":["TEXT","IMAGE"],"temperature":0.8}
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            r = json.loads(resp.read().decode())
            for part in r['candidates'][0]['content']['parts']:
                if 'inlineData' in part:
                    img_data = part['inlineData']['data']
                    mime = part['inlineData'].get('mimeType','image/png')
                    return img_data, mime, None
            return None, None, "이미지가 생성되지 않았습니다."
    except urllib.error.HTTPError as e:
        return None, None, f"API오류({e.code})"
    except Exception as e:
        return None, None, f"연결오류: {str(e)}"

def parse_rec_json(text):
    m = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    js = m.group(1) if m else re.search(r'\{.*\}', text, re.DOTALL)
    if not m and js: js = js.group(0)
    elif m: js = m.group(1)
    else: return None, "JSON 파싱 실패"
    try: return json.loads(js), None
    except json.JSONDecodeError as e: return None, f"JSON오류: {e}"

def validate_rec(rec, df_raw):
    valid_names = set(df_raw['원료명'].tolist())
    ok, warn = [], []
    for item in rec.get('recommendation',[]):
        n = item.get('name','')
        if n in valid_names: ok.append(item)
        else:
            cands = [x for x in valid_names if n[:3] in x or x[:3] in n]
            warn.append(f"⚠️ '{n}' DB에 없음" + (f" → 유사: {', '.join(cands[:3])}" if cands else ""))
    return ok, warn

# ============================================================
# 엑셀/PDF 내보내기
# ============================================================
def export_excel(ingredients, volume, product_name, total_cost, pack_vals, mfg_vals, selling_price):
    """배합표 + 원가계산서 엑셀 생성"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # 배합표
        df = pd.DataFrame(ingredients)
        if len(df) > 0:
            df['당기여(Bx)'] = df['배합비(%)'] / 100 * df['Brix']
            df['산기여(%)'] = df['배합비(%)'] / 100 * df['산도']
            df['단가기여(원/kg)'] = df['배합비(%)'] / 100 * df['단가']
            df['배합량(g/kg)'] = df['배합비(%)'] * 10
        meta = pd.DataFrame([{
            '제품명': product_name, '용량(ml)': volume,
            '원재료비(원/kg)': f"{total_cost:,.0f}",
            '작성일': datetime.now().strftime('%Y-%m-%d')
        }])
        meta.to_excel(writer, sheet_name='배합표', index=False, startrow=0)
        if len(df) > 0:
            df.to_excel(writer, sheet_name='배합표', index=False, startrow=3)
        # 원가
        cost_rows = []
        for i in ingredients:
            up = sf(i.get('단가')); pct = sf(i.get('배합비(%)'))
            cost_rows.append({'항목':i['원료명'],'배합비(%)':pct,'단가(원/kg)':up,
                '비용(원/kg)':up*pct/100,'비용(원/병)':up*pct/100*volume/1000})
        dfc = pd.DataFrame(cost_rows)
        dfc.to_excel(writer, sheet_name='원가계산서', index=False, startrow=0)
        raw_total = sum(r['비용(원/병)'] for r in cost_rows)
        pk_total = sum(pack_vals); mf_total = sum(mfg_vals)
        summary = pd.DataFrame([{
            '원재료비(원/병)': raw_total, '포장재비(원/병)': pk_total,
            '제조경비(원/병)': mf_total, '제조원가합계(원/병)': raw_total+pk_total+mf_total,
            '소비자가(원)': selling_price,
            '원가율(%)': (raw_total+pk_total+mf_total)/selling_price*100 if selling_price>0 else 0
        }])
        summary.to_excel(writer, sheet_name='원가계산서', index=False, startrow=len(cost_rows)+3)
    return output.getvalue()

def export_pdf_html(ingredients, volume, product_name, total_cost, est_ph, pack_vals, mfg_vals, selling_price):
    """HTML기반 인쇄용 PDF 대체 (HTML 다운로드)"""
    rows_html = ""
    for i in ingredients:
        brix_c = sf(i.get('배합비(%)'))/100*sf(i.get('Brix'))
        acid_c = sf(i.get('배합비(%)'))/100*sf(i.get('산도'))
        cost_c = sf(i.get('단가'))*sf(i.get('배합비(%)'))/100
        rows_html += f"<tr><td>{i.get('구분','')}</td><td>{i['원료명']}</td><td>{sf(i.get('배합비(%)')):.3f}</td><td>{brix_c:.2f}</td><td>{acid_c:.4f}</td><td>{cost_c:,.0f}</td></tr>\n"
    t_brix = sum(sf(i.get('배합비(%)'))/100*sf(i.get('Brix')) for i in ingredients)
    t_acid = sum(sf(i.get('배합비(%)'))/100*sf(i.get('산도')) for i in ingredients)
    raw_cost = sum(sf(i.get('단가'))*sf(i.get('배합비(%)'))/100*volume/1000 for i in ingredients)
    pk = sum(pack_vals); mf = sum(mfg_vals); total = raw_cost+pk+mf
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:'Malgun Gothic',sans-serif;margin:30px;font-size:12px}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #333;padding:5px 8px;text-align:center}}
th{{background:#2c3e50;color:white}}h1{{text-align:center;color:#2c3e50}}
.meta{{display:flex;justify-content:space-between;margin:10px 0;padding:10px;background:#f0f0f0;border-radius:5px}}
.summary{{margin:15px 0;padding:10px;background:#e8f5e9;border-radius:5px}}
@media print{{body{{margin:10mm}}}}
</style></head><body>
<h1>🥤 음료 배합비 & 원가계산서</h1>
<div class="meta"><span><b>제품명:</b> {product_name}</span><span><b>용량:</b> {volume}ml</span><span><b>작성일:</b> {datetime.now().strftime('%Y-%m-%d')}</span></div>
<h2>📋 배합표</h2>
<table><tr><th>구분</th><th>원료명</th><th>배합비(%)</th><th>당기여(Bx)</th><th>산기여(%)</th><th>단가기여(원/kg)</th></tr>
{rows_html}</table>
<div class="summary">
<b>예상당도:</b> {t_brix:.2f}Bx | <b>예상산도:</b> {t_acid:.4f}% | <b>예상pH:</b> {est_ph:.1f} | <b>원재료비:</b> {total_cost:,.0f}원/kg
</div>
<h2>💰 원가계산서</h2>
<table><tr><th>항목</th><th>금액(원/병)</th></tr>
<tr><td>원재료비</td><td>{raw_cost:,.0f}</td></tr>
<tr><td>포장재비</td><td>{pk:,.0f}</td></tr>
<tr><td>제조경비</td><td>{mf:,.0f}</td></tr>
<tr style="font-weight:bold;background:#fff3e0"><td>★ 제조원가 합계</td><td>{total:,.0f}</td></tr>
<tr><td>소비자가</td><td>{selling_price:,.0f}</td></tr>
<tr><td>원가율</td><td>{total/selling_price*100:.1f}%</td></tr>
</table>
<p style="text-align:center;color:#888;margin-top:20px">© FoodWell R&D Training | Powered by Streamlit + Gemini AI</p>
</body></html>"""
    return html

# ============================================================
# PAGE: 대시보드
# ============================================================
if page == "🏠 대시보드":
    st.title("🥤 음료개발 데이터베이스 v3")
    st.markdown("**FoodWell 음료 R&D 통합 데이터베이스 — Streamlit + Gemini AI**")
    c1,c2,c3 = st.columns(3)
    c1.metric("🧬 등록 원료", f"{len(data['원료DB'])}종")
    c2.metric("📏 규격 유형", f"{len(data['음료규격기준'])}종")
    c3.metric("📖 가이드 배합", f"{len(data['가이드배합비'])}건")
    st.markdown("---")
    col1,col2 = st.columns(2)
    with col1:
        st.subheader("📂 데이터 구성")
        for k,v in {"원료DB":f"{len(data['원료DB'])}행 — 원료 SPEC","음료규격기준":f"{len(data['음료규격기준'])}행 — 유형별 규격","가이드배합비":f"{len(data['가이드배합비'])}행 — AI+사례 가이드"}.items():
            st.markdown(f"- **{k}**: {v}")
        st.markdown("---")
        st.subheader("🆕 v3 주요 개선")
        st.markdown("""
- 🤖 **Gemini AI 배합비 추천** (20년차 연구원 페르소나)
- 🧪 **실시간 Brix/pH/산도 변화 추적**
- 📐 **산미료 pKa 기반 pH·산도 정밀 계산**
- 🎨 **나노바나나 제품 이미지 생성**
- 📥 **엑셀 + PDF 출력**
        """)
    with col2:
        st.subheader("🧬 원료 대분류 분포")
        st.bar_chart(data['원료DB']['원료대분류'].value_counts())

# ============================================================
# PAGE: 배합시뮬레이터
# ============================================================
elif page == "🧪 배합시뮬레이터":
    st.title("🧪 음료 배합비 시뮬레이터")
    df_raw = data['원료DB']
    df_std = data['음료규격기준']
    df_guide = data['가이드배합비']
    bev_types = df_std['음료유형'].dropna().tolist()

    # ─── 좌측: 표준배합비 선택 / 우측: 입력 ───
    left_col, right_col = st.columns([1, 3])

    with left_col:
        st.markdown("### 📋 표준배합비")
        combo_list = sorted(df_guide['combo'].dropna().unique().tolist())
        selected_std = st.selectbox("유형+맛 조합", ["선택안함"] + combo_list, key="std_combo")

        if selected_std != "선택안함":
            std_data = df_guide[df_guide['combo']==selected_std]
            st.markdown("**🟢 사례배합비:**")
            for _, r in std_data.iterrows():
                n = r['사례원료명']; p = sf(r['사례배합비(%)'])
                if n and str(n) not in ('0','nan','') and p > 0:
                    st.caption(f"• {n}: {p}%")
            st.markdown("**🟣 AI추천배합비:**")
            for _, r in std_data.iterrows():
                n = r['AI원료명']; p = sf(r['AI배합비(%)'])
                if n and str(n) not in ('0','nan','') and p > 0:
                    st.caption(f"• {n}: {p}%")

            if st.button("📥 사례배합비 자동채움", use_container_width=True, type="primary"):
                for _, r in std_data.iterrows():
                    slot = int(r['slot'])
                    n = str(r['사례원료명']) if pd.notna(r['사례원료명']) else ''
                    p = sf(r['사례배합비(%)'])
                    if n and n != '0' and p > 0:
                        raw_names_list = [""] + df_raw['원료명'].dropna().tolist()
                        if n in raw_names_list:
                            st.session_state[f"raw_{slot}"] = n
                            st.session_state[f"pct_{slot}"] = p
                st.rerun()

            if st.button("📥 AI추천 자동채움", use_container_width=True):
                for _, r in std_data.iterrows():
                    slot = int(r['slot'])
                    n = str(r['AI원료명']) if pd.notna(r['AI원료명']) else ''
                    p = sf(r['AI배합비(%)'])
                    if n and n != '0' and p > 0:
                        raw_names_list = [""] + df_raw['원료명'].dropna().tolist()
                        if n in raw_names_list:
                            st.session_state[f"raw_{slot}"] = n
                            st.session_state[f"pct_{slot}"] = p
                st.rerun()

        st.markdown("---")
        st.markdown("### 🔧 도구")
        if st.button("🗑️ 배합비 초기화", use_container_width=True):
            for i in range(1, 21):
                st.session_state[f"raw_{i}"] = ""
                st.session_state[f"pct_{i}"] = 0.0
            for k in ['ai_recommendation','ai_meta']:
                st.session_state[k] = {}
            st.rerun()

    with right_col:
        # ── 제품 기본정보 ──
        st.markdown("### 📝 제품 기본정보")
        ic1,ic2 = st.columns(2)
        product_name = ic1.text_input("제품명", key="product_name")
        volume = ic2.number_input("목표용량(ml)", key="volume", step=50)

        # ── 음료유형 + 맛 ──
        st.markdown("### 🎯 음료유형 + 맛")
        tc1,tc2,tc3 = st.columns(3)
        bev_type = tc1.selectbox("음료유형", bev_types, key="bev_type_idx")
        flavors = ["사과","딸기","포도","오렌지","복숭아","망고","레몬","자몽","블루베리","감귤","유자","키위"]
        flavor = tc2.selectbox("맛", flavors, key="flavor_idx")
        custom_flavor = tc3.text_input("직접입력", key="custom_flavor", placeholder="없으면 비워두세요")
        eff_flavor = custom_flavor if custom_flavor else flavor

        # ── 규격기준 ──
        std = get_std(bev_type, df_std)
        if std is not None:
            st.markdown("### 📏 규격기준")
            sc = st.columns(5)
            for i,(lbl,col) in enumerate([("당도","당도(Brix,°)"),("pH","pH 범위"),("산도","산도(%)"),("과즙","과즙함량(%)"),("비고","비고")]):
                v = std.get(col,'—'); v = v if pd.notna(v) else '—'
                sc[i].info(f"**{lbl}**: {v}")

        # ── 품질목표 ──
        st.markdown("### 🎯 품질목표")
        qc = st.columns(4)
        target_brix = qc[0].number_input("목표당도(Bx)", key="target_brix", step=0.5)
        target_acid = qc[1].number_input("목표산도(%)", key="target_acid", step=0.05, format="%.3f")
        target_sweet = qc[2].text_input("목표감미도", key="target_sweet")
        target_cost = qc[3].number_input("목표단가(원/kg)", key="target_cost", step=100)

        # ── AI 배합비 추천 (Gemini) ──
        st.markdown("---")
        st.markdown("### 🤖 AI 배합비 추천 (Gemini Flash 2.0)")
        ai_c1, ai_c2 = st.columns([4,6])
        extra_req = ai_c1.text_area("추가 요청", placeholder="예: 비타민C 강화, 저칼로리...", height=68, key="extra_req")
        ai_c2.markdown("""<div style='background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:10px 14px;border-radius:8px;font-size:13px;'>
        <b>🧑‍🔬 AI 연구원</b> | 경력20년 · 관능전문가 · 혼합/기능성음료 · 원료DB 174종 기반 · 식품공전 준수</div>""", unsafe_allow_html=True)

        gc1,gc2 = st.columns(2)
        gen_btn = gc1.button("🚀 AI 배합비 생성", type="primary", use_container_width=True)
        if gc2.button("🗑️ AI추천 초기화", use_container_width=True):
            st.session_state['ai_recommendation'] = {}
            st.session_state['ai_meta'] = {}
            st.rerun()

        if gen_btn:
            if not gemini_api_key:
                st.error("❌ 사이드바에서 Gemini API Key를 입력하세요.")
            else:
                with st.spinner("🧑‍🔬 배합비 설계중..."):
                    raw_ctx = build_raw_context(df_raw)
                    prompt = build_rec_prompt(bev_type, eff_flavor, std, target_brix, target_acid, target_cost, raw_ctx, extra_req)
                    resp, err = call_gemini(gemini_api_key, prompt)
                    if err: st.error(f"❌ {err}")
                    else:
                        rec, perr = parse_rec_json(resp)
                        if perr:
                            st.error(perr)
                            with st.expander("원본응답"): st.code(resp)
                        else:
                            ok, warns = validate_rec(rec, df_raw)
                            ai_d = {}
                            for item in ok:
                                ai_d[item['slot']] = {'AI원료':item['name'],'AI%':item['pct'],'reason':item.get('reason','')}
                            st.session_state['ai_recommendation'] = ai_d
                            st.session_state['ai_meta'] = {
                                'concept':rec.get('design_concept',''),'sensory':rec.get('sensory_note',''),
                                'tips':rec.get('tips',''),'expected_brix':rec.get('expected_brix',0),
                                'expected_acidity':rec.get('expected_acidity',0),'expected_ph':rec.get('expected_ph',0),
                                'expected_cost':rec.get('expected_cost_per_kg',0)}
                            for w in warns: st.warning(w)
                            st.success(f"✅ AI배합비 생성완료! ({len(ok)}종)")
                            st.rerun()

        # AI 메타정보 표시
        if st.session_state.get('ai_meta'):
            meta = st.session_state['ai_meta']
            with st.expander("🧑‍🔬 AI 설계컨셉 & 관능노트", expanded=True):
                mc = st.columns(4)
                mc[0].metric("예상Bx", f"{meta.get('expected_brix',0):.1f}")
                mc[1].metric("예상산도", f"{meta.get('expected_acidity',0):.3f}%")
                mc[2].metric("예상pH", f"{meta.get('expected_ph',0):.1f}")
                mc[3].metric("예상원가", f"{meta.get('expected_cost',0):,.0f}원/kg")
                for icon,key,color in [("💡","concept","#F3E8FF"),("👅","sensory","#FFF8E1"),("🔧","tips","#E8F5E9")]:
                    st.markdown(f"<div style='background:{color};padding:10px;border-radius:6px;margin:4px 0;'><b>{icon}</b> {meta.get(key,'')}</div>", unsafe_allow_html=True)

        # ── 배합비 입력 테이블 ──
        st.markdown("### 🧪 배합비 입력 (100% 기준)")
        st.caption("🟣 = Gemini AI 추천 | 🟢 = 사례 가이드")

        raw_names = [""] + df_raw['원료명'].dropna().tolist()
        categories = [("🍎 원재료",4,"raw"),("🍬 당류/감미료",4,"sugar"),("🧊 안정제/호료",4,"stab"),("📦 기타자재",8,"etc")]

        # 사례가이드 dict
        guide_matches = get_guide(bev_type, eff_flavor, df_guide)
        case_dict = {}
        if len(guide_matches) > 0:
            for _, r in guide_matches.iterrows():
                s = int(r['slot']); cn = str(r['사례원료명']) if pd.notna(r['사례원료명']) else ''; cp = sf(r['사례배합비(%)'])
                if cn == '0': cn = ''
                case_dict[s] = {'사례원료':cn,'사례%':cp if cp>0 else 0}
        ai_dict = st.session_state.get('ai_recommendation', {})

        ingredients = []
        slot_num = 0

        # 헤더
        hdr = st.columns([0.4,2.8,1.2,2.2,0.8,2.2,0.8])
        for i,txt in enumerate(["#","원료 선택","배합%","🟣 AI추천","AI%","🟢 사례","사례%"]):
            clr = "#7B68EE" if i in (3,4) else ("#2E8B57" if i in (5,6) else "#666")
            hdr[i].markdown(f"<div style='text-align:center;font-size:11px;font-weight:bold;color:{clr};'>{txt}</div>", unsafe_allow_html=True)

        for cat_name, num_rows, _ in categories:
            st.markdown(f"**{cat_name}**")
            for i in range(num_rows):
                slot_num += 1
                ai = ai_dict.get(slot_num, {})
                cs = case_dict.get(slot_num, {})
                cols = st.columns([0.4,2.8,1.2,2.2,0.8,2.2,0.8])
                cols[0].markdown(f"<div style='padding-top:28px;text-align:center;color:#888;'>{slot_num}</div>", unsafe_allow_html=True)
                name = cols[1].selectbox("원료", raw_names, key=f"raw_{slot_num}", label_visibility="collapsed")
                pct = cols[2].number_input("%", value=0.0, min_value=0.0, max_value=100.0, step=0.1, format="%.3f", key=f"pct_{slot_num}", label_visibility="collapsed")
                # AI 추천
                at = f"🟣 {ai.get('AI원료','')}" if ai.get('AI원료') else ""
                bg1 = "#F3E8FF" if ai.get('AI원료') else "#FAFAFA"
                cols[3].markdown(f"<div style='padding-top:6px;font-size:11px;color:#7B68EE;background:{bg1};border-radius:4px;padding:5px;min-height:34px;'>{at}</div>", unsafe_allow_html=True)
                ap = f"{ai.get('AI%','')}%" if ai.get('AI%') else ""
                cols[4].markdown(f"<div style='padding-top:6px;font-size:11px;color:#7B68EE;text-align:center;background:{bg1};border-radius:4px;padding:5px;min-height:34px;'>{ap}</div>", unsafe_allow_html=True)
                # 사례
                ct = f"🟢 {cs.get('사례원료','')}" if cs.get('사례원료') else ""
                bg2 = "#E8FFE8" if cs.get('사례원료') else "#FAFAFA"
                cols[5].markdown(f"<div style='padding-top:6px;font-size:11px;color:#2E8B57;background:{bg2};border-radius:4px;padding:5px;min-height:34px;'>{ct}</div>", unsafe_allow_html=True)
                cpt = f"{cs.get('사례%','')}%" if cs.get('사례%') else ""
                cols[6].markdown(f"<div style='padding-top:6px;font-size:11px;color:#2E8B57;text-align:center;background:{bg2};border-radius:4px;padding:5px;min-height:34px;'>{cpt}</div>", unsafe_allow_html=True)

                if name and pct > 0:
                    mat = get_raw(name, df_raw)
                    brix_v = matv(mat,'Brix(°)'); acid_v = matv(mat,'산도(%)'); sweet_v = matv(mat,'감미도(설탕대비)'); price_v = matv(mat,'예상단가(원/kg)')
                    # DB에 없으면 이름 유추
                    if mat is None:
                        inf = infer_from_name(name)
                        if inf:
                            brix_v = inf.get('brix', brix_v); acid_v = inf.get('acidity', acid_v)
                            sweet_v = inf.get('sweetness', sweet_v)
                    ingredients.append({
                        'slot':slot_num,'구분':cat_name.split(' ')[1] if ' ' in cat_name else cat_name,
                        '원료명':name,'배합비(%)':pct,'Brix':brix_v,'산도':acid_v,
                        '감미도':sweet_v,'단가':price_v})

        # ── 정제수 ──
        total_pct = sum(i['배합비(%)'] for i in ingredients)
        water_pct = 100.0 - total_pct
        st.markdown("**💧 정제수**")
        if water_pct >= 0:
            st.metric("정제수 배합비", f"{water_pct:.3f}%")
        else:
            st.error(f"⚠️ 배합비 초과! {total_pct:.1f}% > 100%")
        if water_pct > 0:
            ingredients.append({'slot':21,'구분':'정제수','원료명':'정제수','배합비(%)':water_pct,'Brix':0,'산도':0,'감미도':0,'단가':2})

        # ── 실시간 예상치 변화표 ──
        st.markdown("---")
        st.markdown("### 📊 실시간 품질 예상치")
        if ingredients:
            t_brix = sum(i['배합비(%)']/100*i['Brix'] for i in ingredients)
            t_acid = sum(i['배합비(%)']/100*i['산도'] for i in ingredients)
            t_sweet = sum(i['배합비(%)']/100*i['감미도'] for i in ingredients)
            t_cost = sum(i['배합비(%)']/100*i['단가'] for i in ingredients)
            est_ph = estimate_ph(ingredients, df_raw)
            raw_pct = sum(i['배합비(%)'] for i in ingredients if i['slot']<=4)/100
            n_ing = len([i for i in ingredients if i['원료명']!='정제수'])

            # 규격 비교 테이블
            preview_data = []
            if std is not None:
                bmin=sf(std.get('Brix_min')); bmax=sf(std.get('Brix_max'))
                amin=sf(std.get('산도_min')); amax=sf(std.get('산도_max'))
                pmin=sf(std.get('pH_min')); pmax=sf(std.get('pH_max'))
                preview_data.append({"항목":"당도(Bx)","현재값":f"{t_brix:.2f}","규격범위":f"{std.get('당도(Brix,°)','—')}","판정":"✅" if (bmin<=t_brix<=bmax and bmax>0) else "⚠️"})
                preview_data.append({"항목":"산도(%)","현재값":f"{t_acid:.4f}","규격범위":f"{std.get('산도(%)','—')}","판정":"✅" if (amin<=t_acid<=amax and amax>0) else ("⚠️" if amax>0 else "ℹ️")})
                preview_data.append({"항목":"pH","현재값":f"{est_ph:.2f}","규격범위":f"{std.get('pH 범위','—')}","판정":"✅" if (pmin<=est_ph<=pmax and pmax>0) else ("⚠️" if pmax>0 else "ℹ️")})
            preview_data.append({"항목":"감미도","현재값":f"{t_sweet:.2f}","규격범위":"—","판정":"ℹ️"})
            preview_data.append({"항목":"원재료비(원/kg)","현재값":f"{t_cost:,.0f}","규격범위":f"≤{target_cost:,.0f}","판정":"✅" if t_cost<=target_cost else "⚠️"})
            st.dataframe(pd.DataFrame(preview_data), use_container_width=True, hide_index=True)

            # 메트릭 카드
            rc = st.columns(4)
            rc[0].metric("배합비 합계", f"{sum(i['배합비(%)'] for i in ingredients):.1f}%", "✅ 100%" if abs(sum(i['배합비(%)'] for i in ingredients)-100)<0.1 else "⚠️")
            rc[1].metric("원료 종류", f"{n_ing}종")
            rc[2].metric("정제수", f"{water_pct:.1f}%")
            rc[3].metric("원재료함량", f"{raw_pct*100:.1f}%")

            # 배합 상세표
            st.markdown("#### 📋 배합 상세표")
            df_r = pd.DataFrame(ingredients)
            df_r['당기여(Bx)'] = df_r['배합비(%)']/100*df_r['Brix']
            df_r['산기여(%)'] = df_r['배합비(%)']/100*df_r['산도']
            df_r['감미기여'] = df_r['배합비(%)']/100*df_r['감미도']
            df_r['단가기여(원/kg)'] = df_r['배합비(%)']/100*df_r['단가']
            df_r['배합량(g/kg)'] = df_r['배합비(%)']*10
            dcols = ['구분','원료명','배합비(%)','당기여(Bx)','산기여(%)','감미기여','단가기여(원/kg)','배합량(g/kg)']
            st.dataframe(df_r[dcols].style.format({'배합비(%)':'{:.3f}','당기여(Bx)':'{:.2f}','산기여(%)':'{:.4f}','감미기여':'{:.4f}','단가기여(원/kg)':'{:,.0f}','배합량(g/kg)':'{:.1f}'}),use_container_width=True,hide_index=True)

            # session 저장
            st.session_state['ingredients'] = ingredients
            st.session_state['total_cost'] = t_cost
            st.session_state['est_ph'] = est_ph

            # ── 내보내기 ──
            st.markdown("---")
            st.markdown("### 📥 내보내기")
            ex1,ex2,ex3 = st.columns(3)
            try:
                xlsx = export_excel(ingredients, volume, product_name, t_cost,
                    st.session_state.get('pack_vals',[45,8,12,50,0,5]),
                    st.session_state.get('mfg_vals',[20,18,22]),
                    st.session_state.get('selling_price',1500))
                ex1.download_button("📥 엑셀 다운로드", xlsx,
                    file_name=f"{product_name}_배합표_{datetime.now():%Y%m%d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            except Exception as e:
                ex1.warning(f"엑셀 생성 실패: {e}\npip install openpyxl 필요")

            pdf_html = export_pdf_html(ingredients, volume, product_name, t_cost, est_ph,
                st.session_state.get('pack_vals',[45,8,12,50,0,5]),
                st.session_state.get('mfg_vals',[20,18,22]),
                st.session_state.get('selling_price',1500))
            ex2.download_button("📥 인쇄용 HTML", pdf_html.encode('utf-8'),
                file_name=f"{product_name}_배합표_{datetime.now():%Y%m%d}.html",
                mime="text/html", use_container_width=True)

            # ── 🎨 제품 이미지 생성 (나노바나나) ──
            st.markdown("---")
            st.markdown("### 🎨 제품 이미지 생성 (Nano Banana)")
            img_c1, img_c2 = st.columns([3,7])
            with img_c1:
                bottle_type = st.selectbox("용기 타입", ["PET 투명병","PET 유색병","캔(알루미늄)","유리병","파우치","테트라팩"], key="bottle_type")
                img_style = st.selectbox("스타일", ["스튜디오 제품촬영","자연 배경","카페 분위기","미니멀"], key="img_style")
                img_extra = st.text_input("추가 프롬프트", key="img_extra", placeholder="배경 색상, 소품 등")
            with img_c2:
                if st.button("🎨 제품 이미지 생성", type="primary", use_container_width=True):
                    if not gemini_api_key:
                        st.error("❌ API Key 필요")
                    else:
                        # 주요 원재료 추출
                        main_ings = [i['원료명'] for i in ingredients if i['slot']<=4 and i['원료명']!='정제수']
                        color_hint = "golden amber" if "사과" in eff_flavor else "red pink" if "딸기" in eff_flavor else "purple" if "포도" in eff_flavor else "orange" if "오렌지" in eff_flavor else "light yellow"

                        img_prompt = f"""Create a professional commercial product photograph of a Korean beverage.

Product: "{product_name}" - {bev_type}, {eff_flavor} flavor
Container: {bottle_type}, {volume}ml
Liquid color: {color_hint}, clear/translucent
Main ingredients shown as props: {', '.join(main_ings[:3]) if main_ings else eff_flavor}
Style: {img_style} photography, premium quality
Label: Clean modern Korean beverage label with product name "{product_name}"
{f'Additional: {img_extra}' if img_extra else ''}
High-end product photography, soft studio lighting, slight reflection on surface, 4K quality, photorealistic"""

                        with st.spinner("🎨 이미지 생성중..."):
                            img_data, mime, img_err = call_gemini_image(gemini_api_key, img_prompt)
                            if img_err:
                                st.error(f"❌ {img_err}")
                            elif img_data:
                                st.image(base64.b64decode(img_data), caption=f"🎨 {product_name} — AI 생성 제품 이미지", use_container_width=True)
                                st.download_button("📥 이미지 저장", base64.b64decode(img_data),
                                    file_name=f"{product_name}_제품이미지.png", mime=mime or "image/png")

# ============================================================
# PAGE: 원가계산서
# ============================================================
elif page == "💰 원가계산서":
    st.title("💰 음료 제품 원가계산서")
    ingredients = st.session_state.get('ingredients',[])
    volume = st.session_state.get('volume',1000)
    product_name = st.session_state.get('product_name','(먼저 배합시뮬레이터 입력)')
    st.markdown(f"**제품명**: {product_name} | **용량**: {volume}ml")
    if not ingredients:
        st.warning("⚠️ 배합시뮬레이터에서 먼저 배합비를 입력해주세요.")
        st.stop()

    st.markdown("### ① 원재료비")
    rows = []
    for i in ingredients:
        up=sf(i.get('단가')); pct=sf(i.get('배합비(%)'))
        cpb = up*(pct/100)*volume/1000
        rows.append({'항목':i['원료명'],'배합비':f"{pct:.2f}%",'단가(원/kg)':f"{up:,.0f}",
            '사용량(kg/병)':f"{pct/100*volume/1000:.5f}",'비용(원/병)':f"{cpb:,.1f}"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    raw_kg = sum(sf(i.get('단가'))*sf(i.get('배합비(%)'))/100 for i in ingredients)
    raw_btl = raw_kg * volume / 1000
    st.metric("원재료비 소계(원/병)", f"{raw_btl:,.0f}")

    st.markdown("### ② 포장재비")
    pk_labels = ["PET용기","PE캡","라벨","박스(원/병)","빨대","쉬링크"]
    pk_defaults = st.session_state.get('pack_vals',[45,8,12,50,0,5])
    pc = st.columns(6)
    pk_vals = []
    for idx in range(6):
        v = pc[idx].number_input(pk_labels[idx], value=pk_defaults[idx], key=f"pk_{idx}")
        pk_vals.append(v)
    st.session_state['pack_vals'] = pk_vals
    pk_total = sum(pk_vals)
    st.metric("포장재비 소계(원/병)", f"{pk_total:,.0f}")

    st.markdown("### ③ 제조경비")
    mf_labels = ["인건비(직접+간접)","전력+용수+스팀+냉각","CIP+검사+감가+임차"]
    mf_defaults = st.session_state.get('mfg_vals',[20,18,22])
    mc = st.columns(3)
    mf_vals = []
    for idx in range(3):
        v = mc[idx].number_input(mf_labels[idx], value=mf_defaults[idx], key=f"mf_{idx}")
        mf_vals.append(v)
    st.session_state['mfg_vals'] = mf_vals
    mf_total = sum(mf_vals)
    st.metric("제조경비 소계(원/병)", f"{mf_total:,.0f}")

    st.markdown("---")
    st.markdown("### ④ 총괄 원가 요약")
    total_all = raw_btl + pk_total + mf_total
    tc = st.columns(4)
    tc[0].metric("원재료비", f"{raw_btl:,.0f}원/병")
    tc[1].metric("포장재비", f"{pk_total:,.0f}원/병")
    tc[2].metric("제조경비", f"{mf_total:,.0f}원/병")
    tc[3].metric("★ 제조원가 합계", f"{total_all:,.0f}원/병", delta=f"{total_all*1000/volume:,.0f}원/kg")

    sp = st.number_input("소비자가(원)", value=st.session_state.get('selling_price',1500), step=100, key="sp_input")
    st.session_state['selling_price'] = sp
    if sp > 0:
        cr = total_all/sp*100
        st.metric("원가율", f"{cr:.1f}%", delta="양호" if cr<40 else ("보통" if cr<50 else "높음"))

    # 내보내기
    st.markdown("---")
    ec1,ec2 = st.columns(2)
    try:
        xlsx = export_excel(ingredients, volume, product_name, st.session_state.get('total_cost',0), pk_vals, mf_vals, sp)
        ec1.download_button("📥 엑셀 다운로드", xlsx, file_name=f"{product_name}_원가계산서.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    except: pass
    pdf_html = export_pdf_html(ingredients, volume, product_name, st.session_state.get('total_cost',0),
        st.session_state.get('est_ph',3.5), pk_vals, mf_vals, sp)
    ec2.download_button("📥 인쇄용 HTML", pdf_html.encode('utf-8'),
        file_name=f"{product_name}_원가계산서.html", mime="text/html", use_container_width=True)

# ============================================================
# PAGE: 원료DB
# ============================================================
elif page == "🧬 원료DB":
    st.title("🧬 원료 데이터베이스")
    df = data['원료DB']
    c1,c2,c3 = st.columns(3)
    cf = c1.multiselect("대분류", df['원료대분류'].dropna().unique().tolist())
    sf2 = c2.multiselect("소분류", df['원료소분류'].dropna().unique().tolist())
    srch = c3.text_input("🔍 원료명 검색", key="raw_srch")
    if cf: df = df[df['원료대분류'].isin(cf)]
    if sf2: df = df[df['원료소분류'].isin(sf2)]
    if srch: df = df[df['원료명'].str.contains(srch, case=False, na=False)]
    st.dataframe(df, use_container_width=True, hide_index=True, height=500)
    st.caption(f"총 {len(df)}종")
    if len(df)>0:
        st.markdown("---")
        sel = st.selectbox("📋 상세 조회", df['원료명'].tolist())
        if sel:
            d = df[df['원료명']==sel].iloc[0]
            dc = st.columns(5)
            dc[0].metric("Brix(°)", sf(d.get('Brix(°)')))
            dc[1].metric("pH", sf(d.get('pH')))
            dc[2].metric("산도(%)", sf(d.get('산도(%)')))
            dc[3].metric("1%pH", sf(d.get('1%당pH(1%용액)')))
            dc[4].metric("단가(원/kg)", f"{sf(d.get('예상단가(원/kg)')):,.0f}")

# ============================================================
# PAGE: 음료규격기준
# ============================================================
elif page == "📏 음료규격기준":
    st.title("📏 음료규격기준")
    df = data['음료규격기준']
    hide = ['Brix_min','Brix_max','pH_min','pH_max','산도_min','산도_max']
    st.dataframe(df[[c for c in df.columns if c not in hide]], use_container_width=True, hide_index=True)
    st.markdown("---")
    sel = st.selectbox("유형 선택", df['음료유형'].tolist())
    if sel:
        r = df[df['음료유형']==sel].iloc[0]
        sc = st.columns(5)
        for i,(l,c) in enumerate([("당도","당도(Brix,°)"),("pH","pH 범위"),("산도","산도(%)"),("과즙","과즙함량(%)"),("비고","비고")]):
            v=r.get(c,'—'); v=v if pd.notna(v) else '—'
            sc[i].info(f"**{l}**: {v}")

# ============================================================
# PAGE: 가이드배합비DB
# ============================================================
elif page == "📖 가이드배합비DB":
    st.title("📖 가이드 배합비 데이터베이스")
    df = data['가이드배합비']
    st.markdown("AI추천 + 실제사례 가이드")
    if len(df)>0:
        combos = sorted(df['combo'].dropna().unique().tolist())
        sel = st.selectbox("유형+맛 조합", combos)
        if sel:
            filt = df[df['combo']==sel]
            c1,c2 = st.columns(2)
            with c1:
                st.markdown("#### 🟣 AI 추천")
                for _,r in filt.iterrows():
                    n=r['AI원료명']; p=sf(r['AI배합비(%)'])
                    if n and str(n) not in ('0','nan','') and p>0: st.markdown(f"- **{n}**: {p}%")
            with c2:
                st.markdown("#### 🟢 실제 사례")
                for _,r in filt.iterrows():
                    n=r['사례원료명']; p=sf(r['사례배합비(%)'])
                    if n and str(n) not in ('0','nan','') and p>0: st.markdown(f"- **{n}**: {p}%")
            st.dataframe(filt, use_container_width=True, hide_index=True)

# ============================================================
st.sidebar.markdown("---")
st.sidebar.caption("© FoodWell R&D Training\n음료개발 DB v3 + Gemini AI\nPowered by Streamlit")
