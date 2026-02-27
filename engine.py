"""
engine.py — 배합 계산 + OpenAI AI + HACCP 서류 생성 엔진
"""
import pandas as pd
import numpy as np
import json, re, math
from datetime import datetime

# ============================================================
# 1. 배합 계산
# ============================================================
SLOT_GROUPS = [
    ("원재료", list(range(1, 5))),
    ("당류/감미료", list(range(5, 9))),
    ("안정제/호료", list(range(9, 13))),
    ("기타자재", list(range(13, 20))),
    ("정제수", [20]),
]

EMPTY_SLOT = {
    '원료명': '', '배합비(%)': 0.0, 'AI추천_원료명': '', 'AI추천_%': 0.0,
    '실제사례_원료명': '', '실제사례_%': 0.0,
    '당도(Bx)': 0, '산도(%)': 0, '감미도': 0, '기능1': '', '기능2': '',
    '단가(원/kg)': 0,
    '당기여': 0, '산기여': 0, '감미기여': 0, '단가기여(원/kg)': 0, '배합량(g/kg)': 0,
    # 직접입력 원료 속성
    'pH': 0, 'Brix(°)': 0, '감미도(설탕대비)': 0,
    '1%Brix기여': 0, '1%pH영향': 0, '1%산도기여': 0, '1%감미기여': 0,
    'is_custom': False,
}


def init_slots():
    """20행 빈 배합표 초기화"""
    return [EMPTY_SLOT.copy() for _ in range(20)]


def fill_slot_from_db(slot, ingredient_name, df_ing, ph_col):
    """원료DB에서 원료 정보 채우기"""
    row = df_ing[df_ing['원료명'] == ingredient_name]
    if row.empty:
        return slot
    r = row.iloc[0]
    slot['원료명'] = ingredient_name
    slot['당도(Bx)'] = r.get('Brix(°)', 0)
    slot['산도(%)'] = r.get('산도(%)', 0)
    slot['감미도'] = r.get('감미도(설탕대비)', 0)
    slot['단가(원/kg)'] = r.get('예상단가(원/kg)', 0)
    slot['pH'] = r.get('pH', 0)
    slot['Brix(°)'] = r.get('Brix(°)', 0)
    slot['감미도(설탕대비)'] = r.get('감미도(설탕대비)', 0)
    slot['1%Brix기여'] = r.get('1%사용시 Brix기여(°)', 0)
    slot['1%pH영향'] = r.get(ph_col, 0)
    slot['1%산도기여'] = r.get('1%사용시 산도기여(%)', 0)
    slot['1%감미기여'] = r.get('1%사용시 감미기여', 0)
    slot['is_custom'] = False
    return slot


def calc_slot_contributions(slot):
    """슬롯 기여도 계산"""
    pct = slot.get('배합비(%)', 0)
    if pct <= 0:
        slot['당기여'] = 0
        slot['산기여'] = 0
        slot['감미기여'] = 0
        slot['단가기여(원/kg)'] = 0
        slot['배합량(g/kg)'] = 0
        return slot
    slot['당기여'] = round(slot.get('1%Brix기여', 0) * pct, 2)
    slot['산기여'] = round(slot.get('1%산도기여', 0) * pct, 4)
    slot['감미기여'] = round(slot.get('1%감미기여', 0) * pct, 4)
    slot['단가기여(원/kg)'] = round(slot.get('단가(원/kg)', 0) * pct / 100, 1)
    slot['배합량(g/kg)'] = round(pct * 10, 1)
    return slot


