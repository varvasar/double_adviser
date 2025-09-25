"""
Run on Laptop 1 (sender).
- Listens for hotkey (Ctrl+Alt+L by default).
- When pressed, grabs clipboard text. If empty, takes a screenshot.
- Sends content to server (Laptop 2) over LAN via HTTP POST.
- Shows a small notification (optional).
"""

import io
import os
import time
import base64
import json
import threading
import argparse
from pathlib import Path

import requests
from pynput import keyboard
import pyperclip
from PIL import ImageGrab

# Config
SERVER_URL = os.environ.get('LLM_SERVER_URL', 'http://192.168.1.100:5000/process')
HOTKEY = {keyboard.Key.ctrl_l, keyboard.Key.alt_l, keyboard.KeyCode.from_char('l')}

# Internal state for hotkey
current_keys = set()


def send_text(text, meta):
    payload = {
        'type': 'text',
        'text': text,
        'meta': meta,
    }
    try:
        r = requests.post(SERVER_URL, json=payload, timeout=30)
        r.raise_for_status()
        print('Sent text, server responded:', r.text)
    except Exception as e:
        print('Failed to send text:', e)


def send_image(img: 'PIL.Image.Image', meta):
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    payload = {
        'type': 'image',
        'image_b64': b64,
        'meta': meta,
    }
    try:
        r = requests.post(SERVER_URL, json=payload, timeout=60)
        r.raise_for_status()
        print('Sent image, server responded:', r.text)
    except Exception as e:
        print('Failed to send image:', e)


def on_press(key):
    try:
        if key in HOTKEY or (isinstance(key, keyboard.KeyCode) and key.char == 'l'):
            current_keys.add(key)
        else:
            current_keys.add(key)
    except AttributeError:
        current_keys.add(key)

    if all(k in current_keys for k in HOTKEY):
        # Hotkey triggered
        threading.Thread(target=handle_capture_and_send, daemon=True).start()


def on_release(key):
    try:
        current_keys.discard(key)
    except KeyError:
        pass


def handle_capture_and_send():
    print('Hotkey pressed — capturing...')
    text = None
    try:
        text = pyperclip.paste()
        if text and len(text.strip()) > 0:
            meta = {'source': 'clipboard', 'timestamp': time.time()}
            send_text(text, meta)
            return
    except Exception as e:
        print('Clipboard read failed:', e)

    # If no clipboard text, take a screenshot
    try:
        img = ImageGrab.grab()
        meta = {'source': 'screenshot', 'timestamp': time.time()}
        send_image(img, meta)
    except Exception as e:
        print('Screenshot failed:', e)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', help='Server URL (default from env or in code)')
    parser.add_argument('--hotkey', help='Hotkey characters, e.g. ctrl+alt+l', default=None)
    args = parser.parse_args()
    global SERVER_URL
    if args.server:
        SERVER_URL = args.server

    print('Starting client. Sending to', SERVER_URL)
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == '__main__':
    main()
