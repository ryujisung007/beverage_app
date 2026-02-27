import streamlit as st
import pandas as pd
import json, os, re, math, io, base64
from datetime import datetime

st.set_page_config(page_title="🥤 음료개발 DB v3", layout="wide", initial_sidebar_state="expanded")

# 빈공간 줄이기 CSS
st.markdown("""<style>
.block-container{padding-top:1.5rem;padding-bottom:0.5rem;}
[data-testid="stSidebar"] .block-container{padding-top:1rem;}
div[data-testid="stMetricValue"]{font-size:1.1rem;}
.stSelectbox>div>div{min-height:32px;}
</style>""", unsafe_allow_html=True)

# ============================================================
# SESSION STATE
# ============================================================
for k, v in {'product_name':'사과과채음료_시제1호','volume':1000,'bev_type_idx':1,
    'flavor_idx':0,'custom_flavor':'','target_brix':11.0,'target_acid':0.35,
    'target_sweet':'0.56','target_cost':1500,'ingredients':[],'total_cost':0,
    'ai_recommendation':{},'ai_meta':{},'pack_vals':[45,8,12,50,0,5],
    'mfg_vals':[20,18,22],'selling_price':1500,'est_ph':3.5}.items():
    if k not in st.session_state: st.session_state[k] = v

# ============================================================
# DATA LOADING
# ============================================================
@st.cache_data
def load_data():
    jp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beverage_data.json")
    if not os.path.exists(jp): st.error("❌ beverage_data.json 필요"); st.stop()
    with open(jp,'r',encoding='utf-8') as f: raw=json.load(f)
    s={}
    df=pd.DataFrame(raw['raw_materials'])
    df.rename(columns={'cat':'원료대분류','subcat':'원료소분류','name':'원료명',
        'brix':'Brix(°)','ph':'pH','acidity':'산도(%)','sweetness':'감미도(설탕대비)',
        'component':'주요성분','form':'공급형태','storage':'보관조건','price':'예상단가(원/kg)',
        'brix_1pct':'1%당Brix기여','ph_1pct':'1%당pH(1%용액)',
        'acid_1pct':'1%당산도기여','sweet_1pct':'1%당감미도기여','note':'비고'},inplace=True)
    s['원료DB']=df
    ds=pd.DataFrame(raw['standards'])
    ds.rename(columns={'type':'음료유형','brix_text':'당도(Brix,°)','ph_text':'pH 범위',
        'acid_text':'산도(%)','juice_text':'과즙함량(%)','solid_text':'고형분(%)',
        'co2_text':'탄산가스(vol)','note':'비고','brix_min':'Brix_min','brix_max':'Brix_max',
        'ph_min':'pH_min','ph_max':'pH_max','acid_min':'산도_min','acid_max':'산도_max'},inplace=True)
    s['음료규격기준']=ds
    rows=[]
    for ck,items in raw['guides'].items():
        for it in items:
            rows.append({'key':f"{ck}_{it['slot']:02d}",'combo':ck,'slot':it['slot'],
                'cat':it.get('cat',''),'AI원료명':it.get('ai_name',''),'AI배합비(%)':it.get('ai_pct',0),
                '사례원료명':it.get('case_name',''),'사례배합비(%)':it.get('case_pct',0)})
    s['가이드배합비']=pd.DataFrame(rows)
    return s

data = load_data()

# ============================================================
# SIDEBAR: API + 메뉴 + 표준배합비
# ============================================================
st.sidebar.title("🥤 음료개발 DB v3")
st.sidebar.markdown("---")

# API Keys
with st.sidebar.expander("🔑 API Keys", expanded=False):
    gemini_key = st.text_input("Gemini API Key", type="password", placeholder="AIza...", key="gem_k")
    openai_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...", key="oai_k")
    if gemini_key: st.caption("✅ Gemini 입력됨")
    if openai_key: st.caption("✅ OpenAI 입력됨")

st.sidebar.markdown("---")
page = st.sidebar.radio("📂 메뉴", [
    "🏠 대시보드","🧪 배합시뮬레이터","💰 원가계산서",
    "🧬 원료DB","📏 음료규격기준","📖 가이드배합비DB"])

# 표준배합비 자동채움 (사이드바 하단)
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 표준배합비")
df_guide = data['가이드배합비']
combo_list = sorted(df_guide['combo'].dropna().unique().tolist())
sel_combo = st.sidebar.selectbox("유형+맛 조합", ["미선택"]+combo_list, key="sb_combo")
if sel_combo != "미선택":
    sd = df_guide[df_guide['combo']==sel_combo]
    # 간략 표시
    case_items = [(str(r['사례원료명']),r['사례배합비(%)']) for _,r in sd.iterrows()
                  if str(r.get('사례원료명','')) not in ('0','nan','','None') and float(r.get('사례배합비(%)',0) or 0)>0]
    ai_items = [(str(r['AI원료명']),r['AI배합비(%)']) for _,r in sd.iterrows()
                if str(r.get('AI원료명','')) not in ('0','nan','','None') and float(r.get('AI배합비(%)',0) or 0)>0]
    st.sidebar.caption(f"🟢 사례 {len(case_items)}종 | 🟣 AI {len(ai_items)}종")
    raw_names_set = set(data['원료DB']['원료명'].tolist())

    sc1,sc2 = st.sidebar.columns(2)
    if sc1.button("🟢사례채움", use_container_width=True):
        for _,r in sd.iterrows():
            s=int(r['slot']); n=str(r['사례원료명']) if pd.notna(r['사례원료명']) else ''; p=float(r.get('사례배합비(%)',0) or 0)
            if n and n!='0' and p>0 and n in raw_names_set:
                st.session_state[f"raw_{s}"]=n; st.session_state[f"pct_{s}"]=p
        st.rerun()
    if sc2.button("🟣AI채움", use_container_width=True):
        for _,r in sd.iterrows():
            s=int(r['slot']); n=str(r['AI원료명']) if pd.notna(r['AI원료명']) else ''; p=float(r.get('AI배합비(%)',0) or 0)
            if n and n!='0' and p>0 and n in raw_names_set:
                st.session_state[f"raw_{s}"]=n; st.session_state[f"pct_{s}"]=p
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("© FoodWell R&D Training\nGemini AI + OpenAI DALL-E")

