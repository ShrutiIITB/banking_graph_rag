# -*- coding: utf-8 -*-
"""
graph_schema.py -- FalkorDB Graph Schema & Few-Shot Cypher Examples
====================================================================
Single source of truth for:
  1. SCHEMA_TEXT       -- plain-English schema injected into LLM prompts
  2. CYPHER_EXAMPLES   -- few-shot (question, cypher) pairs for the LLM
  3. Helper accessors  -- get_schema_prompt(), get_few_shot_prompt()

Used by agent.py to build the Cypher-generation system prompt.
"""

# ---------------------------------------------------------------------------
# 1. Node definitions
# ---------------------------------------------------------------------------

NODE_DEFINITIONS = {
    "Customer": {
        "description": "A bank customer. One row per unique Customer ID.",
        "properties": {
            "customer_id":    "Unique identifier for the customer.",
            "first_name":     "Customer first name.",
            "last_name":      "Customer last name.",
            "age":            "Customer age as an integer.",
            "gender":         "Gender string, e.g. 'Male', 'Female'.",
            "address":        "Street address.",
            "city":           "City of residence.",
            "contact_number": "Phone number as a string.",
            "email":          "Email address.",
            "anomaly":        "Anomaly flag string; empty string means no anomaly detected.",
        },
    },
    "Account": {
        "description": (
            "A bank account. account_id is synthesised as "
            "CustomerID + '_' + AccountType, so one customer "
            "can have multiple accounts of different types."
        ),
        "properties": {
            "account_id":             "Synthetic key: customer_id + '_' + account_type.",
            "account_type":           "Account type string, e.g. 'Savings', 'Checking'.",
            "balance":                "Current account balance as a float.",
            "date_opened":            "Date the account was opened (YYYY-MM-DD).",
            "last_transaction_date":  "Date of the most recent transaction (YYYY-MM-DD).",
        },
    },
    "Transaction": {
        "description": "A single financial transaction.",
        "properties": {
            "transaction_id": "Unique TransactionID from the CSV.",
            "date":           "Transaction date (YYYY-MM-DD).",
            "type":           "Transaction type, e.g. 'Deposit', 'Withdrawal', 'Transfer'.",
            "amount":         "Transaction amount as a float.",
            "balance_after":  "Account balance immediately after this transaction.",
        },
    },
    "Branch": {
        "description": "A bank branch.",
        "properties": {
            "branch_id": "Branch identifier string from the CSV.",
        },
    },
    "Loan": {
        "description": "A loan record associated with a customer.",
        "properties": {
            "loan_id":                  "Unique Loan ID.",
            "amount":                   "Loan principal amount as a float.",
            "type":                     "Loan type, e.g. 'Personal', 'Mortgage', 'Auto'.",
            "interest_rate":            "Annual interest rate as a float (e.g. 5.5 means 5.5%).",
            "term":                     "Loan term in months as an integer.",
            "approval_rejection_date":  "Date of approval or rejection (YYYY-MM-DD).",
            "status":                   "Loan status, e.g. 'Approved', 'Rejected', 'Pending'.",
        },
    },
    "CreditCard": {
        "description": "A credit card associated with a customer.",
        "properties": {
            "card_id":           "Unique CardID.",
            "card_type":         "Card type, e.g. 'Visa', 'MasterCard', 'Amex'.",
            "credit_limit":      "Credit limit as a float.",
            "balance":           "Current credit card balance as a float.",
            "min_payment_due":   "Minimum payment due as a float.",
            "payment_due_date":  "Payment due date (YYYY-MM-DD).",
            "last_payment_date": "Date of last credit card payment (YYYY-MM-DD).",
            "rewards_points":    "Accumulated rewards points as an integer.",
        },
    },
    "Feedback": {
        "description": "Customer feedback or complaint record.",
        "properties": {
            "feedback_id":       "Unique Feedback ID.",
            "date":              "Date feedback was submitted (YYYY-MM-DD).",
            "type":              "Feedback type, e.g. 'Complaint', 'Suggestion', 'Compliment'.",
            "resolution_status": "Resolution status, e.g. 'Resolved', 'Pending', 'Escalated'.",
            "resolution_date":   "Date feedback was resolved (YYYY-MM-DD), empty if unresolved.",
        },
    },
}

