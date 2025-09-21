require('dotenv').config();
const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const sqlite3 = require('sqlite3');
const { open } = require('sqlite');
const bodyParser = require('body-parser');
const cron = require('node-cron');
const axios = require('axios');
const cors = require('cors');
const { Configuration, OpenAIApi } = require('openai');

const PORT = process.env.PORT || 3000;
const UPLOAD_DIR = path.join(__dirname, 'public', 'uploads');
fs.mkdirSync(UPLOAD_DIR, { recursive: true });

const app = express();
app.use(cors());
app.use(bodyParser.json({ limit: '10mb' }));
app.use('/public', express.static(path.join(__dirname, 'public')));

// multer setup
const storage = multer.diskStorage({
  destination: function (req, file, cb) {
    cb(null, UPLOAD_DIR);
  },
  filename: function (req, file, cb) {
    const name = Date.now() + '-' + file.originalname.replace(/\s+/g, '-');
    cb(null, name);
  }
});
const upload = multer({ storage: storage });

// openai setup (optional)
const configuration = new Configuration({ apiKey: process.env.OPENAI_API_KEY || '' });
const openai = new OpenAIApi(configuration);

// sqlite db
let db;
(async () => {
  db = await open({ filename: './db.sqlite', driver: sqlite3.Database });
  await db.exec(`CREATE TABLE IF NOT EXISTS queue (
    id TEXT PRIMARY KEY,
    imageUrl TEXT,
    caption TEXT,
    scheduledAt TEXT,
    status TEXT,
    createdAt TEXT
  )`);
})();

// Helpers
function makeId() { return Math.random().toString(36).slice(2, 10); }

// POST /api/upload -> multipart file, returns { imageUrl }
app.post('/api/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: 'No file' });
    const imageUrl = `${req.protocol}://${req.get('host')}/public/uploads/${req.file.filename}`;
    return res.json({ imageUrl });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// POST /api/generate_caption -> { imageDescription } returns { caption }
app.post('/api/generate_caption', async (req, res) => {
  const { imageDescription } = req.body || {};
  if (!imageDescription) return res.status(400).json({ error: 'Missing imageDescription' });
  try {
    if (!process.env.OPENAI_API_KEY) {
      // fallback simple caption
      const caption = imageDescription + ' #programming';
      return res.json({ caption });
    }
    const prompt = `You are a witty social media copywriter. Write a short IG caption (<=140 chars) and 3-5 hashtags for this image description:\n\n${imageDescription}\n\nReturn only the caption.`;
    const resp = await openai.createCompletion({ model: 'gpt-4o-mini', prompt, max_tokens: 150, temperature: 0.8 });
    const caption = resp.data.choices[0].text.trim();
    res.json({ caption });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// POST /api/create_media -> { imageUrl, caption } returns { creation_id }
app.post('/api/create_media', async (req, res) => {
  const { imageUrl, caption } = req.body || {};
  if (!imageUrl) return res.status(400).json({ error: 'Missing imageUrl' });
  try {
    const id = makeId();
    await db.run('INSERT INTO queue (id, imageUrl, caption, status, createdAt) VALUES (?, ?, ?, ?, ?)', [id, imageUrl, caption || '', 'created', new Date().toISOString()]);
    res.json({ creation_id: id });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// POST /api/publish_media -> { creation_id } publishes and returns result
app.post('/api/publish_media', async (req, res) => {
  const { creation_id } = req.body || {};
  if (!creation_id) return res.status(400).json({ error: 'Missing creation_id' });
  try {
    const postId = 'post_' + makeId();
    const now = new Date().toISOString();
    await db.run('UPDATE queue SET status = ?, scheduledAt = ? WHERE id = ?', ['published', now, creation_id]);
    res.json({ id: postId, publishedAt: now });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// POST /api/schedule -> { imageUrl, caption, scheduleTime } returns { jobId }
app.post('/api/schedule', async (req, res) => {
  const { imageUrl, caption, scheduleTime } = req.body || {};
  if (!imageUrl) return res.status(400).json({ error: 'Missing imageUrl' });
  try {
    const id = makeId();
    const scheduledAt = scheduleTime || new Date(Date.now() + 60*60*1000).toISOString();
    await db.run('INSERT INTO queue (id, imageUrl, caption, scheduledAt, status, createdAt) VALUES (?, ?, ?, ?, ?, ?)', [id, imageUrl, caption || '', scheduledAt, 'scheduled', new Date().toISOString()]);
    res.json({ jobId: id, scheduledAt });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

// GET /api/queue -> list
app.get('/api/queue', async (req, res) => {
  try {
    const rows = await db.all('SELECT * FROM queue ORDER BY createdAt DESC');
    res.json(rows);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// DELETE /api/queue/:id
app.delete('/api/queue/:id', async (req, res) => {
  const id = req.params.id;
  try {
    await db.run('DELETE FROM queue WHERE id = ?', [id]);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Simple scheduler: runs every minute and publishes due posts (simulated)
cron.schedule('* * * * *', async () => {
  try {
    const now = new Date().toISOString();
    const due = await db.all('SELECT * FROM queue WHERE status = ? AND scheduledAt <= ?', ['scheduled', now]);
    for (const row of due) {
      console.log('Publishing scheduled post', row.id);
      await db.run('UPDATE queue SET status = ?, scheduledAt = ? WHERE id = ?', ['published', new Date().toISOString(), row.id]);
    }
  } catch (e) {
    console.error('Scheduler error', e);
  }
});

app.listen(PORT, () => {
  console.log('Backend listening on', PORT);
});
