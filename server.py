from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI
import os, json, time

load_dotenv()

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ASSISTANT_ID = os.getenv("ASSISTANT_ID")


@app.get("/")
def home():
    return {"status": "running"}


@app.post("/feasibility")
def feasibility():

    data = request.get_json()

    thread = client.beta.threads.create(
        messages=[{"role": "user", "content": json.dumps(data)}]
    )

    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID
    )

    while True:
        run = client.beta.threads.runs.retrieve(thread.id, run.id)
        if run.status in ["completed", "failed"]:
            break
        time.sleep(0.5)

    msgs = client.beta.threads.messages.list(thread.id)

    return jsonify({
        "response": msgs.data[0].content[0].text.value
    })


if __name__ == "__main__":
    app.run(port=2500, debug=True)