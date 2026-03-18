-- Agent Chat Database Schema
-- SQLite database for managing AI agent chat threads

-- Agents table
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT,
    avatar_path TEXT,
    emoji TEXT DEFAULT '🤖',
    provider TEXT DEFAULT 'claude',
    model TEXT DEFAULT 'sonnet',
    cwd TEXT NOT NULL,
    system_prompt TEXT,
    role TEXT DEFAULT 'worker',  -- 'worker' | 'manager'
    status TEXT DEFAULT 'offline',  -- 'offline' | 'online' | 'busy'
    notification TEXT DEFAULT NULL,  -- NULL | 'attention' | 'done'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Threads (1:1 with agents)
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL UNIQUE,
    session_id TEXT,  -- for --resume
    last_activity DATETIME,
    unread_count INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- Messages
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
);

-- Reports (Manager inbox)
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'decision' | 'plan' | 'blocked' | 'complete' | 'checkpoint'
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    payload JSON,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_reports_agent ON reports(agent_id);
CREATE INDEX IF NOT EXISTS idx_reports_acknowledged ON reports(acknowledged);
CREATE INDEX IF NOT EXISTS idx_threads_last_activity ON threads(last_activity);
