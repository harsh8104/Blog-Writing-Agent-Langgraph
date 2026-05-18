from langchain_openai import ChatOpenAI

from app.core import config  # noqa: F401

llm = ChatOpenAI(model="gpt-4.1-mini")
