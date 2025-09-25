# LLM LAN Clipboard & Screenshot App

## Overview
This small system lets you press a hotkey on Laptop 1 to send the clipboard text (or screenshot if clipboard empty) to Laptop 2 over LAN. Laptop 2 runs a small server that extracts text (OCR if image), passes it to an LLM, and shows the AI's result in a browser.

## Setup
1. Install Python 3.10+ on both machines.
2. On both: `pip install -r requirements.txt` (install Tesseract separately if you want OCR).
3. Configure server IP on client (either edit client.py SERVER_URL or set env LLM_SERVER_URL).
4. Run server on Laptop 2: `python server.py` (set OPENAI_API_KEY env if using OpenAI).
5. Run client on Laptop 1: `python client.py`.
6. Press Ctrl+Alt+L on Laptop 1 to send.

## Security
This example is intentionally minimal. For any real use:
- Add authentication (API key, mutual TLS) before exposing on network.
- Use HTTPS.
- Limit accepted clients (IP allowlist).

## Customization
- Replace `call_llm` in server.py to call your local model runtime (llama.cpp, etc.).
- Change hotkey in client.py's HOTKEY set.
- Add file attachments, choose cropping or image pre-processing before OCR.