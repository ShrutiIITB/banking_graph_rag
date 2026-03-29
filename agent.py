# -*- coding: utf-8 -*-
"""
agent.py -- Simple Multi-Query Graph RAG Agent
===============================================
Pipeline:
  decompose -> generate_cypher -> execute -> generate_answer
"""

import os
import re
import json

from dotenv import load_dotenv
from falkordb import FalkorDB
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict, List

from graph_schema import get_schema_prompt

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

FALKORDB_HOST  = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT  = int(os.getenv("FALKORDB_PORT", 6379))
GRAPH_NAME     = os.getenv("GRAPH_NAME", "banking")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = os.getenv("LLM_MODEL", "gpt-4o")

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

def get_llm():
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=0,
        openai_api_key=OPENAI_API_KEY,
    )

def get_graph():
    db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    return db.select_graph(GRAPH_NAME)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class State(TypedDict):
    question:    str
    history:     List[dict]
    sub_queries: List[str]
    cypher_list: List[str]
    results:     List[str]
    answer:      str

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def llm_call(system: str, user: str) -> str:
    llm  = get_llm()
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return resp.content.strip()


def clean_cypher(text: str) -> str:
    """Strip markdown fences and whitespace from LLM output."""
    text = re.sub(r"```(?:cypher|sql|python)?", "", text, flags=re.IGNORECASE)
    return text.strip().rstrip("`").strip()


def run_cypher(cypher: str) -> str:
    """
    Execute one Cypher query against FalkorDB.
    Returns results as a plain-text string for the LLM to read.
    """
    if not cypher.strip():
        return "No query was generated."

    # Block write operations
    upper = cypher.upper()
    for kw in ("CREATE ", "MERGE ", "DELETE ", "SET ", "DROP "):
        if kw in upper:
            return "Blocked: query contains write operation ({}).".format(kw.strip())

    # Inject LIMIT if the LLM forgot it
    if "LIMIT" not in upper:
        cypher = cypher.rstrip(";").strip() + "\nLIMIT 25"

    print("[cypher full]\n{}\n".format(cypher))

    try:
        graph  = get_graph()
        result = graph.query(cypher)

        rows = result.result_set
        if not rows:
            return "Query ran successfully but returned 0 rows."

        # --- Robust header extraction ---
        # FalkorDB header can be:
        #   - a list of strings:          ["city", "count"]
        #   - a list of (name, type) tuples: [("city", 1), ("count", 1)]
        #   - None / empty
        raw_header = getattr(result, "header", None) or []
        header = []
        for h in raw_header:
            if isinstance(h, (list, tuple)):
                header.append(str(h[0]))   # first element is always the column name
            else:
                header.append(str(h))

        lines = []
        for row in rows[:25]:
            if header and len(header) == len(row):
                lines.append(str(dict(zip(header, row))))
            else:
                lines.append(str(list(row)))

        return "{} row(s) returned:\n".format(len(rows)) + "\n".join(lines)

    except Exception as e:
        return "Query error: {}".format(e)


def verify_connection():
    """Sanity-check: confirm FalkorDB has data before running the agent."""
    try:
        graph  = get_graph()
        result = graph.query("MATCH (n) RETURN count(n) AS total")
        total  = result.result_set[0][0] if result.result_set else 0
        print("[DB check] Total nodes in graph '{}': {}".format(GRAPH_NAME, total))
        if total == 0:
            print("[WARN] Graph is empty -- run ingest.py first.")
        return total > 0
    except Exception as e:
        print("[DB check] Connection error: {}".format(e))
        return False

# ---------------------------------------------------------------------------
# Node 1: Decompose
# ---------------------------------------------------------------------------

DECOMPOSE_SYSTEM = """You are a query decomposition assistant for a banking database.
Break the user question into 1 to 3 focused sub-questions.
Each sub-question must be answerable with a single database query.
If the question is simple, return exactly 1 sub-question.
Return ONLY a JSON array of strings. No markdown, no explanation.
Example: ["sub-question 1", "sub-question 2"]"""


