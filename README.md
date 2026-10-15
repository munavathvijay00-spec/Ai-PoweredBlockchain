# 🚀 Blockchain Intelligence Platform

**Live Demo (current bundled frontend):** [ai-poweredblockchain-production.up.railway.app/app/](https://ai-poweredblockchain-production.up.railway.app/app/)  
**Legacy Vercel frontend:** [frontend-mu-woad-t9a0714g2q.vercel.app](https://frontend-mu-woad-t9a0714g2q.vercel.app)  
**API Docs:** [ai-poweredblockchain-production.up.railway.app/docs](https://ai-poweredblockchain-production.up.railway.app/docs)  
**Backend API:** [ai-poweredblockchain-production.up.railway.app](https://ai-poweredblockchain-production.up.railway.app)

Ethereum wallet investigation dashboard with observed transfers, counterparty analysis, graph exploration, and evidence-linked review signals. Data coverage is bounded; fraud-detection accuracy is not yet measured.

---

## 📸 What It Does

- **Queries Ethereum transfers** — Requests bounded mainnet transfer pages from the configured provider; indexed ingestion is currently interrupted by a checkpoint mismatch
- **Shows review signals** — Displays rule-based signals and transaction evidence; scores are not calibrated fraud probabilities
- **Generates investigation summaries** — Presents the API's evidence-linked wallet report, coverage and limitations
- **Provides an investigation dashboard** — React wallet lookup, direction filters, counterparties, 3D fund-flow graph, and CSV/JSON exports
- **Exposes a documented REST API** — See the deployed OpenAPI docs for current routes and schemas

---

## ⚠️ Current limitations

- Indexed external ETH and ERC-20 transfers only; internal calls, NFTs, and complete historical coverage are not established.
- The production ingestion worker is blocked by a canonical-chain checkpoint mismatch. Indexed dashboard data may be stale.
- Behavioral review signals are not fraud verdicts. Detection precision, recall, and false-positive rates have not been measured against a sufficiently large independently labeled holdout yet.
- Transfer counterparties are observed addresses, not proof of common ownership.
- The Vercel URL is retained only as a legacy deployment; use the Railway `/app/` URL to inspect the frontend bundled from the current repository deployment.

## 🏗️ Architecture

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Blockchain** | Web3.py + Alchemy |
| **Backend** | Python 3.12 + FastAPI + asyncpg |
| **Database** | PostgreSQL |
| **AI** | Ollama + llama3.2:1b (local LLM) |
| **Frontend** | React + Vite + TailwindCSS + Recharts + custom canvas 3D fund-flow renderer |
| **Infra** | Docker + Railway + Vercel (legacy frontend) |

---

## 🚀 Quick Start (Local)

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker Desktop
- Ollama (for AI explanations)

### Setup

```bash
# Clone the repo
git clone https://github.com/munavathvijay00-spec/Ai-PoweredBlockchain.git
cd Ai-PoweredBlockchain

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Start PostgreSQL + Redis
docker compose up -d

# Copy env template and fill in your values
cp .env.example .env
# Edit .env with your Alchemy API key, DB URL, etc.

# Apply database schema
cat scripts/init.sql | psql "$DATABASE_URL"

# Fetch real Ethereum data
python -m scripts.test_ingest

# Score transactions for risk
python -m scripts.score_transactions

# Generate AI explanations
python -m scripts.explain_transactions

# Start backend
uvicorn src.api.main:app --reload --port 8000

# Start frontend (in another terminal)
cd frontend
npm install
npm run dev
```

## 📡 API Endpoints

Method	Endpoint	Description
GET	/	Health check
GET	/api/transactions?limit=N	List recent transactions
GET	/api/transactions/{hash}	Get transaction by hash
GET	/api/flagged?min_score=20	List flagged (high-risk) transactions
GET	/api/stats	System statistics
GET	/api/wallets/{address}/transfers	Paginated wallet transfers
GET	/api/wallets/{address}/indexed-graph	Observed wallet network
GET	/api/wallets/{address}/investigation-report	Evidence-linked investigation report
.
├── src/
│   ├── api/                 # FastAPI endpoints
│   │   ├── main.py
│   │   ├── routes.py
│   │   ├── models.py
│   │   └── dependencies.py
│   ├── blockchain/          # Web3 + normalizer
│   │   ├── client.py
│   │   └── normalizer.py
│   ├── database/            # DB connection + repos
│   │   ├── connection.py
│   │   └── repositories.py
│   ├── risk/                # Risk scoring engine
│   │   └── scorer.py
│   ├── agents/              # AI explainer
│   │   └── explainer.py
│   └── utils/
│       └── config.py
├── scripts/
│   ├── init.sql             # Database schema
│   ├── test_blockchain.py   # Test Web3 connection
│   ├── test_ingest.py       # Fetch and store transactions
│   ├── score_transactions.py # Batch risk scoring
│   └── explain_transactions.py # Batch AI explanations
├── frontend/                # React dashboard
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   └── App.jsx
│   └── package.json
├── Dockerfile               # Backend container
├── docker-compose.yml       # Local PostgreSQL + Redis
├── requirements.txt
└── README.md
🎓 What I Learned

This project was built from scratch as a learning exercise. Key learnings:

Async Python — Connection pooling, async/await patterns, context managers
Blockchain data — Web3.py, transaction parsing, wei/ETH conversion
Production debugging — Docker networking, CORS, env vars, cache invalidation
Full-stack deployment — Railway, Vercel, environment management
Local AI — Running LLMs with Ollama (no cloud costs)

📄 License

MIT
👤 Author

Munavath Vijay
