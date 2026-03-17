# ============================================================
# [패치 1] session_state 초기화 목록에 아래 2줄 추가
# 위치: 기존 ('ai_est_results', []) 바로 다음
# ============================================================
# ('gemini_chat',    []),          # Gemini 대화 기록
# ('gemini_pending', None),        # 적용 대기 배합 변경


# ============================================================
# [패치 2] page_simulator() 함수 맨 끝에 아래 전체 추가
# 위치: with b3: ... 블록 끝난 직후 (함수 안, 들여쓰기 없음)
# ============================================================

    # ══════════════════════════════════════════════════════
    # 🤖 Gemini 배합 에이전트 챗봇
    # ══════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown('<div class="sim-hdr" style="font-size:18px;">🤖 Gemini 배합 에이전트</div>',
                unsafe_allow_html=True)
    st.caption("배합 조언 · 식품 기술 Q&A · 배합비 수정 제안 — 현재 배합표를 자동으로 인식합니다.")

    # ── Gemini 키 로딩 ──
    def _get_gemini_key():
        try:
            for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "google_api_key"):
                v = st.secrets.get(k, "")
                if v and v.strip():
                    return v.strip()
        except Exception:
            pass
        return ""

    gemini_key = _get_gemini_key()
    if not gemini_key:
        st.warning("⚠️ Gemini API 키 없음 — secrets.toml에 GOOGLE_API_KEY 추가 필요")
    else:
        # ── 현재 배합 컨텍스트 빌더 ──
        def _build_context():
            result = calc_formulation(st.session_state.slots, st.session_state.volume)
            lines  = []
            for i, s in enumerate(st.session_state.slots):
                nm  = s.get('원료명', '')
                pct = safe_float(s.get('배합비(%)', 0))
                if nm and pct > 0:
                    lines.append(f"  슬롯{i+1}: {nm} {pct:.3f}%")
            formulation_str = '\n'.join(lines) if lines else "  (배합표 비어있음)"
            return (
                f"음료유형: {st.session_state.bev_type or '미설정'}\n"
                f"제품명: {st.session_state.product_name or '미설정'}\n"
                f"용량: {st.session_state.volume}ml / 용기: {st.session_state.container}\n"
                f"배합표:\n{formulation_str}\n"
                f"계산결과: Brix {result['예상당도(Bx)']:.2f}° / "
                f"pH {result['예상pH']:.2f} / "
                f"산도 {result['예상산도(%)']:.4f}% / "
                f"과즙 {result['과즙함량(%)']:.1f}% / "
                f"원가 {result['원재료비(원/kg)']:,.0f}원/kg"
            )

        # ── Gemini REST 호출 ──
        def _call_gemini_agent(user_msg: str, history: list) -> str:
            import requests as _req

            system_prompt = (
                "당신은 15년 경력의 음료 R&D 수석연구원입니다.\n"
                "아래 [현재 배합 컨텍스트]를 항상 참고하여 답변하세요.\n\n"
                f"[현재 배합 컨텍스트]\n{_build_context()}\n\n"
                "역할:\n"
                "1. 식품공전·음료 기술 전문 Q&A (탄산가스 함량, 증점제 필요성, 규격 등)\n"
                "2. 현재 배합 분석 및 개선 제안\n"
                "3. 배합 변경 제안이 필요하면 답변 끝에 아래 JSON 블록 포함:\n"
                "```json\n"
                '{"changes": [{"슬롯": 3, "원료명": "구연산", "배합비": 0.15}]}\n'
                "```\n"
                "변경 제안 없는 일반 질문은 JSON 없이 텍스트만 답변.\n"
                "한국어로 답변. 수치는 근거와 함께 제시."
            )

            # 대화 히스토리 → Gemini contents 형식
            contents = []
            for turn in history[-6:]:   # 최근 6턴만 (토큰 절약)
                contents.append({
                    "role": turn["role"],
                    "parts": [{"text": turn["text"]}]
                })
            contents.append({"role": "user", "parts": [{"text": user_msg}]})

            payload = {
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": {"maxOutputTokens": 1200, "temperature": 0.4},
            }

            url = (
                "https://generativelanguage.googleapis.com/v1/models/"
                f"gemini-2.5-flash:generateContent?key={gemini_key}"
            )
            resp = _req.post(url,
                             headers={"Content-Type": "application/json"},
                             json=payload, timeout=60)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        # ── JSON 파싱 (배합 변경 추출) ──
        def _parse_changes(text: str):
            import re as _re
            m = _re.search(r'```json\s*(\{.*?\})\s*```', text, _re.DOTALL)
            if not m:
                return None
            try:
                data = json.loads(m.group(1))
                return data.get("changes")
            except Exception:
                return None

        # ── 대화 기록 표시 ──
        chat_container = st.container()
        with chat_container:
            for turn in st.session_state.gemini_chat:
                if turn["role"] == "user":
                    with st.chat_message("user"):
                        st.markdown(turn["text"])
                else:
                    with st.chat_message("assistant", avatar="🤖"):
                        # JSON 블록 숨기고 텍스트만 표시
                        import re as _re
                        display_text = _re.sub(
                            r'```json.*?```', '📋 *(배합 변경 제안 포함 — 아래 버튼으로 적용)*',
                            turn["text"], flags=_re.DOTALL
                        )
                        st.markdown(display_text)

        # ── 적용 대기 중인 배합 변경 ──
        if st.session_state.gemini_pending:
            pending = st.session_state.gemini_pending
            st.markdown("---")
            st.markdown("##### 📋 Gemini 배합 변경 제안")
            st.dataframe(
                pd.DataFrame(pending),
                use_container_width=True, hide_index=True
            )
            ap1, ap2 = st.columns(2)
            with ap1:
                if st.button("✅ 배합 변경 적용", type="primary",
                             use_container_width=True, key="gem_apply"):
                    new_slots, est_results = load_formulation_with_estimation(
                        pending, auto_estimate=True
                    )
                    # 변경된 슬롯만 덮어쓰기 (나머지 유지)
                    for item in pending:
                        idx = int(item.get('슬롯', 1)) - 1
                        if 0 <= idx < 19:
                            st.session_state.slots[idx] = new_slots[idx]
                    if est_results:
                        st.session_state.ai_est_results = est_results
                    st.session_state.gemini_pending = None
                    clear_slot_widget_keys()
                    st.rerun()
            with ap2:
                if st.button("❌ 무시", use_container_width=True, key="gem_dismiss"):
                    st.session_state.gemini_pending = None
                    st.rerun()

        # ── 입력창 ──
        user_input = st.chat_input(
            "질문하세요. 예) 산미를 더 강하게 해줘 / 탄산가스 함량 기준은? / 증점제 필요한가?",
            key="gem_input"
        )

        if user_input:
            # 대화 기록에 추가
            st.session_state.gemini_chat.append({"role": "user", "text": user_input})

            with st.spinner("🤖 Gemini 분석 중..."):
                try:
                    reply = _call_gemini_agent(
                        user_input,
                        st.session_state.gemini_chat[:-1]   # 방금 추가한 것 제외
                    )
                    st.session_state.gemini_chat.append({"role": "model", "text": reply})

                    # 배합 변경 제안 파싱
                    changes = _parse_changes(reply)
                    if changes:
                        st.session_state.gemini_pending = changes

                except Exception as e:
                    err_msg = f"❌ Gemini 오류: {e}"
                    st.session_state.gemini_chat.append({"role": "model", "text": err_msg})

            st.rerun()

        # ── 대화 초기화 버튼 ──
        if st.session_state.gemini_chat:
            if st.button("🔄 대화 초기화", key="gem_clear", use_container_width=False):
                st.session_state.gemini_chat    = []
                st.session_state.gemini_pending = None
                st.rerun()