def decompose(state: State) -> State:
    history_text = ""
    if state["history"]:
        turns = state["history"][-4:]
        history_text = "\n".join(
            "{}: {}".format(t["role"].upper(), t["content"]) for t in turns
        ) + "\n\n"

    user = "{}Question: {}".format(history_text, state["question"])
    raw  = llm_call(DECOMPOSE_SYSTEM, user)

    try:
        cleaned     = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
        sub_queries = json.loads(cleaned)
        if not isinstance(sub_queries, list) or not sub_queries:
            sub_queries = [state["question"]]
    except Exception:
        sub_queries = [state["question"]]

    sub_queries = [str(q) for q in sub_queries[:3]]
    print("[decompose] {} sub-quer(ies):".format(len(sub_queries)))
    for i, q in enumerate(sub_queries, 1):
        print("  {}: {}".format(i, q))

    return {**state, "sub_queries": sub_queries}

# ---------------------------------------------------------------------------
# Node 2: Generate Cypher
# ---------------------------------------------------------------------------

CYPHER_SYSTEM = get_schema_prompt(max_examples=10)


def generate_cypher(state: State) -> State:
    cypher_list = []
    for i, sub_q in enumerate(state["sub_queries"], 1):
        print("[cypher gen {}] {}".format(i, sub_q))
        raw    = llm_call(CYPHER_SYSTEM, "Question: {}".format(sub_q))
        cypher = clean_cypher(raw)
        cypher_list.append(cypher)

    return {**state, "cypher_list": cypher_list}

# ---------------------------------------------------------------------------
# Node 3: Execute
# ---------------------------------------------------------------------------

def execute(state: State) -> State:
    results = []
    for i, (sub_q, cypher) in enumerate(
        zip(state["sub_queries"], state["cypher_list"]), 1
    ):
        result_text = run_cypher(cypher)
        block = (
            "Sub-query {}: {}\n"
            "Result:\n{}"
        ).format(i, sub_q, result_text)
        results.append(block)
        print("[execute {}] {}".format(i, result_text.splitlines()[0]))

    return {**state, "results": results}

# ---------------------------------------------------------------------------
# Node 4: Generate answer
# ---------------------------------------------------------------------------

ANSWER_SYSTEM = """You are a helpful banking data assistant.
Use ONLY the database results below to answer the user question.
Be concise and factual. Use bullet points for lists.
If the results show 0 rows or an error, say so clearly and do not guess."""


def generate_answer(state: State) -> State:
    context = "\n\n".join(state["results"])
    user    = "Question: {}\n\nDatabase results:\n{}".format(
        state["question"], context
    )
    answer = llm_call(ANSWER_SYSTEM, user)
    print("[answer] {}".format(answer[:120]))
    return {**state, "answer": answer}

# ---------------------------------------------------------------------------
# Build LangGraph
# ---------------------------------------------------------------------------

def build_app():
    g = StateGraph(State)
    g.add_node("decompose",       decompose)
    g.add_node("generate_cypher", generate_cypher)
    g.add_node("execute",         execute)
    g.add_node("generate_answer", generate_answer)

    g.set_entry_point("decompose")
    g.add_edge("decompose",       "generate_cypher")
    g.add_edge("generate_cypher", "execute")
    g.add_edge("execute",         "generate_answer")
    g.add_edge("generate_answer", END)

    return g.compile()


_app = None

def get_app():
    global _app
    if _app is None:
        _app = build_app()
    return _app

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_agent(question: str, history: List[dict] = None) -> str:
    """
    Run the agent and return the answer string.

    Parameters
    ----------
    question : str  -- user's natural language question
    history  : list -- [{"role": "user/assistant", "content": "..."}]

    Returns
    -------
    str -- final grounded answer
    """
    state = {
        "question":    question,
        "history":     history or [],
        "sub_queries": [],
        "cypher_list": [],
        "results":     [],
        "answer":      "",
    }
    result = get_app().invoke(state)
    return result["answer"]

# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Agent Smoke Test")
    print("=" * 60)

    # 1. Check DB has data
    ok = verify_connection()
    if not ok:
        print("Stopping -- no data in graph. Run injest.py first.")
        exit(1)

    questions = [
        "How many customers are in the database?",
        "Which city has the most customers?",
        "What is the loan approval rate?",
    ]

    history = []
    for q in questions:
        print("\n" + "-" * 60)
        print("Q:", q)
        print("-" * 60)
        answer = run_agent(q, history=history)
        print("\nA:", answer)
        history.append({"role": "user",      "content": q})
        history.append({"role": "assistant", "content": answer})