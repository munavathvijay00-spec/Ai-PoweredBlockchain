## Day 1 — Live Ingestion Pipeline

### Built
- src/ingest/worker.py — single-block processor
- src/ingest/loop.py — infinite daemon
- Dockerfile.worker — container config
- Deployed to Railway as new service

### Results
- Local: 2,366 transactions ingested in 10 min
- Cloud: 5,810+ transactions, running 24/7
- 65 flagged transactions with risk scores

### Key Learnings
- Docker Desktop blocks ports 443/22 on macOS (known bug)
- Removed SSH config override → port 22 works
- Railway services need own env vars
- Heredoc for creating files in terminal
- Ctrl+C escapes stuck `quote>` prompt

### Wins
- Live production pipeline running
- Zero-cost operation
- Dashboard showing real-time data
## Day [X] — [Date]

### What I Built Today
- REST API with FastAPI (5 endpoints + auto docs)
- React dashboard with Vite + TailwindCSS
- Transaction modal with AI explanations
- Search bar and filter tabs (All/Flagged/High Risk)
- Risk distribution donut chart
- Fixed Docker/GitHub network conflict
- Set up SSH authentication for GitHub

### Key Learnings
- How FastAPI dependency injection works
- React hooks: useState, useEffect, useMemo
- TailwindCSS utility-first styling
- Debugging network issues systematically (Docker was blocking port 443)
- SSH is more reliable than HTTPS for GitHub

### Struggles
- Docker Desktop was blocking GitHub HTTPS traffic
- Solution: switched to SSH (port 22 bypasses the issue)
- Indentation errors when pasting partial code
- Solution: always do full file rewrites

### Tomorrow's Plan
- Deploy to production (Railway + Vercel)
- Update README for portfolio
- Get live URL to share

### Wins
- ✅ Full-stack app running locally
- ✅ Gorgeous dashboard with real Ethereum data
- ✅ GitHub SSH working
- ✅ Portfolio-worthy screenshots captured