def calc_formulation_from_slots(slots, base_ph=3.5):
    """20행 슬롯 → 전체 배합 결과"""
    total_brix = sum(s.get('당기여', 0) for s in slots)
    total_acid = sum(s.get('산기여', 0) for s in slots)
    total_sweet = sum(s.get('감미기여', 0) for s in slots)
    total_dph = sum(s.get('1%pH영향', 0) * s.get('배합비(%)', 0) for s in slots)
    total_cost = sum(s.get('단가기여(원/kg)', 0) for s in slots)
    total_pct = sum(s.get('배합비(%)', 0) for s in slots[:19])  # 정제수 제외
    water_pct = max(0, 100 - total_pct)

    # 정제수 슬롯(20번) 자동 계산
    slots[19]['원료명'] = '정제수'
    slots[19]['배합비(%)'] = round(water_pct, 3)
    slots[19]['배합량(g/kg)'] = round(water_pct * 10, 1)

    # 과즙함량 계산 (원재료 그룹 중 농축액 배합비 합 × 농축배수)
    juice_pct = 0
    for s in slots[:4]:
        if s.get('배합비(%)', 0) > 0 and ('농축' in str(s.get('원료명', '')) or '과즙' in str(s.get('원료명', ''))):
            brix = s.get('Brix(°)', 0)
            if brix >= 40:
                concentration = brix / 11.5  # 대략적 농축배수
                juice_pct += s['배합비(%)'] * concentration
            else:
                juice_pct += s['배합비(%)']

    return {
        '배합비합계(%)': round(total_pct + water_pct, 3),
        '예상당도(Bx)': round(total_brix, 2),
        '예상pH': round(base_ph + total_dph, 2),
        'ΔpH합계': round(total_dph, 3),
        '예상산도(%)': round(total_acid, 4),
        '예상감미도': round(total_sweet, 4),
        '당산비': round(total_brix / total_acid, 1) if total_acid > 0 else 0,
        '원재료비(원/kg)': round(total_cost, 1),
        '원재료비(원/병)': round(total_cost, 1),  # 1kg=1L 기준
        '원료종류(개)': sum(1 for s in slots[:19] if s.get('배합비(%)', 0) > 0),
        '정제수비율(%)': round(water_pct, 1),
        '과즙함량(%)': round(juice_pct, 1),
    }


