-- Run this in your Supabase SQL Editor
-- Creates the secretary_tasks table

CREATE TABLE IF NOT EXISTS secretary_tasks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    title TEXT NOT NULL,
    due_date DATE,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for faster queries
CREATE INDEX IF NOT EXISTS idx_tasks_completed ON secretary_tasks(completed);
