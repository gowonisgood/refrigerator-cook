import os
import requests
from langchain.tools import tool


# ── 공유 LLM 인스턴스 (generate_recipe_with_llm 내부에서 사용) ──────────────
_llm = None

def _get_llm():
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI
        _llm = ChatOpenAI(model="gpt-5-mini", temperature=0.7)
    return _llm


# ── Tool 1: TheMealDB 레시피 검색 ────────────────────────────────────────────
@tool
def search_mealdb(ingredient: str) -> str:
    """TheMealDB API로 재료 기반 레시피를 검색합니다.
    ingredient: 영어로 된 재료명 (예: chicken, carrot, egg)
    결과가 있으면 레시피 상세 정보를, 없으면 실패 메시지를 반환합니다."""
    try:
        # 공백을 _로 변환 (TheMealDB URL 규칙)
        ing_query = ingredient.strip().replace(" ", "_")
        url = f"https://www.themealdb.com/api/json/v1/1/filter.php?i={ing_query}"
        resp = requests.get(url, timeout=8)
        data = resp.json()

        if not data.get("meals"):
            return f"MEALDB_NOT_FOUND: '{ingredient}'으로 TheMealDB에서 레시피를 찾을 수 없습니다."

        # 상위 1개 레시피만 상세 조회
        meals = data["meals"][:1]
        results = []
        for meal in meals:
            detail_url = f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal['idMeal']}"
            detail_resp = requests.get(detail_url, timeout=8)
            detail_data = detail_resp.json()

            if not detail_data.get("meals"):
                continue

            m = detail_data["meals"][0]
            ingredients = []
            for i in range(1, 21):
                ing = (m.get(f"strIngredient{i}") or "").strip()
                meas = (m.get(f"strMeasure{i}") or "").strip()
                if ing:
                    ingredients.append(f"{meas} {ing}".strip())

            instructions = (m.get("strInstructions") or "").strip()
            results.append({
                "name": m["strMeal"],
                "category": m.get("strCategory", ""),
                "area": m.get("strArea", ""),
                "ingredients": ingredients,
                "instructions": instructions[:800],
            })

        if not results:
            return f"MEALDB_NOT_FOUND: '{ingredient}'의 상세 레시피를 가져올 수 없습니다."

        output_lines = [f"TheMealDB 검색 결과 ({len(results)}개):"]
        for r in results:
            output_lines.append(f"\n## {r['name']} ({r['area']} / {r['category']})")
            output_lines.append(f"재료: {', '.join(r['ingredients'][:10])}")
            output_lines.append(f"조리법: {r['instructions']}")
        return "\n".join(output_lines)

    except Exception as e:
        return f"MEALDB_ERROR: TheMealDB 검색 오류 — {str(e)}"


# ── Tool 2: Open Food Facts 영양 정보 조회 ───────────────────────────────────
@tool
def get_nutrition_info(ingredient: str) -> str:
    """Open Food Facts API로 재료의 영양 정보를 조회합니다.
    ingredient: 재료명 (한국어 또는 영어)
    100g 기준 칼로리, 단백질, 탄수화물, 지방을 반환합니다."""
    try:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": ingredient,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 3,
            "fields": "product_name,nutriments",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()

        products = data.get("products", [])
        # 영양 정보가 있는 첫 번째 제품 선택
        for product in products:
            nutriments = product.get("nutriments", {})
            calories = nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal")
            if calories:
                protein = nutriments.get("proteins_100g", "?")
                carbs = nutriments.get("carbohydrates_100g", "?")
                fat = nutriments.get("fat_100g", "?")
                name = product.get("product_name", ingredient)
                return (
                    f"'{ingredient}' 영양 정보 (100g 기준, 출처: {name}):\n"
                    f"- 칼로리: {round(float(calories), 1)} kcal\n"
                    f"- 단백질: {protein} g\n"
                    f"- 탄수화물: {carbs} g\n"
                    f"- 지방: {fat} g"
                )

        return (
            f"'{ingredient}'의 정확한 영양 정보를 찾지 못했습니다. "
            "일반적인 추정값을 사용해주세요."
        )

    except Exception as e:
        return f"영양 정보 조회 오류: {str(e)}. 일반적인 추정값을 사용해주세요."


# ── Tool 3: Tavily 웹 레시피 검색 ────────────────────────────────────────────
@tool
def search_web_recipe(query: str) -> str:
    """Tavily Search로 실시간 웹에서 레시피를 검색합니다.
    TheMealDB에서 결과가 없을 때 보조적으로 사용합니다.
    query: 검색할 요리 또는 재료 키워드"""
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        return "TAVILY_UNAVAILABLE: Tavily API 키가 설정되지 않았습니다."

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=tavily_key)
        results = client.search(
            query=f"{query} 레시피 만드는 법",
            max_results=3,
            search_depth="basic",
        )

        if not results.get("results"):
            return f"'{query}'에 대한 웹 레시피 검색 결과가 없습니다."

        lines = [f"웹 레시피 검색 결과 ('{query}'):"]
        for r in results["results"][:3]:
            lines.append(f"\n제목: {r.get('title', '')}")
            lines.append(f"내용: {r.get('content', '')[:400]}")
        return "\n".join(lines)

    except Exception as e:
        return f"웹 검색 오류: {str(e)}"


# ── Tool 4: LLM 직접 레시피 생성 (TheMealDB 실패 시 폴백) ─────────────────────
@tool
def generate_recipe_with_llm(ingredients: str, excluded_ingredients: str = "") -> str:
    """LLM 내부 지식으로 재료에 맞는 레시피를 직접 생성합니다.
    TheMealDB에서 레시피를 찾지 못했을 때 사용하는 폴백 도구입니다.
    ingredients: 사용 가능한 재료 목록 (쉼표로 구분)
    excluded_ingredients: 제외할 재료 목록 (쉼표로 구분, 선택사항)"""
    excluded_line = (
        f"\n반드시 제외할 재료: {excluded_ingredients}" if excluded_ingredients else ""
    )

    prompt = f"""다음 재료들로 만들 수 있는 요리 **딱 1가지**의 레시피를 상세하게 알려주세요.
여러 요리를 나열하거나 "또는", "다른 선택지" 같은 대안을 절대 제시하지 마세요.
가장 잘 어울리는 요리 하나만 골라 완성된 레시피를 작성합니다.

사용 가능한 재료: {ingredients}{excluded_line}

아래 형식을 정확히 따라 한국어로 작성해주세요:

## 요리 이름
[짧고 자연스러운 요리 이름 — 재료명을 나열하지 말고, 조리법·카테고리·주재료 1개 중심으로 작성
 좋은 예: "갈릭 스프레드", "민트 초콜릿 무스", "파인애플 볶음밥", "된장 크림파스타"
 나쁜 예: "파인애플 콜라 글레이즈와 초콜릿-민트 딥 김치-갈릭 크런치 토핑"]

## 필요한 재료
- [재료명]: [분량]
- [재료명]: [분량]

## 조리 순서
1. [1단계 — 구체적으로]
2. [2단계 — 구체적으로]
3. [계속...]

## 조리 시간
- 준비 시간: [X]분
- 조리 시간: [X]분

## 난이도
[초급 / 중급 / 고급]

## 요리 팁
[초보자를 위한 유용한 팁 1-2가지]"""

    try:
        llm = _get_llm()
        response = llm.invoke(prompt)
        return response.content
    except Exception as e:
        return f"레시피 생성 오류: {str(e)}"