# ---------------------------------------------------------------------------
# 2. Relationship definitions
# ---------------------------------------------------------------------------

RELATIONSHIP_DEFINITIONS = {
    "HAS_ACCOUNT": {
        "pattern":     "(Customer)-[:HAS_ACCOUNT]->(Account)",
        "description": "Links a customer to their bank account(s).",
        "properties":  {},
    },
    "MADE_TRANSACTION": {
        "pattern":     "(Customer)-[:MADE_TRANSACTION]->(Transaction)",
        "description": "Links a customer to each transaction they made.",
        "properties":  {},
    },
    "AT_BRANCH": {
        "pattern":     "(Transaction)-[:AT_BRANCH]->(Branch)",
        "description": "Links a transaction to the branch where it occurred.",
        "properties":  {},
    },
    "HAS_LOAN": {
        "pattern":     "(Customer)-[:HAS_LOAN]->(Loan)",
        "description": "Links a customer to their loan record(s).",
        "properties":  {},
    },
    "HAS_CARD": {
        "pattern":     "(Customer)-[:HAS_CARD]->(CreditCard)",
        "description": "Links a customer to their credit card(s).",
        "properties":  {},
    },
    "GAVE_FEEDBACK": {
        "pattern":     "(Customer)-[:GAVE_FEEDBACK]->(Feedback)",
        "description": "Links a customer to their feedback/complaint record(s).",
        "properties":  {},
    },
}

# ---------------------------------------------------------------------------
# 3. Plain-English schema text (injected into every LLM prompt)
# ---------------------------------------------------------------------------

SCHEMA_TEXT = """
You are querying a FalkorDB property graph built from a comprehensive banking dataset.
FalkorDB uses openCypher syntax. Always use MATCH, RETURN, WHERE, WITH, ORDER BY, LIMIT.

=== NODE LABELS & PROPERTIES ===

(:Customer)
  - customer_id        : string  -- unique customer identifier
  - first_name         : string
  - last_name          : string
  - age                : integer
  - gender             : string  -- e.g. 'Male', 'Female'
  - address            : string
  - city               : string
  - contact_number     : string
  - email              : string
  - anomaly            : string  -- empty = no anomaly; non-empty = anomaly type flag

(:Account)
  - account_id         : string  -- synthetic key: customer_id + '_' + account_type
  - account_type       : string  -- e.g. 'Savings', 'Checking'
  - balance            : float   -- current balance
  - date_opened        : string  -- YYYY-MM-DD
  - last_transaction_date : string -- YYYY-MM-DD

(:Transaction)
  - transaction_id     : string  -- unique
  - date               : string  -- YYYY-MM-DD
  - type               : string  -- e.g. 'Deposit', 'Withdrawal', 'Transfer'
  - amount             : float
  - balance_after      : float   -- account balance after this transaction

(:Branch)
  - branch_id          : string  -- unique branch identifier

(:Loan)
  - loan_id            : string  -- unique
  - amount             : float   -- principal loan amount
  - type               : string  -- e.g. 'Personal', 'Mortgage', 'Auto'
  - interest_rate      : float   -- annual rate as a percentage, e.g. 5.5
  - term               : integer -- loan term in months
  - approval_rejection_date : string -- YYYY-MM-DD
  - status             : string  -- e.g. 'Approved', 'Rejected', 'Pending'

(:CreditCard)
  - card_id            : string  -- unique
  - card_type          : string  -- e.g. 'Visa', 'MasterCard', 'Amex'
  - credit_limit       : float
  - balance            : float   -- current credit card balance
  - min_payment_due    : float
  - payment_due_date   : string  -- YYYY-MM-DD
  - last_payment_date  : string  -- YYYY-MM-DD
  - rewards_points     : integer

(:Feedback)
  - feedback_id        : string  -- unique
  - date               : string  -- YYYY-MM-DD
  - type               : string  -- e.g. 'Complaint', 'Suggestion', 'Compliment'
  - resolution_status  : string  -- e.g. 'Resolved', 'Pending', 'Escalated'
  - resolution_date    : string  -- YYYY-MM-DD, empty if not yet resolved

=== RELATIONSHIPS ===

(Customer)-[:HAS_ACCOUNT]      ->(Account)
(Customer)-[:MADE_TRANSACTION] ->(Transaction)
(Transaction)-[:AT_BRANCH]     ->(Branch)
(Customer)-[:HAS_LOAN]         ->(Loan)
(Customer)-[:HAS_CARD]         ->(CreditCard)
(Customer)-[:GAVE_FEEDBACK]    ->(Feedback)

=== CYPHER RULES ===

1. Always use MATCH ... RETURN. Never use CREATE, MERGE, DELETE, or SET.
2. Use WITH for multi-hop aggregations before filtering.
3. Dates are stored as strings (YYYY-MM-DD); use string comparison for date filters,
   e.g.  WHERE t.date >= '2023-01-01' AND t.date <= '2023-12-31'
4. Use toLower() for case-insensitive string matching, e.g. toLower(c.city) = 'london'.
5. Use count(), avg(), sum(), min(), max() for aggregations.
6. Always add LIMIT (default 25) unless the question explicitly asks for all results.
7. Return only columns relevant to the question. Use aliases for clarity.
8. For anomaly queries: WHERE c.anomaly <> '' AND c.anomaly <> 'None'
9. Do NOT invent properties or labels not listed above.
"""

