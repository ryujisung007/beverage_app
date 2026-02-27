"""
engine.py — 배합 계산 엔진 + OpenAI AI 엔진
"""
import pandas as pd
import numpy as np
import json, re, io
from datetime import datetime

# ============================================================
# 1. 배합 계산 엔진
# ============================================================
def calc_formulation(df_ingredient, ingredients_list, ph_col, base_ph=3.5):
    """배합표 → 품질예측 + 원가 계산"""
    total = {'brix': 0, 'acid': 0, 'sweet': 0, 'dph': 0, 'cost': 0, 'pct': 0}
    details = []

    for item in ingredients_list:
        name, pct = item['원료명'], item['배합비(%)']
        if pct <= 0:
            continue
        row = df_ingredient[df_ingredient['원료명'] == name]
        if row.empty:
            continue
        r = row.iloc[0]

        d = {
            '원료명': name, '배합비(%)': pct, '분류': r['원료대분류'],
            'Brix기여': round(r['1%사용시 Brix기여(°)'] * pct, 2),
            '산도기여': round(r['1%사용시 산도기여(%)'] * pct, 4),
            '감미기여': round(r['1%사용시 감미기여'] * pct, 4),
            'ΔpH기여': round(r[ph_col] * pct, 3),
            '단가(원/kg)': r['예상단가(원/kg)'],
            '원가기여(원/kg)': round(r['예상단가(원/kg)'] * pct / 100, 1),
        }
        for k in ['brix', 'acid', 'sweet', 'dph', 'cost']:
            total[k] += [d['Brix기여'], d['산도기여'], d['감미기여'], d['ΔpH기여'], d['원가기여(원/kg)']][
                ['brix', 'acid', 'sweet', 'dph', 'cost'].index(k)]
        total['pct'] += pct
        details.append(d)

    return {
        '총Brix(°)': round(total['brix'], 2),
        '예상pH': round(base_ph + total['dph'], 2),
        'ΔpH합계': round(total['dph'], 3),
        '총산도(%)': round(total['acid'], 4),
        '총감미도': round(total['sweet'], 4),
        '당산비': round(total['brix'] / total['acid'], 1) if total['acid'] > 0 else 0,
        '원재료비(원/kg)': round(total['cost'], 1),
        '원재료비(원/500ml)': round(total['cost'] * 0.5, 1),
        '정제수(%)': round(max(0, 100 - total['pct']), 2),
        '원료합계(%)': round(total['pct'], 2),
        'details': details,
    }


def get_spec_range(df_spec, bev_type):
    """음료유형별 규격 범위"""
    row = df_spec[df_spec['음료유형'].str.contains(bev_type.split('(')[0], na=False)]
    if row.empty:
        return None
    r = row.iloc[0]
    return {k: r.get(k, 0) for k in ['Brix_min', 'Brix_max', 'pH_min', 'pH_max', '산도_min', '산도_max']}


def check_compliance(result, spec):
    """규격 적합 판정"""
    if not spec:
        return []
    checks = [
        ('Brix', result['총Brix(°)'], spec.get('Brix_min', 0), spec.get('Brix_max', 99)),
        ('pH', result['예상pH'], spec.get('pH_min', 0), spec.get('pH_max', 14)),
        ('산도', result['총산도(%)'], spec.get('산도_min', 0), spec.get('산도_max', 99)),
    ]
    issues = []
    for name, val, lo, hi in checks:
        if pd.notna(lo) and lo > 0 and val < lo:
            issues.append(f"⚠️ {name} {val} < 최소 {lo}")
        if pd.notna(hi) and hi > 0 and val > hi:
            issues.append(f"⚠️ {name} {val} > 최대 {hi}")
    return issues


# ============================================================
# 2. 역설계 엔진
# ============================================================
def reverse_engineer_product(product_row, df_ingredient):
    """시판제품 배합순위 → 원료DB 매칭 → 추정 배합표"""
    formulation = []
    for i in range(1, 8):
        col = f'배합순위{i}' if i > 1 else '배합순위1(원재료/배합비%/원산지)'
        val = product_row.get(col)
        if pd.isna(val) or str(val).strip() in ['—', '-', '0', '']:
            continue
        parts = str(val).split('/')
        raw_name = parts[0].strip()
        pct_str = parts[1].strip() if len(parts) > 1 else ''
        pct = 0
        try:
            pct = float(pct_str.replace('%', ''))
        except:
            pass

        # 원료DB에서 매칭 시도
        matched = df_ingredient[df_ingredient['원료명'].str.contains(raw_name.split('(')[0][:4], na=False)]
        matched_name = matched.iloc[0]['원료명'] if not matched.empty else raw_name

        if pct > 0:
            formulation.append({'원료명': matched_name, '배합비(%)': pct, '원본표기': raw_name, 'DB매칭': not matched.empty})
    return formulation


