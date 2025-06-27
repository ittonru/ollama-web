from flask import Flask, render_template, request, jsonify, send_file
import requests
import json
import os
from datetime import datetime
import tempfile
import base64

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Загрузка списка моделей из файла
def load_models():
    try:
        with open('models.json', 'r', encoding='utf-8') as f:
            return json.load(f)['models']
    except FileNotFoundError:
        # Базовый список моделей, если файл не найден
        return [
            {"name": "llama2", "display_name": "Llama 2", "description": "Default model"},
            {"name": "mistral", "display_name": "Mistral 7B", "description": "Fast model"}
        ]

# Получение списка установленных моделей из Ollama
def get_installed_models():
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
    except:
        pass
    return []

def read_file_content(file):
    """Читает содержимое файла и возвращает текст"""
    try:
        content = file.read()

        # Попробуем декодировать как текст
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return content.decode('cp1251')
            except UnicodeDecodeError:
                try:
                    return content.decode('latin1')
                except UnicodeDecodeError:
                    return f"[Binary file: {file.filename}, size: {len(content)} bytes]"
    except Exception as e:
        return f"[Error reading file: {str(e)}]"

@app.route('/')
def index():
    models = load_models()
    installed_models = get_installed_models()

    # Отмечаем установленные модели
    for model in models:
        model['installed'] = model['name'] in installed_models

    return render_template('index.html', models=models)

@app.route('/chat', methods=['POST'])
def chat():
    try:
        # Получаем данные из формы
        model = request.form.get('model')
        message = request.form.get('message')

        print(f"Debug - Model: {model}")
        print(f"Debug - Message: {message}")
        print(f"Debug - Form data: {request.form}")
        print(f"Debug - Files: {request.files}")

        if not message:
            return jsonify({'error': 'Message is required'}), 400

        if not model:
            return jsonify({'error': 'Model is required'}), 400

        # Обработка прикрепленного файла
        file_content = ""
        attached_file = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                attached_file = file.filename
                file_content = read_file_content(file)
                message = f"File: {file.filename}\n\nContent:\n{file_content}\n\nQuestion: {message}"

        # Отправка запроса к Ollama API
        ollama_data = {
            'model': model,
            'prompt': message,
            'stream': False
        }

        print(f"Debug - Sending to Ollama: {ollama_data}")

        response = requests.post(
            'http://localhost:11434/api/generate',
            json=ollama_data,
            timeout=1800
        )

        if response.status_code == 200:
            result = response.json()
            return jsonify({
                'response': result.get('response', ''),
                'model': model,
                'timestamp': datetime.now().isoformat(),
                'has_file': bool(attached_file),
                'file_name': attached_file
            })
        else:
            print(f"Debug - Ollama error: {response.status_code}, {response.text}")
            return jsonify({'error': f'Ollama API error: {response.status_code}'}), 500

    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Cannot connect to Ollama. Make sure Ollama is running on localhost:11434'}), 503
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request timeout. The model might be loading or the request is too complex.'}), 504
    except Exception as e:
        print(f"Debug - Unexpected error: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/models/refresh', methods=['POST'])
def refresh_models():
    """Обновить список установленных моделей"""
    models = load_models()
    installed_models = get_installed_models()

    for model in models:
        model['installed'] = model['name'] in installed_models

    return jsonify({'models': models})

@app.route('/models/pull', methods=['POST'])
def pull_model():
    """Загрузить модель через Ollama"""
    data = request.json
    model_name = data.get('model')

    if not model_name:
        return jsonify({'error': 'Model name is required'}), 400

    try:
        # Запрос на загрузку модели
        response = requests.post(
            'http://localhost:11434/api/pull',
            json={'name': model_name},
            timeout=300  # 5 минут на загрузку
        )

        if response.status_code == 200:
            return jsonify({'success': True, 'message': f'Model {model_name} pulled successfully'})
        else:
            return jsonify({'error': f'Failed to pull model: {response.status_code}'}), 500

    except Exception as e:
        return jsonify({'error': f'Error pulling model: {str(e)}'}), 500

@app.route('/export/chat', methods=['POST'])
def export_chat():
    """Экспорт истории чата в файл"""
    data = request.json
    chat_history = data.get('chat_history', [])
    format_type = data.get('format', 'txt')  # txt, json, md

    if not chat_history:
        return jsonify({'error': 'No chat history to export'}), 400

    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format_type == 'json':
            filename = f'chat_export_{timestamp}.json'
            content = json.dumps(chat_history, indent=2, ensure_ascii=False)
            mimetype = 'application/json'

        elif format_type == 'md':
            filename = f'chat_export_{timestamp}.md'
            content = f"# Chat Export - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            for msg in chat_history:
                if msg['type'] == 'user':
                    content += f"## User\n{msg['content']}\n\n"
                else:
                    content += f"## Assistant ({msg.get('model', 'Unknown')})\n{msg['content']}\n\n"
            mimetype = 'text/markdown'

        else:  # txt
            filename = f'chat_export_{timestamp}.txt'
            content = f"Chat Export - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            content += "=" * 50 + "\n\n"
            for msg in chat_history:
                if msg['type'] == 'user':
                    content += f"USER: {msg['content']}\n\n"
                else:
                    content += f"ASSISTANT ({msg.get('model', 'Unknown')}): {msg['content']}\n\n"
                content += "-" * 30 + "\n\n"
            mimetype = 'text/plain'

        # Создаем временный файл
        temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=f'.{format_type}', encoding='utf-8')
        temp_file.write(content)
        temp_file.close()

        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )

    except Exception as e:
        return jsonify({'error': f'Export failed: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
