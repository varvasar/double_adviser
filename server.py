"""
Run on Laptop 2 (receiver).
- Simple Flask web server that receives clipboard text or screenshot images.
- If image received, runs OCR (pytesseract) to extract text.
- Sends text to an LLM (two options: OpenAI API or a local LLM adapter function). The LLM function is modular and easy to replace.
- Renders the result in a small browser UI.
"""

from flask import Flask, request, render_template, jsonify, send_from_directory
import base64
import io
import os
import time
from openai import OpenAI
from threading import Lock
from dotenv import load_dotenv

import logging
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
    pytesseract.pytesseract.tesseract_cmd = r"c:\Program Files\Tesseract-OCR\tesseract.exe"
except Exception:
    HAVE_OCR = False


# HAVE_OCR = False

# LLM: you can implement either openai or local llama-cpp-python adapter
USE_OPENAI = os.environ.get('LLM_USE_OPENAI', '1') == '1'

app = Flask(__name__)

# Most recent result stored in-memory for UI
last_result = {'text': '', 'raw': '', 'meta': None, 'timestamp': None}
lock = Lock()


def ocr_from_image(img: Image.Image) -> str:
    if not HAVE_OCR:
        return ''
    return pytesseract.image_to_string(img)


# Example LLM adapter: replace body with a call to your preferred model

def call_llm(prompt: str) -> str:
    """
    Minimal adapter. By default uses OpenAI if configured via OPENAI_API_KEY env var.
    If you want to use a local LLM, replace this function with the code calling
    your local runtime (llama.cpp, text-generation-webui, etc.).
    """
    if USE_OPENAI:
        try:
            client = OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
            )

            if not os.environ.get("OPENAI_API_KEY"):
                return 'OpenAI API key not set (set OPENAI_API_KEY)'

            resp = client.responses.create(
                model="gpt-4o",
                instructions="You are a friendly but sarcastic assistant.",
                input=prompt,
            )

            # resp = openai.ChatCompletion.create(
            #     model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
            #     messages=[{'role': 'user', 'content': prompt}],
            #     max_tokens=800,
            # )
            # return resp.choices[0].message.content.strip()
            # print(resp)
            return resp.output_text
        except Exception as e:
            return f'LLM call failed: {e}'
    else:
        # Placeholder for local LLM — user should implement connection to their local model
        return f'[LOCAL LLM MODE] Echoing prompt (implement your local LLM call):\n\n{prompt[:2000]}'


@app.route('/')
def index():
    with lock:
        data = dict(last_result)
    return render_template('result.html', result=data)


@app.route('/process', methods=['POST'])
def process():
    payload = request.get_json(force=True)

    if not payload or 'type' not in payload:
        return jsonify({'error': 'invalid payload'}), 400

    content_type = payload['type']
    extracted_text = ''
    raw = ''

    if content_type == 'text':
        extracted_text = payload.get('text', '')
        raw = extracted_text
    elif content_type == 'image':
        print("Payload type:", payload['type'])
        print("Image b64 length:", len(payload.get('image_b64', '')))

        b64 = payload.get('image_b64', '')
        if not b64:
            return jsonify({'error': 'no image data'}), 400
        try:
            img_bytes = base64.b64decode(b64)
            print("Decoded bytes:", len(img_bytes))
            img = Image.open(io.BytesIO(img_bytes))
            print("Image format:", img.format, "size:", img.size)
            raw = f'[image {img.size} mode={img.mode}]'
            if HAVE_OCR:
                extracted_text = ocr_from_image(img)
            else:
                raw = f'[image {len(img_bytes)} bytes]'
                # extracted_text = f'[Screenshot received: {len(img_bytes)} bytes. Describe or analyze this screenshot.]'
                extracted_text = llm_input = f"Analyze this screenshot (base64): {b64}"
        except Exception as e:
            print("Image decode failed:", e)
            return jsonify({'error': f'bad image: {e}'}), 400
    else:
        return jsonify({'error': 'unknown type'}), 400

    if not extracted_text:
        prompt = f'No text found. Raw payload meta: {payload.get("meta")}\nYou can summarize the raw content or explain what to do next.'
    else:
        prompt = f'Process the following input and produce a concise, actionable answer (summary, steps, code, or other); include source if relevant.\n\nInput:\n{extracted_text}'


    # Call LLM
    llm_response = call_llm(prompt)

    with lock:
        last_result['text'] = llm_response
        last_result['raw'] = raw
        last_result['meta'] = payload.get('meta')
        last_result['timestamp'] = time.time()

    return jsonify({'status': 'ok', 'result_preview': llm_response[:400]})

# Small static files (template will be included below)
@app.route('/static/<path:p>')
def static_files(p):
    return send_from_directory('static', p)


if __name__ == '__main__':
    load_dotenv()
    app.run(host='0.0.0.0', port=int(os.environ.get('LLM_SERVER_PORT', 5000)), debug=True)
