import os
import sqlite3
import tempfile
from flask import Flask, request, jsonify, send_from_directory
import google.generativeai as genai

app = Flask(__name__)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
MODEL_NAME = "models/gemini-1.5-flash"

# Store training examples in-memory
training_examples = []

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

@app.route("/query", methods=["POST"])
def handle_query():
    prompt = request.form.get("prompt")
    file = request.files.get("db")

    if not prompt or not file:
        return jsonify({"error": "Missing prompt or DB file"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite") as tmp:
        tmp.write(file.read())
        db_path = tmp.name

    schema = extract_schema(db_path)
    print("DEBUG - extracted schema:\n", schema)

    # Build few-shot prompt
    few_shot_prompt = ""
    for q, s in training_examples:
        few_shot_prompt += f"Q: {q}\nA:\n{s}\n\n"
    full_prompt = f"""Given this SQLite schema:

    {schema}

    {few_shot_prompt}Q: {prompt}
    A:"""


    model = genai.GenerativeModel(MODEL_NAME)
    print("DEBUG - full prompt sent to Gemini:\n", full_prompt)
    response = model.generate_content(full_prompt)
    raw_sql = response.text.strip()

    if raw_sql.startswith("```sql"):
        raw_sql = raw_sql.lstrip("```sql").rstrip("```").strip()

    try:
        result = execute_sql(db_path, raw_sql)
    except Exception as e:
        result = []
        error = str(e)
    else:
        error = None
    finally:
        # Delay file delete to ensure connection is released
        import time
        time.sleep(0.1)
        os.remove(db_path)

    if error:
        return jsonify({"sql": raw_sql, "result": [], "error": error})
    return jsonify({"sql": raw_sql, "result": result})


@app.route("/train", methods=["POST"])
def train_example():
    question = request.form.get("question")
    sql = request.form.get("sql")
    if not question or not sql:
        return jsonify({"error": "Missing training question or SQL"}), 400
    training_examples.append((question, sql))
    return jsonify({"message": "Training example added"})

def extract_schema(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("DEBUG - tables found:", tables)
        
    
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
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()  # Ensure connection is fully closed before deleting file


@app.route("/examples", methods=["GET"])
def view_examples():
    return render_template("examples.html", examples=training_examples)

@app.route("/delete-example", methods=["POST"])
def delete_example():
    index = int(request.form.get("index"))
    if 0 <= index < len(training_examples):
        training_examples.pop(index)
    return jsonify({"success": True})

@app.route("/training-data", methods=["GET"])
def get_training_data():
    return jsonify(training_examples)

@app.route("/delete-training/<int:index>", methods=["DELETE"])
def delete_training(index):
    if 0 <= index < len(training_examples):
        training_examples.pop(index)
        return jsonify({"success": True})
    return jsonify({"error": "Invalid index"}), 400


if __name__ == "__main__":
    app.run(debug=True)
