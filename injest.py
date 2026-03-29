# -*- coding: utf-8 -*-
"""
ingest.py -- Banking CSV -> FalkorDB Graph Ingestion
=====================================================
Reads Comprehensive_Banking_Database.csv (40 columns) and builds a
property graph in FalkorDB.

Graph schema
------------
Nodes:
  (:Customer    {customer_id, first_name, last_name, age, gender,
                 address, city, contact_number, email, anomaly})
  (:Account     {account_id, account_type, balance,
                 date_opened, last_transaction_date})
  (:Transaction {transaction_id, date, type, amount, balance_after})
  (:Branch      {branch_id})
  (:Loan        {loan_id, amount, type, interest_rate, term,
                 status, approval_rejection_date})
  (:CreditCard  {card_id, card_type, credit_limit, balance,
                 min_payment_due, payment_due_date,
                 last_payment_date, rewards_points})
  (:Feedback    {feedback_id, date, type,
                 resolution_status, resolution_date})

Relationships:
  (Customer)-[:HAS_ACCOUNT]     ->(Account)
  (Customer)-[:MADE_TRANSACTION]->(Transaction)
  (Transaction)-[:AT_BRANCH]    ->(Branch)
  (Customer)-[:HAS_LOAN]        ->(Loan)
  (Customer)-[:HAS_CARD]        ->(CreditCard)
  (Customer)-[:GAVE_FEEDBACK]   ->(Feedback)

Usage
-----
  python ingest.py                  # read local CSV (default name)
  python ingest.py --csv path/to/file.csv
  python ingest.py --url            # download from GitHub
  python ingest.py --reset          # wipe graph then re-ingest
  python ingest.py --no-smoke-test  # skip sample queries

Prerequisites
-------------
  pip install falkordb pandas requests tqdm python-dotenv
  docker run -p 6379:6379 --rm falkordb/falkordb:latest
"""

import argparse
import io
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from falkordb import FalkorDB
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------



FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", 6379))
GRAPH_NAME    = os.getenv("GRAPH_NAME", "banking")
BATCH_SIZE    = 500

DATASET_URL = (
    "https://raw.githubusercontent.com/ahsan084/"
    "Banking-Dataset/main/Comprehensive_Banking_Database.csv"
)

