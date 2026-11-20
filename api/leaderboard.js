const {createHash} = require('node:crypto');
const subjectPattern = /^(korean|math|english|history|social-0[1-9]|science-0[1-8]|vocational-0[1-6])$/;

let snapshot;
let recheckAt = 0;
let refresh;

async function readSnapshot() {
  if (snapshot && Date.now() < recheckAt) return snapshot;
  if (!refresh) {
    refresh = (async () => {
      const url = new URL(process.env.CSAT_LEADERBOARD_URL);
      if (url.protocol !== 'https:' || !url.hostname.endsWith('.private.blob.vercel-storage.com')) {
        throw new Error('Invalid leaderboard storage');
      }
      url.searchParams.set('cache', '0');
      const response = await fetch(url, {
        headers: {Authorization: `Bearer ${process.env.BLOB_READ_WRITE_TOKEN}`},
        redirect: 'error',
        signal: AbortSignal.timeout(3500),
      });
      if (!response.ok) throw new Error('Leaderboard fetch failed');
      snapshot = await response.json();
      recheckAt = Date.now() + 5000;
      return snapshot;
    })().finally(() => { refresh = undefined; });
  }
  return refresh;
}

function overview(data) {
  return Object.fromEntries(Object.entries(data).filter(([key, board]) => subjectPattern.test(key) && board)
    .map(([key, board]) => [key, {
      max_score: board.max_score,
      updated_at: board.updated_at,
      models: board.models.map(({model, endpoint, rank, mean_score, elapsed_seconds}) =>
        ({model, endpoint, rank, mean_score, elapsed_seconds})),
    }]));
}

module.exports = async (req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('Allow', 'GET, HEAD');
    return res.status(405).end();
  }
  const subject = new URL(req.url, 'http://localhost').searchParams.get('subject');
  if (subject !== 'overview' && !subjectPattern.test(subject ?? '')) {
    return res.status(400).json({error: 'Invalid subject'});
  }

  try {
    const data = await readSnapshot();
    const body = JSON.stringify(subject === 'overview' ? overview(data) : data[subject] ?? null);
    const etag = `"${createHash('sha256').update(body).digest('hex')}"`;
    res.setHeader('ETag', etag);
    res.setHeader('Cache-Control', 'public, max-age=0, must-revalidate');
    res.setHeader('Vercel-CDN-Cache-Control', 'public, s-maxage=10, stale-while-revalidate=30');
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    if (req.headers['if-none-match'] === etag) return res.status(304).end();
    return res.status(200).end(req.method === 'GET' ? body : undefined);
  } catch {
    res.setHeader('Cache-Control', 'no-store');
    return res.status(503).json({error: 'Leaderboard temporarily unavailable'});
  }
};