# ============================================================
# HELPERS
# ============================================================
def sf(val, default=0.0):
    if val is None: return default
    if isinstance(val,(int,float)): return float(val) if pd.notna(val) else default
    s=str(val).strip().replace(',','')
    if not s or s in ('—','-','nan','None',''): return default
    try: return float(s)
    except: return default

def get_raw(n,df):
    m=df[df['원료명']==n]; return m.iloc[0] if len(m)>0 else None
def get_std(bt,df):
    m=df[df['음료유형']==bt]; return m.iloc[0] if len(m)>0 else None
def matv(mat,col):
    if mat is None: return 0.0
    try: return sf(mat.get(col))
    except: return 0.0

def estimate_ph(ingredients, df_raw):
    tH=0.0; tOH=0.0
    for ing in ingredients:
        pct=ing['배합비(%)']/100
        if pct<=0: continue
        mat=get_raw(ing['원료명'],df_raw)
        pv=7.0
        if mat is not None:
            pv=sf(mat.get('1%당pH(1%용액)'))
            if pv<=0: pv=sf(mat.get('pH'))
            if pv<=0: pv=7.0
        elif ing.get('_ph'):
            pv=ing['_ph']
        if pv<7: tH+=pct*(10**(-pv))
        elif pv>7: tOH+=pct*(10**(pv-14))
        else: tH+=pct*1e-7
    net=tH-tOH
    if net>1e-14: return round(-math.log10(net),2)
    elif net<-1e-14: return round(14+math.log10(-net),2)
    return 7.0

# ============================================================
# 원료명 유추 엔진 (개선)
# ============================================================
def infer_from_name(name):
    """DB에 없는 원료의 Brix/pH/산도/감미도를 이름에서 유추"""
    r = {}
    if not name: return None
    # Brix 파싱
    m = re.search(r'(\d+)\s*[Bb]rix', name)
    if m: r['brix'] = float(m.group(1))
    m2 = re.search(r'(\d+)배농축', name)
    if m2 and 'brix' not in r: r['brix'] = float(m2.group(1)) * 11.5
    # 과즙류 → 기본 brix 추정
    fruit_brix = {'사과':12,'딸기':8,'포도':16,'오렌지':11,'복숭아':10,'망고':15,'레몬':8,'자몽':10,'블루베리':10,'유자':8,'감귤':10,'키위':14,'배':12,'체리':16}
    for fr,bx in fruit_brix.items():
        if fr in name and 'brix' not in r:
            if any(kw in name for kw in ['농축','페이스트']): r['brix'] = bx * 4
            elif '착즙' in name or '퓨레' in name: r['brix'] = bx
            elif '과즙' in name: r['brix'] = bx
            r['ph'] = 3.5; r['acidity'] = 0.5
            break
    # 당류
    sug = {'백설탕':(99.9,1.0),'황설탕':(99,1.0),'과당':(77,1.7),'액상과당':(77,1.5),'HFCS':(77,1.5),
        '포도당':(91,0.7),'올리고당':(75,0.5),'물엿':(75,0.4),'꿀':(80,1.0),'스테비아':(0,300),
        '수크랄로스':(0,600),'아스파탐':(0,200),'에리스리톨':(0,0.7),'자일리톨':(0,1.0),'알룰로스':(70,0.7),
        '트레할로스':(0,0.45),'소르비톨':(70,0.6),'말티톨':(75,0.9)}
    for kw,(bx,sw) in sug.items():
        if kw in name:
            r['brix']=bx; r['sweetness']=sw; r['ph']=7.0; r['acidity']=0
            break
    # 산미료
    acid = {'구연산':(2.2,100,1.0),'사과산':(2.3,95.5,0.955),'말산':(2.3,95.5,0.955),
        '주석산':(2.0,85.3,0.853),'젖산':(2.4,71.1,0.711),'인산':(1.6,196.1,1.961),
        '아스코르빈':(2.7,36.4,0.364),'비타민C':(2.7,36.4,0.364),'초산':(2.8,106.7,1.067),'빙초산':(2.4,106.7,1.067)}
    for kw,(ph,ac,a1) in acid.items():
        if kw in name:
            r['ph']=ph; r['acidity']=ac; r['acid_1pct']=a1; r['brix']=r.get('brix',0)
            break
    # 안정제
    stab = ['펙틴','카라기난','잔탄검','구아검','로커스트','CMC','젤라틴','한천','알긴산','타마린드']
    for kw in stab:
        if kw in name:
            r['brix']=r.get('brix',0); r['ph']=r.get('ph',7.0); r['acidity']=0
            break
    # 향료
    if '향' in name or '플레이버' in name or '에센스' in name:
        r['brix']=0; r['ph']=7.0; r['acidity']=0
    return r if r else None

# ============================================================
# GEMINI API (모델 업데이트)
# ============================================================
GEMINI_MODELS = ["gemini-2.5-flash-preview-04-17","gemini-2.0-flash-001","gemini-1.5-flash"]

