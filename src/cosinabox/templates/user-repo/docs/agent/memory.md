# Memory service

Your CoS stores durable facts (decisions, stakeholder context, meeting outcomes) in memory. These persist across conversations and power follow-up tracking, relationship intelligence, and daily briefings.

## Default: local (SQLite)

Out of the box, memory uses SQLite with keyword search. No setup needed. Works well for <10,000 memories.

| What it does | What it doesn't do |
|---|---|
| Store and retrieve facts by keyword | Semantic/meaning-based search |
| Fast for small datasets | Scale beyond ~10k memories |
| Zero config, zero cost | Understand synonyms or context |

## Upgrade: remote memory service

For semantic search (understands meaning, not just keywords), point your CoS at an external memory service:

1. Deploy a memory service (Docker image or Railway template — see cosinabox docs)
2. Add to `.env`:
   ```
   MEMORY_SERVICE_URL=https://your-service.railway.app
   MEMORY_API_KEY=your-api-key
   ```
3. Restart your CoS

The transition is seamless — your CoS will start using semantic search immediately. Local memories are not migrated automatically; new memories go to the remote service.
