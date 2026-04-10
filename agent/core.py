from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from .tools import search_mealdb, get_nutrition_info, search_web_recipe, generate_recipe_with_llm
from .prompts import SYSTEM_PROMPT

TOOLS = [search_mealdb, get_nutrition_info, search_web_recipe, generate_recipe_with_llm]


def create_recipe_agent():
    """ReAct 레시피 추천 에이전트를 생성하여 반환합니다."""
    llm = ChatOpenAI(model="gpt-5-mini", temperature=0)
    agent = create_react_agent(
        llm,
        TOOLS,
        prompt=SYSTEM_PROMPT,
    )
    return agent
