import os
import re

import streamlit as st
from dotenv import load_dotenv

# ── 환경 변수 로드 (로컬 .env → Streamlit Cloud secrets 순서) ─────────────────
load_dotenv()

try:
    for _key in ["OPENAI_API_KEY", "TAVILY_API_KEY"]:
        if _key in st.secrets and not os.environ.get(_key):
            os.environ[_key] = st.secrets[_key]
except Exception:
    pass

# ── 페이지 설정 (반드시 첫 번째 st 명령) ────────────────────────────────────────
st.set_page_config(
    page_title="냉장고 요리사",
    page_icon="🍳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* 전체 배경 */
.stApp { background-color: #fafaf8; }

/* 헤더 */
.main-header {
    background: linear-gradient(135deg, #ff6b35 0%, #f7931e 100%);
    padding: 2rem 2.5rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    color: white;
}
.main-header h1 { margin: 0; font-size: 2.2rem; }
.main-header p  { margin: 0.3rem 0 0; opacity: 0.9; font-size: 1.05rem; }

/* 재료 태그 */
.ingredient-tags {
    display: flex; flex-wrap: wrap; gap: 8px; margin: 0.5rem 0;
}
.tag {
    background: #fff3e0; color: #e65100;
    border: 1.5px solid #ffb74d; border-radius: 20px;
    padding: 4px 12px; font-size: 0.88rem; font-weight: 600;
}
.tag-exclude {
    background: #fce4ec; color: #c62828;
    border: 1.5px solid #ef9a9a; border-radius: 20px;
    padding: 4px 12px; font-size: 0.88rem; font-weight: 600;
}

/* 레시피 결과 카드 */
.recipe-card {
    background: white;
    border-radius: 16px;
    padding: 2rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    border-left: 5px solid #ff6b35;
    margin-top: 1rem;
}

/* 버튼 */
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #ff6b35, #f7931e);
    border: none; border-radius: 12px;
    font-size: 1.1rem; font-weight: 700;
    padding: 0.7rem 2rem;
    box-shadow: 0 4px 12px rgba(255,107,53,0.35);
    transition: transform .15s, box-shadow .15s;
}
div.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(255,107,53,0.45);
}
</style>
""", unsafe_allow_html=True)

# ── 상수: 자주 쓰는 재료 & 알레르기 목록 ───────────────────────────────────────
COMMON_INGREDIENTS: dict[str, list[str]] = {
    "🥩 단백질": ["계란", "닭고기", "돼지고기", "소고기", "두부", "참치(캔)", "새우", "연어", "햄", "베이컨"],
    "🥕 채소":   ["당근", "감자", "양파", "마늘", "대파", "고추", "피망", "브로콜리", "시금치",
                  "버섯", "애호박", "가지", "토마토", "배추", "오이"],
    "🍚 탄수화물": ["쌀밥", "밀가루", "라면", "우동면", "파스타", "빵", "고구마", "떡"],
    "🧀 유제품":  ["우유", "치즈", "버터", "요거트", "크림"],
}

ALLERGENS = [
    "밀/밀가루", "우유/유제품", "계란", "대두/콩", "땅콩", "견과류",
    "새우", "게/갑각류", "조개류", "생선", "돼지고기", "소고기",
]

TOOL_LABEL_MAP = {
    "search_mealdb":           ("🔍", "TheMealDB에서 레시피 검색 중"),
    "get_nutrition_info":      ("📊", "영양 정보 조회 중"),
    "search_web_recipe":       ("🌐", "웹에서 레시피 검색 중"),
    "generate_recipe_with_llm": ("✨", "AI가 직접 레시피 생성 중"),
}

# ── 영양 정보 파싱 헬퍼 ───────────────────────────────────────────────────────
def parse_nutrition(text: str) -> dict[str, str]:
    """LLM 응답 텍스트에서 영양 수치를 추출합니다."""
    patterns = {
        "칼로리": r"칼로리[^\d]*(\d+(?:\.\d+)?)\s*kcal",
        "단백질": r"단백질[^\d]*(\d+(?:\.\d+)?)\s*g",
        "탄수화물": r"탄수화물[^\d]*(\d+(?:\.\d+)?)\s*g",
        "지방":   r"지방[^\d]*(\d+(?:\.\d+)?)\s*g",
    }
    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        result[key] = match.group(1) if match else "?"
    return result

# ── 세션 상태 초기화 ──────────────────────────────────────────────────────────
for _k, _v in [("recipe_result", None), ("agent_steps", []), ("source", ""), ("rating", None)]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── 사이드바 ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 설정")

    openai_key  = os.getenv("OPENAI_API_KEY", "")
    tavily_key  = os.getenv("TAVILY_API_KEY", "")

    if openai_key:
        st.success("✅ OpenAI 연결됨")
    else:
        st.error("❌ OPENAI_API_KEY 없음\n\n`.env` 파일에 키를 추가해주세요.")

    if tavily_key:
        st.success("✅ Tavily 연결됨")
    else:
        st.warning("⚠️ TAVILY_API_KEY 없음\n\n(선택사항 — 없어도 동작합니다)")

    st.divider()

    # ── 인원 수 슬라이더 ──
    st.markdown("### 👥 인원 수")
    serving_size = st.slider("인원 수", min_value=1, max_value=6, value=2, step=1,
                              label_visibility="collapsed")
    st.caption(f"{serving_size}인분 기준으로 레시피를 생성합니다")

    st.divider()

    # ── 자주 쓰는 재료 pills ──
    st.markdown("### 🥕 재료 빠른 선택")
    selected_common: list[str] = []
    for category, items in COMMON_INGREDIENTS.items():
        selected = st.pills(category, items, selection_mode="multi", key=f"pills_{category}")
        if selected:
            selected_common.extend(selected)

    st.divider()

    # ── 알레르기 / 거부 재료 ──
    st.markdown("### 🚫 알레르기 / 거부 재료")
    selected_allergens: list[str] = st.multiselect(
        "제외할 재료를 선택하세요",
        ALLERGENS,
        placeholder="알레르기 또는 싫어하는 재료...",
    )

    st.divider()
    st.caption("Built with LangGraph ReAct + Streamlit")

# ── 메인 헤더 ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
  <h1>🍳 냉장고 요리사</h1>
  <p>재료를 입력하면 AI가 최적의 레시피를 찾아드립니다</p>
</div>
""", unsafe_allow_html=True)

