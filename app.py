

import os
import sqlite3
import tempfile
from flask import Flask, request, jsonify, send_from_directory
import google.generativeai as genai

app = Flask(__name__)
genai.configure(api_key="AIzaSyDAN1sc1ApAOw6QVoJIUkaraz5Zpu6dJ4Q")  # ⬅️ Replace with your actual Gemini API key

MODEL_NAME = "models/gemini-1.5-flash"  # You can swap this to other models as needed

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/query", methods=["POST"])
def handle_query():
    prompt = request.form.get("prompt")
    file = request.files.get("db")

    print("DEBUG - prompt:", prompt)
    print("DEBUG - file:", file)

    if not prompt or not file:
        return jsonify({"error": "Missing prompt or DB file"}), 400

    # Save DB to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        file.save(tmp)
        db_path = tmp.name

    # Extract schema
    schema = extract_schema(db_path)

    # Ask Gemini
    full_prompt = f"""Given this SQLite schema:\n\n{schema}\n\nWrite a SQL query for: {prompt}"""
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(full_prompt)
    raw_sql = response.text.strip()

    # Clean triple backticks or formatting from response
    if raw_sql.startswith("```sql"):
        raw_sql = raw_sql.lstrip("```sql").rstrip("```").strip()

    try:
        result = execute_sql(db_path, raw_sql)
    except Exception as e:
        os.remove(db_path)
        return jsonify({"sql": raw_sql, "result": [], "error": str(e)})

    os.remove(db_path)
    return jsonify({"sql": raw_sql, "result": result})


def extract_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    schema = ""
    for table_name in tables:
        table = table_name[0]
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        schema += f"Table: {table}\n"
        for col in columns:
            schema += f"  {col[1]} {col[2]}\n"
        schema += "\n"

    conn.close()
    return schema


def execute_sql(db_path, query):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    conn.close()

    return [dict(zip(columns, row)) for row in rows]


if __name__ == "__main__":
    app.run(debug=True)
