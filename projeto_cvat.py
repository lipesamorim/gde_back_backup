import os
import requests
import tkinter as tk
from tkinter import filedialog, simpledialog

# Configurações do CVAT
CVAT_URL = "http://localhost:8080/api"
USERNAME = "lipesamorim"
PASSWORD = "Aplopes1952"


# Autenticação no CVAT
def get_auth_token():
    response = requests.post(f"{CVAT_URL}/auth/login", json={"username": USERNAME, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["key"]  # Retorna o token


def create_project(token, project_name, labels):
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": project_name,
        "labels": [{"name": label} for label in labels]
    }
    response = requests.post(f"{CVAT_URL}/projects", json=data, headers=headers)
    response.raise_for_status()
    return response.json()["id"]


def create_task(token, project_id, task_name):
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": task_name,
        "project_id": project_id
    }
    response = requests.post(f"{CVAT_URL}/tasks", json=data, headers=headers)
    response.raise_for_status()
    return response.json()["id"]


def upload_images(token, task_id, image_folder):
    headers = {
        "Authorization": f"Token {token}"
    }
    images = [os.path.join(image_folder, img) for img in os.listdir(image_folder) if
              img.lower().endswith(('png', 'jpg', 'jpeg'))]

    if not images:
        print("Nenhuma imagem encontrada na pasta selecionada.")
        return

    files = [('image', (os.path.basename(img), open(img, 'rb'), 'image/jpeg')) for img in images]

    data = {
        "image_quality": "70",
        "chunk_size": "10"
    }

    response = requests.post(f"{CVAT_URL}/tasks/{task_id}/data", headers=headers, files=files, data=data)

    # Verifique o status code e a resposta para entender o que aconteceu
    if response.status_code == 200:
        print("Imagens carregadas com sucesso.")
    else:
        print(f"Erro no upload das imagens. Código de status: {response.status_code}")
        print(f"Resposta: {response.text}")

    # Fechar os arquivos após o envio
    for file_tuple in files:
        file_tuple[1][1].close()  # Fecha o arquivo



# Interface para entrada de dados
root = tk.Tk()
root.withdraw()

# Obter nome do projeto
project_name = simpledialog.askstring("Criar Projeto", "Digite o nome do projeto:")
if not project_name:
    print("Nome do projeto não pode ser vazio.")
    exit()

# Obter labels
labels = simpledialog.askstring("Criar Labels", "Digite as labels separadas por vírgula:")
labels = [label.strip().lower() for label in labels.split(",") if label.strip()]
if not labels:
    print("É necessário pelo menos uma label.")
    exit()

# Autenticação
try:
    token = get_auth_token()
except requests.RequestException as e:
    print("Erro ao autenticar no CVAT:", e)
    exit()

# Criar projeto
try:
    project_id = create_project(token, project_name, labels)
    print(f"Projeto '{project_name}' criado com ID {project_id}.")
except requests.RequestException as e:
    print("Erro ao criar o projeto:", e)
    exit()

# Criar task
task_name = f"{project_name}_01"
try:
    task_id = create_task(token, project_id, task_name)
    print(f"Task '{task_name}' criada com ID {task_id}.")
except requests.RequestException as e:
    print("Erro ao criar a task:", e)
    exit()

# Selecionar pasta com imagens
image_folder = filedialog.askdirectory(title="Selecione a pasta com imagens")
if not image_folder:
    print("Nenhuma pasta selecionada.")
    exit()

# Upload de imagens
try:
    upload_images(token, task_id, image_folder)
except requests.RequestException as e:
    print("Erro ao carregar as imagens:", e)
    exit()