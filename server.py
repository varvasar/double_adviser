"""
Run on Laptop 2 (receiver).
- Simple Flask web server that receives clipboard text or screenshot images.
- If image received, runs OCR (pytesseract) to extract text (optional).
- Sends text/screenshot to an LLM (OpenAI API or local adapter).
- Saves history to a timestamped .md file.
- Renders all history in browser, newest-first.
"""
import base64
import io
import logging
import markdown
import os
import threading
import time

from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory
from openai import OpenAI

lock = threading.Lock()
app = Flask(__name__)
history = []  # list of {"id": int, "prompt": str, "result": str, "time": str}
next_id = 1
HISTORY_FILE = f"history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
MD_EXTENSIONS = ["fenced_code", "codehilite"]

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

try:
    from PIL import Image
except Exception:
    raise

# OCR: optional
try:
    import pytesseract
    HAVE_OCR = True
    pytesseract.pytesseract.tesseract_cmd = r"{}".format(os.environ.get('TESSERECT_PATH'))
except Exception:
    HAVE_OCR = False

USE_OPENAI = os.environ.get('LLM_USE_OPENAI', '1') == '1'

def save_to_md(entry):
    """Append new entry to history file"""
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"## Block {entry['id']} — {entry['time']}\n\n")
        f.write(f"**Prompt:**\n\n{entry['prompt']}\n\n")
        f.write(f"**Result:**\n\n{entry['result']}\n\n")
        f.write("---\n\n")

def ocr_from_image(img: Image.Image) -> str:
    if not HAVE_OCR:
        return ''
    return pytesseract.image_to_string(img)

def call_llm(prompt: str) -> str:
    """Minimal adapter. OpenAI or local model."""
    if USE_OPENAI:
        try:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            if not os.environ.get("OPENAI_API_KEY"):
                return 'OpenAI API key not set (set OPENAI_API_KEY)'
            resp = client.responses.create(
                model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
                instructions="You are a friendly but sarcastic assistant.",
                input=prompt,
            )
            return resp.output_text
        except Exception as e:
            return f'LLM call failed: {e}'
    else:
        return f'[LOCAL LLM MODE] Echoing prompt:\n\n{prompt[:2000]}'


# def _get_rendered_history():
#     with lock:
#         rev = list(reversed(history))
#     rendered = []
#     for e in rev:
#         rendered.append({
#             'id': e['id'],
#             'time': e['time'],
#             'prompt_html': markdown.markdown(e['prompt'], extensions=MD_EXTENSIONS),
#             'result_html': markdown.markdown(e['result'], extensions=MD_EXTENSIONS),
#         })
#     return rendered
@app.route("/")
def index():
    with lock:
        rendered_history = [
            {
                **entry,
                "prompt_html": markdown.markdown(entry["prompt"], extensions=MD_EXTENSIONS),
                "result_html": markdown.markdown(entry["result"], extensions=MD_EXTENSIONS),
            }
            for entry in reversed(history)  # 👈 newest first
        ]
    return render_template("result.html", history=rendered_history)

@app.route('/process', methods=['POST'])
def process():
    global next_id
    payload = request.get_json(force=True)

    if not payload or 'type' not in payload:
        return jsonify({'error': 'invalid payload'}), 400

    content_type = payload['type']
    extracted_text, raw = '', ''

    if content_type == 'text':
        extracted_text = payload.get('text', '')
        raw = extracted_text
    elif content_type == 'image':
        b64 = payload.get('image_b64', '')
        if not b64:
            return jsonify({'error': 'no image data'}), 400
        try:
            img_bytes = base64.b64decode(b64)
            img = Image.open(io.BytesIO(img_bytes))
            raw = f'[image {img.size} mode={img.mode}]'
            if HAVE_OCR:
                extracted_text = ocr_from_image(img)
            else:
                raw = f'[image {len(img_bytes)} bytes]'
                extracted_text = f"Analyze this screenshot (base64): {b64}"
        except Exception as e:
            return jsonify({'error': f'bad image: {e}'}), 400
    else:
        return jsonify({'error': 'unknown type'}), 400

    prompt = (
        f'Process the following input and produce a concise, actionable answer.\n\nInput:\n{extracted_text}'
        if extracted_text else
        f'No text found. Raw payload: {payload.get("meta")}'
    )

    llm_response = call_llm(prompt)

    with lock:
        entry = {
            "id": next_id,
            "prompt": prompt,
            "result": llm_response,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        history.append(entry)
        next_id += 1
        save_to_md(entry)

    return {"status": "ok", "id": entry["id"], 'result_preview': llm_response[:400]}

@app.route('/static/<path:p>')
def static_files(p):
    return send_from_directory('static', p)

if __name__ == '__main__':
    load_dotenv()
    app.run(host='0.0.0.0', port=int(os.environ.get('LLM_SERVER_PORT', 5000)), debug=True)
