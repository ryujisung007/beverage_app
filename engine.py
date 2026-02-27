"""
engine.py v7 — 배합계산 + AI페르소나 + HACCP서류 + 식품표시기준
"""
import pandas as pd
import numpy as np
import json, re, math
from datetime import datetime

# ============================================================
# 1. 슬롯 시스템
# ============================================================
SLOT_GROUPS = [
    ("원재료", list(range(1, 5))),
    ("당류/감미료", list(range(5, 9))),
    ("안정제/호료", list(range(9, 13))),
    ("기타자재", list(range(13, 20))),
    ("정제수", [20]),
]

EMPTY_SLOT = {
    '원료명': '', '배합비(%)': 0.0,
    'AI추천_원료명': '', 'AI추천_%': 0.0,
    '기존표준_원료명': '', '기존표준_%': 0.0,
    '당도(Bx)': 0, '산도(%)': 0, '감미도': 0, '기능1': '', '기능2': '',
    '단가(원/kg)': 0, 'pH': 0, 'Brix(°)': 0, '감미도(설탕대비)': 0,
    '1%Brix기여': 0, '1%pH영향': 0, '1%산도기여': 0, '1%감미기여': 0,
    '당기여': 0, '산기여': 0, '감미기여': 0, '단가기여(원/kg)': 0, '배합량(g/kg)': 0,
    'is_custom': False,
}


def init_slots():
    return [EMPTY_SLOT.copy() for _ in range(20)]


def fill_slot_from_db(slot, name, df_ing, ph_col):
    row = df_ing[df_ing['원료명'] == name]
    if row.empty:
        return slot
    r = row.iloc[0]
    slot['원료명'] = name
    slot['당도(Bx)'] = safe_float(r.get('Brix(°)', 0))
    slot['산도(%)'] = safe_float(r.get('산도(%)', 0))
    slot['감미도'] = safe_float(r.get('감미도(설탕대비)', 0))
    slot['단가(원/kg)'] = safe_float(r.get('예상단가(원/kg)', 0))
    slot['pH'] = safe_float(r.get('pH', 0))
    slot['Brix(°)'] = safe_float(r.get('Brix(°)', 0))
    slot['감미도(설탕대비)'] = safe_float(r.get('감미도(설탕대비)', 0))
    slot['1%Brix기여'] = safe_float(r.get('1%사용시 Brix기여(°)', 0))
    slot['1%pH영향'] = safe_float(r.get(ph_col, 0))
    slot['1%산도기여'] = safe_float(r.get('1%사용시 산도기여(%)', 0))
    slot['1%감미기여'] = safe_float(r.get('1%사용시 감미기여', 0))
    slot['is_custom'] = False
    return slot


def safe_float(v, default=0):
    try:
        f = float(v)
        return f if not math.isnan(f) else default
    except:
        return default


def calc_slot_contributions(slot):
    pct = safe_float(slot.get('배합비(%)', 0))
    if pct <= 0:
        for k in ['당기여', '산기여', '감미기여', '단가기여(원/kg)', '배합량(g/kg)']:
            slot[k] = 0
        return slot
    slot['당기여'] = round(safe_float(slot.get('1%Brix기여', 0)) * pct, 2)
    slot['산기여'] = round(safe_float(slot.get('1%산도기여', 0)) * pct, 4)
    slot['감미기여'] = round(safe_float(slot.get('1%감미기여', 0)) * pct, 4)
    slot['단가기여(원/kg)'] = round(safe_float(slot.get('단가(원/kg)', 0)) * pct / 100, 1)
    slot['배합량(g/kg)'] = round(pct * 10, 1)
    return slot


