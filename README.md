# Instagram Daily Post — Full Project (Frontend + Backend + Auto Meme Worker)

This repository contains:
- `frontend/` — React + Vite dashboard (UI)
- `backend/`  — Node/Express backend with required API endpoints
- `worker/`   — `auto_meme_agent.py` Python worker that finds memes, converts to programming memes, uploads and schedules posts.

## Quick local setup (recommended for testing)
1. **Backend**
   ```
   cd backend
   npm install
   # create .env if you want, e.g. OPENAI_API_KEY=sk-...
   npm start
   ```
   Backend runs on port 3000 by default.

2. **Frontend**
   ```
   cd frontend
   npm install
   npm run dev
   ```
   Open the URL printed by Vite (usually http://localhost:5173). The frontend calls `/api/*` on the same origin when proxied — for local testing you can run both and set up a proxy, or change API calls to `http://localhost:3000/api/*`.

3. **Worker**
   ```
   cd worker
   pip install -r requirements.txt
   # create .env with BACKEND_BASE (e.g. http://localhost:3000) and optional OPENAI_API_KEY
   python auto_meme_agent.py
   ```

## Notes & Warnings
- This demo simulates Instagram publishing. Replace simulated parts with real Instagram Graph API calls and store tokens securely.
- Respect copyright and platform policies when reposting content from the web.
