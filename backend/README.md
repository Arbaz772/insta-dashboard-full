# Backend — Instagram Dashboard (Node/Express)

## Quickstart (local)
1. Install dependencies:
   ```
   npm install
   ```
2. Create a `.env` file with optional values:
   ```
   OPENAI_API_KEY=sk-...
   PORT=3000
   ```
3. Start server:
   ```
   npm start
   ```
4. The server will serve uploads under `/public/uploads` and expose the API at `/api/*`.

## Notes
- The create/publish endpoints are simulated for demos. Replace with real Instagram Graph API calls in production.
- The scheduler uses `node-cron` and runs every minute to publish due items.
