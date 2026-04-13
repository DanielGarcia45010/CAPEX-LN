from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import os, time, json, re

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

OPENAI_API_KEY = "OPENAI_API_KEY"
ASSISTANT_ID   = "ASSISTANT_ID"

client = OpenAI(api_key=OPENAI_API_KEY)

@app.get("/")
def home():
    return "API is running!"

def parse_json_payload(text: str):
    """
    Intenta parsear:
    - un único objeto { ... }
    - o una lista [ {...}, {...}, {...} ]
    Devuelve lista de objetos uniformada.
    """
    m = re.search(r"\[.*\]|\{.*\}", text, re.S)
    if not m:
        return None
    blob = m.group(0).strip()
    data = json.loads(blob)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return None

def call_assistant(costoObraCivil: float, mrc: float, term: int, thread_id: str | None):
    """
    Envía SOLO el JSON {costoObraCivil, mrc, term} al assistant.
    El assistant debe devolver 1 o varias oportunidades en el formato indicado.
    """
    user_json = json.dumps({
        "costoObraCivil": costoObraCivil,
        "mrc": mrc,
        "term": term
    })

    if thread_id is None:
        thread = client.beta.threads.create(messages=[{"role": "user", "content": user_json}])
        thread_id = thread.id
    else:
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_json)

    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)

    # Poll hasta completar
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run.status in ("completed", "failed", "cancelled", "expired"):
            break
        time.sleep(0.8)

    if run.status != "completed":
        return {"error": "run_failed", "thread_id": thread_id}

    # Toma el último mensaje del assistant
    msgs = client.beta.threads.messages.list(thread_id=thread_id)
    latest = next((m for m in msgs.data if m.role == "assistant"), msgs.data[0])
    raw_text = ""
    for block in latest.content:
        if getattr(block, "type", None) == "text":
            raw_text += block.text.value
        elif isinstance(block, str):
            raw_text += block

    try:
        items = parse_json_payload(raw_text)
        if not items:
            return {"error": "no_json", "raw": raw_text, "thread_id": thread_id}
        # Normaliza campos esperados
        normalized = []
        for i, op in enumerate(items, start=1):
            normalized.append({
                "oportunidad": op.get("oportunidad", i),
                "mrc": float(op["mrc"]),
                "nrc": float(op["nrc"]),
                "term": int(op["term"])
            })
        return {"opportunities": normalized, "thread_id": thread_id}
    except Exception:
        return {"error": "json_parse", "raw": raw_text, "thread_id": thread_id}

@app.post("/feasibility-advise")
def feasibility_advise():
    data = request.get_json(force=True)
    try:
        costoObraCivil = float(data["costoObraCivil"])
        mrc            = float(data["mrc"])
        term           = int(data["term"])
    except Exception:
        return jsonify({"error": "invalid_input"}), 400

    if costoObraCivil <= 0 or mrc <= 0 or term <= 0:
        return jsonify({"error": "invalid_input"}), 400

    thread_id = data.get("thread_id")
    result = call_assistant(costoObraCivil, mrc, term, thread_id)
    return jsonify(result), (200 if "opportunities" in result else 502)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=2500, debug=True)
