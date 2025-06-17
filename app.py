import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file

app = Flask(__name__)

# CORS middleware
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

# Configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "codellama:13b"
SESSION_DIR = "sessions"
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs("saved_files", exist_ok=True)

current_session = None

def get_available_models():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        return [model['name'] for model in response.json().get('models', [])]
    except:
        return [DEFAULT_MODEL]

def generate_response(prompt, model, file_content=None):
    full_prompt = prompt
    if file_content:
        full_prompt = f"File content:\n```\n{file_content}\n```\n\n{prompt}"

    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=1800
        )
        response.raise_for_status()
        return response.json()['response']
    except Exception as e:
        print(f"Error generating response: {str(e)}")
        return f"Error: {str(e)}"

@app.route('/')
def home():
    models = get_available_models()
    return render_template('index.html', models=models, default_model=DEFAULT_MODEL)

@app.route('/api/ask', methods=['POST'])
def ask():
    global current_session

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        prompt = data.get('prompt', '').strip()
        model = data.get('model', DEFAULT_MODEL).strip()
        file_content = data.get('file_content')

        if not prompt and not file_content:
            return jsonify({"error": "Prompt or file content required"}), 400

        # Generate response
        response = generate_response(prompt, model, file_content)

        # Save to session if active
        if current_session:
            session_data = {
                "timestamp": datetime.now().isoformat(),
                "prompt": prompt,
                "response": response,
                "model": model,
                "file_content": file_content
            }
            session_path = os.path.join(SESSION_DIR, f"{current_session}.json")

            try:
                if os.path.exists(session_path):
                    with open(session_path, 'r+') as f:
                        history = json.load(f)
                        history.append(session_data)
                        f.seek(0)
                        json.dump(history, f)
                else:
                    with open(session_path, 'w') as f:
                        json.dump([session_data], f)
            except Exception as e:
                print(f"Error saving session: {str(e)}")

        return jsonify({
            "response": response,
            "model": model
        })

    except Exception as e:
        print(f"Error in /api/ask: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions', methods=['GET', 'POST'])
def sessions():
    global current_session

    try:
        if request.method == 'GET':
            sessions = []
            for file in os.listdir(SESSION_DIR):
                if file.endswith('.json'):
                    sessions.append({
                        "name": file[:-5],
                        "size": os.path.getsize(os.path.join(SESSION_DIR, file))
                    })
            return jsonify({"sessions": sessions})

        elif request.method == 'POST':
            data = request.get_json()
            action = data.get('action')
            name = data.get('name', '').strip()

            if not name:
                return jsonify({"error": "Session name required"}), 400

            path = os.path.join(SESSION_DIR, f"{name}.json")

            if action == "new":
                if os.path.exists(path):
                    return jsonify({"error": "Session exists"}), 400

                with open(path, 'w') as f:
                    json.dump([], f)

                current_session = name
                return jsonify({"message": "Session created", "session": name})

            elif action == "load":
                if not os.path.exists(path):
                    return jsonify({"error": "Session not found"}), 404

                with open(path, 'r') as f:
                    history = json.load(f)

                current_session = name
                return jsonify({
                    "message": "Session loaded",
                    "session": name,
                    "history": history
                })

    except Exception as e:
        print(f"Error in sessions endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_content():
    try:
        data = request.get_json()
        content = data.get('content', '')
        filename = data.get('filename', '').strip()

        if not content:
            return jsonify({"error": "Content required"}), 400

        if not filename:
            filename = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        path = os.path.join("saved_files", filename)

        with open(path, 'w') as f:
            f.write(content)

        return jsonify({
            "message": "Content saved",
            "path": os.path.abspath(path)
        })

    except Exception as e:
        print(f"Error saving content: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='10.17.1.239', port=5000, debug=True)