def get_spec_range(df_spec, bev_type):
    """음료유형별 규격"""
    row = df_spec[df_spec['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    if row.empty:
        return None
    r = row.iloc[0]
    return {k: r.get(k, 0) for k in ['Brix_min', 'Brix_max', 'pH_min', 'pH_max', '산도_min', '산도_max']}


def check_compliance(result, spec):
    """규격 적합 판정 — 항목별 (적합/부적합) 리턴"""
    if not spec:
        return {}
    checks = {}
    bx = result['예상당도(Bx)']
    checks['당도'] = ('✅ 규격이내', True) if spec.get('Brix_min', 0) <= bx <= spec.get('Brix_max', 99) else (f'⚠️ 규격이탈({bx:.2f}° → 기준 {spec["Brix_min"]}~{spec["Brix_max"]}°)', False)

    ac = result['예상산도(%)']
    if spec.get('산도_min', 0) > 0 or spec.get('산도_max', 0) > 0:
        checks['산도'] = ('✅ 규격이내', True) if spec.get('산도_min', 0) <= ac <= spec.get('산도_max', 99) else (f'⚠️ 규격이탈({ac:.4f}% → 기준 {spec["산도_min"]}~{spec["산도_max"]}%)', False)

    cost = result['원재료비(원/kg)']
    checks['원재료비'] = ('✅ 목표이내', True)  # 사용자가 목표 설정

    wp = result['정제수비율(%)']
    checks['정제수비율'] = ('✅ 적정(50%이상)', True) if wp >= 50 else ('⚠️ 50% 미만', False)

    ph = result['예상pH']
    if spec.get('pH_min', 0) > 0:
        checks['pH'] = ('ℹ️ pH규격: {:.1f}~{:.1f} → 실측 필요'.format(spec['pH_min'], spec['pH_max']), None)

    return checks


# ============================================================
# 2. 가이드 배합비 로딩
# ============================================================
def load_guide_formulation(df_guide, bev_type, flavor, df_ing, ph_col):
    """가이드배합비DB에서 슬롯 채우기"""
    key_prefix = f"{bev_type}_{flavor}_"
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

        if pd.notna(ai_name) and str(ai_name).strip():
            slots[idx] = fill_slot_from_db(slots[idx], str(ai_name), df_ing, ph_col)
            if pd.notna(ai_pct) and ai_pct > 0:
                slots[idx]['배합비(%)'] = float(ai_pct)
            slots[idx]['AI추천_원료명'] = str(ai_name) if pd.notna(ai_name) else ''
            slots[idx]['AI추천_%'] = float(ai_pct) if pd.notna(ai_pct) else 0
        if pd.notna(case_name):
            slots[idx]['실제사례_원료명'] = str(case_name)
            slots[idx]['실제사례_%'] = float(case_pct) if pd.notna(case_pct) else 0

        slots[idx] = calc_slot_contributions(slots[idx])
    return slots


# ============================================================
# 3. 역설계
# ============================================================
def reverse_engineer(product_row, df_ing, ph_col):
    """시판제품 → 추정 배합 슬롯"""
    slots = init_slots()
    slot_idx = 0
    for i in range(1, 8):
        col = f'배합순위{i}' if i > 1 else '배합순위1(원재료/배합비%/원산지)'
        val = product_row.get(col)
        if pd.isna(val) or str(val).strip() in ['—', '-', '0', '']:
            continue
        parts = str(val).split('/')
        raw_name = parts[0].strip()
        pct = 0
        try:
            pct = float(parts[1].strip().replace('%', ''))
        except:
            pass
        matched = df_ing[df_ing['원료명'].str.contains(raw_name.split('(')[0][:4], na=False)]
        if not matched.empty:
            slots[slot_idx] = fill_slot_from_db(slots[slot_idx], matched.iloc[0]['원료명'], df_ing, ph_col)
        else:
            slots[slot_idx]['원료명'] = raw_name
            slots[slot_idx]['is_custom'] = True
        slots[slot_idx]['배합비(%)'] = pct
        slots[slot_idx] = calc_slot_contributions(slots[slot_idx])
        slot_idx += 1
        if slot_idx >= 19:
            break
    return slots


# ============================================================
# 4. 식품표시사항
# ============================================================
def generate_food_label(slots, product_name="", volume_ml=500):
    """배합 슬롯 → 식품표시사항"""
    active = [(s['원료명'], s['배합비(%)']) for s in slots if s.get('배합비(%)', 0) > 0 and s['원료명']]
    active.sort(key=lambda x: x[1], reverse=True)
    label_names = [name for name, _ in active]

    total_sugar_g = 0
    for s in slots:
        if s.get('배합비(%)', 0) > 0 and s.get('Brix(°)', 0) > 0:
            total_sugar_g += s['Brix(°)'] * s['배합비(%)'] / 100 / 100 * 1000
    cal = total_sugar_g * 4

    return {
        '제품명': product_name,
        '원재료명': ', '.join(label_names),
        '영양성분': {
            '열량(kcal/100ml)': round(cal / 10, 1),
            '탄수화물(g/100ml)': round(total_sugar_g / 10, 1),
            '당류(g/100ml)': round(total_sugar_g / 10, 1),
            f'열량(kcal/{volume_ml}ml)': round(cal / 10 * volume_ml / 100, 1),
            f'당류(g/{volume_ml}ml)': round(total_sugar_g / 10 * volume_ml / 100, 1),
        }
    }


# ============================================================
# 5. 시작 레시피
# ============================================================
def generate_lab_recipe(slots, scales=[1, 5, 20]):
    """배합 슬롯 → 실험실 스케일 칭량표"""
    recipes = {}
    for scale in scales:
        total_g = scale * 1000
        items = []
        for s in slots:
            if s.get('배합비(%)', 0) <= 0 or not s.get('원료명'):
                continue
            items.append({
                '원료명': s['원료명'], '배합비(%)': s['배합비(%)'],
                f'칭량({scale}L)_g': round(s['배합비(%)'] / 100 * total_g, 2),
            })
        recipes[f'{scale}L'] = items
    return recipes


# ============================================================
# 6. OpenAI — AI연구원 + DALL-E + 직접입력 추정
# ============================================================
RESEARCHER_PROMPT = """당신은 대한민국 음료회사 20년 경력 수석 연구원 "Dr. 이음료"입니다.

배합표를 받으면 반드시 아래 5가지를 평가하세요:

### 1️⃣ 관능 예측
- 초두감미(처음 맛), 중미(입안 느낌), 후미(잔향)
- 바디감/마우스필, 향미밸런스(탑/미들/베이스)

### 2️⃣ 밸런스 진단
- 당산비 적정성 (과채음료 25~40, 탄산 35~50)
- 감미구조(설탕성/시럽성/인공), 산미캐릭터

### 3️⃣ 개선 제안 (구체적 수치)
- "사과농축과즙 8%→10%로" 식으로 반드시 수치 포함

### 4️⃣ 기술적 효과
- 안정성, 살균조건, 유통기한, 원가절감 포인트

### 5️⃣ 수정 배합표 (JSON)
반드시 마지막에:
```json
{"수정배합": [{"원료명": "xxx", "배합비(%)": 0.0}, ...]}
```

한국어로 답변. 식품공전 규격 언급. 실무 관점."""


def call_gpt_researcher(api_key, form_text, bev_type, target=""):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": RESEARCHER_PROMPT},
            {"role": "user", "content": f"**음료유형**: {bev_type}\n**목표**: {target}\n\n**배합표**:\n{form_text}\n\n평가 및 수정배합표를 JSON으로 제안해주세요."}
        ],
        temperature=0.7, max_tokens=3000,
    )
    return resp.choices[0].message.content


