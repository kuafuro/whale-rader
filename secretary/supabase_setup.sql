-- Run this in your Supabase SQL Editor
-- Creates the secretary_tasks table

CREATE TABLE IF NOT EXISTS secretary_tasks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    chat_id TEXT,                          -- Telegram chat_id for member isolation
    title TEXT NOT NULL,
    due_date DATE,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_tasks_completed ON secretary_tasks(completed);
CREATE INDEX IF NOT EXISTS idx_tasks_chat_id ON secretary_tasks(chat_id);

-- Migration: if table already exists, add chat_id column
-- ALTER TABLE secretary_tasks ADD COLUMN IF NOT EXISTS chat_id TEXT;
-- CREATE INDEX IF NOT EXISTS idx_tasks_chat_id ON secretary_tasks(chat_id);
