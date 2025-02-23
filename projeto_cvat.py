import requests
import tkinter as tk
from tkinter import simpledialog

# --------------------------------------------------
# CONFIGURAÇÕES DE ACESSO
# --------------------------------------------------
CVAT_URL = "http://localhost:8080/api"
USERNAME = "lipesamorim"
PASSWORD = "Aplopes1952"

# --------------------------------------------------
# FUNÇÕES AUXILIARES
# --------------------------------------------------

def get_auth_token():
    """
    Faz autenticação no CVAT e retorna o token de acesso.
    """
    response = requests.post(
        f"{CVAT_URL}/auth/login",
        json={"username": USERNAME, "password": PASSWORD}
    )
    response.raise_for_status()
    return response.json()["key"]  # Retorna o token recebido


def create_project(token, project_name, labels):
    """
    Cria um novo projeto no CVAT, com as labels fornecidas.
    Retorna o ID do projeto.
    """
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

# --------------------------------------------------
# FLUXO PRINCIPAL
# --------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    # 1) Obter o nome do projeto
    project_name = simpledialog.askstring("Criar Projeto", "Digite o nome do projeto:")
    if not project_name:
        print("Nome do projeto não pode ser vazio. Encerrando.")
        exit()

    # 2) Obter labels, separadas por vírgula
    labels_str = simpledialog.askstring("Criar Labels", "Digite as labels separadas por vírgula:")
    labels = [label.strip().lower() for label in labels_str.split(",") if label.strip()]
    if not labels:
        print("É necessário pelo menos uma label. Encerrando.")
        exit()

    # 3) Autenticar no CVAT
    try:
        token = get_auth_token()
    except requests.RequestException as e:
        print("Erro ao autenticar no CVAT:", e)
        exit()

    # 4) Criar o projeto
    try:
        project_id = create_project(token, project_name, labels)
        print(f"Projeto '{project_name}' criado com sucesso! ID do projeto: {project_id}")
    except requests.RequestException as e:
        print("Erro ao criar o projeto:", e)
        exit()

    # OBS: A criação da task e o upload das imagens
    #      serão feitos manualmente na interface do CVAT.
    print("\nCriação de tarefa e upload serão feitos manualmente no CVAT.")