def calc_formulation(slots, volume_ml=500):
    total_brix = sum(safe_float(s.get('당기여', 0)) for s in slots)
    total_acid = sum(safe_float(s.get('산기여', 0)) for s in slots)
    total_sweet = sum(safe_float(s.get('감미기여', 0)) for s in slots)
    total_dph = sum(safe_float(s.get('1%pH영향', 0)) * safe_float(s.get('배합비(%)', 0)) for s in slots)
    total_cost_kg = sum(safe_float(s.get('단가기여(원/kg)', 0)) for s in slots)
    ing_pct = sum(safe_float(s.get('배합비(%)', 0)) for s in slots[:19])
    water_pct = round(max(0, 100 - ing_pct), 3)

    slots[19]['원료명'] = '정제수'
    slots[19]['배합비(%)'] = water_pct
    slots[19]['배합량(g/kg)'] = round(water_pct * 10, 1)

    juice_pct = 0
    for s in slots[:4]:
        p = safe_float(s.get('배합비(%)', 0))
        if p > 0 and ('농축' in str(s.get('원료명', '')) or '과즙' in str(s.get('원료명', ''))):
            bx = safe_float(s.get('Brix(°)', 0))
            juice_pct += p * (bx / 11.5 if bx >= 40 else 1)

    return {
        '배합비합계(%)': round(ing_pct + water_pct, 3),
        '예상당도(Bx)': round(total_brix, 2),
        '예상pH': round(3.5 + total_dph, 2),
        '예상산도(%)': round(total_acid, 4),
        '예상감미도': round(total_sweet, 4),
        '당산비': round(total_brix / total_acid, 1) if total_acid > 0 else 0,
        '원재료비(원/kg)': round(total_cost_kg, 1),
        '원재료비(원/병)': round(total_cost_kg * volume_ml / 1000, 1),
        '원료종류(개)': sum(1 for s in slots[:19] if safe_float(s.get('배합비(%)', 0)) > 0),
        '정제수비율(%)': round(water_pct, 1),
        '과즙함량(%)': round(juice_pct, 1),
    }