def call_gemini(api_key, prompt):
    import urllib.request, urllib.error
    for model in GEMINI_MODELS:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        body=json.dumps({"contents":[{"parts":[{"text":prompt}]}],
            "generationConfig":{"temperature":0.7,"topP":0.9,"maxOutputTokens":4096}}).encode()
        req=urllib.request.Request(url,data=body,headers={"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req,timeout=60) as resp:
                r=json.loads(resp.read().decode())
                return r['candidates'][0]['content']['parts'][0]['text'], None
        except urllib.error.HTTPError as e:
            code=e.code
            if code==404: continue  # 모델 없으면 다음 시도
            return None, f"API오류({code}): {e.read().decode()[:200] if e.fp else ''}"
        except Exception as e:
            return None, f"연결오류: {str(e)}"
    return None, "모든 Gemini 모델 사용 불가. API Key를 확인하세요."

def build_raw_context(df):
    lines=[]
    for cat in df['원료대분류'].unique():
        sub=df[df['원료대분류']==cat]; lines.append(f"\n【{cat}】")
        for _,r in sub.iterrows():
            lines.append(f"  - {r['원료명']}|Bx:{sf(r.get('Brix(°)')):.0f}|pH:{sf(r.get('pH')):.1f}|산도:{sf(r.get('산도(%)'))}%|감미:{sf(r.get('감미도(설탕대비)'))}|₩{sf(r.get('예상단가(원/kg)')):,.0f}")
    return "\n".join(lines)

def build_rec_prompt(bt,fl,std,tb,ta,tc,raw_ctx,extra=""):
    si="규격없음"
    if std is not None:
        si=f"당도:{std.get('당도(Brix,°)','—')}|pH:{std.get('pH 범위','—')}|산도:{std.get('산도(%)','—')}|과즙:{std.get('과즙함량(%)','—')}"
    return f"""당신은 대한민국 식품음료 R&D 수석연구원(경력20년). 관능전문가, 혼합/기능성음료개발.

【요청】유형:{bt}|맛:{fl}|목표Bx:{tb}|목표산도:{ta}%|목표원가:≤{tc:,.0f}원/kg
【규격】{si}
【추가】{extra or '없음'}

【원료DB — 반드시 이 목록에서 선택】
{raw_ctx}

【규칙】원료명정확히사용, 정제수제외15~35%, 규격충족, 관능최우선, 3~12종
【슬롯】1~4:원재료|5~7:당류|8~12:호료/안정제|13~18:부재료/기타

【JSON만 출력 — 다른텍스트없이】
```json
{{"recommendation":[{{"slot":1,"name":"원료명","pct":8.0,"reason":"이유"}},...],
"expected_brix":11.2,"expected_acidity":0.35,"expected_ph":3.5,
"expected_cost_per_kg":1350,
"design_concept":"컨셉","sensory_note":"관능특성","tips":"실무팁"}}
```"""

def parse_json(text):
    m=re.search(r'```json\s*(.*?)\s*```',text,re.DOTALL)
    js=m.group(1) if m else None
    if not js:
        m2=re.search(r'\{.*\}',text,re.DOTALL)
        js=m2.group(0) if m2 else None
    if not js: return None,"JSON 파싱실패"
    try: return json.loads(js),None
    except json.JSONDecodeError as e: return None,f"JSON오류:{e}"

def validate_rec(rec,df):
    vn=set(df['원료명'].tolist()); ok=[]; w=[]
    for it in rec.get('recommendation',[]):
        n=it.get('name','')
        if n in vn: ok.append(it)
        else:
            cs=[x for x in vn if n[:2] in x][:3]
            w.append(f"⚠️'{n}'DB없음"+(f"→유사:{','.join(cs)}" if cs else ""))
    return ok,w

# ============================================================
# OpenAI DALL-E 3 이미지 생성
# ============================================================
def call_dalle(api_key, prompt):
    import urllib.request, urllib.error
    url="https://api.openai.com/v1/images/generations"
    body=json.dumps({"model":"dall-e-3","prompt":prompt,"n":1,"size":"1024x1024","quality":"standard"}).encode()
    req=urllib.request.Request(url,data=body,headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req,timeout=120) as resp:
            r=json.loads(resp.read().decode())
            img_url=r['data'][0]['url']
            # 이미지 다운로드
            with urllib.request.urlopen(img_url,timeout=60) as img_resp:
                img_bytes=img_resp.read()
            return img_bytes, None
    except urllib.error.HTTPError as e:
        return None,f"DALL-E 오류({e.code}): {e.read().decode()[:200] if e.fp else ''}"
    except Exception as e:
        return None,f"연결오류: {str(e)}"

# ============================================================
# 내보내기
# ============================================================
def export_excel(ings,vol,pname,tcost,pkv,mfv,sp):
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine='openpyxl') as w:
        df=pd.DataFrame(ings)
        if len(df)>0:
            df['당기여도']=df['배합비(%)']/100*df['Brix']
            df['산기여도']=df['배합비(%)']/100*df['산도']
            df['감미기여도']=df['배합비(%)']/100*df['감미도']
            df['제품단가']=df['단가']*df['배합비(%)']/100
            df['배합량(g)']=df['배합비(%)']*vol/100
        meta=pd.DataFrame([{'제품명':pname,'용량(ml)':vol,'원재료비(원/kg)':f"{tcost:,.0f}",'작성일':datetime.now().strftime('%Y-%m-%d')}])
        meta.to_excel(w,sheet_name='배합표',index=False,startrow=0)
        if len(df)>0:
            cols=['구분','원료명','배합비(%)','Brix','산도','감미도','단가','당기여도','산기여도','감미기여도','제품단가','배합량(g)']
            df[[c for c in cols if c in df.columns]].to_excel(w,sheet_name='배합표',index=False,startrow=3)
        # 원가
        cr=[]
        for i in ings:
            up=sf(i.get('단가'));pct=sf(i.get('배합비(%)'))
            cr.append({'항목':i['원료명'],'배합비(%)':pct,'단가(원/kg)':up,'비용(원/kg)':up*pct/100,'비용(원/병)':up*pct/100*vol/1000})
        pd.DataFrame(cr).to_excel(w,sheet_name='원가계산서',index=False)
    return out.getvalue()

def export_html(ings,vol,pname,tcost,eph,pkv,mfv,sp):
    rows=""
    for i in ings:
        bc=sf(i.get('배합비(%)'))/100*sf(i.get('Brix'));ac=sf(i.get('배합비(%)'))/100*sf(i.get('산도'))
        sc=sf(i.get('배합비(%)'))/100*sf(i.get('감미도'));cc=sf(i.get('단가'))*sf(i.get('배합비(%)'))/100
        amt=sf(i.get('배합비(%)'))*vol/100
        rows+=f"<tr><td>{i.get('구분','')}</td><td>{i['원료명']}</td><td>{sf(i.get('배합비(%)')):.3f}</td><td>{bc:.2f}</td><td>{ac:.4f}</td><td>{sc:.2f}</td><td>{cc:,.0f}</td><td>{amt:.1f}</td></tr>\n"
    tb=sum(sf(i.get('배합비(%)'))/100*sf(i.get('Brix')) for i in ings)
    ta=sum(sf(i.get('배합비(%)'))/100*sf(i.get('산도')) for i in ings)
    rc=sum(sf(i.get('단가'))*sf(i.get('배합비(%)'))/100*vol/1000 for i in ings)
    pk=sum(pkv);mf=sum(mfv);tot=rc+pk+mf
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>body{{font-family:'Malgun Gothic',sans-serif;margin:20px;font-size:11px}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #333;padding:4px 6px;text-align:center}}
th{{background:#2c3e50;color:white;font-size:10px}}h1{{text-align:center;color:#2c3e50;font-size:16px}}
.qt{{background:#ffe0e0;padding:6px;border-radius:4px;margin:8px 0;font-weight:bold;text-align:center}}
@media print{{body{{margin:8mm}}}}
</style></head><body>
<h1>🥤 {pname} — 배합비 & 원가계산서</h1>
<div style="display:flex;justify-content:space-between;margin:8px 0;font-size:12px;">
<span>용량: {vol}ml</span><span>작성일: {datetime.now():%Y-%m-%d}</span></div>
<div class="qt">품질목표 | Brix: {tb:.2f} | 산도: {ta:.4f}% | pH: {eph:.1f} | 원가: {tcost:,.0f}원/kg</div>
<table><tr><th>구분</th><th>성분</th><th>배합비(%)</th><th>당기여도</th><th>산기여도</th><th>감미기여도</th><th>제품단가</th><th>배합량(g)</th></tr>
{rows}
<tr style="font-weight:bold;background:#f5f5f5"><td colspan=2>합계</td><td>100%</td><td>{tb:.2f}</td><td>{ta:.4f}</td><td></td><td>{tcost:,.0f}</td><td>{vol}</td></tr>
</table>
<h2 style="font-size:14px;margin-top:15px;">💰 원가계산서</h2>
<table><tr><th>항목</th><th>금액(원/병)</th></tr>
<tr><td>원재료비</td><td>{rc:,.0f}</td></tr><tr><td>포장재비</td><td>{pk:,.0f}</td></tr>
<tr><td>제조경비</td><td>{mf:,.0f}</td></tr>
<tr style="font-weight:bold;background:#fff3e0"><td>★ 제조원가</td><td>{tot:,.0f}</td></tr>
<tr><td>소비자가</td><td>{sp:,.0f}</td></tr><tr><td>원가율</td><td>{tot/sp*100:.1f}%</td></tr></table>
<p style="text-align:center;color:#888;margin-top:15px;font-size:10px">© FoodWell R&D | Gemini AI + OpenAI DALL-E</p>
</body></html>"""

# ============================================================
# PAGE: 대시보드
# ============================================================
if page == "🏠 대시보드":
    st.title("🥤 음료개발 데이터베이스 v3")
    c1,c2,c3=st.columns(3)
    c1.metric("🧬 등록원료",f"{len(data['원료DB'])}종")
    c2.metric("📏 규격유형",f"{len(data['음료규격기준'])}종")
    c3.metric("📖 가이드배합",f"{len(data['가이드배합비'])}건")
    col1,col2=st.columns(2)
    with col1:
        st.markdown("""
**v3 주요기능**
- 🤖 Gemini AI 배합비 추천 (20년차 연구원 페르소나)
- 📐 pKa기반 pH·산도 정밀계산 (31종 보정)
- 📊 실시간 Brix/pH/산도/감미도 변화 추적
- 🎨 OpenAI DALL-E 제품이미지 생성
- 📥 엑셀 + HTML 출력
- 🔧 원료명 유추 엔진 (DB외 원료 자동추정)
        """)
    with col2:
        st.subheader("원료 대분류 분포")
        st.bar_chart(data['원료DB']['원료대분류'].value_counts())

# ============================================================
# PAGE: 배합시뮬레이터
# ============================================================
elif page == "🧪 배합시뮬레이터":
    st.title("🧪 배합비 시뮬레이터")
    df_raw=data['원료DB']; df_std=data['음료규격기준']; df_gd=data['가이드배합비']
    bev_types=df_std['음료유형'].dropna().tolist()

    # ── 제품정보 + 유형 + 품질목표 (1줄로 컴팩트) ──
    r1=st.columns([2,1,2,1.5,1])
    pname=r1[0].text_input("제품명",key="product_name")
    vol=r1[1].number_input("용량(ml)",key="volume",step=50)
    bt=r1[2].selectbox("음료유형",bev_types,key="bev_type_idx")
    flavors=["사과","딸기","포도","오렌지","복숭아","망고","레몬","자몽","블루베리","감귤","유자","키위"]
    fl=r1[3].selectbox("맛",flavors,key="flavor_idx")
    cfl=r1[4].text_input("직접입력",key="custom_flavor")
    eff_fl=cfl if cfl else fl

    # 규격기준 한줄 표시
    std=get_std(bt,df_std)
    if std is not None:
        vals=[f"**당도**:{std.get('당도(Brix,°)','—') if pd.notna(std.get('당도(Brix,°)')) else '—'}",
              f"**pH**:{std.get('pH 범위','—') if pd.notna(std.get('pH 범위')) else '—'}",
              f"**산도**:{std.get('산도(%)','—') if pd.notna(std.get('산도(%)')) else '—'}",
              f"**과즙**:{std.get('과즙함량(%)','—') if pd.notna(std.get('과즙함량(%)')) else '—'}"]
        st.markdown(f"📏 **규격**: {' | '.join(vals)}")

    # 품질목표 (빨간 라인 스타일 — 엑셀처럼)
    st.markdown("<div style='background:#FFE0E0;padding:6px 12px;border-radius:4px;border-left:4px solid red;display:flex;gap:20px;align-items:center;'>", unsafe_allow_html=True)
    qc=st.columns([1,1,1,1])
    t_brix=qc[0].number_input("🎯목표Brix",key="target_brix",step=0.5)
    t_acid=qc[1].number_input("🎯목표산도(%)",key="target_acid",step=0.05,format="%.3f")
    t_sweet=qc[2].text_input("🎯목표감미도",key="target_sweet")
    t_cost=qc[3].number_input("🎯목표단가(원/kg)",key="target_cost",step=100)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── AI 배합비 추천 ──
    with st.expander("🤖 AI 배합비 추천 (Gemini)", expanded=False):
        ac1,ac2=st.columns([3,7])
        extra=ac1.text_area("추가요청",placeholder="비타민C강화, 저칼로리...",height=60,key="extra_req")
        ac2.markdown("<div style='background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:8px 12px;border-radius:6px;font-size:12px;'><b>🧑‍🔬</b> 경력20년 · 관능전문 · 혼합/기능성 · 174종원료 · 식품공전준수</div>",unsafe_allow_html=True)
        gc1,gc2=st.columns(2)
        if gc1.button("🚀 AI 배합비 생성",type="primary",use_container_width=True):
            if not gemini_key: st.error("❌ Gemini API Key 필요")
            else:
                with st.spinner("🧑‍🔬 설계중..."):
                    raw_ctx=build_raw_context(df_raw)
                    prompt=build_rec_prompt(bt,eff_fl,std,t_brix,t_acid,t_cost,raw_ctx,extra)
                    resp,err=call_gemini(gemini_key,prompt)
                    if err: st.error(f"❌ {err}")
                    else:
                        rec,pe=parse_json(resp)
                        if pe: st.error(pe); st.code(resp)
                        else:
                            ok,warns=validate_rec(rec,df_raw)
                            ad={}
                            for it in ok: ad[it['slot']]={'AI원료':it['name'],'AI%':it['pct'],'reason':it.get('reason','')}
                            st.session_state['ai_recommendation']=ad
                            st.session_state['ai_meta']={
                                'concept':rec.get('design_concept',''),'sensory':rec.get('sensory_note',''),
                                'tips':rec.get('tips',''),'eb':rec.get('expected_brix',0),
                                'ea':rec.get('expected_acidity',0),'ep':rec.get('expected_ph',0),
                                'ec':rec.get('expected_cost_per_kg',0)}
                            for w in warns: st.warning(w)
                            st.success(f"✅ {len(ok)}종 추천완료!"); st.rerun()
        if gc2.button("🗑️ AI초기화",use_container_width=True):
            st.session_state['ai_recommendation']={}; st.session_state['ai_meta']={}; st.rerun()

        if st.session_state.get('ai_meta'):
            m=st.session_state['ai_meta']
            mc=st.columns(4)
            mc[0].metric("Bx",f"{m.get('eb',0):.1f}"); mc[1].metric("산도",f"{m.get('ea',0):.3f}%")
            mc[2].metric("pH",f"{m.get('ep',0):.1f}"); mc[3].metric("원가",f"{m.get('ec',0):,.0f}")
            st.caption(f"💡 {m.get('concept','')} | 👅 {m.get('sensory','')} | 🔧 {m.get('tips','')}")

    # ── 배합표 (엑셀 양식 기반) ──
    st.markdown("### 📋 배합표")
    raw_names=[""] + df_raw['원료명'].dropna().tolist()
    CUSTOM_TAG = "✏️ 직접입력"
    raw_names_with_custom = ["", CUSTOM_TAG] + df_raw['원료명'].dropna().tolist()

    categories=[("원재료",4),("당류",3),("호료/안정제",5),("부재료/기타",6)]
    ai_dict=st.session_state.get('ai_recommendation',{})
    guide_matches = df_gd[df_gd['key'].str.startswith(f"{bt}_{eff_fl}_", na=False)]
    case_dict={}
    for _,r in guide_matches.iterrows():
        s=int(r['slot']); cn=str(r['사례원료명']) if pd.notna(r['사례원료명']) else ''; cp=sf(r['사례배합비(%)'])
        if cn=='0': cn=''
        case_dict[s]={'n':cn,'p':cp}

    ingredients=[]; slot_num=0

    # 테이블 헤더
    hc=st.columns([0.3,2.5,0.8,2,0.7,2,0.7])
    for i,t in enumerate(["#","성분","배합비(%)","🟣AI추천","AI%","🟢사례","사례%"]):
        c="#7B68EE" if i in(3,4) else("#2E8B57" if i in(5,6) else "#444")
        hc[i].markdown(f"<div style='font-size:10px;font-weight:bold;color:{c};text-align:center;background:#f0f0f0;padding:3px;border-radius:3px;'>{t}</div>",unsafe_allow_html=True)

    for cat_name, num_rows in categories:
        st.markdown(f"<div style='background:#e8eaf6;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:bold;margin:4px 0;'>📌 {cat_name}</div>",unsafe_allow_html=True)
        for i in range(num_rows):
            slot_num+=1
            ai=ai_dict.get(slot_num,{}); cs=case_dict.get(slot_num,{})
            cols=st.columns([0.3,2.5,0.8,2,0.7,2,0.7])
            cols[0].markdown(f"<div style='padding-top:26px;text-align:center;color:#999;font-size:11px;'>{slot_num}</div>",unsafe_allow_html=True)

            # 원료 선택 (selectbox + 직접입력 옵션)
            sel_val = cols[1].selectbox("원료",raw_names_with_custom,key=f"raw_{slot_num}",label_visibility="collapsed")
            actual_name = sel_val
            # 직접입력 선택시 text_input 표시
            if sel_val == CUSTOM_TAG:
                actual_name = cols[1].text_input("원료명입력",key=f"custom_{slot_num}",label_visibility="collapsed",placeholder="원료명 직접입력")

            pct=cols[2].number_input("%",value=0.0,min_value=0.0,max_value=100.0,step=0.1,format="%.3f",key=f"pct_{slot_num}",label_visibility="collapsed")

            # AI추천 표시
            at=ai.get('AI원료',''); ap=ai.get('AI%','')
            bg1="#F3E8FF" if at else "#fafafa"
            cols[3].markdown(f"<div style='font-size:10px;color:#7B68EE;background:{bg1};padding:4px;border-radius:3px;min-height:30px;padding-top:8px;'>{'🟣'+at if at else ''}</div>",unsafe_allow_html=True)
            cols[4].markdown(f"<div style='font-size:10px;color:#7B68EE;text-align:center;background:{bg1};padding:4px;border-radius:3px;min-height:30px;padding-top:8px;'>{str(ap)+'%' if ap else ''}</div>",unsafe_allow_html=True)
            # 사례
            cn=cs.get('n',''); cp=cs.get('p',0)
            bg2="#E8FFE8" if cn else "#fafafa"
            cols[5].markdown(f"<div style='font-size:10px;color:#2E8B57;background:{bg2};padding:4px;border-radius:3px;min-height:30px;padding-top:8px;'>{'🟢'+cn if cn else ''}</div>",unsafe_allow_html=True)
            cols[6].markdown(f"<div style='font-size:10px;color:#2E8B57;text-align:center;background:{bg2};padding:4px;border-radius:3px;min-height:30px;padding-top:8px;'>{str(cp)+'%' if cp and cp>0 else ''}</div>",unsafe_allow_html=True)

            if actual_name and actual_name != CUSTOM_TAG and pct>0:
                mat=get_raw(actual_name,df_raw)
                bx=matv(mat,'Brix(°)'); ac=matv(mat,'산도(%)'); sw=matv(mat,'감미도(설탕대비)'); pr=matv(mat,'예상단가(원/kg)')
                extra_ph=None
                if mat is None:
                    inf=infer_from_name(actual_name)
                    if inf:
                        bx=inf.get('brix',bx); ac=inf.get('acidity',ac); sw=inf.get('sweetness',sw)
                        extra_ph=inf.get('ph',None)
                        st.caption(f"  ↳ 🔧유추: Bx={bx}, 산도={ac}%, 감미={sw}")
                ingredients.append({'slot':slot_num,'구분':cat_name,'원료명':actual_name,'배합비(%)':pct,
                    'Brix':bx,'산도':ac,'감미도':sw,'단가':pr,'_ph':extra_ph})

    # 정제수
    total_pct=sum(i['배합비(%)'] for i in ingredients)
    water=100.0-total_pct
    if water>0:
        ingredients.append({'slot':99,'구분':'정제수','원료명':'정제수','배합비(%)':water,'Brix':0,'산도':0,'감미도':0,'단가':2,'_ph':7.0})

    # ── 합계 & 실시간 판정 ──
    if ingredients:
        tb=sum(i['배합비(%)']/100*i['Brix'] for i in ingredients)
        ta=sum(i['배합비(%)']/100*i['산도'] for i in ingredients)
        ts=sum(i['배합비(%)']/100*i['감미도'] for i in ingredients)
        tc=sum(i['배합비(%)']/100*i['단가'] for i in ingredients)
        eph=estimate_ph(ingredients,df_raw)
        tpct=sum(i['배합비(%)'] for i in ingredients)

        # 엑셀 스타일 결과 테이블
        st.markdown("<div style='background:#e8eaf6;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:bold;margin:4px 0;'>📊 시뮬레이션 결과</div>",unsafe_allow_html=True)
        df_res=pd.DataFrame(ingredients)
        df_res['당기여도']=df_res['배합비(%)']/100*df_res['Brix']
        df_res['산기여도']=df_res['배합비(%)']/100*df_res['산도']
        df_res['감미기여도']=df_res['배합비(%)']/100*df_res['감미도']
        df_res['제품단가']=df_res['단가']*df_res['배합비(%)']/100
        df_res['배합량(g)']=df_res['배합비(%)']*vol/100
        dcols=['구분','원료명','배합비(%)','당기여도','산기여도','감미기여도','제품단가','배합량(g)']
        st.dataframe(df_res[dcols].style.format({'배합비(%)':'{:.3f}','당기여도':'{:.2f}','산기여도':'{:.4f}','감미기여도':'{:.2f}','제품단가':'{:,.0f}','배합량(g)':'{:.1f}'}),use_container_width=True,hide_index=True,height=250)

        # 합계 & 규격판정 (한줄)
        st.markdown(f"""<div style='display:flex;gap:8px;flex-wrap:wrap;margin:8px 0;'>
<div style='background:#e3f2fd;padding:6px 10px;border-radius:4px;font-size:12px;'><b>합계</b> {tpct:.1f}% {'✅' if abs(tpct-100)<0.1 else '⚠️'}</div>
<div style='background:#fff8e1;padding:6px 10px;border-radius:4px;font-size:12px;'><b>Brix</b> {tb:.2f} {'✅' if std is not None and sf(std.get('Brix_min'))<=tb<=sf(std.get('Brix_max')) and sf(std.get('Brix_max'))>0 else '⚠️'}</div>
<div style='background:#fff8e1;padding:6px 10px;border-radius:4px;font-size:12px;'><b>산도</b> {ta:.4f}%</div>
<div style='background:#e8f5e9;padding:6px 10px;border-radius:4px;font-size:12px;'><b>pH</b> {eph:.2f}</div>
<div style='background:#fff8e1;padding:6px 10px;border-radius:4px;font-size:12px;'><b>감미도</b> {ts:.2f}</div>
<div style='background:#fce4ec;padding:6px 10px;border-radius:4px;font-size:12px;'><b>원가</b> {tc:,.0f}원/kg {'✅' if tc<=t_cost else '⚠️'}</div>
<div style='background:#e3f2fd;padding:6px 10px;border-radius:4px;font-size:12px;'><b>정제수</b> {water:.1f}%</div>
<div style='background:#e3f2fd;padding:6px 10px;border-radius:4px;font-size:12px;'><b>원재료함량</b> {sum(i["배합비(%)"] for i in ingredients if i["slot"]<=4):.1f}%</div>
</div>""",unsafe_allow_html=True)

        # session 저장
        st.session_state['ingredients']=ingredients
        st.session_state['total_cost']=tc
        st.session_state['est_ph']=eph

        # ── 내보내기 & 이미지 생성 ──
        st.markdown("---")
        ex1,ex2,ex3=st.columns(3)
        try:
            xlsx=export_excel(ingredients,vol,pname,tc,st.session_state['pack_vals'],st.session_state['mfg_vals'],st.session_state['selling_price'])
            ex1.download_button("📥 엑셀",xlsx,file_name=f"{pname}_배합표.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
        except Exception as e: ex1.caption(f"엑셀실패(openpyxl필요)")
        html=export_html(ingredients,vol,pname,tc,eph,st.session_state['pack_vals'],st.session_state['mfg_vals'],st.session_state['selling_price'])
        ex2.download_button("📥 인쇄HTML",html.encode(),file_name=f"{pname}_배합표.html",mime="text/html",use_container_width=True)

        # 🎨 제품 이미지
        with ex3:
            if st.button("🎨 제품이미지 생성",use_container_width=True):
                if not openai_key: st.error("❌ OpenAI API Key 필요")
                else:
                    main_ings=[i['원료명'] for i in ingredients if i['slot']<=4 and i['원료명']!='정제수']
                    color_map={'사과':'golden amber','딸기':'pink red','포도':'deep purple','오렌지':'bright orange',
                        '복숭아':'peach','망고':'yellow-orange','레몬':'pale yellow','자몽':'pink','블루베리':'dark purple'}
                    clr=color_map.get(eff_fl,'light golden')
                    img_prompt=f"""Professional product photography of a Korean beverage called "{pname}".
Clear PET bottle, {vol}ml, containing {bt} with {eff_fl} flavor.
Liquid color: {clr}, translucent. Fresh {eff_fl} fruits as decoration props.
Clean modern Korean label with "{pname}" text.
Studio lighting, white background, slight reflection, premium commercial quality, 4K, photorealistic."""
                    with st.spinner("🎨 DALL-E 생성중..."):
                        img,ierr=call_dalle(openai_key,img_prompt)
                        if ierr: st.error(f"❌ {ierr}")
                        elif img:
                            st.session_state['product_image']=img
                            st.rerun()

        if st.session_state.get('product_image'):
            st.image(st.session_state['product_image'],caption=f"🎨 {pname} AI제품이미지",use_container_width=True)
            st.download_button("📥 이미지저장",st.session_state['product_image'],file_name=f"{pname}_제품이미지.png",mime="image/png")

# ============================================================
# PAGE: 원가계산서
# ============================================================
elif page == "💰 원가계산서":
    st.title("💰 원가계산서")
    ings=st.session_state.get('ingredients',[])
    vol=st.session_state.get('volume',1000)
    pname=st.session_state.get('product_name','')
    if not ings: st.warning("⚠️ 배합시뮬레이터 먼저 입력"); st.stop()
    st.caption(f"제품: {pname} | {vol}ml")

    st.markdown("##### ① 원재료비")
    rows=[]
    for i in ings:
        up=sf(i.get('단가'));pct=sf(i.get('배합비(%)'))
        rows.append({'항목':i['원료명'],'배합비':f"{pct:.2f}%",'단가':f"{up:,.0f}",'원/병':f"{up*pct/100*vol/1000:,.1f}"})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=200)
    rk=sum(sf(i.get('단가'))*sf(i.get('배합비(%)'))/100 for i in ings)
    rb=rk*vol/1000
    st.metric("원재료비(원/병)",f"{rb:,.0f}")

    c1,c2=st.columns(2)
    with c1:
        st.markdown("##### ② 포장재비")
        pk_l=["PET용기","PE캡","라벨","박스","빨대","쉬링크"]
        pk_d=st.session_state.get('pack_vals',[45,8,12,50,0,5])
        pv=[]
        for idx in range(6):
            v=st.number_input(pk_l[idx],value=pk_d[idx],key=f"pk_{idx}",label_visibility="visible")
            pv.append(v)
        st.session_state['pack_vals']=pv
        st.metric("포장재비",f"{sum(pv):,.0f}원/병")
    with c2:
        st.markdown("##### ③ 제조경비")
        mf_l=["인건비","전력/용수","CIP/검사/감가"]
        mf_d=st.session_state.get('mfg_vals',[20,18,22])
        mv=[]
        for idx in range(3):
            v=st.number_input(mf_l[idx],value=mf_d[idx],key=f"mf_{idx}")
            mv.append(v)
        st.session_state['mfg_vals']=mv
        st.metric("제조경비",f"{sum(mv):,.0f}원/병")

    st.markdown("---")
    tot=rb+sum(pv)+sum(mv)
    tc=st.columns(4)
    tc[0].metric("원재료비",f"{rb:,.0f}원"); tc[1].metric("포장재비",f"{sum(pv):,.0f}원")
    tc[2].metric("제조경비",f"{sum(mv):,.0f}원"); tc[3].metric("★ 제조원가",f"{tot:,.0f}원/병")
    sp=st.number_input("소비자가(원)",value=st.session_state.get('selling_price',1500),step=100,key="sp_i")
    st.session_state['selling_price']=sp
    if sp>0: st.metric("원가율",f"{tot/sp*100:.1f}%",delta="양호" if tot/sp<0.4 else "높음")

    ec1,ec2=st.columns(2)
    try:
        xl=export_excel(ings,vol,pname,st.session_state.get('total_cost',0),pv,mv,sp)
        ec1.download_button("📥 엑셀",xl,file_name=f"{pname}_원가.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
    except: pass
    ht=export_html(ings,vol,pname,st.session_state.get('total_cost',0),st.session_state.get('est_ph',3.5),pv,mv,sp)
    ec2.download_button("📥 인쇄HTML",ht.encode(),file_name=f"{pname}_원가.html",mime="text/html",use_container_width=True)

# ============================================================
# PAGE: 원료DB
# ============================================================
elif page == "🧬 원료DB":
    st.title("🧬 원료DB")
    df=data['원료DB']
    c1,c2,c3=st.columns([1,1,2])
    cf=c1.multiselect("대분류",df['원료대분류'].dropna().unique().tolist())
    sf2=c2.multiselect("소분류",df['원료소분류'].dropna().unique().tolist())
    sr=c3.text_input("🔍 검색",key="rs")
    if cf: df=df[df['원료대분류'].isin(cf)]
    if sf2: df=df[df['원료소분류'].isin(sf2)]
    if sr: df=df[df['원료명'].str.contains(sr,case=False,na=False)]
    st.dataframe(df,use_container_width=True,hide_index=True,height=450)
    st.caption(f"{len(df)}종")
    if len(df)>0:
        sel=st.selectbox("상세조회",df['원료명'].tolist())
        if sel:
            d=df[df['원료명']==sel].iloc[0]
            dc=st.columns(6)
            dc[0].metric("Brix",sf(d.get('Brix(°)'))); dc[1].metric("pH",sf(d.get('pH')))
            dc[2].metric("산도(%)",sf(d.get('산도(%)'))); dc[3].metric("1%pH",sf(d.get('1%당pH(1%용액)')))
            dc[4].metric("감미도",sf(d.get('감미도(설탕대비)'))); dc[5].metric("단가",f"{sf(d.get('예상단가(원/kg)')):,.0f}")

# ============================================================
# PAGE: 음료규격기준
# ============================================================
elif page == "📏 음료규격기준":
    st.title("📏 음료규격기준")
    df=data['음료규격기준']
    hide=['Brix_min','Brix_max','pH_min','pH_max','산도_min','산도_max']
    st.dataframe(df[[c for c in df.columns if c not in hide]],use_container_width=True,hide_index=True)

# ============================================================
# PAGE: 가이드배합비DB
# ============================================================
elif page == "📖 가이드배합비DB":
    st.title("📖 가이드배합비DB")
    df=data['가이드배합비']
    if len(df)>0:
        combos=sorted(df['combo'].dropna().unique().tolist())
        sel=st.selectbox("조합",combos)
        if sel:
            ft=df[df['combo']==sel]
            c1,c2=st.columns(2)
            with c1:
                st.markdown("#### 🟣 AI추천")
                for _,r in ft.iterrows():
                    n=r['AI원료명'];p=sf(r['AI배합비(%)'])
                    if n and str(n) not in('0','nan','') and p>0: st.markdown(f"• **{n}**: {p}%")
            with c2:
                st.markdown("#### 🟢 사례")
                for _,r in ft.iterrows():
                    n=r['사례원료명'];p=sf(r['사례배합비(%)'])
                    if n and str(n) not in('0','nan','') and p>0: st.markdown(f"• **{n}**: {p}%")
            st.dataframe(ft,use_container_width=True,hide_index=True)
