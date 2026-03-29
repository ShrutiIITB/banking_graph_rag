# -*- coding: utf-8 -*-
"""
app.py -- Streamlit Banking Graph RAG Chatbot
=============================================
Run:  streamlit run app.py
"""

import os
import subprocess
import sys
import threading

import streamlit as st
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", 6379))
GRAPH_NAME    = os.getenv("GRAPH_NAME", "banking")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Banking Graph RAG",
    page_icon=":bank:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []          # [{"role": ..., "content": ...}]

if "ingest_log"   not in st.session_state:
    st.session_state.ingest_log = ""

if "ingest_done"  not in st.session_state:
    st.session_state.ingest_done = False

if "ingest_running" not in st.session_state:
    st.session_state.ingest_running = False

# ---------------------------------------------------------------------------
# Helper: check FalkorDB connection & node count
# ---------------------------------------------------------------------------

@st.cache_data(ttl=10)
def get_graph_stats():
    """Return (connected: bool, node_count: int, rel_count: int)."""
    try:
        db    = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        graph = db.select_graph(GRAPH_NAME)
        nodes = graph.query("MATCH (n) RETURN count(n) AS c").result_set
        rels  = graph.query("MATCH ()-[r]->() RETURN count(r) AS c").result_set
        n = nodes[0][0] if nodes else 0
        r = rels[0][0]  if rels  else 0
        return True, n, r
    except Exception as e:
        return False, 0, 0

# ---------------------------------------------------------------------------
# Helper: run ingest.py in a subprocess and stream output
# ---------------------------------------------------------------------------

def run_ingest(csv_path: str, reset: bool, log_placeholder):
    """Runs injest.py as a subprocess, streaming output into the placeholder."""
    st.session_state.ingest_running = True
    st.session_state.ingest_log     = ""

    cmd = [sys.executable, "injest.py"]
    if csv_path:
        cmd += ["--csv", csv_path]
    if reset:
        cmd += ["--reset"]
    cmd += ["--no-smoke-test"]

    log_lines = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        for line in proc.stdout:
            log_lines.append(line.rstrip())
            log_placeholder.code("\n".join(log_lines), language="bash")
        proc.wait()
        if proc.returncode == 0:
            log_lines.append("\n[DONE] Ingestion complete.")
            st.session_state.ingest_done = True
        else:
            log_lines.append("\n[ERROR] ingest.py exited with code {}.".format(proc.returncode))
    except Exception as e:
        log_lines.append("[ERROR] Could not run ingest.py: {}".format(e))

    st.session_state.ingest_log     = "\n".join(log_lines)
    st.session_state.ingest_running = False
    get_graph_stats.clear()          # bust the cache so stats refresh

# ---------------------------------------------------------------------------
# Sidebar -- Setup & Data Ingestion
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Banking Graph RAG")
    st.caption("FalkorDB + LangGraph + Streamlit")

    st.divider()

    # -- Connection status
    st.subheader("1. Database status")
    connected, node_count, rel_count = get_graph_stats()

    if connected:
        if node_count > 0:
            st.success("FalkorDB connected")
            col1, col2 = st.columns(2)
            col1.metric("Nodes", "{:,}".format(node_count))
            col2.metric("Relationships", "{:,}".format(rel_count))
        else:
            st.warning("FalkorDB connected -- graph is empty. Ingest data below.")
    else:
        st.error(
            "Cannot reach FalkorDB at {}:{}.\n\n"
            "Run:\n```\ndocker run -p 6379:6379 --rm falkordb/falkordb:latest\n```".format(
                FALKORDB_HOST, FALKORDB_PORT
            )
        )

    if st.button("Refresh status"):
        get_graph_stats.clear()
        st.rerun()

    st.divider()

    # -- Data ingestion
    st.subheader("2. Ingest data")

    csv_path = st.text_input(
        "CSV file path",
        value="Comprehensive_Banking_Database.csv",
        help="Path to the CSV relative to this script, or absolute path.",
    )

    reset_graph = st.checkbox(
        "Reset graph before ingesting",
        value=False,
        help="Wipes all existing nodes and relationships before loading.",
    )

    ingest_btn = st.button(
        "Run Ingest",
        disabled=st.session_state.ingest_running or not connected,
        type="primary",
    )

    log_area = st.empty()

    # Show previous log if available
    if st.session_state.ingest_log:
        log_area.code(st.session_state.ingest_log, language="bash")

    if ingest_btn:
        # Validate CSV path
        if not os.path.exists(csv_path):
            st.error("File not found: {}".format(csv_path))
        else:
            st.session_state.ingest_log = ""
            log_area.code("Starting ingestion...", language="bash")
            # Run in a thread so Streamlit doesn't freeze
            t = threading.Thread(
                target=run_ingest,
                args=(csv_path, reset_graph, log_area),
                daemon=True,
            )
            t.start()
            t.join()          # block until done so the log fully appears
            get_graph_stats.clear()
            st.rerun()

    st.divider()

    # -- Sample questions
    st.subheader("3. Try a question")
    SAMPLES = [
        "How many customers are there?",
        "Which city has the most customers?",
        "What is the loan approval rate?",
        "Which card type has the highest average credit limit?",
        "Show customers flagged as anomalies.",
        "How many unresolved complaints are there?",
        "What is the average account balance by account type?",
        "Which branch processed the most transactions?",
    ]
    for sample in SAMPLES:
        if st.button(sample, use_container_width=True):
            st.session_state.chat_history.append(
                {"role": "user", "content": sample}
            )
            st.rerun()

    st.divider()
    if st.button("Clear chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

# ---------------------------------------------------------------------------
# Main area -- Chat interface
# ---------------------------------------------------------------------------

st.header("Banking Graph RAG Chatbot")

if not connected:
    st.info("Start FalkorDB with Docker, then refresh the status in the sidebar.")
    st.stop()

if connected and node_count == 0:
    st.info(
        "The graph is empty. Enter the CSV path in the sidebar and click **Run Ingest**."
    )
    st.stop()

# Render chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Ask a question about customers, loans, transactions...")

if user_input:
    # Display user message immediately
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run agent and display answer
    with st.chat_message("assistant"):
        with st.spinner("Querying the graph..."):
            try:
                from agent import run_agent
                # Pass all prior turns except the one we just added
                history = st.session_state.chat_history[:-1]
                answer  = run_agent(user_input, history=history)
            except Exception as e:
                answer = "Error running agent: {}".format(e)
        st.markdown(answer)

    st.session_state.chat_history.append({"role": "assistant", "content": answer})
    st.rerun()