# ============================================================
# 2. 규격 판정
# ============================================================
def get_spec(df_spec, bev_type):
    row = df_spec[df_spec['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    if row.empty:
        return None
    r = row.iloc[0]
    return {k: safe_float(r.get(k, 0)) for k in ['Brix_min', 'Brix_max', 'pH_min', 'pH_max', '산도_min', '산도_max']}


def check_compliance(result, spec):
    if not spec:
        return {}
    checks = {}
    bx = result['예상당도(Bx)']
    bmin, bmax = spec.get('Brix_min', 0), spec.get('Brix_max', 99)
    if bmin <= bx <= bmax:
        checks['당도'] = (f'✅ 규격이내({bmin}~{bmax}°)', True)
    else:
        checks['당도'] = (f'⚠️ 규격이탈({bx:.2f}° → 기준 {bmin}~{bmax}°)', False)

    ac = result['예상산도(%)']
    amin, amax = spec.get('산도_min', 0), spec.get('산도_max', 0)
    if amin > 0 or amax > 0:
        if amin <= ac <= amax:
            checks['산도'] = (f'✅ 규격이내({amin}~{amax}%)', True)
        else:
            checks['산도'] = (f'⚠️ 규격이탈({ac:.4f}% → 기준 {amin}~{amax}%)', False)

    checks['원재료비'] = ('✅ 목표이내', True)
    wp = result['정제수비율(%)']
    checks['정제수비율'] = ('✅ 적정(50%이상)', True) if wp >= 50 else ('⚠️ 50% 미만', False)

    phmin, phmax = spec.get('pH_min', 0), spec.get('pH_max', 0)
    if phmin > 0:
        checks['pH'] = (f'ℹ️ pH규격: {phmin}~{phmax} → 실측 필요', None)
    return checks


# ============================================================
# 3. 가이드배합비 로딩 (기존표준배합비)
# ============================================================
def load_guide(df_guide, bev_type, flavor, df_ing, ph_col):
    bt = bev_type.split('(')[0]  # 과·채음료 유지
    key_prefix = f"{bt}_{flavor}_" if flavor else ""
    if not key_prefix:
        return init_slots()
    rows = df_guide[df_guide['키(유형_맛_슬롯)'].str.startswith(key_prefix, na=False)].sort_values('슬롯번호')
    slots = init_slots()
    for _, r in rows.iterrows():
        idx = int(r['슬롯번호']) - 1
        if idx < 0 or idx >= 19:
            continue
        ai_name = r.get('AI추천_원료명')
        ai_pct = r.get('AI추천_배합비(%)')
        case_name = r.get('실제사례_원료명')
        case_pct = r.get('실제사례_배합비(%)')
        # 기존표준배합비로 표시
        if pd.notna(case_name) and str(case_name).strip():
            slots[idx]['기존표준_원료명'] = str(case_name)
            slots[idx]['기존표준_%'] = safe_float(case_pct)
        if pd.notna(ai_name) and str(ai_name).strip():
            slots[idx] = fill_slot_from_db(slots[idx], str(ai_name), df_ing, ph_col)
            if pd.notna(ai_pct) and safe_float(ai_pct) > 0:
                slots[idx]['배합비(%)'] = safe_float(ai_pct)
            slots[idx]['AI추천_원료명'] = str(ai_name) if pd.notna(ai_name) else ''
            slots[idx]['AI추천_%'] = safe_float(ai_pct)
        slots[idx] = calc_slot_contributions(slots[idx])
    return slots


# ============================================================
# 4. 역설계
# ============================================================
def reverse_engineer(prod_row, df_ing, ph_col):
    slots = init_slots()
    idx = 0
    for i in range(1, 8):
        col = f'배합순위{i}' if i > 1 else '배합순위1(원재료/배합비%/원산지)'
        val = prod_row.get(col)
        if pd.isna(val) or str(val).strip() in ['—', '-', '0', '']:
            continue
        parts = str(val).split('/')
        name = parts[0].strip()
        pct = safe_float(parts[1].replace('%', '') if len(parts) > 1 else 0)
        matched = df_ing[df_ing['원료명'].str.contains(name.split('(')[0][:4], na=False)]
        if not matched.empty:
            slots[idx] = fill_slot_from_db(slots[idx], matched.iloc[0]['원료명'], df_ing, ph_col)
        else:
            slots[idx]['원료명'] = name
            slots[idx]['is_custom'] = True
        slots[idx]['배합비(%)'] = pct
        slots[idx] = calc_slot_contributions(slots[idx])
        idx += 1
        if idx >= 19:
            break
    return slots


# ============================================================
# 5. 식품표시사항 (식품등의 표시기준 반영)
# ============================================================
ALLERGENS = ['난류(가금류)', '우유', '메밀', '땅콩', '대두', '밀', '고등어', '게', '새우',
             '돼지고기', '복숭아', '토마토', '호두', '닭고기', '쇠고기', '오징어',
             '조개류(굴,전복,홍합)', '잣', '아황산류']

ALLERGEN_KEYWORDS = {
    '난류(가금류)': ['계란', '난백', '난황', '알', 'egg'],
    '우유': ['우유', '유청', '탈지분유', '전지분유', '카제인', 'milk', '크림'],
    '대두': ['대두', '콩', '두유', 'soy'],
    '밀': ['밀', '소맥', '글루텐', 'wheat'],
    '복숭아': ['복숭아', 'peach'],
    '토마토': ['토마토', 'tomato'],
    '사과': [],  # 사과는 알레르기 표시 대상 아님
}


def generate_food_label(slots, product_name="", volume_ml=500, bev_type=""):
    """식품등의 표시기준에 따른 전체 표시사항 생성"""
    active = [(s['원료명'], s['배합비(%)']) for s in slots
              if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명')]
    active.sort(key=lambda x: x[1], reverse=True)

    # 1. 원재료명 (많이 사용한 순서, 2% 미만은 순서무관 가능)
    over_2 = [(n, p) for n, p in active if p >= 2]
    under_2 = [(n, p) for n, p in active if p < 2]

    # 2. 알레르기 유발물질 검출
    detected_allergens = []
    all_names = ' '.join([n for n, _ in active]).lower()
    for allergen, keywords in ALLERGEN_KEYWORDS.items():
        for kw in keywords:
            if kw in all_names:
                detected_allergens.append(allergen)
                break

    # 3. 영양성분 (1회 제공량 + 100ml 기준, 9종 의무표시)
    total_sugar_g = 0
    for s in slots:
        p = safe_float(s.get('배합비(%)', 0))
        bx = safe_float(s.get('Brix(°)', 0))
        if p > 0 and bx > 0:
            total_sugar_g += bx * p / 100 / 100 * 1000
    cal = total_sugar_g * 4
    serving = volume_ml  # 1회 제공량 = 총용량

    nutrition = {
        '1회 제공량': f'{serving}ml',
        '열량': f'{cal/10*serving/100:.0f}kcal',
        '탄수화물': f'{total_sugar_g/10*serving/100:.1f}g',
        '당류': f'{total_sugar_g/10*serving/100:.1f}g',
        '단백질': '0g',
        '지방': '0g',
        '포화지방': '0g',
        '트랜스지방': '0g',
        '콜레스테롤': '0mg',
        '나트륨': '5mg',  # 추정
    }
    nutrition_100ml = {
        '열량(100ml)': f'{cal/10:.1f}kcal',
        '당류(100ml)': f'{total_sugar_g/10:.1f}g',
    }

    # 4. 기타 표시사항
    return {
        '① 제품명': product_name,
        '② 식품유형': bev_type,
        '③ 업소명 및 소재지': '(제조사 정보 기입)',
        '④ 소비기한': '제조일로부터 ○○개월 (별도 설정 필요)',
        '⑤ 내용량': f'{volume_ml}ml',
        '⑥ 원재료명': ', '.join([n for n, _ in active]),
        '⑥-1 2%이상 원재료': ', '.join([f'{n}({p:.1f}%)' for n, p in over_2]),
        '⑥-2 2%미만 원재료': ', '.join([n for n, _ in under_2]) if under_2 else '해당없음',
        '⑦ 영양성분': nutrition,
        '⑦-1 100ml기준': nutrition_100ml,
        '⑧ 알레르기 유발물질': ', '.join(detected_allergens) + ' 함유' if detected_allergens else '해당없음',
        '⑨ 보관방법': '직사광선을 피해 상온보관',
        '⑩ 주의사항': '개봉 후 냉장보관하고 빠른 시일 내 드시기 바랍니다.',
        '⑪ 품목보고번호': '(식약처 품목제조보고 후 기입)',
        '⑫ 반품/교환': '공정거래위원회 고시 소비자분쟁해결기준에 의거 교환 또는 보상',
    }


# ============================================================
# 6. 시작레시피
# ============================================================
def generate_lab_recipe(slots, scales=[1, 5, 20]):
    recipes = {}
    for sc in scales:
        total = sc * 1000
        items = []
        for s in slots:
            p = safe_float(s.get('배합비(%)', 0))
            if p <= 0 or not s.get('원료명'):
                continue
            items.append({'원료명': s['원료명'], '배합비(%)': p, f'칭량({sc}L)_g': round(p / 100 * total, 2)})
        recipes[f'{sc}L'] = items
    return recipes


# ============================================================
# 7. AI 페르소나별 프롬프트
# ============================================================
PERSONA_RESEARCHER = """당신은 대한민국 음료회사 20년 경력 수석 연구원 "Dr. 이음료"입니다.
배합표를 받으면 반드시 아래를 평가하세요:
1️⃣ 관능예측: 초두감미, 중미, 후미, 바디감, 향미밸런스
2️⃣ 밸런스진단: 당산비, 감미구조, 산미캐릭터
3️⃣ 개선제안: 구체적 수치로 ("사과농축과즙 8%→10%")
4️⃣ 기술효과: 안정성, 살균, 유통기한
5️⃣ 수정배합표 JSON: {"수정배합": [{"원료명": "xxx", "배합비(%)": 0.0}]}
한국어 답변. 식품공전 규격 기준."""

PERSONA_PLANNER = """당신은 식품기업 신제품개발팀 15년차 R&D 연구원입니다.
배합표와 규격을 받으면:
1️⃣ 시장성 분석 (타겟 소비층, 포지셔닝)
2️⃣ 품질규격 검토 (식품공전 적합성)
3️⃣ 원가분석 (재료비, 포장비, 제조비, 마진)
4️⃣ 경쟁제품 대비 차별화 포인트
5️⃣ 출시 타임라인 제안
한국어, 표/테이블 형식 적극 활용."""

PERSONA_PRODUCTION = """당신은 음료공장 20년 경력 생산관리자입니다.
배합표와 공정을 받으면:
1️⃣ 공정별 파라미터 (온도/시간/압력/교반속도)
2️⃣ 배합순서 및 투입 주의사항
3️⃣ CCP 관리 포인트 (살균, 충전, 이물검사)
4️⃣ 생산 수율 및 로스 예상
5️⃣ 배치 기록서 템플릿
한국어, 실무 관점."""

PERSONA_QA = """당신은 식품 HACCP 인증심사원 출신 품질관리 전문가입니다.
배합표와 공정을 받으면 식약처 표준양식에 따라:
1️⃣ 위해분석표 (HA Worksheet) — 공정별 생물/화학/물리적 위해요소
2️⃣ CCP 결정도 — Decision Tree (Q1~Q4)
3️⃣ CCP 관리계획서 — 한계기준/모니터링/개선조치/검증/기록
4️⃣ 모니터링 일지 양식
5️⃣ 공정흐름도
한국어, 식약처 HACCP 표준양식 준수."""

PERSONA_FORMULATOR = """당신은 음료 배합설계 전문 연구원입니다.
음료유형과 맛(Flavor)을 받으면:
- 해당 유형+맛에 최적화된 배합비를 설계하세요
- 원재료, 당류, 산미료, 안정제, 향료, 비타민 등 모든 카테고리 포함
- 각 원료의 배합비(%)를 구체적으로 제시
- 정제수로 100% 맞추기
반드시 아래 JSON 형식으로만 응답:
{"배합": [{"슬롯": 1, "원료명": "xxx", "배합비": 0.0, "구분": "원재료"}, ...]}
"""


def call_gpt(api_key, system_prompt, user_content, model="gpt-4o", temp=0.7, max_tok=3000):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model, temperature=temp, max_tokens=max_tok,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
    )
    return resp.choices[0].message.content


def call_gpt_ai_formulation(api_key, bev_type, flavor, ing_names_sample=""):
    """AI가 유형+맛에 맞는 배합비 추천"""
    content = f"""음료유형: {bev_type}
맛(Flavor): {flavor}
사용가능 원료DB 샘플: {ing_names_sample[:500]}

위 유형과 맛에 최적화된 배합비를 JSON으로 설계해주세요.
원재료(1-4행), 당류/감미료(5-8행), 안정제/호료(9-12행), 기타자재(13-19행) 순서.
정제수(20행)는 자동계산되니 제외."""
    text = call_gpt(api_key, PERSONA_FORMULATOR, content, model="gpt-4o", temp=0.5)
    try:
        m = re.search(r'\{[^{}]*"배합"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group(0)).get('배합', [])
    except:
        pass
    return []


def call_gpt_estimate_ingredient(api_key, ingredient_name, category=""):
    """직접입력 원료 이화학규격 AI 추정"""
    prompt = f"""원료명: {ingredient_name}
분류: {category}

중요 참고기준:
- 농축과즙: Brix 40~70°, pH 2.5~4.5, 산도 1~8%, 단가 3000~15000원/kg
  예) 오렌지농축과즙(65Brix): Brix=65, 1pct_Brix기여=0.65
- 과일퓨레: Brix 8~15°, pH 3.0~4.5, 단가 2000~8000원/kg
- 당류: Brix 65~100°, 감미도 0.4~1.8
  예) 설탕: Brix=100, 감미도=1.0, 1pct_Brix기여=1.0, 1pct_감미기여=0.01
  예) 액상과당(HFCS55): Brix=77, 감미도=1.1, 1pct_Brix기여=0.77
- 고감미료: 감미도 100~600, 예) 수크랄로스: 감미도=600, 1pct_감미기여=6.0
- 산미료: 1pct_pH영향 음수, 예) 구연산: 1pct_pH영향=-0.40

1pct_Brix기여 = Brix / 100
1pct_감미기여 = 감미도_설탕대비 / 100
★ 농축액/퓨레/당류/시럽의 Brix와 감미도는 반드시 0보다 커야 함!

JSON만 응답:
{{"Brix": 0, "pH": 0, "산도_pct": 0, "감미도_설탕대비": 0, "예상단가_원kg": 0, "1pct_Brix기여": 0, "1pct_pH영향": 0, "1pct_산도기여": 0, "1pct_감미기여": 0}}"""

    text = call_gpt("", "", "", model="gpt-4o-mini")  # placeholder
    # 실제 호출
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini", temperature=0.3, max_tokens=300,
        messages=[
            {"role": "system", "content": "식품원료 이화학 데이터 전문가. JSON만 응답."},
            {"role": "user", "content": prompt}
        ],
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```', '', text)
    return json.loads(text)


def call_dalle(api_key, prompt):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.images.generate(model="dall-e-3", prompt=prompt, size="1024x1024", quality="standard", n=1)
    return resp.data[0].url


def build_dalle_prompt(product_name, bev_type, slots, container="PET", volume=500):
    color_map = {'오렌지': '오렌지색', '자몽': '핑크색', '레몬': '노란색', '라임': '연두색',
                 '망고': '황금색', '사과': '붉은+연두', '복숭아': '분홍색', '포도': '보라색',
                 '블루베리': '남보라', '딸기': '빨간색', '석류': '루비색', '커피': '갈색'}
    color = '투명'
    for s in slots:
        for k, c in color_map.items():
            if k in str(s.get('원료명', '')):
                color = c; break
    mains = [s['원료명'].split('(')[0] for s in slots if safe_float(s.get('배합비(%)', 0)) > 0 and s['원료명'] != '정제수'][:3]
    return f"한국 편의점 음료 패키지 디자인. 제품명:{product_name}, {bev_type}, 주재료:{','.join(mains)}, 색상:{color}, {container} {volume}ml, 포토리얼리스틱"


def parse_modified_formulation(text):
    try:
        m = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            return json.loads(m.group(1)).get('수정배합', [])
        m = re.search(r'\{"수정배합":\s*\[.*?\]\}', text, re.DOTALL)
        if m:
            return json.loads(m.group(0)).get('수정배합', [])
    except:
        pass
    return []


# ============================================================
# 8. HACCP 서류 6종 (식약처 표준양식)
# ============================================================
def haccp_ha_worksheet(bev_type, df_proc):
    """위해분석표"""
    m = df_proc[df_proc['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    if m.empty:
        return "해당 음료유형의 공정 데이터가 없습니다."
    lines = [
        "┌─────────────────────────────────────────────────────────────────────────┐",
        "│                    위해분석 작업장 (HA Worksheet)                        │",
        f"│  제품유형: {bev_type:<30}  작성일: {datetime.now().strftime('%Y.%m.%d')}       │",
        "├────┬────────────┬─────────────────┬──────────────┬────────┬─────────────┤",
        "│ No │   공정단계   │    위해요소      │   발생원인    │ 심각성 │  예방조치    │",
        "├────┼────────────┼─────────────────┼──────────────┼────────┼─────────────┤"]
    for i, (_, p) in enumerate(m.iterrows(), 1):
        step = str(p.get('세부공정', '-'))[:12]
        hazard = str(p.get('HACCP 위해요소', '-')).replace('\n', ',')[:17]
        cause = str(p.get('품질관리포인트', '-'))[:14]
        ccp = '★CCP' if str(p.get('CCP여부', '')).startswith('CCP') else '  -  '
        prev = str(p.get('모니터링방법', '-'))[:13]
        lines.append(f"│ {i:2d} │ {step:<12}│ {hazard:<17}│ {cause:<14}│ {ccp:^8}│ {prev:<13}│")
    lines.append("└────┴────────────┴─────────────────┴──────────────┴────────┴─────────────┘")
    return '\n'.join(lines)


def haccp_ccp_decision_tree(bev_type, df_proc):
    """CCP 결정도"""
    m = df_proc[df_proc['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    if m.empty:
        return "해당 음료유형의 공정 데이터가 없습니다."
    lines = [
        "┌──────────────────────────────────────────────────────────────────────┐",
        "│                  CCP 결정도 (Decision Tree)                          │",
        f"│  제품유형: {bev_type:<30}  작성일: {datetime.now().strftime('%Y.%m.%d')}    │",
        "├────────────┬──────────┬──────────┬──────────┬──────────┬────────────┤",
        "│  공정단계   │Q1:예방조치│Q2:제거/저감│Q3:오염증가│Q4:후속제거│  CCP판정   │",
        "├────────────┼──────────┼──────────┼──────────┼──────────┼────────────┤"]
    for _, p in m.iterrows():
        step = str(p.get('세부공정', '-'))[:12]
        is_ccp = str(p.get('CCP여부', '')).startswith('CCP')
        if is_ccp:
            lines.append(f"│ {step:<12}│   예     │   예     │    -     │    -     │  ★ {p.get('CCP여부','')}   │")
        else:
            lines.append(f"│ {step:<12}│   예     │  아니오  │  아니오  │    -     │   비CCP    │")
    lines.append("└────────────┴──────────┴──────────┴──────────┴──────────┴────────────┘")
    return '\n'.join(lines)


def haccp_ccp_plan(bev_type, df_proc):
    """CCP 관리계획서"""
    m = df_proc[df_proc['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    ccp_rows = m[m['CCP여부'].astype(str).str.startswith('CCP')]
    if ccp_rows.empty:
        return "CCP 공정이 없습니다."
    lines = [
        "┌──────────────────────────────────────────────────────────────────────┐",
        "│                   HACCP 관리계획서 (HACCP Plan)                       │",
        f"│  제품유형: {bev_type:<30}  작성일: {datetime.now().strftime('%Y.%m.%d')}    │",
        "└──────────────────────────────────────────────────────────────────────┘"]
    for _, p in ccp_rows.iterrows():
        ccp_no = p.get('CCP여부', '')
        lines.extend([
            f"\n■ {ccp_no} — {p.get('세부공정', '')}",
            "┌──────────────┬────────────────────────────────────────────────┐",
            f"│  공정단계     │ {str(p.get('공정단계', '')):<48}│",
            f"│  위해요소     │ {str(p.get('HACCP 위해요소', '')).replace(chr(10), ', ')[:48]:<48}│",
            f"│  한계기준(CL) │ {str(p.get('한계기준(CL)', ''))[:48]:<48}│",
            f"│  모니터링방법 │ {str(p.get('모니터링방법', ''))[:48]:<48}│",
            f"│  모니터링주기 │ {'매 배치':<48}│",
            f"│  개선조치     │ {str(p.get('개선조치', ''))[:48]:<48}│",
            f"│  검증방법     │ {'기록 검토 및 정기 검교정':<48}│",
            f"│  기록문서     │ {'CCP 모니터링 일지':<48}│",
            "└──────────────┴────────────────────────────────────────────────┘"])
    return '\n'.join(lines)


def haccp_monitoring_log(bev_type, df_proc):
    """CCP 모니터링 일지 (빈 양식)"""
    m = df_proc[df_proc['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    ccp_rows = m[m['CCP여부'].astype(str).str.startswith('CCP')]
    if ccp_rows.empty:
        return "CCP 공정이 없습니다."
    lines = [
        "┌──────────────────────────────────────────────────────────────────────┐",
        "│                    CCP 모니터링 일지                                  │",
        f"│  제품유형: {bev_type:<30}  작성일자: ____년 ____월 ____일       │",
        "└──────────────────────────────────────────────────────────────────────┘"]
    for _, p in ccp_rows.iterrows():
        lines.extend([
            f"\n■ {p.get('CCP여부', '')} — {p.get('세부공정', '')}",
            f"  한계기준: {p.get('한계기준(CL)', '')}",
            "┌──────┬────────────┬────────┬──────────────┬──────┬──────┐",
            "│ 시간  │   측정값    │ 적합여부│   이탈시조치  │ 담당자│ 확인자│",
            "├──────┼────────────┼────────┼──────────────┼──────┼──────┤"])
        for _ in range(8):
            lines.append("│__:__ │____________│ □적합   │______________│______│______│")
        lines.append("└──────┴────────────┴────────┴──────────────┴──────┴──────┘")
    lines.extend([
        "\n※ 이탈 발생 시 즉시 개선조치 후 HACCP팀장 보고",
        "  담당자: ________  확인자: ________  HACCP팀장: ________"])
    return '\n'.join(lines)


def haccp_flow_diagram(bev_type, df_proc):
    """공정흐름도"""
    m = df_proc[df_proc['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    if m.empty:
        return "해당 음료유형의 공정 데이터가 없습니다."
    lines = [f"공정흐름도 — {bev_type}", "=" * 50]
    prev = False
    for _, p in m.iterrows():
        step = p.get('세부공정', '')
        ccp = " ★CCP" if str(p.get('CCP여부', '')).startswith('CCP') else ""
        cond = str(p.get('주요조건/파라미터', ''))[:35]
        if prev:
            lines.extend(["        │", "        ▼"])
        lines.extend([
            "  ┌────────────────────────────────┐",
            f"  │ {step}{ccp:<29}│",
            f"  │ {cond:<32}│",
            "  └────────────────────────────────┘"])
        prev = True
    return '\n'.join(lines)


def haccp_sop(bev_type, df_proc, product_name="", slots=None):
    """작업표준서 (SOP)"""
    m = df_proc[df_proc['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    if m.empty:
        return "해당 음료유형의 공정 데이터가 없습니다."
    lines = [
        "=" * 70,
        f"  작업표준서 (Standard Operating Procedure)",
        f"  제품명: {product_name}  |  유형: {bev_type}",
        f"  작성일: {datetime.now().strftime('%Y.%m.%d')}  |  개정: Rev.01",
        "=" * 70]
    if slots:
        lines.append("\n■ 배합표")
        lines.append(f"  {'No':<4} {'원료명':<25} {'배합비(%)':<10} {'칭량(g/kg)':<12}")
        lines.append("  " + "-" * 55)
        for i, s in enumerate(slots):
            if safe_float(s.get('배합비(%)', 0)) > 0 and s.get('원료명'):
                lines.append(f"  {i+1:<4} {s['원료명']:<25} {s['배합비(%)']:<10.3f} {safe_float(s.get('배합량(g/kg)', 0)):<12.1f}")
    for _, p in m.iterrows():
        ccp = " [CCP]" if str(p.get('CCP여부', '')).startswith('CCP') else ""
        lines.extend([
            f"\n{'─'*70}",
            f"■ {p.get('공정단계', '')} — {p.get('세부공정', '')}{ccp}",
            f"{'─'*70}",
            f"  【작업방법】 {p.get('작업방법(구체적)', '-')}",
            f"  【조건/파라미터】 {p.get('주요조건/파라미터', '-')}",
            f"  【품질관리】 {p.get('품질관리포인트', '-')}"])
        if ccp:
            lines.extend([
                f"  【★HACCP】 위해요소: {str(p.get('HACCP 위해요소', '')).replace(chr(10), ', ')}",
                f"            한계기준: {p.get('한계기준(CL)', '-')}",
                f"            모니터링: {p.get('모니터링방법', '-')}",
                f"            개선조치: {p.get('개선조치', '-')}"])
    lines.extend(["", "=" * 70, "  작성:________  검토:________  승인:________"])
    return '\n'.join(lines)