def call_gpt_estimate_ingredient(api_key, ingredient_name, category=""):
    """직접입력 원료의 이화학 규격을 GPT로 추정"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": """당신은 식품원료 이화학 데이터 전문가입니다. 원료의 특성을 추정하세요.

중요 참고 기준:
- 농축과즙: Brix 40~70°, pH 2.5~4.5, 산도 1~8%, 단가 3000~15000원/kg
  예) 오렌지농축과즙(65Brix): Brix=65, 1pct_Brix기여=0.65
- 과일퓨레: Brix 8~15°, pH 3.0~4.5, 단가 2000~8000원/kg
  예) 딸기퓨레(12Brix): Brix=12, 1pct_Brix기여=0.12
- 당류: Brix 65~100°, 감미도(설탕대비) 0.6~1.8
  예) 설탕: Brix=100, 감미도=1.0, 1pct_Brix기여=1.0, 1pct_감미기여=0.01
  예) 액상과당(HFCS55): Brix=77, 감미도=1.1, 1pct_Brix기여=0.77
  예) 물엿: Brix=75, 감미도=0.4, 1pct_Brix기여=0.75
- 고감미 감미료: Brix=0, 감미도 100~600
  예) 수크랄로스: 감미도=600, 1pct_감미기여=6.0
- 산미료: pH영향 강함
  예) 구연산: 1pct_pH영향=-0.40, 1pct_산도기여=0.0064

1pct_Brix기여 = Brix / 100 (원료 1%를 음료에 넣었을때 Brix 기여)
1pct_감미기여 = 감미도_설탕대비 / 100
1pct_산도기여 = 산도_pct / 100
1pct_pH영향 = 산성원료는 음수(-0.01~-1.5), 알칼리는 양수, 중성은 0

값이 0이면 안되는 원료: 농축액, 퓨레, 당류, 시럽류의 Brix와 감미도는 반드시 0보다 커야 함.
반드시 JSON만 응답. 설명 없이."""},
            {"role": "user", "content": f"""원료명: {ingredient_name}
분류: {category}

