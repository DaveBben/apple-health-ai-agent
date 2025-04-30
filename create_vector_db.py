import ollama
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
import json

import uuid
from dotenv import load_dotenv
import os
import csv

load_dotenv()
db_params = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "192.168.1.16"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

OLLAMA_MODEL = "bge-m3"
TABLE_NAME  = "data_dictionary"


def flatten_once(vec):
    """
    If vec is [[...]], unwrap one level so it's a flat list.
    """
    if len(vec) == 1 and isinstance(vec[0], list):
        return vec[0]
    return vec

def get_embeddings(texts: list[str]) -> list[list[float]]:
    """
    Call Ollama BGE‑M3 on each text and return list of embeddings.
    """
    embed_results = []
    for txt in texts:
        resp = ollama.embed(model=OLLAMA_MODEL, input=txt)
        raw = resp["embeddings"]
        vec = flatten_once(raw)
        embed_results.append(vec)
    return embed_results


def load_csv(path: str) -> list[dict]:
    """
    Read CSV and build list of dicts with the fields we want.
    """
    docs = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc_id = f"{row['name'].strip().lower()}_{row['table'].strip().lower()}"
            docs.append(
                {
                    "id": doc_id,
                    "text": row["description"],
                    "metadata": {"column_name":  row["name"], "table_name": row["table"]},
                }
            )
    return docs


def insert_into_pg(docs: list[dict]):
    """
    Batch-insert into PostgreSQL + PGVector.
    """
    conn = psycopg2.connect(
        host=db_params["host"],
        port=db_params["port"],
        dbname=db_params["dbname"],
        user=db_params["user"],
        password=db_params["password"],
    )
    register_vector(conn)
    cur = conn.cursor()

    # Prepare rows with embeddings
    texts = [d["text"] for d in docs]
    embeddings = get_embeddings(texts)

    rows = []
    for doc, emb in zip(docs, embeddings):
        rows.append(
            (
                doc["id"],
                doc["text"],
                json.dumps(doc["metadata"]),  # JSONB
                emb,  # Python list → PGVector
            )
        )

    sql = f"""
    INSERT INTO {TABLE_NAME}
      (id, text, metadata, embedding)
    VALUES %s
    ON CONFLICT (id) DO NOTHING;
    """

    execute_values(cur, sql, rows)
    conn.commit()
    cur.close()
    conn.close()


def search_with_threshold(query: str, max_dist: float = 5.0):
    # 1) Embed the query
    qvec = get_embeddings([query])[0]
    # Convert the Python list to a Postgres‐style string literal
    vec_literal = "[" + ",".join(str(x) for x in qvec) + "]"

    # 2) Query
    conn = psycopg2.connect(**db_params)
    register_vector(conn)
    cur = conn.cursor()
    sql = f"""
    SELECT
      id,
      text,
      (embedding <-> '{vec_literal}'::vector) AS distance
    FROM {TABLE_NAME}
    WHERE (embedding <-> '{vec_literal}'::vector) < %s
    ORDER BY distance;
    """
    cur.execute(sql, (max_dist,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # 3) Display
    print(f"\nResults within distance {max_dist} for “{query}”:")
    for rid, col, tbl, text, dist in rows:
        print(f"- id={rid}, table={tbl}, column={col}, dist={dist:.4f} → {text}")




def main():
    docs = load_csv('./data_dictionary.csv')
    insert_into_pg(docs)
    print(f"Inserted {len(docs)} rows into {TABLE_NAME}.")



if __name__ == "__main__":
    main()
    # search_with_threshold("sleWhat is the SQL information for start_time_health_records?", max_dist=5.0)