# ---------------------------------------------------------------------------
# 4. Few-shot (question, Cypher) pairs
# ---------------------------------------------------------------------------

CYPHER_EXAMPLES = [

    # --- Customer queries ---
    {
        "question": "How many customers are there?",
        "cypher": "MATCH (c:Customer) RETURN count(c) AS total_customers",
    },
    {
        "question": "List all customers from Mumbai.",
        "cypher": (
            "MATCH (c:Customer)\n"
            "WHERE toLower(c.city) = 'mumbai'\n"
            "RETURN c.customer_id, c.first_name, c.last_name, c.email\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "Which cities have the most customers?",
        "cypher": (
            "MATCH (c:Customer)\n"
            "RETURN c.city AS city, count(c) AS customer_count\n"
            "ORDER BY customer_count DESC\n"
            "LIMIT 10"
        ),
    },
    {
        "question": "Show customers above the age of 60.",
        "cypher": (
            "MATCH (c:Customer)\n"
            "WHERE c.age > 60\n"
            "RETURN c.customer_id, c.first_name, c.last_name, c.age, c.city\n"
            "ORDER BY c.age DESC\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "What is the gender distribution of customers?",
        "cypher": (
            "MATCH (c:Customer)\n"
            "RETURN c.gender AS gender, count(c) AS total\n"
            "ORDER BY total DESC"
        ),
    },

    # --- Account queries ---
    {
        "question": "What account types exist and how many of each?",
        "cypher": (
            "MATCH (a:Account)\n"
            "RETURN a.account_type AS account_type, count(a) AS total\n"
            "ORDER BY total DESC"
        ),
    },
    {
        "question": "Which customers have a savings account with balance above 50000?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_ACCOUNT]->(a:Account)\n"
            "WHERE toLower(a.account_type) = 'savings' AND a.balance > 50000\n"
            "RETURN c.customer_id, c.first_name, c.last_name, a.balance\n"
            "ORDER BY a.balance DESC\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "What is the average account balance by account type?",
        "cypher": (
            "MATCH (a:Account)\n"
            "RETURN a.account_type AS account_type, round(avg(a.balance)) AS avg_balance\n"
            "ORDER BY avg_balance DESC"
        ),
    },
    {
        "question": "Which customers have both a savings and a checking account?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_ACCOUNT]->(a:Account)\n"
            "WITH c, collect(toLower(a.account_type)) AS types\n"
            "WHERE 'savings' IN types AND 'checking' IN types\n"
            "RETURN c.customer_id, c.first_name, c.last_name\n"
            "LIMIT 25"
        ),
    },

    # --- Transaction queries ---
    {
        "question": "What is the total transaction amount by transaction type?",
        "cypher": (
            "MATCH (t:Transaction)\n"
            "RETURN t.type AS transaction_type, round(sum(t.amount)) AS total_amount\n"
            "ORDER BY total_amount DESC"
        ),
    },
    {
        "question": "Which customers made the most transactions?",
        "cypher": (
            "MATCH (c:Customer)-[:MADE_TRANSACTION]->(t:Transaction)\n"
            "RETURN c.customer_id, c.first_name, c.last_name, count(t) AS tx_count\n"
            "ORDER BY tx_count DESC\n"
            "LIMIT 10"
        ),
    },
    {
        "question": "Show all withdrawal transactions above 10000.",
        "cypher": (
            "MATCH (c:Customer)-[:MADE_TRANSACTION]->(t:Transaction)\n"
            "WHERE toLower(t.type) = 'withdrawal' AND t.amount > 10000\n"
            "RETURN c.customer_id, c.first_name, t.transaction_id, t.date, t.amount\n"
            "ORDER BY t.amount DESC\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "What is the average transaction amount per customer?",
        "cypher": (
            "MATCH (c:Customer)-[:MADE_TRANSACTION]->(t:Transaction)\n"
            "WITH c, avg(t.amount) AS avg_amount\n"
            "RETURN c.customer_id, c.first_name, c.last_name, round(avg_amount) AS avg_tx_amount\n"
            "ORDER BY avg_tx_amount DESC\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "How many transactions happened in 2023?",
        "cypher": (
            "MATCH (t:Transaction)\n"
            "WHERE t.date >= '2023-01-01' AND t.date <= '2023-12-31'\n"
            "RETURN count(t) AS transactions_in_2023"
        ),
    },

    # --- Branch queries ---
    {
        "question": "Which branch has the highest number of transactions?",
        "cypher": (
            "MATCH (t:Transaction)-[:AT_BRANCH]->(b:Branch)\n"
            "RETURN b.branch_id AS branch, count(t) AS tx_count\n"
            "ORDER BY tx_count DESC\n"
            "LIMIT 10"
        ),
    },
    {
        "question": "What is the total deposit amount per branch?",
        "cypher": (
            "MATCH (t:Transaction)-[:AT_BRANCH]->(b:Branch)\n"
            "WHERE toLower(t.type) = 'deposit'\n"
            "RETURN b.branch_id AS branch, round(sum(t.amount)) AS total_deposits\n"
            "ORDER BY total_deposits DESC\n"
            "LIMIT 10"
        ),
    },

    # --- Loan queries ---
    {
        "question": "How many loans are approved, rejected, or pending?",
        "cypher": (
            "MATCH (l:Loan)\n"
            "RETURN l.status AS loan_status, count(l) AS total\n"
            "ORDER BY total DESC"
        ),
    },
    {
        "question": "What is the average loan amount by loan type?",
        "cypher": (
            "MATCH (l:Loan)\n"
            "RETURN l.type AS loan_type, round(avg(l.amount)) AS avg_loan_amount\n"
            "ORDER BY avg_loan_amount DESC"
        ),
    },
    {
        "question": "Which customers have an approved mortgage loan above 200000?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_LOAN]->(l:Loan)\n"
            "WHERE toLower(l.type) = 'mortgage'\n"
            "  AND toLower(l.status) = 'approved'\n"
            "  AND l.amount > 200000\n"
            "RETURN c.customer_id, c.first_name, c.last_name, l.loan_id, l.amount\n"
            "ORDER BY l.amount DESC\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "What is the highest interest rate loan and who holds it?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_LOAN]->(l:Loan)\n"
            "RETURN c.customer_id, c.first_name, c.last_name,\n"
            "       l.loan_id, l.type, l.interest_rate\n"
            "ORDER BY l.interest_rate DESC\n"
            "LIMIT 5"
        ),
    },
    {
        "question": "What is the total approved loan amount by city?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_LOAN]->(l:Loan)\n"
            "WHERE toLower(l.status) = 'approved'\n"
            "RETURN c.city AS city, round(sum(l.amount)) AS total_approved_loans\n"
            "ORDER BY total_approved_loans DESC\n"
            "LIMIT 10"
        ),
    },

    # --- Credit card queries ---
    {
        "question": "What is the average credit limit by card type?",
        "cypher": (
            "MATCH (cc:CreditCard)\n"
            "RETURN cc.card_type AS card_type, round(avg(cc.credit_limit)) AS avg_credit_limit\n"
            "ORDER BY avg_credit_limit DESC"
        ),
    },
    {
        "question": "Which customers have the highest credit card balance?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_CARD]->(cc:CreditCard)\n"
            "RETURN c.customer_id, c.first_name, c.last_name,\n"
            "       cc.card_type, cc.balance\n"
            "ORDER BY cc.balance DESC\n"
            "LIMIT 10"
        ),
    },
    {
        "question": "Which customers have overdue credit card payments?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_CARD]->(cc:CreditCard)\n"
            "WHERE cc.balance > 0 AND cc.min_payment_due > 0\n"
            "  AND (cc.last_payment_date = '' OR cc.last_payment_date < cc.payment_due_date)\n"
            "RETURN c.customer_id, c.first_name, c.last_name,\n"
            "       cc.card_id, cc.balance, cc.min_payment_due, cc.payment_due_date\n"
            "ORDER BY cc.balance DESC\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "Who has the most rewards points?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_CARD]->(cc:CreditCard)\n"
            "RETURN c.customer_id, c.first_name, c.last_name,\n"
            "       sum(cc.rewards_points) AS total_rewards\n"
            "ORDER BY total_rewards DESC\n"
            "LIMIT 10"
        ),
    },

    # --- Feedback queries ---
    {
        "question": "What is the breakdown of feedback types?",
        "cypher": (
            "MATCH (f:Feedback)\n"
            "RETURN f.type AS feedback_type, count(f) AS total\n"
            "ORDER BY total DESC"
        ),
    },
    {
        "question": "How many feedbacks are still unresolved?",
        "cypher": (
            "MATCH (f:Feedback)\n"
            "WHERE toLower(f.resolution_status) <> 'resolved'\n"
            "RETURN f.resolution_status AS status, count(f) AS total\n"
            "ORDER BY total DESC"
        ),
    },
    {
        "question": "Which customers have submitted the most complaints?",
        "cypher": (
            "MATCH (c:Customer)-[:GAVE_FEEDBACK]->(f:Feedback)\n"
            "WHERE toLower(f.type) = 'complaint'\n"
            "RETURN c.customer_id, c.first_name, c.last_name, count(f) AS complaint_count\n"
            "ORDER BY complaint_count DESC\n"
            "LIMIT 10"
        ),
    },

    # --- Anomaly queries ---
    {
        "question": "How many customers have been flagged as anomalies?",
        "cypher": (
            "MATCH (c:Customer)\n"
            "WHERE c.anomaly <> '' AND c.anomaly <> 'None'\n"
            "RETURN count(c) AS anomaly_count"
        ),
    },
    {
        "question": "What types of anomalies exist and how many customers have each?",
        "cypher": (
            "MATCH (c:Customer)\n"
            "WHERE c.anomaly <> '' AND c.anomaly <> 'None'\n"
            "RETURN c.anomaly AS anomaly_type, count(c) AS total\n"
            "ORDER BY total DESC"
        ),
    },
    {
        "question": "Show anomaly-flagged customers who also have a rejected loan.",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_LOAN]->(l:Loan)\n"
            "WHERE c.anomaly <> '' AND c.anomaly <> 'None'\n"
            "  AND toLower(l.status) = 'rejected'\n"
            "RETURN c.customer_id, c.first_name, c.last_name,\n"
            "       c.anomaly, l.loan_id, l.type, l.amount\n"
            "LIMIT 25"
        ),
    },

    # --- Multi-hop / cross-entity queries ---
    {
        "question": "Which branches handled the most deposits from savings account customers?",
        "cypher": (
            "MATCH (c:Customer)-[:HAS_ACCOUNT]->(a:Account),\n"
            "      (c)-[:MADE_TRANSACTION]->(t:Transaction)-[:AT_BRANCH]->(b:Branch)\n"
            "WHERE toLower(a.account_type) = 'savings'\n"
            "  AND toLower(t.type) = 'deposit'\n"
            "RETURN b.branch_id AS branch, count(t) AS deposit_count\n"
            "ORDER BY deposit_count DESC\n"
            "LIMIT 10"
        ),
    },
    {
        "question": (
            "Find customers who have a pending loan, an overdue credit card, "
            "and at least one unresolved complaint."
        ),
        "cypher": (
            "MATCH (c:Customer)-[:HAS_LOAN]->(l:Loan)\n"
            "WHERE toLower(l.status) = 'pending'\n"
            "WITH c\n"
            "MATCH (c)-[:HAS_CARD]->(cc:CreditCard)\n"
            "WHERE cc.balance > 0\n"
            "  AND (cc.last_payment_date = '' OR cc.last_payment_date < cc.payment_due_date)\n"
            "WITH c\n"
            "MATCH (c)-[:GAVE_FEEDBACK]->(f:Feedback)\n"
            "WHERE toLower(f.resolution_status) <> 'resolved'\n"
            "RETURN c.customer_id, c.first_name, c.last_name, c.email\n"
            "LIMIT 25"
        ),
    },
    {
        "question": "What is the total transaction volume per city?",
        "cypher": (
            "MATCH (c:Customer)-[:MADE_TRANSACTION]->(t:Transaction)\n"
            "RETURN c.city AS city,\n"
            "       count(t) AS tx_count,\n"
            "       round(sum(t.amount)) AS total_volume\n"
            "ORDER BY total_volume DESC\n"
            "LIMIT 10"
        ),
    },
]

