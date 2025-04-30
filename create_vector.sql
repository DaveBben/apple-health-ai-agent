CREATE EXTENSION vector;
-- Planning on using BGE-M3  model
CREATE TABLE data_dictionary (
  id TEXT PRIMARY KEY,
  content TEXT NOT NULL,              -- Raw text or data being embedded
  embedding VECTOR(1024),             -- Vector from BGE-M3
  table_name TEXT,                     -- What table this can be found in
  column_name TEXT,                     -- The name of the column
  created_at TIMESTAMP DEFAULT NOW(),-- Insertion timestamp
  metadata JSONB                      -- Flexible extra metadata
);