# ============================================================
# 3. 식품표시사항 생성
# ============================================================
def generate_food_label(ingredients_list, df_ingredient, product_name="", volume_ml=500):
    """배합표 → 식품표시사항 (원재료명, 영양성분 추정)"""
    sorted_ing = sorted(ingredients_list, key=lambda x: x['배합비(%)'], reverse=True)

    # 원재료명 표시 (다→소 순서)
    label_names = []
    for item in sorted_ing:
        if item['배합비(%)'] <= 0:
            continue
        row = df_ingredient[df_ingredient['원료명'] == item['원료명']]
        cat = row.iloc[0]['원료대분류'] if not row.empty else ''
        if cat == '기본원료' and '정제수' in item['원료명']:
            label_names.append('정제수')
        else:
            label_names.append(item['원료명'])

    # 정제수 추가 (배합비 가장 큰 경우 맨 앞)
    water_pct = 100 - sum(i['배합비(%)'] for i in sorted_ing)
    if water_pct > 0:
        if water_pct > (sorted_ing[0]['배합비(%)'] if sorted_ing else 0):
            label_names.insert(0, '정제수')
        else:
            # 적절한 위치에 삽입
            inserted = False
            for idx, item in enumerate(sorted_ing):
                if water_pct > item['배합비(%)']:
                    label_names.insert(idx, '정제수')
                    inserted = True
                    break
            if not inserted:
                label_names.append('정제수')

    # 영양성분 추정 (100ml 기준)
    total_sugar_g = 0
    total_cal = 0
    for item in sorted_ing:
        row = df_ingredient[df_ingredient['원료명'] == item['원료명']]
        if row.empty:
            continue
        r = row.iloc[0]
        brix = r['Brix(°)']
        cat = r['원료대분류']
        pct = item['배합비(%)']

        if cat in ['당류', '과즙농축액'] and brix > 0:
            sugar_contrib = brix * pct / 100 / 100 * 1000  # g/L
            total_sugar_g += sugar_contrib
            total_cal += sugar_contrib * 4  # 4kcal/g

    nutrition = {
        '열량(kcal/100ml)': round(total_cal / 10, 1),
        '탄수화물(g/100ml)': round(total_sugar_g / 10, 1),
        '당류(g/100ml)': round(total_sugar_g / 10, 1),
        '단백질(g/100ml)': 0,
        '지방(g/100ml)': 0,
        '나트륨(mg/100ml)': 0,
    }
    nutrition[f'열량(kcal/{volume_ml}ml)'] = round(nutrition['열량(kcal/100ml)'] * volume_ml / 100, 1)
    nutrition[f'당류(g/{volume_ml}ml)'] = round(nutrition['당류(g/100ml)'] * volume_ml / 100, 1)

    return {
        '제품명': product_name,
        '원재료명': ', '.join(label_names),
        '영양성분': nutrition,
    }


# ============================================================
# 4. 시작 레시피 시트
# ============================================================
def generate_lab_recipe(ingredients_list, df_ingredient, scales=[1, 5, 20]):
    """배합표 → 실험실 스케일(L) 칭량표"""
    recipes = {}
    for scale in scales:
        total_g = scale * 1000  # 1L = 1000g (음료 밀도 ≈ 1)
        items = []
        used_g = 0
        for item in ingredients_list:
            row = df_ingredient[df_ingredient['원료명'] == item['원료명']]
            cat = row.iloc[0]['원료대분류'] if not row.empty else '-'
            weight = round(item['배합비(%)'] / 100 * total_g, 2)
            used_g += weight
            items.append({
                '투입순서': len(items) + 1,
                '원료명': item['원료명'],
                '분류': cat,
                '배합비(%)': item['배합비(%)'],
                f'칭량({scale}L)_g': weight,
            })
        # 정제수 (잔량)
        water_g = round(total_g - used_g, 2)
        items.insert(0, {
            '투입순서': 0, '원료명': '정제수', '분류': '기본원료',
            '배합비(%)': round(water_g / total_g * 100, 2),
            f'칭량({scale}L)_g': water_g,
        })
        # 투입순서 재정렬 (정제수 먼저)
        for idx, item in enumerate(items):
            item['투입순서'] = idx + 1
        recipes[f'{scale}L'] = items
    return recipes


