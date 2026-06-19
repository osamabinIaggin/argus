import express from 'express'
import { pool } from './db.js'
import { createLibraryAgent } from './agent.js'

const app = express()
app.use(express.json())

const PORT = process.env.PORT ?? 3001

// ---------------------------------------------------------------------------
// POST /chat  — stream a cross-video agent response
// ---------------------------------------------------------------------------

interface ChatBody {
  user_id: string
  message: string
}

app.post('/chat', async (req, res) => {
  const { user_id, message } = req.body as ChatBody

  if (!user_id || !message) {
    res.status(400).json({ error: 'user_id and message are required' })
    return
  }

  try {
    // Load conversation history (last 20 messages) for multi-turn context
    const historyResult = await pool.query<{ role: string; content: string }>(
      `SELECT role, content FROM library_messages
       WHERE user_id = $1
       ORDER BY created_at DESC
       LIMIT 20`,
      [user_id]
    )
    // Rows come newest-first; reverse to chronological order
    const history = historyResult.rows.reverse().map((r) => ({
      role: r.role as 'user' | 'assistant',
      content: r.content,
    }))

    // Persist user message before generating (so history is consistent on retry)
    await pool.query(
      `INSERT INTO library_messages (id, user_id, role, content)
       VALUES (gen_random_uuid()::text, $1, 'user', $2)`,
      [user_id, message]
    )

    const agent = createLibraryAgent(user_id)
    // Pass full conversation history + new user message so agent has context
    const messages = [
      ...history,
      { role: 'user' as const, content: message },
    ]
    const result = await agent.generate(messages, {
      providerOptions: {
        google: { thinkingConfig: { thinkingBudget: 8000 } },
      },
    })
    const response = result.text ?? ''

    // Persist assistant message
    await pool.query(
      `INSERT INTO library_messages (id, user_id, role, content)
       VALUES (gen_random_uuid()::text, $1, 'assistant', $2)`,
      [user_id, response]
    )

    res.json({ response })
  } catch (err) {
    console.error('Library agent error:', err)
    res.status(500).json({ error: 'Agent failed', detail: String(err) })
  }
})

// ---------------------------------------------------------------------------
// GET /health
// ---------------------------------------------------------------------------

app.get('/health', (_req, res) => {
  res.json({ ok: true })
})

app.listen(PORT, () => {
  console.log(`Mastra library agent listening on :${PORT}`)
})
