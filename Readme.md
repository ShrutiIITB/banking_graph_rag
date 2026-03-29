# Banking Graph RAG

A local, fully offline Graph Retrieval-Augmented Generation (RAG) chatbot built on **FalkorDB**, **LangGraph**, and **Streamlit**. Ask natural-language questions about customers, transactions, loans, credit cards, and feedback -- the agent automatically converts them into Cypher queries, runs them against the graph database, and returns grounded answers.

---

## Table of contents

1. [Architecture overview](#architecture-overview)
2. [Graph schema](#graph-schema)
3. [Project structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Step-by-step setup](#step-by-step-setup)
6. [Running the app](#running-the-app)
7. [Using the chatbot](#using-the-chatbot)
8. [Using the graph explorer](#using-the-graph-explorer)
9. [Sample questions](#sample-questions)
10. [Configuration reference](#configuration-reference)
11. [Troubleshooting](#troubleshooting)

---

## Architecture overview

```
 User (browser)
      |
      v
+---------------------+
|    Streamlit UI      |   app.py
|  Chat | Graph View  |
+---------------------+
      |
      | natural-language question
      v
+---------------------+
|   LangGraph Agent   |   agent.py
|                     |
|  1. decompose()     |  -- splits question into 1-3 sub-questions
|  2. gen_cypher()    |  -- LLM generates Cypher per sub-question
|  3. execute()       |  -- runs Cypher against FalkorDB
|  4. gen_answer()    |  -- LLM produces grounded answer
+---------------------+
      |            ^
 Cypher query   results
      |            |
      v            |
+---------------------+
|     FalkorDB        |   Docker container (port 6379)
|   (graph DB)        |
+---------------------+
      ^
      | (one-time)
      |
+---------------------+
|     ingest.py       |  CSV --> nodes + relationships
+---------------------+
      ^
      |
+--------------------------------------+
| Comprehensive_Banking_Database.csv   |
| 40 columns, 7 entity types           |
+--------------------------------------+
```

### LangGraph agent pipeline

```
decompose
    |
    v
generate_cypher  <-- graph_schema.py (schema text + 30 few-shot examples)
    |
    v
execute          <-- FalkorDB (openCypher)
    |
    v
generate_answer  <-- OpenAI GPT-4o (grounded to DB results only)
    |
    v
  answer (str)
```

Each step is a **LangGraph node** sharing a typed `State` dictionary:

| State key     | Type        | Set by           |
|---------------|-------------|------------------|
| `question`    | `str`       | caller           |
| `history`     | `list[dict]`| caller           |
| `sub_queries` | `list[str]` | `decompose`      |
| `cypher_list` | `list[str]` | `generate_cypher`|
| `results`     | `list[str]` | `execute`        |
| `answer`      | `str`       | `generate_answer`|

---

## Graph schema

### Nodes

| Label         | Key property      | Important properties                                         |
|---------------|-------------------|--------------------------------------------------------------|
| `Customer`    | `customer_id`     | first\_name, last\_name, age, gender, city, email, anomaly  |
| `Account`     | `account_id`      | account\_type, balance, date\_opened, last\_transaction\_date|
| `Transaction` | `transaction_id`  | date, type, amount, balance\_after                           |
| `Branch`      | `branch_id`       | (identifier only)                                            |
| `Loan`        | `loan_id`         | amount, type, interest\_rate, term, status                   |
| `CreditCard`  | `card_id`         | card\_type, credit\_limit, balance, rewards\_points          |
| `Feedback`    | `feedback_id`     | date, type, resolution\_status, resolution\_date             |

### Relationships

```
(Customer)-[:HAS_ACCOUNT]      -->(Account)
(Customer)-[:MADE_TRANSACTION] -->(Transaction)
(Transaction)-[:AT_BRANCH]     -->(Branch)
(Customer)-[:HAS_LOAN]         -->(Loan)
(Customer)-[:HAS_CARD]         -->(CreditCard)
(Customer)-[:GAVE_FEEDBACK]    -->(Feedback)
```

### Entity-relationship diagram

```
Customer ----HAS_ACCOUNT------> Account
    |
    +---MADE_TRANSACTION------> Transaction ---AT_BRANCH---> Branch
    |
    +---HAS_LOAN--------------> Loan
    |
    +---HAS_CARD--------------> CreditCard
    |
    +---GAVE_FEEDBACK---------> Feedback
```

### CSV to graph mapping

The source CSV has **40 columns** mapped across 7 node types:

```
Customer ID, First Name, Last Name, Age, Gender,
Address, City, Contact Number, Email              --> Customer node
                                                      (+ Anomaly flag)

Account Type, Account Balance,
Date Of Account Opening, Last Transaction Date    --> Account node

TransactionID, Transaction Date,
Transaction Type, Transaction Amount,
Account Balance After Transaction                 --> Transaction node

Branch ID                                         --> Branch node

Loan ID, Loan Amount, Loan Type, Interest Rate,
Loan Term, Approval/Rejection Date, Loan Status   --> Loan node

CardID, Card Type, Credit Limit, Credit Card Balance,
Minimum Payment Due, Payment Due Date,
Last Credit Card Payment Date, Rewards Points     --> CreditCard node

Feedback ID, Feedback Date, Feedback Type,
Resolution Status, Resolution Date                --> Feedback node
```

---

## Project structure

```
banking_graph_rag/
|
|-- app.py                          # Streamlit UI (Chat + Graph View pages)
|-- agent.py                        # LangGraph multi-query RAG agent
|-- graph_schema.py                 # Schema text + 30 few-shot Cypher examples
|-- ingest.py                       # CSV --> FalkorDB ingestion script
|
|-- Comprehensive_Banking_Database.csv   # Source dataset (40 columns)
|-- .env                            # API keys and DB config (create this)
|-- requirements.txt                # Python dependencies
|-- README.md                       # This file
```

---

## Prerequisites

### Software

| Requirement   | Version  | Notes                                         |
|---------------|----------|-----------------------------------------------|
| Python        | 3.10+    | `python --version`                            |
| Docker Desktop| Latest   | For running FalkorDB locally                  |
| Git           | Any      | To clone the repo                             |

### Accounts / keys

| Service   | Purpose              | Where to get                        |
|-----------|----------------------|-------------------------------------|
| OpenAI    | LLM (Cypher + answer)| https://platform.openai.com/api-keys|

---

## Step-by-step setup

### 1. Clone and enter the project

```bash
git clone <your-repo-url>
cd banking_graph_rag
```

### 2. Create a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python -m venv venv
source venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install streamlit langgraph langchain langchain-openai \
            falkordb pandas requests tqdm python-dotenv
```

Or create `requirements.txt`:

```
streamlit
langgraph
langchain
langchain-openai
falkordb
pandas
requests
tqdm
python-dotenv
```

Then run:

```bash
pip install -r requirements.txt
```

### 4. Create the `.env` file

Create a file named `.env` in the project root:

```env
OPENAI_API_KEY=sk-...your-key-here...

FALKORDB_HOST=localhost
FALKORDB_PORT=6379
GRAPH_NAME=banking

LLM_MODEL=gpt-4o
```

### 5. Start FalkorDB with Docker

```bash
docker run -p 6379:6379 --rm falkordb/falkordb:latest
```

Leave this terminal running. FalkorDB is now available at `localhost:6379`.

To verify it is running:

```bash
# In a separate terminal
docker ps
# You should see falkordb/falkordb listed
```

### 6. Download the dataset

Download `Comprehensive_Banking_Database.csv` from:

```
https://github.com/ahsan084/Banking-Dataset/blob/main/Comprehensive_Banking_Database.csv
```

Place it in the project root (same folder as `ingest.py`).

### 7. Ingest the CSV into FalkorDB

```bash
python ingest.py
```

Expected output:

```
============================================================
  Banking Graph RAG -- Data Ingestion (40-column schema)
============================================================
[INFO] Reading Comprehensive_Banking_Database.csv ...
[INFO] Loaded 10,000 rows.
[INFO] Cleaning and normalising data ...
[INFO] 10,000 rows ready for ingestion.
[INFO] Connecting to FalkorDB at localhost:6379 ...
[INFO] Connected -> graph: 'banking'
[INFO] Creating indexes ...
[INFO] Ingesting Customer nodes ...
  Customers             10000 rows [====================] 100%
[INFO] Ingesting Account nodes ...
...
[INFO] Verification counts ...
  Customer nodes              2,000
  Account nodes               3,800
  Transaction nodes          10,000
  Branch nodes                   12
  Loan nodes                  8,500
  CreditCard nodes            9,200
  Feedback nodes              6,300
  HAS_ACCOUNT edges          10,000
  MADE_TRANSACTION edges     10,000
  AT_BRANCH edges            10,000
  HAS_LOAN edges              8,500
  HAS_CARD edges              9,200
  GAVE_FEEDBACK edges         6,300
[DONE] Ingestion complete in 38.4s
```

> **Re-ingesting from scratch:** add the `--reset` flag to wipe and reload:
> ```bash
> python ingest.py --reset
> ```

---

## Running the app

```bash
streamlit run app.py
```

The browser opens automatically at `http://localhost:8501`.

---

## Using the chatbot

1. Open the app at `http://localhost:8501`
2. The sidebar shows the database status (node and edge counts)
3. If the graph is empty, enter the CSV path in the sidebar and click **Run Ingest**
4. Use the **Chat** page (selected in the sidebar navigation)
5. Type a question in the chat box, or click one of the sample question buttons
6. The agent decomposes your question, generates Cypher, queries FalkorDB, and returns a grounded answer

### How multi-query works

A complex question is automatically split into simpler sub-questions:

```
User: "Which city has the most customers with approved loans over $50,000?"

  Sub-query 1: "Which city has the most customers?"
  Sub-query 2: "Which customers have an approved loan above $50,000?"

  --> Cypher generated for each
  --> Both run against FalkorDB
  --> Results merged into a single answer
```

---

## Using the graph explorer

Switch to the **Graph View** page in the sidebar navigation.

### Controls

| Control               | Description                                      |
|-----------------------|--------------------------------------------------|
| Node types            | Select which node labels to show                 |
| Relationship types    | Select which edge types to draw                  |
| Max nodes per type    | Slider 5-100 -- controls sample size per label    |
| Show node labels      | Toggle display names on nodes                    |
| Show properties on hover | Toggle tooltip with node details              |

### Node colours

| Node label  | Colour  |
|-------------|---------|
| Customer    | Purple  |
| Account     | Teal    |
| Transaction | Coral   |
| Branch      | Gray    |
| Loan        | Amber   |
| CreditCard  | Blue    |
| Feedback    | Green   |

### Interaction

- **Drag** nodes to rearrange
- **Scroll** to zoom in/out
- **Hover** over a node to see its properties
- **Click** a node to highlight its connections

### Raw Cypher explorer

At the bottom of the Graph View page there is a **Raw Cypher explorer** panel. Type any read-only Cypher query and click **Run query** to see results as a table. Write operations (`CREATE`, `MERGE`, `DELETE`, `SET`) are blocked.

Example:

```cypher
MATCH (c:Customer)-[:HAS_LOAN]->(l:Loan)
WHERE l.status = 'Approved' AND l.amount > 50000
RETURN c.first_name, c.last_name, c.city, l.amount
ORDER BY l.amount DESC
LIMIT 10
```

---

## Sample questions

### Customers

```
How many customers are in the database?
Which city has the most customers?
Show me all customers over the age of 60.
What is the gender distribution of customers?
```

### Accounts

```
What is the average account balance by account type?
Which customers have a savings account balance above 50000?
Which customers have both a savings and a checking account?
```

### Transactions

```
Which branch processed the most transactions?
What is the total deposit amount per branch?
Show all withdrawal transactions above 10000.
How many transactions happened in 2023?
```

### Loans

```
What is the loan approval rate?
What is the average loan amount by loan type?
Which customers have an approved mortgage over 200000?
What is the total approved loan amount by city?
```

### Credit cards

```
Which card type has the highest average credit limit?
Who has the most rewards points?
Which customers have overdue credit card payments?
```

### Feedback

```
How many unresolved complaints are there?
What is the breakdown of feedback types?
Which customers submitted the most complaints?
```

### Anomaly detection

```
Show customers flagged as anomalies.
What types of anomalies exist and how many customers have each?
Show anomaly-flagged customers who also have a rejected loan.
```

---

## Configuration reference

All settings live in `.env`:

| Variable         | Default       | Description                            |
|------------------|---------------|----------------------------------------|
| `OPENAI_API_KEY` | (required)    | Your OpenAI API key                    |
| `FALKORDB_HOST`  | `localhost`   | FalkorDB host                          |
| `FALKORDB_PORT`  | `6379`        | FalkorDB port                          |
| `GRAPH_NAME`     | `banking`     | Name of the graph inside FalkorDB      |
| `LLM_MODEL`      | `gpt-4o`      | OpenAI model for Cypher + answer gen   |

---

## Troubleshooting

### FalkorDB not reachable

```
Error: Cannot reach FalkorDB at localhost:6379
```

Make sure Docker Desktop is running and the container is started:

```bash
docker run -p 6379:6379 --rm falkordb/falkordb:latest
```

### Graph is empty after ingestion

Re-run with the reset flag:

```bash
python ingest.py --reset
```

Check the CSV path is correct. The file must be in the same directory as `injest.py`, or provide an absolute path:

```bash
python ingest.py --csv "C:\Users\you\Downloads\Comprehensive_Banking_Database.csv" --reset
```

### SyntaxError on Windows (encoding)

All `.py` files begin with `# -*- coding: utf-8 -*-`. If you still see encoding errors, open the file in VS Code, check the bottom-right encoding indicator, and save as **UTF-8 without BOM**.

### LLM returns write queries

The agent blocks any Cypher containing `CREATE`, `MERGE`, `DELETE`, `SET`, or `DROP`. This is logged as:

```
Blocked: query contains write operation (CREATE).
```

This is by design and not an error. The LLM will retry with a read query on the next turn.

### Query returns 0 rows

Check the `[cypher full]` log printed to the terminal. If the Cypher looks wrong, the few-shot examples in `graph_schema.py` can be extended with domain-specific examples matching your actual data values.

### Streamlit port already in use

```bash
streamlit run app.py --server.port 8502
```

---

## Tech stack

| Component    | Library / Tool                  | Role                            |
|--------------|---------------------------------|---------------------------------|
| UI           | Streamlit                       | Chat interface + graph explorer |
| Graph viz    | vis.js (via CDN)                | Interactive node/edge rendering |
| Agent        | LangGraph                       | Pipeline orchestration          |
| LLM          | LangChain + OpenAI GPT-4o       | Cypher generation + answering   |
| Graph DB     | FalkorDB (Docker)               | openCypher property graph       |
| Data loading | Pandas + falkordb Python client | CSV ingestion                   |
| Config       | python-dotenv                   | Environment variable management |