# ---------------------------------------------------------------------------
# 5. Accessor functions used by agent.py
# ---------------------------------------------------------------------------

def get_schema_text():
    """Return the raw schema string for use in prompts."""
    return SCHEMA_TEXT.strip()


def get_few_shot_text(max_examples=10):
    """
    Return a formatted string of few-shot examples for the LLM prompt.

    Parameters
    ----------
    max_examples : int
        Maximum number of examples to include. Defaults to 10 to keep
        the prompt within token budget. Pass None to include all.
    """
    examples = CYPHER_EXAMPLES if max_examples is None else CYPHER_EXAMPLES[:max_examples]
    lines = []
    for i, ex in enumerate(examples, 1):
        lines.append("Example {}:".format(i))
        lines.append("  Question: {}".format(ex["question"]))
        lines.append("  Cypher:")
        for ln in ex["cypher"].strip().splitlines():
            lines.append("    {}".format(ln))
        lines.append("")
    return "\n".join(lines)


def get_schema_prompt(max_examples=10):
    """
    Return the complete system prompt string combining schema + few-shot examples.
    Plug this directly into the LLM system message in agent.py.
    """
    return (
        "{schema}\n\n"
        "=== FEW-SHOT CYPHER EXAMPLES ===\n\n"
        "{examples}"
        "=== END OF EXAMPLES ===\n\n"
        "Now generate a valid FalkorDB Cypher query for the user question. "
        "Return ONLY the Cypher query, no explanation, no markdown fences."
    ).format(
        schema=get_schema_text(),
        examples=get_few_shot_text(max_examples=max_examples),
    )


def get_node_labels():
    """Return a list of all node label strings."""
    return list(NODE_DEFINITIONS.keys())


def get_relationship_types():
    """Return a list of all relationship type strings."""
    return list(RELATIONSHIP_DEFINITIONS.keys())


def get_node_properties(label):
    """Return the property dict for a given node label, or empty dict."""
    return NODE_DEFINITIONS.get(label, {}).get("properties", {})


# ---------------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Node labels ===")
    for label in get_node_labels():
        props = get_node_properties(label)
        print("  {:14}  {} properties".format(label, len(props)))

    print("\n=== Relationship types ===")
    for rel, info in RELATIONSHIP_DEFINITIONS.items():
        print("  {}  ->  {}".format(rel, info["pattern"]))

    print("\n=== Schema prompt (first 60 lines) ===")
    prompt = get_schema_prompt()
    for line in prompt.splitlines()[:60]:
        print(line)
    print("... ({} total lines)".format(len(prompt.splitlines())))

    print("\n=== Few-shot examples loaded: {} ===".format(len(CYPHER_EXAMPLES)))