# ── 재료 입력 영역 ────────────────────────────────────────────────────────────
text_input = st.text_input(
    "✏️ 보유한 재료를 입력하세요",
    placeholder="예: 당근, 계란, 밀가루, 우유",
    help="쉼표(,)로 구분하여 여러 재료를 입력할 수 있습니다. 왼쪽 사이드바에서 pills로도 선택 가능합니다.",
)

# 입력 재료 통합 & 중복 제거
all_ingredients: list[str] = []
if text_input:
    all_ingredients += [i.strip() for i in text_input.split(",") if i.strip()]
all_ingredients += selected_common
all_ingredients = list(dict.fromkeys(all_ingredients))

# 현재 선택 상태 표시
if all_ingredients:
    tags_html = " ".join(f'<span class="tag">{i}</span>' for i in all_ingredients)
    st.markdown(
        f'<div class="ingredient-tags">📋 선택된 재료: {tags_html}</div>',
        unsafe_allow_html=True,
    )

if selected_allergens:
    excl_html = " ".join(f'<span class="tag-exclude">🚫 {a}</span>' for a in selected_allergens)
    st.markdown(
        f'<div class="ingredient-tags">{excl_html}</div>',
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ── 실행 버튼 ─────────────────────────────────────────────────────────────────
run_clicked = st.button(
    "🔍 요리 추천받기",
    type="primary",
    disabled=(not all_ingredients) or (not openai_key),
    use_container_width=True,
)

if not openai_key:
    st.info("💡 OpenAI API 키를 `.env` 파일에 설정하면 요리 추천을 받을 수 있습니다.")

# ── 에이전트 실행 ─────────────────────────────────────────────────────────────
if run_clicked and all_ingredients and openai_key:
    from langchain_core.messages import HumanMessage
    from agent.core import create_recipe_agent

    ingredients_str = ", ".join(all_ingredients)
    excluded_str    = ", ".join(selected_allergens) if selected_allergens else "없음"

    user_query = f"""다음 재료로 만들 수 있는 요리 **딱 1개**의 완성된 레시피를 알려주세요.
{serving_size}인분 기준으로 재료 분량을 작성해주세요.

보유 재료: {ingredients_str}
제외할 재료 (알레르기/거부): {excluded_str}

여러 요리를 나열하지 말고, 가장 적합한 요리 하나만 골라 완성된 레시피를 제공해주세요."""

    # 세션 초기화
    st.session_state.recipe_result = None
    st.session_state.agent_steps   = []
    st.session_state.source        = ""
    st.session_state.rating        = None

    agent        = create_recipe_agent()
    final_answer = ""
    steps: list[str] = []

    with st.status("🤖 AI 요리사가 레시피를 찾고 있습니다...", expanded=True) as status:
        try:
            for chunk in agent.stream(
                {"messages": [HumanMessage(content=user_query)]},
                stream_mode="updates",
            ):
                # ── 에이전트 노드 (thinking / tool call 결정) ──
                if "agent" in chunk:
                    for msg in chunk["agent"]["messages"]:
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                icon, label = TOOL_LABEL_MAP.get(
                                    tc["name"], ("🔧", tc["name"])
                                )
                                step_text = f"{icon} {label}..."
                                steps.append(step_text)
                                st.write(f"**{step_text}**")
                        elif hasattr(msg, "content") and msg.content:
                            final_answer = msg.content

                # ── 도구 노드 (tool 실행 결과 반환) ──
                elif "tools" in chunk:
                    for msg in chunk["tools"]["messages"]:
                        icon, label = TOOL_LABEL_MAP.get(
                            msg.name, ("✅", msg.name)
                        )
                        done_text = f"✅ {label} 완료"
                        steps.append(done_text)
                        st.write(done_text)

                        # 출처 태그 파싱
                        if msg.name == "search_mealdb":
                            if "MEALDB_NOT_FOUND" in msg.content or "MEALDB_ERROR" in msg.content:
                                st.session_state.source = "AI 직접 생성"
                                st.write("↪️ TheMealDB 결과 없음 → AI 직접 생성으로 전환")
                            else:
                                st.session_state.source = "TheMealDB"

            if final_answer:
                status.update(label="✅ 레시피 준비 완료!", state="complete", expanded=False)
                st.session_state.recipe_result = final_answer
                st.session_state.agent_steps   = steps
                st.toast("레시피가 준비됐어요!", icon="🍳")
            else:
                status.update(label="⚠️ 레시피를 생성하지 못했습니다.", state="error", expanded=True)

        except Exception as exc:
            status.update(label="❌ 오류 발생", state="error", expanded=True)
            st.error(f"오류: {exc}")

# ── 결과 표시 ─────────────────────────────────────────────────────────────────
if st.session_state.recipe_result:
    st.divider()

    # ── 출처 배지 (st.badge) + 다운로드 버튼 ──
    col_badge, col_dl = st.columns([3, 1])
    with col_badge:
        source = st.session_state.source
        if source == "TheMealDB":
            st.badge("TheMealDB", color="blue", icon="🗄️")
        elif source == "AI 직접 생성":
            st.badge("AI 직접 생성", color="violet", icon="✨")

    with col_dl:
        st.download_button(
            "📥 레시피 저장",
            data=st.session_state.recipe_result,
            file_name="recipe.md",
            mime="text/markdown",
            use_container_width=True,
        )

    # ── 탭 레이아웃 ──
    tab_recipe, tab_nutrition, tab_log = st.tabs(["🍽️ 레시피", "📊 영양정보", "🔄 실행 로그"])

    with tab_recipe:
        st.markdown(
            f'<div class="recipe-card">{st.session_state.recipe_result}</div>',
            unsafe_allow_html=True,
        )

    with tab_nutrition:
        nutrition = parse_nutrition(st.session_state.recipe_result)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🔥 칼로리", f"{nutrition['칼로리']} kcal")
        col2.metric("💪 단백질", f"{nutrition['단백질']} g")
        col3.metric("🌾 탄수화물", f"{nutrition['탄수화물']} g")
        col4.metric("🫒 지방", f"{nutrition['지방']} g")

        if "?" in nutrition.values():
            st.caption("일부 수치를 파싱하지 못했습니다. 레시피 본문의 영양 정보 섹션을 확인해주세요.")

    with tab_log:
        if st.session_state.agent_steps:
            for step in st.session_state.agent_steps:
                st.markdown(f"- {step}")
        else:
            st.caption("실행 로그가 없습니다.")

    # ── 별점 & 다시 검색 ──
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**이 레시피가 마음에 드셨나요?**")
    st.feedback("stars", key="rating")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 다른 재료로 다시 검색", use_container_width=True):
        st.session_state.recipe_result = None
        st.session_state.agent_steps   = []
        st.session_state.source        = ""
        st.session_state.rating        = None
        st.rerun()