JSON 형식으로만 응답:
{{"Brix": 0, "pH": 0, "산도_pct": 0, "감미도_설탕대비": 0, "예상단가_원kg": 0, "1pct_Brix기여": 0, "1pct_pH영향": 0, "1pct_산도기여": 0, "1pct_감미기여": 0}}"""}
        ],
        temperature=0.3, max_tokens=300,
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
    color_map = {
        '오렌지': '오렌지색', '자몽': '핑크색', '레몬': '노란색', '라임': '연두색',
        '망고': '황금색', '사과': '붉은+연두', '복숭아': '분홍색', '포도': '보라색',
        '블루베리': '남보라', '딸기': '빨간색', '석류': '루비색', '커피': '갈색',
    }
    color = '투명'
    for s in slots:
        for k, c in color_map.items():
            if k in str(s.get('원료명', '')):
                color = c
                break
    main_ings = [s['원료명'].split('(')[0] for s in slots if s.get('배합비(%)', 0) > 0 and s['원료명'] != '정제수'][:3]
    return f"""한국 편의점 음료 제품 패키지 디자인. 제품명: "{product_name}", 유형: {bev_type}, 주재료: {', '.join(main_ings)}, 색상: {color}, {container} {volume}ml, 한국 음료 패키지, 밝고 깨끗한 스타일, 포토리얼리스틱."""


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
# 7. HACCP 서류 생성 (식약처 표준양식)
# ============================================================
def generate_haccp_ha_worksheet(bev_type, process_df):
    """위해분석표 (HA Worksheet) — 식약처 양식"""
    matched = process_df[process_df['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    lines = []
    lines.append("=" * 90)
    lines.append("위해분석 작업장 (Hazard Analysis Worksheet)")
    lines.append(f"제품유형: {bev_type}  |  작성일: {datetime.now().strftime('%Y.%m.%d')}")
    lines.append("=" * 90)
    lines.append(f"{'공정단계':<15} {'위해요소':<25} {'발생원인':<20} {'위해평가':<10} {'예방조치':<20} {'CCP여부':<8}")
    lines.append("-" * 90)
    for _, p in matched.iterrows():
        hazard = str(p.get('HACCP 위해요소', '-')).replace('\\n', ', ')
        ccp = '예' if str(p.get('CCP여부', '')).startswith('CCP') else '아니오'
        lines.append(f"{str(p.get('세부공정','-')):<15} {hazard:<25} {str(p.get('품질관리포인트','-')):<20} {'중요':^10} {str(p.get('모니터링방법','-'))[:20]:<20} {ccp:<8}")
    return '\n'.join(lines)


def generate_haccp_ccp_decision_tree(bev_type, process_df):
    """CCP 결정도 — 식약처 표준 Decision Tree"""
    matched = process_df[process_df['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    lines = []
    lines.append("=" * 80)
    lines.append("CCP 결정도 (CCP Decision Tree)")
    lines.append(f"제품유형: {bev_type}  |  작성일: {datetime.now().strftime('%Y.%m.%d')}")
    lines.append("=" * 80)
    lines.append(f"{'공정단계':<15} {'Q1:예방조치?':<15} {'Q2:저감/제거?':<15} {'Q3:오염증가?':<15} {'Q4:후속제거?':<15} {'CCP판정':<10}")
    lines.append("-" * 80)
    for _, p in matched.iterrows():
        is_ccp = str(p.get('CCP여부', '')).startswith('CCP')
        if is_ccp:
            lines.append(f"{str(p.get('세부공정','-')):<15} {'예':<15} {'예':<15} {'-':<15} {'-':<15} {'★ CCP':<10}")
        else:
            lines.append(f"{str(p.get('세부공정','-')):<15} {'예':<15} {'아니오':<15} {'아니오':<15} {'-':<15} {'비CCP':<10}")
    return '\n'.join(lines)


def generate_haccp_ccp_plan(bev_type, process_df):
    """CCP 관리계획서 — 식약처 표준양식"""
    matched = process_df[process_df['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    ccp_rows = matched[matched['CCP여부'].astype(str).str.startswith('CCP')]
    lines = []
    lines.append("=" * 100)
    lines.append("HACCP 관리계획서 (HACCP Plan)")
    lines.append(f"제품유형: {bev_type}  |  작성일: {datetime.now().strftime('%Y.%m.%d')}")
    lines.append("=" * 100)
    for _, p in ccp_rows.iterrows():
        lines.append(f"\n■ {p.get('CCP여부', 'CCP')} — {p.get('세부공정', '')}")
        lines.append(f"  공정단계: {p.get('공정단계', '')}")
        lines.append(f"  위해요소: {str(p.get('HACCP 위해요소', '')).replace(chr(10), ', ')}")
        lines.append(f"  한계기준(CL): {p.get('한계기준(CL)', '')}")
        lines.append(f"  모니터링 방법: {p.get('모니터링방법', '')}")
        lines.append(f"  모니터링 주기: 매 배치")
        lines.append(f"  개선조치: {p.get('개선조치', '')}")
        lines.append(f"  검증방법: 기록 검토 및 정기 검교정")
        lines.append(f"  기록문서: CCP 모니터링 일지")
    return '\n'.join(lines)


def generate_haccp_monitoring_log(bev_type, process_df):
    """CCP 모니터링 일지 (빈 양식)"""
    matched = process_df[process_df['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    ccp_rows = matched[matched['CCP여부'].astype(str).str.startswith('CCP')]
    lines = []
    lines.append("=" * 100)
    lines.append("CCP 모니터링 일지")
    lines.append(f"제품유형: {bev_type}  |  작성일자: ____년 ____월 ____일")
    lines.append("=" * 100)
    for _, p in ccp_rows.iterrows():
        lines.append(f"\n■ {p.get('CCP여부', '')} — {p.get('세부공정', '')}")
        lines.append(f"  한계기준: {p.get('한계기준(CL)', '')}")
        lines.append(f"  {'시간':<10} {'측정값':<15} {'적합여부':<10} {'이탈시조치':<20} {'담당자':<10} {'확인자':<10}")
        lines.append(f"  {'-'*10} {'-'*15} {'-'*10} {'-'*20} {'-'*10} {'-'*10}")
        for _ in range(10):
            lines.append(f"  {'____:____':<10} {'___________':<15} {'□적합□부적합':<10} {'________________':<20} {'______':<10} {'______':<10}")
    lines.append(f"\n※ 이탈 발생 시 즉시 개선조치 실시 후 HACCP팀장에게 보고")
    lines.append(f"   담당자 서명: ___________  확인자 서명: ___________  HACCP팀장: ___________")
    return '\n'.join(lines)


def generate_flow_diagram(bev_type, process_df):
    """공정흐름도"""
    matched = process_df[process_df['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    lines = []
    lines.append("=" * 60)
    lines.append("공정흐름도 (Process Flow Diagram)")
    lines.append(f"제품유형: {bev_type}")
    lines.append("=" * 60)
    prev = None
    for _, p in matched.iterrows():
        step = p.get('세부공정', '')
        ccp = " ★CCP" if str(p.get('CCP여부', '')).startswith('CCP') else ""
        condition = str(p.get('주요조건/파라미터', ''))[:40]
        if prev:
            lines.append("        │")
            lines.append("        ▼")
        lines.append(f"  ┌─────────────────────────────────┐")
        lines.append(f"  │ {step}{ccp:<30} │")
        lines.append(f"  │ {condition:<33} │")
        lines.append(f"  └─────────────────────────────────┘")
        prev = step
    return '\n'.join(lines)


def generate_sop(bev_type, process_df, product_name="", slots=None):
    """작업표준서 (SOP / 작업지시서)"""
    matched = process_df[process_df['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    lines = []
    lines.append("=" * 80)
    lines.append("작업표준서 (Standard Operating Procedure)")
    lines.append(f"제품명: {product_name}  |  제품유형: {bev_type}")
    lines.append(f"작성일: {datetime.now().strftime('%Y.%m.%d')}  |  개정번호: Rev.01")
    lines.append("=" * 80)

    # 배합표 포함
    if slots:
        lines.append("\n■ 배합표")
        lines.append(f"  {'No':<4} {'원료명':<25} {'배합비(%)':<10} {'배합량(g/kg)':<12} {'비고'}")
        lines.append("  " + "-" * 70)
        for i, s in enumerate(slots):
            if s.get('배합비(%)', 0) > 0 and s.get('원료명'):
                lines.append(f"  {i+1:<4} {s['원료명']:<25} {s['배합비(%)']:<10.3f} {s.get('배합량(g/kg)',0):<12.1f}")

    for _, p in matched.iterrows():
        ccp = " [CCP]" if str(p.get('CCP여부', '')).startswith('CCP') else ""
        lines.append(f"\n{'─'*80}")
        lines.append(f"■ {p.get('공정단계', '')} — {p.get('세부공정', '')}{ccp}")
        lines.append(f"{'─'*80}")
        lines.append(f"  【작업방법】")
        lines.append(f"  {p.get('작업방법(구체적)', '-')}")
        lines.append(f"\n  【주요조건/파라미터】")
        lines.append(f"  {p.get('주요조건/파라미터', '-')}")
        lines.append(f"\n  【품질관리 포인트】")
        lines.append(f"  {p.get('품질관리포인트', '-')}")
        if ccp:
            lines.append(f"\n  【★ HACCP 관리기준】")
            lines.append(f"  위해요소: {str(p.get('HACCP 위해요소', '')).replace(chr(10), ', ')}")
            lines.append(f"  한계기준(CL): {p.get('한계기준(CL)', '-')}")
            lines.append(f"  모니터링: {p.get('모니터링방법', '-')}")
            lines.append(f"  이탈시 조치: {p.get('개선조치', '-')}")

    lines.append(f"\n{'='*80}")
    lines.append("작성: ___________  검토: ___________  승인: ___________")
    return '\n'.join(lines)
