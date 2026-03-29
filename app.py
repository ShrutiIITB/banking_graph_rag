# -*- coding: utf-8 -*-
"""
app.py -- Streamlit Banking Graph RAG Chatbot
=============================================
Run:  streamlit run app.py

Pages:
  - Chat       : Multi-turn RAG chatbot
  - Graph View : Interactive node/relationship explorer
"""

import os
import subprocess
import sys
import threading
import json

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", 6379))
GRAPH_NAME    = os.getenv("GRAPH_NAME", "banking")

# Node colour palette (one per label)
NODE_COLORS = {
    "Customer":    "#7F77DD",   # purple
    "Account":     "#1D9E75",   # teal
    "Transaction": "#D85A30",   # coral
    "Branch":      "#888780",   # gray
    "Loan":        "#BA7517",   # amber
    "CreditCard":  "#378ADD",   # blue
    "Feedback":    "#639922",   # green
}
DEFAULT_COLOR = "#B4B2A9"

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Banking Graph RAG",
    page_icon=":bank:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

for key, default in [
    ("chat_history",   []),
    ("ingest_log",     ""),
    ("ingest_done",    False),
    ("ingest_running", False),
    ("page",           "Chat"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=10)
def get_graph_stats():
    try:
        db    = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        g     = db.select_graph(GRAPH_NAME)
        nodes = g.query("MATCH (n) RETURN count(n) AS c").result_set
        rels  = g.query("MATCH ()-[r]->() RETURN count(r) AS c").result_set
        n = nodes[0][0] if nodes else 0
        r = rels[0][0]  if rels  else 0
        return True, n, r
    except Exception:
        return False, 0, 0


def get_falkor_graph():
    db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    return db.select_graph(GRAPH_NAME)


def query_falkor(cypher):
    """Run a read Cypher and return (header, rows)."""
    g      = get_falkor_graph()
    result = g.query(cypher)
    rows   = result.result_set or []
    raw_h  = getattr(result, "header", None) or []
    header = []
    for h in raw_h:
        header.append(str(h[0]) if isinstance(h, (list, tuple)) else str(h))
    return header, rows


def run_ingest(csv_path, reset, log_placeholder):
    st.session_state.ingest_running = True
    st.session_state.ingest_log     = ""
    cmd = [sys.executable, "ingest.py", "--csv", csv_path, "--no-smoke-test"]
    if reset:
        cmd.append("--reset")
    log_lines = []
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
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
        log_lines.append("[ERROR] {}".format(e))
    st.session_state.ingest_log     = "\n".join(log_lines)
    st.session_state.ingest_running = False
    get_graph_stats.clear()

# ---------------------------------------------------------------------------
# Sidebar (shared across pages)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Banking Graph RAG")
    st.caption("FalkorDB + LangGraph + Streamlit")
    st.divider()

    # Page navigation
    page = st.radio(
        "Navigate",
        ["Chat", "Graph View"],
        index=0 if st.session_state.page == "Chat" else 1,
        label_visibility="collapsed",
    )
    st.session_state.page = page
    st.divider()

    # DB status
    st.subheader("Database status")
    connected, node_count, rel_count = get_graph_stats()
    if connected and node_count > 0:
        st.success("FalkorDB connected")
        c1, c2 = st.columns(2)
        c1.metric("Nodes", "{:,}".format(node_count))
        c2.metric("Edges", "{:,}".format(rel_count))
    elif connected:
        st.warning("Connected -- graph empty. Ingest data below.")
    else:
        st.error("Cannot reach FalkorDB at {}:{}.".format(FALKORDB_HOST, FALKORDB_PORT))
        st.code("docker run -p 6379:6379 --rm falkordb/falkordb:latest", language="bash")

    if st.button("Refresh status"):
        get_graph_stats.clear()
        st.rerun()

    st.divider()

    # Ingest panel
    st.subheader("Ingest data")
    csv_path    = st.text_input("CSV path", value="Comprehensive_Banking_Database.csv")
    reset_graph = st.checkbox("Reset graph first", value=False)
    ingest_btn  = st.button(
        "Run Ingest",
        disabled=st.session_state.ingest_running or not connected,
        type="primary",
    )
    log_area = st.empty()
    if st.session_state.ingest_log:
        log_area.code(st.session_state.ingest_log, language="bash")

    if ingest_btn:
        if not os.path.exists(csv_path):
            st.error("File not found: {}".format(csv_path))
        else:
            log_area.code("Starting ingestion...", language="bash")
            t = threading.Thread(
                target=run_ingest, args=(csv_path, reset_graph, log_area), daemon=True
            )
            t.start()
            t.join()
            get_graph_stats.clear()
            st.rerun()

# ===========================================================================
# PAGE: CHAT
# ===========================================================================

if st.session_state.page == "Chat":
    st.header("Chatbot")

    if not connected:
        st.info("Start FalkorDB with Docker, then refresh status in the sidebar.")
        st.stop()
    if node_count == 0:
        st.info("Graph is empty. Enter the CSV path in the sidebar and click Run Ingest.")
        st.stop()

    # Sample question buttons
    st.subheader("Sample questions")
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
    cols = st.columns(4)
    for i, sample in enumerate(SAMPLES):
        if cols[i % 4].button(sample, use_container_width=True, key="s_{}".format(i)):
            st.session_state.chat_history.append({"role": "user", "content": sample})
            st.rerun()

    st.divider()

    # Chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    user_input = st.chat_input("Ask about customers, loans, transactions...")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            with st.spinner("Querying the graph..."):
                try:
                    from agent import run_agent
                    history = st.session_state.chat_history[:-1]
                    answer  = run_agent(user_input, history=history)
                except Exception as e:
                    answer = "Error: {}".format(e)
            st.markdown(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()

    if st.session_state.chat_history:
        if st.button("Clear chat"):
            st.session_state.chat_history = []
            st.rerun()

# ===========================================================================
# PAGE: GRAPH VIEW
# ===========================================================================

elif st.session_state.page == "Graph View":
    st.header("Graph Explorer")

    if not connected or node_count == 0:
        st.info("Ingest data first using the sidebar.")
        st.stop()

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    ALL_LABELS = ["Customer", "Account", "Transaction", "Branch",
                  "Loan", "CreditCard", "Feedback"]
    ALL_RELS   = ["HAS_ACCOUNT", "MADE_TRANSACTION", "AT_BRANCH",
                  "HAS_LOAN", "HAS_CARD", "GAVE_FEEDBACK"]

    col_l, col_r = st.columns([1, 3])

    with col_l:
        st.subheader("Filters")

        selected_labels = st.multiselect(
            "Node types",
            ALL_LABELS,
            default=["Customer", "Account", "Loan"],
        )

        selected_rels = st.multiselect(
            "Relationship types",
            ALL_RELS,
            default=["HAS_ACCOUNT", "HAS_LOAN"],
        )

        sample_size = st.slider(
            "Max nodes per type",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
        )

        show_labels = st.checkbox("Show node labels", value=True)
        show_props  = st.checkbox("Show properties on hover", value=True)

        st.divider()
        st.subheader("Legend")
        for label in ALL_LABELS:
            color = NODE_COLORS.get(label, DEFAULT_COLOR)
            st.markdown(
                '<span style="display:inline-block;width:14px;height:14px;'
                'border-radius:50%;background:{};margin-right:6px;'
                'vertical-align:middle"></span>{}'.format(color, label),
                unsafe_allow_html=True,
            )

        render_btn = st.button("Render graph", type="primary", use_container_width=True)

    # ------------------------------------------------------------------
    # Graph data fetch
    # ------------------------------------------------------------------

    def fetch_nodes(labels, limit):
        """Return list of node dicts {id, label, props}."""
        nodes = []
        for label in labels:
            # Choose display property per label
            prop_map = {
                "Customer":    "c.first_name + ' ' + c.last_name",
                "Account":     "a.account_type + ' (' + a.account_id + ')'",
                "Transaction": "t.type + ' $' + toString(toInteger(t.amount))",
                "Branch":      "b.branch_id",
                "Loan":        "l.type + ' (' + l.status + ')'",
                "CreditCard":  "cc.card_type + ' (' + cc.card_id + ')'",
                "Feedback":    "f.type + ' - ' + f.resolution_status",
            }
            alias_map = {
                "Customer": "c", "Account": "a", "Transaction": "t",
                "Branch": "b", "Loan": "l", "CreditCard": "cc", "Feedback": "f",
            }
            alias      = alias_map.get(label, "n")
            display_fn = prop_map.get(label, "{}.id".format(alias))

            cypher = (
                "MATCH ({alias}:{label}) "
                "RETURN id({alias}) AS nid, {display} AS display "
                "LIMIT {limit}"
            ).format(alias=alias, label=label, display=display_fn, limit=limit)

            try:
                header, rows = query_falkor(cypher)
                for row in rows:
                    nid     = row[0]
                    display = str(row[1]) if len(row) > 1 else label
                    nodes.append({"id": nid, "label": label, "display": display})
            except Exception as e:
                st.warning("Could not fetch {} nodes: {}".format(label, e))
        return nodes


    def fetch_edges(labels, rel_types):
        """Return list of edge dicts {src, tgt, rel}."""
        edges = []
        # Build a Cypher per relationship type, filtering to the selected labels
        rel_label_map = {
            "HAS_ACCOUNT":     ("Customer", "Account"),
            "MADE_TRANSACTION":("Customer", "Transaction"),
            "AT_BRANCH":       ("Transaction", "Branch"),
            "HAS_LOAN":        ("Customer", "Loan"),
            "HAS_CARD":        ("Customer", "CreditCard"),
            "GAVE_FEEDBACK":   ("Customer", "Feedback"),
        }
        for rel in rel_types:
            src_label, tgt_label = rel_label_map.get(rel, (None, None))
            if src_label not in labels or tgt_label not in labels:
                continue
            cypher = (
                "MATCH (a:{src})-[r:{rel}]->(b:{tgt}) "
                "RETURN id(a) AS src, id(b) AS tgt LIMIT 500"
            ).format(src=src_label, rel=rel, tgt=tgt_label)
            try:
                _, rows = query_falkor(cypher)
                for row in rows:
                    edges.append({"src": row[0], "tgt": row[1], "rel": rel})
            except Exception as e:
                st.warning("Could not fetch {} edges: {}".format(rel, e))
        return edges

    # ------------------------------------------------------------------
    # Build pyvis HTML
    # ------------------------------------------------------------------

    def build_graph_html(nodes, edges, show_labels, show_props):
        """
        Render an interactive graph using vis.js (loaded from CDN).
        Returns a self-contained HTML string.
        """
        # Build node set (only nodes that appear in edges, to avoid orphans,
        # but always include all fetched nodes)
        node_ids_in_edges = set()
        for e in edges:
            node_ids_in_edges.add(e["src"])
            node_ids_in_edges.add(e["tgt"])

        node_lookup = {n["id"]: n for n in nodes}

        vis_nodes = []
        for n in nodes:
            color  = NODE_COLORS.get(n["label"], DEFAULT_COLOR)
            title  = "<b>{}</b><br>{}".format(n["label"], n["display"]) if show_props else n["label"]
            lbl    = n["display"][:22] + "..." if show_labels and len(n["display"]) > 22 else (n["display"] if show_labels else "")
            vis_nodes.append({
                "id":    n["id"],
                "label": lbl,
                "title": title,
                "color": {"background": color, "border": color,
                          "highlight": {"background": color, "border": "#ffffff"}},
                "font":  {"color": "#ffffff", "size": 12},
                "shape": "dot",
                "size":  18,
            })

        vis_edges = []
        for e in edges:
            if e["src"] in node_lookup and e["tgt"] in node_lookup:
                vis_edges.append({
                    "from":   e["src"],
                    "to":     e["tgt"],
                    "label":  e["rel"],
                    "arrows": "to",
                    "color":  {"color": "#aaaaaa", "highlight": "#555555"},
                    "font":   {"size": 10, "color": "#555555", "align": "middle"},
                    "smooth": {"type": "curvedCW", "roundness": 0.1},
                })

        nodes_json = json.dumps(vis_nodes)
        edges_json = json.dumps(vis_edges)

        html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin:0; padding:0; background:#1a1a2e; }}
  #graph {{ width:100%; height:620px; border:1px solid #333; background:#1a1a2e; }}
  #info  {{ position:absolute; top:10px; right:10px; background:rgba(0,0,0,0.7);
            color:#ccc; padding:8px 12px; border-radius:6px; font-size:12px;
            font-family:sans-serif; }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="info">{node_count} nodes &nbsp;|&nbsp; {edge_count} edges</div>
<script>
  var nodes = new vis.DataSet({nodes_json});
  var edges = new vis.DataSet({edges_json});
  var container = document.getElementById("graph");
  var options = {{
    physics: {{
      enabled: true,
      solver: "forceAtlas2Based",
      forceAtlas2Based: {{
        gravitationalConstant: -60,
        centralGravity: 0.005,
        springLength: 120,
        springConstant: 0.05,
        damping: 0.4,
        avoidOverlap: 0.5
      }},
      stabilization: {{ iterations: 150, updateInterval: 25 }}
    }},
    interaction: {{
      hover: true,
      tooltipDelay: 100,
      navigationButtons: true,
      keyboard: true
    }},
    edges: {{ width: 1.2 }},
    nodes: {{ borderWidth: 1.5 }}
  }};
  var network = new vis.Network(container, {{nodes:nodes, edges:edges}}, options);

  // Freeze layout after stabilisation for performance
  network.on("stabilizationIterationsDone", function() {{
    network.setOptions({{ physics: {{ enabled: false }} }});
  }});
</script>
</body>
</html>
""".format(
            nodes_json=nodes_json,
            edges_json=edges_json,
            node_count=len(vis_nodes),
            edge_count=len(vis_edges),
        )
        return html

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    with col_r:
        if not selected_labels:
            st.info("Select at least one node type from the left panel.")
        else:
            with st.spinner("Fetching graph data..."):
                nodes = fetch_nodes(selected_labels, sample_size)
                edges = fetch_edges(selected_labels, selected_rels)

            if not nodes:
                st.warning("No nodes found for the selected types.")
            else:
                html = build_graph_html(nodes, edges, show_labels, show_props)
                components.html(html, height=640, scrolling=False)

                # Summary table below the graph
                st.divider()
                st.subheader("Node breakdown")
                from collections import Counter
                counts = Counter(n["label"] for n in nodes)
                rcounts = Counter(e["rel"] for e in edges)

                c1, c2 = st.columns(2)
                with c1:
                    st.caption("Nodes rendered")
                    for label, cnt in sorted(counts.items()):
                        color = NODE_COLORS.get(label, DEFAULT_COLOR)
                        st.markdown(
                            '<span style="display:inline-block;width:12px;height:12px;'
                            'border-radius:50%;background:{};margin-right:6px;'
                            'vertical-align:middle"></span>'
                            '**{}**: {}'.format(color, label, cnt),
                            unsafe_allow_html=True,
                        )
                with c2:
                    st.caption("Edges rendered")
                    for rel, cnt in sorted(rcounts.items()):
                        st.markdown("**{}**: {}".format(rel, cnt))

    # ------------------------------------------------------------------
    # Raw Cypher explorer (expander below graph)
    # ------------------------------------------------------------------

    st.divider()
    with st.expander("Raw Cypher explorer"):
        st.caption(
            "Run any read-only Cypher query and see the results as a table. "
            "Write operations (CREATE, MERGE, DELETE, SET) are blocked."
        )
        cypher_input = st.text_area(
            "Cypher query",
            value=(
                "MATCH (c:Customer)-[:HAS_ACCOUNT]->(a:Account)\n"
                "RETURN c.first_name, c.last_name, a.account_type, a.balance\n"
                "LIMIT 10"
            ),
            height=120,
        )
        if st.button("Run query"):
            upper = cypher_input.upper()
            blocked = [kw for kw in ("CREATE ", "MERGE ", "DELETE ", "SET ", "DROP ") if kw in upper]
            if blocked:
                st.error("Blocked: query contains write operation(s): {}".format(blocked))
            else:
                try:
                    header, rows = query_falkor(cypher_input)
                    if rows:
                        import pandas as pd
                        df = pd.DataFrame(rows, columns=header if header else None)
                        st.dataframe(df, use_container_width=True)
                        st.caption("{} row(s) returned.".format(len(rows)))
                    else:
                        st.info("Query returned 0 rows.")
                except Exception as e:
                    st.error("Query error: {}".format(e))