# All 40 columns exactly as they appear in the CSV header
EXPECTED_COLUMNS = [
    "Customer ID",
    "First Name",
    "Last Name",
    "Age",
    "Gender",
    "Address",
    "City",
    "Contact Number",
    "Email",
    "Account Type",
    "Account Balance",
    "Date Of Account Opening",
    "Last Transaction Date",
    "TransactionID",
    "Transaction Date",
    "Transaction Type",
    "Transaction Amount",
    "Account Balance After Transaction",
    "Branch ID",
    "Loan ID",
    "Loan Amount",
    "Loan Type",
    "Interest Rate",
    "Loan Term",
    "Approval/Rejection Date",
    "Loan Status",
    "CardID",
    "Card Type",
    "Credit Limit",
    "Credit Card Balance",
    "Minimum Payment Due",
    "Payment Due Date",
    "Last Credit Card Payment Date",
    "Rewards Points",
    "Feedback ID",
    "Feedback Date",
    "Feedback Type",
    "Resolution Status",
    "Resolution Date",
    "Anomaly",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_str(val):
    """Return a clean string, or empty string for NaN/None."""
    if pd.isna(val):
        return ""
    return str(val).strip()


def _fmt_date(series):
    """Parse a date series and return ISO YYYY-MM-DD strings."""
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d").fillna("")


def _batch_execute(graph, query, rows, label):
    """Run an UNWIND query in BATCH_SIZE chunks with a tqdm progress bar."""
    total = len(rows)
    with tqdm(total=total, desc="  {:<20}".format(label), unit="rows") as pbar:
        for start in range(0, total, BATCH_SIZE):
            chunk = rows[start : start + BATCH_SIZE]
            graph.query(query, {"rows": chunk})
            pbar.update(len(chunk))


# ---------------------------------------------------------------------------
# Step 1 -- Load CSV
# ---------------------------------------------------------------------------

def load_csv(csv_path, from_url):
    if from_url:
        print("[INFO] Downloading dataset from GitHub ...")
        resp = requests.get(DATASET_URL, timeout=30)
        resp.raise_for_status()
        raw = io.StringIO(resp.text)
        df  = pd.read_csv(raw)
        print("[INFO] Downloaded {:,} rows.".format(len(df)))
    else:
        path = Path(csv_path)
        if not path.exists():
            sys.exit("[ERROR] File not found: {}".format(path))
        print("[INFO] Reading {} ...".format(path.name))
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
        print("[INFO] Loaded {:,} rows.".format(len(df)))

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    missing = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing:
        print("[WARN] Some expected columns not found in CSV:")
        for col in sorted(missing):
            print("       - {}".format(col))
        print("       Proceeding with available columns.")

    return df


# ---------------------------------------------------------------------------
# Step 2 -- Clean & normalise
# ---------------------------------------------------------------------------

def clean_df(df):
    print("[INFO] Cleaning and normalising data ...")

    before = len(df)
    df = df.dropna(subset=["Customer ID"])
    if before - len(df):
        print("[INFO] Dropped {:,} rows with null Customer ID.".format(before - len(df)))

    # --- Customer fields ---
    df["Customer ID"]      = df["Customer ID"].astype(str).str.strip()
    df["First Name"]       = df["First Name"].fillna("").astype(str).str.strip()
    df["Last Name"]        = df["Last Name"].fillna("").astype(str).str.strip()
    df["Age"]              = pd.to_numeric(df.get("Age"), errors="coerce").fillna(0).astype(int)
    df["Gender"]           = df["Gender"].fillna("").astype(str).str.strip()
    df["Address"]          = df["Address"].fillna("").astype(str).str.strip()
    df["City"]             = df["City"].fillna("").astype(str).str.strip()
    df["Contact Number"]   = df["Contact Number"].fillna("").astype(str).str.strip()
    df["Email"]            = df["Email"].fillna("").astype(str).str.strip()
    df["Anomaly"]          = df["Anomaly"].fillna("").astype(str).str.strip()

    # --- Account fields ---
    df["Account Type"]           = df["Account Type"].fillna("").astype(str).str.strip()
    df["Account Balance"]        = pd.to_numeric(df.get("Account Balance"), errors="coerce").fillna(0.0)
    df["Date Of Account Opening"]= _fmt_date(df.get("Date Of Account Opening"))
    df["Last Transaction Date"]  = _fmt_date(df.get("Last Transaction Date"))

    # --- Transaction fields ---
    df["TransactionID"]                    = df["TransactionID"].fillna("").astype(str).str.strip()
    df["Transaction Date"]                 = _fmt_date(df.get("Transaction Date"))
    df["Transaction Type"]                 = df["Transaction Type"].fillna("").astype(str).str.strip()
    df["Transaction Amount"]               = pd.to_numeric(df.get("Transaction Amount"), errors="coerce").fillna(0.0)
    df["Account Balance After Transaction"]= pd.to_numeric(df.get("Account Balance After Transaction"), errors="coerce").fillna(0.0)

    # --- Branch ---
    df["Branch ID"] = df["Branch ID"].fillna("").astype(str).str.strip()

    # --- Loan fields ---
    df["Loan ID"]                = df["Loan ID"].fillna("").astype(str).str.strip()
    df["Loan Amount"]            = pd.to_numeric(df.get("Loan Amount"), errors="coerce").fillna(0.0)
    df["Loan Type"]              = df["Loan Type"].fillna("").astype(str).str.strip()
    df["Interest Rate"]          = pd.to_numeric(df.get("Interest Rate"), errors="coerce").fillna(0.0)
    df["Loan Term"]              = pd.to_numeric(df.get("Loan Term"), errors="coerce").fillna(0).astype(int)
    df["Approval/Rejection Date"]= _fmt_date(df.get("Approval/Rejection Date"))
    df["Loan Status"]            = df["Loan Status"].fillna("").astype(str).str.strip()

    # --- Credit card fields ---
    df["CardID"]                     = df["CardID"].fillna("").astype(str).str.strip()
    df["Card Type"]                  = df["Card Type"].fillna("").astype(str).str.strip()
    df["Credit Limit"]               = pd.to_numeric(df.get("Credit Limit"), errors="coerce").fillna(0.0)
    df["Credit Card Balance"]        = pd.to_numeric(df.get("Credit Card Balance"), errors="coerce").fillna(0.0)
    df["Minimum Payment Due"]        = pd.to_numeric(df.get("Minimum Payment Due"), errors="coerce").fillna(0.0)
    df["Payment Due Date"]           = _fmt_date(df.get("Payment Due Date"))
    df["Last Credit Card Payment Date"] = _fmt_date(df.get("Last Credit Card Payment Date"))
    df["Rewards Points"]             = pd.to_numeric(df.get("Rewards Points"), errors="coerce").fillna(0).astype(int)

    # --- Feedback fields ---
    df["Feedback ID"]       = df["Feedback ID"].fillna("").astype(str).str.strip()
    df["Feedback Date"]     = _fmt_date(df.get("Feedback Date"))
    df["Feedback Type"]     = df["Feedback Type"].fillna("").astype(str).str.strip()
    df["Resolution Status"] = df["Resolution Status"].fillna("").astype(str).str.strip()
    df["Resolution Date"]   = _fmt_date(df.get("Resolution Date"))

    # Synthesise account_id: customer + account type (no dedicated account key in CSV)
    df["account_id"] = df["Customer ID"] + "_" + df["Account Type"]

    df = df.reset_index(drop=True)
    print("[INFO] {:,} rows ready for ingestion.".format(len(df)))
    return df


# ---------------------------------------------------------------------------
# Step 3 -- Connect to FalkorDB
# ---------------------------------------------------------------------------

def connect_graph(reset):
    print("[INFO] Connecting to FalkorDB at {}:{} ...".format(FALKORDB_HOST, FALKORDB_PORT))
    try:
        db    = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        graph = db.select_graph(GRAPH_NAME)
    except Exception as exc:
        sys.exit(
            "[ERROR] Cannot connect to FalkorDB: {}\n"
            "        Ensure Docker is running:\n"
            "        docker run -p 6379:6379 --rm falkordb/falkordb:latest".format(exc)
        )

    if reset:
        print("[INFO] --reset: deleting graph '{}' ...".format(GRAPH_NAME))
        try:
            graph.delete()
        except Exception:
            pass
        graph = db.select_graph(GRAPH_NAME)
        print("[INFO] Graph cleared.")

    print("[INFO] Connected -> graph: '{}'".format(GRAPH_NAME))
    return graph


# ---------------------------------------------------------------------------
# Step 4 -- Create indexes
# ---------------------------------------------------------------------------

def create_indexes(graph):
    print("[INFO] Creating indexes ...")
    indexes = [
        ("Customer",    "customer_id"),
        ("Account",     "account_id"),
        ("Transaction", "transaction_id"),
        ("Branch",      "branch_id"),
        ("Loan",        "loan_id"),
        ("CreditCard",  "card_id"),
        ("Feedback",    "feedback_id"),
    ]
    for label, prop in indexes:
        try:
            graph.query("CREATE INDEX FOR (n:{}) ON (n.{})".format(label, prop))
            print("[INFO]   Index created  : {}.{}".format(label, prop))
        except Exception as exc:
            msg = str(exc).lower()
            if "already indexed" in msg or "equivalent index" in msg:
                print("[INFO]   Index exists   : {}.{}".format(label, prop))
            else:
                print("[WARN]   Index skipped  : {}.{} -- {}".format(label, prop, exc))


# ---------------------------------------------------------------------------
# Step 5 -- Ingest nodes
# ---------------------------------------------------------------------------

def ingest_customers(graph, df):
    print("[INFO] Ingesting Customer nodes ...")
    cols = ["Customer ID", "First Name", "Last Name", "Age", "Gender",
            "Address", "City", "Contact Number", "Email", "Anomaly"]
    records = (
        df[cols]
        .drop_duplicates(subset=["Customer ID"])
        .rename(columns={
            "Customer ID":    "customer_id",
            "First Name":     "first_name",
            "Last Name":      "last_name",
            "Age":            "age",
            "Gender":         "gender",
            "Address":        "address",
            "City":           "city",
            "Contact Number": "contact_number",
            "Email":          "email",
            "Anomaly":        "anomaly",
        })
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MERGE (c:Customer {customer_id: row.customer_id})
    SET   c.first_name      = row.first_name,
          c.last_name       = row.last_name,
          c.age             = row.age,
          c.gender          = row.gender,
          c.address         = row.address,
          c.city            = row.city,
          c.contact_number  = row.contact_number,
          c.email           = row.email,
          c.anomaly         = row.anomaly
    """
    _batch_execute(graph, query, records, "Customers")


def ingest_accounts(graph, df):
    print("[INFO] Ingesting Account nodes ...")
    cols = ["account_id", "Account Type", "Account Balance",
            "Date Of Account Opening", "Last Transaction Date"]
    records = (
        df[cols]
        .drop_duplicates(subset=["account_id"])
        .rename(columns={
            "Account Type":            "account_type",
            "Account Balance":         "balance",
            "Date Of Account Opening": "date_opened",
            "Last Transaction Date":   "last_transaction_date",
        })
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MERGE (a:Account {account_id: row.account_id})
    SET   a.account_type          = row.account_type,
          a.balance                = row.balance,
          a.date_opened            = row.date_opened,
          a.last_transaction_date  = row.last_transaction_date
    """
    _batch_execute(graph, query, records, "Accounts")


def ingest_branches(graph, df):
    print("[INFO] Ingesting Branch nodes ...")
    records = (
        df[["Branch ID"]]
        .drop_duplicates()
        .rename(columns={"Branch ID": "branch_id"})
        .query("branch_id != ''")
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MERGE (b:Branch {branch_id: row.branch_id})
    """
    _batch_execute(graph, query, records, "Branches")


def ingest_transactions(graph, df):
    print("[INFO] Ingesting Transaction nodes ...")
    # Only rows that actually have a TransactionID
    tx_df = df[df["TransactionID"] != ""].copy()
    cols = {
        "TransactionID":                    "transaction_id",
        "Transaction Date":                 "date",
        "Transaction Type":                 "type",
        "Transaction Amount":               "amount",
        "Account Balance After Transaction":"balance_after",
    }
    records = (
        tx_df[list(cols.keys())]
        .drop_duplicates(subset=["TransactionID"])
        .rename(columns=cols)
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MERGE (t:Transaction {transaction_id: row.transaction_id})
    SET   t.date          = row.date,
          t.type          = row.type,
          t.amount        = row.amount,
          t.balance_after = row.balance_after
    """
    _batch_execute(graph, query, records, "Transactions")


def ingest_loans(graph, df):
    print("[INFO] Ingesting Loan nodes ...")
    loan_df = df[df["Loan ID"] != ""].copy()
    cols = {
        "Loan ID":                "loan_id",
        "Loan Amount":            "amount",
        "Loan Type":              "type",
        "Interest Rate":          "interest_rate",
        "Loan Term":              "term",
        "Approval/Rejection Date":"approval_rejection_date",
        "Loan Status":            "status",
    }
    records = (
        loan_df[list(cols.keys())]
        .drop_duplicates(subset=["Loan ID"])
        .rename(columns=cols)
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MERGE (l:Loan {loan_id: row.loan_id})
    SET   l.amount                  = row.amount,
          l.type                    = row.type,
          l.interest_rate           = row.interest_rate,
          l.term                    = row.term,
          l.approval_rejection_date = row.approval_rejection_date,
          l.status                  = row.status
    """
    _batch_execute(graph, query, records, "Loans")


def ingest_credit_cards(graph, df):
    print("[INFO] Ingesting CreditCard nodes ...")
    card_df = df[df["CardID"] != ""].copy()
    cols = {
        "CardID":                       "card_id",
        "Card Type":                    "card_type",
        "Credit Limit":                 "credit_limit",
        "Credit Card Balance":          "balance",
        "Minimum Payment Due":          "min_payment_due",
        "Payment Due Date":             "payment_due_date",
        "Last Credit Card Payment Date":"last_payment_date",
        "Rewards Points":               "rewards_points",
    }
    records = (
        card_df[list(cols.keys())]
        .drop_duplicates(subset=["CardID"])
        .rename(columns=cols)
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MERGE (cc:CreditCard {card_id: row.card_id})
    SET   cc.card_type        = row.card_type,
          cc.credit_limit     = row.credit_limit,
          cc.balance          = row.balance,
          cc.min_payment_due  = row.min_payment_due,
          cc.payment_due_date = row.payment_due_date,
          cc.last_payment_date= row.last_payment_date,
          cc.rewards_points   = row.rewards_points
    """
    _batch_execute(graph, query, records, "CreditCards")


def ingest_feedback(graph, df):
    print("[INFO] Ingesting Feedback nodes ...")
    fb_df = df[df["Feedback ID"] != ""].copy()
    cols = {
        "Feedback ID":      "feedback_id",
        "Feedback Date":    "date",
        "Feedback Type":    "type",
        "Resolution Status":"resolution_status",
        "Resolution Date":  "resolution_date",
    }
    records = (
        fb_df[list(cols.keys())]
        .drop_duplicates(subset=["Feedback ID"])
        .rename(columns=cols)
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MERGE (f:Feedback {feedback_id: row.feedback_id})
    SET   f.date              = row.date,
          f.type              = row.type,
          f.resolution_status = row.resolution_status,
          f.resolution_date   = row.resolution_date
    """
    _batch_execute(graph, query, records, "Feedback")


# ---------------------------------------------------------------------------
# Step 6 -- Ingest relationships
# ---------------------------------------------------------------------------

def ingest_has_account(graph, df):
    records = (
        df[["Customer ID", "account_id"]]
        .drop_duplicates()
        .rename(columns={"Customer ID": "customer_id"})
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (a:Account  {account_id:  row.account_id})
    MERGE (c)-[:HAS_ACCOUNT]->(a)
    """
    _batch_execute(graph, query, records, "HAS_ACCOUNT")


def ingest_made_transaction(graph, df):
    tx_df = df[df["TransactionID"] != ""].copy()
    records = (
        tx_df[["Customer ID", "TransactionID", "Branch ID"]]
        .drop_duplicates(subset=["TransactionID"])
        .rename(columns={
            "Customer ID":    "customer_id",
            "TransactionID":  "transaction_id",
            "Branch ID":      "branch_id",
        })
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer    {customer_id:    row.customer_id})
    MATCH (t:Transaction {transaction_id: row.transaction_id})
    MERGE (c)-[:MADE_TRANSACTION]->(t)
    WITH t, row
    MATCH (b:Branch {branch_id: row.branch_id})
    MERGE (t)-[:AT_BRANCH]->(b)
    """
    _batch_execute(graph, query, records, "MADE_TXN + AT_BRANCH")


def ingest_has_loan(graph, df):
    loan_df = df[df["Loan ID"] != ""].copy()
    records = (
        loan_df[["Customer ID", "Loan ID"]]
        .drop_duplicates(subset=["Loan ID"])
        .rename(columns={"Customer ID": "customer_id", "Loan ID": "loan_id"})
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (l:Loan     {loan_id:     row.loan_id})
    MERGE (c)-[:HAS_LOAN]->(l)
    """
    _batch_execute(graph, query, records, "HAS_LOAN")


def ingest_has_card(graph, df):
    card_df = df[df["CardID"] != ""].copy()
    records = (
        card_df[["Customer ID", "CardID"]]
        .drop_duplicates(subset=["CardID"])
        .rename(columns={"Customer ID": "customer_id", "CardID": "card_id"})
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer   {customer_id: row.customer_id})
    MATCH (cc:CreditCard {card_id:    row.card_id})
    MERGE (c)-[:HAS_CARD]->(cc)
    """
    _batch_execute(graph, query, records, "HAS_CARD")


def ingest_gave_feedback(graph, df):
    fb_df = df[df["Feedback ID"] != ""].copy()
    records = (
        fb_df[["Customer ID", "Feedback ID"]]
        .drop_duplicates(subset=["Feedback ID"])
        .rename(columns={"Customer ID": "customer_id", "Feedback ID": "feedback_id"})
        .to_dict("records")
    )
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (f:Feedback  {feedback_id: row.feedback_id})
    MERGE (c)-[:GAVE_FEEDBACK]->(f)
    """
    _batch_execute(graph, query, records, "GAVE_FEEDBACK")


def ingest_relationships(graph, df):
    print("[INFO] Ingesting relationships ...")
    ingest_has_account(graph, df)
    ingest_made_transaction(graph, df)
    ingest_has_loan(graph, df)
    ingest_has_card(graph, df)
    ingest_gave_feedback(graph, df)


# ---------------------------------------------------------------------------
# Step 7 -- Verify
# ---------------------------------------------------------------------------

def verify(graph):
    print("\n[INFO] Verification counts ...")
    node_checks = [
        ("Customer nodes",    "MATCH (n:Customer)    RETURN count(n) AS cnt"),
        ("Account nodes",     "MATCH (n:Account)     RETURN count(n) AS cnt"),
        ("Transaction nodes", "MATCH (n:Transaction) RETURN count(n) AS cnt"),
        ("Branch nodes",      "MATCH (n:Branch)      RETURN count(n) AS cnt"),
        ("Loan nodes",        "MATCH (n:Loan)        RETURN count(n) AS cnt"),
        ("CreditCard nodes",  "MATCH (n:CreditCard)  RETURN count(n) AS cnt"),
        ("Feedback nodes",    "MATCH (n:Feedback)    RETURN count(n) AS cnt"),
    ]
    rel_checks = [
        ("HAS_ACCOUNT edges",      "MATCH ()-[r:HAS_ACCOUNT]->()      RETURN count(r) AS cnt"),
        ("MADE_TRANSACTION edges", "MATCH ()-[r:MADE_TRANSACTION]->() RETURN count(r) AS cnt"),
        ("AT_BRANCH edges",        "MATCH ()-[r:AT_BRANCH]->()        RETURN count(r) AS cnt"),
        ("HAS_LOAN edges",         "MATCH ()-[r:HAS_LOAN]->()         RETURN count(r) AS cnt"),
        ("HAS_CARD edges",         "MATCH ()-[r:HAS_CARD]->()         RETURN count(r) AS cnt"),
        ("GAVE_FEEDBACK edges",    "MATCH ()-[r:GAVE_FEEDBACK]->()    RETURN count(r) AS cnt"),
    ]
    print("  --- Nodes ---")
    for label, cypher in node_checks:
        result = graph.query(cypher)
        count  = result.result_set[0][0] if result.result_set else 0
        print("  {:<28} {:>8,}".format(label, count))
    print("  --- Relationships ---")
    for label, cypher in rel_checks:
        result = graph.query(cypher)
        count  = result.result_set[0][0] if result.result_set else 0
        print("  {:<28} {:>8,}".format(label, count))


# ---------------------------------------------------------------------------
# Step 8 -- Smoke-test queries
# ---------------------------------------------------------------------------

def smoke_test(graph):
    print("\n[INFO] Smoke-test queries ...")
    tests = [
        (
            "Top 5 cities by number of customers",
            """
            MATCH (c:Customer)
            RETURN c.city AS city, count(c) AS total
            ORDER BY total DESC LIMIT 5
            """,
        ),
        (
            "Loan status breakdown",
            """
            MATCH (l:Loan)
            RETURN l.status AS status, count(l) AS total
            ORDER BY total DESC
            """,
        ),
        (
            "Average credit limit by card type",
            """
            MATCH (cc:CreditCard)
            RETURN cc.card_type AS card_type,
                   round(avg(cc.credit_limit)) AS avg_limit
            ORDER BY avg_limit DESC
            """,
        ),
        (
            "Feedback resolution rate",
            """
            MATCH (f:Feedback)
            RETURN f.resolution_status AS status, count(f) AS total
            ORDER BY total DESC
            """,
        ),
        (
            "Customers flagged as anomaly",
            """
            MATCH (c:Customer)
            WHERE c.anomaly <> '' AND c.anomaly <> 'None'
            RETURN c.anomaly AS anomaly_type, count(c) AS total
            ORDER BY total DESC LIMIT 5
            """,
        ),
        (
            "Top 5 branches by transaction volume",
            """
            MATCH (t:Transaction)-[:AT_BRANCH]->(b:Branch)
            RETURN b.branch_id AS branch, count(t) AS total
            ORDER BY total DESC LIMIT 5
            """,
        ),
    ]
    for title, cypher in tests:
        print("\n  [{}]".format(title))
        try:
            result = graph.query(cypher)
            for row in result.result_set[:5]:
                print("    {}".format(row))
        except Exception as exc:
            print("  [WARN] Query failed: {}".format(exc))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Ingest the Comprehensive Banking CSV (40 columns) into FalkorDB."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--csv",
        metavar="PATH",
        default="Comprehensive_Banking_Database.csv",
        help="Path to local CSV (default: Comprehensive_Banking_Database.csv)",
    )
    source.add_argument(
        "--url",
        action="store_true",
        help="Download CSV directly from GitHub.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete the existing graph before ingesting.",
    )
    parser.add_argument(
        "--no-smoke-test",
        action="store_true",
        help="Skip sample queries at the end.",
    )
    return parser.parse_args()


def main():
    args  = parse_args()
    start = time.time()

    print("=" * 60)
    print("  Banking Graph RAG -- Data Ingestion (40-column schema)")
    print("=" * 60)

    df    = load_csv(csv_path=args.csv, from_url=args.url)
    df    = clean_df(df)
    graph = connect_graph(reset=args.reset)

    create_indexes(graph)

    # Nodes first
    ingest_customers(graph, df)
    ingest_accounts(graph, df)
    ingest_branches(graph, df)
    ingest_transactions(graph, df)
    ingest_loans(graph, df)
    ingest_credit_cards(graph, df)
    ingest_feedback(graph, df)

    # Relationships after all nodes exist
    ingest_relationships(graph, df)

    verify(graph)

    if not args.no_smoke_test:
        smoke_test(graph)

    elapsed = time.time() - start
    print("\n[DONE] Ingestion complete in {:.1f}s".format(elapsed))
    print("[DONE] Graph '{}' is ready for querying.".format(GRAPH_NAME))


if __name__ == "__main__":
    main()