# ============================================================
# 5. OpenAI AI 엔진
# ============================================================
RESEARCHER_SYSTEM_PROMPT = """당신은 대한민국 대형 음료회사에서 20년간 근무한 수석 음료개발연구원 "Dr. 이음료"입니다.

## 전문 분야
- 과채음료, 탄산음료, 유산균음료, 기능성음료, 커피음료 등 전 음료 카테고리 개발 경험
- 2,000건 이상의 시작(試作) 실험 경험
- 관능평가 전문위원 자격 보유

## 응답 규칙
1. 반드시 한국어로 답변
2. 배합표를 받으면 다음 5가지를 체계적으로 평가:

### 1️⃣ 관능 예측 (맛/향/바디감/후미)
- 초두감미(initial sweetness): 처음 맛볼 때 느낌
- 중미(middle): 삼키기 전 입안 느낌
- 후미(aftertaste): 삼킨 후 잔향
- 바디감/마우스필: 음료의 무게감, 점도감
- 향미 밸런스: 탑노트/미들/베이스 향 분석

### 2️⃣ 밸런스 진단
- 당산비 적정성 (유형별 최적 당산비: 과채음료 25~40, 탄산음료 35~50)
- 감미 구조 (설탕성 vs 시럽성 vs 인공감미)
- 산미 캐릭터 (구연산=시트러스, 사과산=그린, 주석산=샤프)

### 3️⃣ 개선 제안 (구체적 수치와 함께)
- "사과농축과즙을 8% → 10%로 올리면 과즙감이 살아납니다"
- "구연산 0.08% → 0.05%로 줄이고 사과산 0.03% 추가하면 산미가 부드러워집니다"
- 반드시 수치를 제시

### 4️⃣ 기술적 효과 제안
- 안정성 (분리, 침전, 색변화 우려)
- 살균 조건에 따른 풍미 변화
- 유통기한 중 품질 변화 예측
- 원가 절감 가능 포인트

### 5️⃣ 수정 배합표 (JSON)
반드시 응답 마지막에 아래 형식으로 수정 배합표를 제공:
```json
{"수정배합": [{"원료명": "xxx", "배합비(%)": 0.0}, ...]}
```

## 중요
- 항상 식품공전 규격 기준을 언급
- 실무에서 발생할 수 있는 문제를 미리 경고
- 원가 영향도 함께 고려
- 경쟁 시장 트렌드를 반영한 제안"""


DALLE_PROMPT_TEMPLATE = """한국 편의점/마트에서 판매되는 음료 제품 패키지 디자인.
제품명: "{product_name}"
음료 유형: {bev_type}
주요 원료: {main_ingredients}
색상 톤: {color_tone}
용기: {container} {volume}ml
스타일: 한국 음료 패키지 디자인, 밝고 깨끗한 느낌, 제품 사진 스타일, 편의점 진열대 배경.
고해상도, 포토리얼리스틱."""


def get_color_from_ingredients(ingredients_list, df_ingredient):
    """원료 기반 색상 추정"""
    color_map = {
        '오렌지': '오렌지색, 밝은 주황', '자몽': '핑크-살몬색', '레몬': '밝은 노란색',
        '라임': '연두-그린', '감귤': '진한 주황', '유자': '밝은 노란색',
        '망고': '진한 황금색', '파인애플': '노란색', '패션프루트': '진한 노란-주황',
        '사과': '붉은색+연두색', '배': '연한 크림색', '복숭아': '연분홍-살구색',
        '체리': '진한 적색', '매실': '연두-녹색', '포도': '진한 보라색',
        '블루베리': '남보라색', '크랜베리': '진한 빨간색', '딸기': '밝은 빨간색',
        '석류': '진한 빨간색-루비', '토마토': '빨간색', '당근': '주황색',
        '녹차': '연한 녹색', '커피': '갈색', '유산균': '흰색-크림',
    }
    for item in ingredients_list:
        for key, color in color_map.items():
            if key in item['원료명']:
                return color
    return '투명-연한 색상'


def build_dalle_prompt(product_name, bev_type, ingredients_list, df_ingredient, container="PET", volume=500):
    """배합 정보 → DALL-E 프롬프트 자동 생성"""
    main_ings = [i['원료명'].split('(')[0] for i in sorted(ingredients_list, key=lambda x: x['배합비(%)'], reverse=True)[:3]]
    color = get_color_from_ingredients(ingredients_list, df_ingredient)

    return DALLE_PROMPT_TEMPLATE.format(
        product_name=product_name,
        bev_type=bev_type,
        main_ingredients=', '.join(main_ings),
        color_tone=color,
        container=container,
        volume=volume,
    )


def call_gpt_researcher(api_key, formulation_text, bev_type, target_spec=""):
    """OpenAI GPT로 AI연구원 평가 호출"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    user_msg = f"""## 배합표 평가 요청

**음료유형**: {bev_type}
**목표규격**: {target_spec}

**배합표**:
{formulation_text}

위 배합표를 20년 경력의 음료개발연구원 관점에서 평가하고, 개선된 수정 배합표를 JSON으로 제안해주세요."""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": RESEARCHER_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg}
        ],
        temperature=0.7,
        max_tokens=3000,
    )
    return response.choices[0].message.content


def call_dalle(api_key, prompt):
    """DALL-E 이미지 생성"""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    return response.data[0].url


def parse_modified_formulation(ai_response):
    """AI 응답에서 수정 배합표 JSON 추출"""
    try:
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
            return data.get('수정배합', [])
        json_match = re.search(r'\{"수정배합":\s*\[.*?\]\}', ai_response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            return data.get('수정배합', [])
    except:
        pass
    return []
