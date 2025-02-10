import os
import requests


def autenticar_cvat(base_url, username, password):
    """
    Realiza login no CVAT (com usuário e senha) e retorna
    um objeto 'requests.Session' com cookies de sessão válidos.

    Observação: dependendo da versão do CVAT, o endpoint de login pode ser:
      - /api/v1/auth/login  (mais comum em versões 2.x)
      - /api/auth/login     (algumas instalações custom)

    Se receber 404, tente ajustar a URL de login.
    """
    session = requests.Session()
    # Tente primeiro com /api/v1/auth/login
    url_login = f"{base_url}/auth/login"

    # Faz POST usando JSON
    response = session.post(url_login, json={
        "username": username,
        "password": password
    })

    if response.status_code == 200:
        print(f"[LOGIN] Sucesso para o usuário: {username}")
        return session
    else:
        print("[LOGIN] Falha. Status code:", response.status_code)
        print("Resposta:", response.text)
        return None


def criar_projeto(session, base_url, nome_projeto, labels):
    """
    Cria um projeto no CVAT com o nome e labels especificados.
    Retorna o ID do projeto criado se tiver sucesso, caso contrário None.
    """
    url = f"{base_url}/projects"
    payload = {
        "name": nome_projeto,
        "labels": [{"name": label.strip()} for label in labels]
    }
    r = session.post(url, json=payload)
    if r.status_code == 201:
        project_data = r.json()
        print(f"[PROJETO] '{nome_projeto}' criado com sucesso. ID: {project_data['id']}")
        return project_data["id"]
    else:
        print("[PROJETO] Falha ao criar projeto.")
        print("Status code:", r.status_code)
        print("Detalhes:", r.text)
        return None


def criar_task_no_projeto(session, base_url, projeto_id, nome_task):
    """
    Cria uma task dentro de um projeto existente no CVAT.
    Retorna o ID da task criada se tiver sucesso, caso contrário None.
    """
    url = f"{base_url}/tasks"
    payload = {
        "name": nome_task,
        "project_id": projeto_id
    }
    r = session.post(url, json=payload)
    if r.status_code == 201:
        task_data = r.json()
        print(f"[TASK] '{nome_task}' criada com sucesso. ID: {task_data['id']}")
        return task_data["id"]
    else:
        print("[TASK] Falha ao criar task.")
        print("Status code:", r.status_code)
        print("Detalhes:", r.text)
        return None


def upload_imagens_task(session, base_url, task_id, pasta_imagens):
    """
    Faz upload das imagens (arquivos .jpg/.png/etc) presentes em 'pasta_imagens'
    para a task especificada por 'task_id'.
    """
    url = f"{base_url}/tasks/{task_id}/data"

    # Lista arquivos da pasta
    arquivos = os.listdir(pasta_imagens)
    extensoes_validas = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tif', '.tiff')
    arquivos_imagem = [f for f in arquivos if f.lower().endswith(extensoes_validas)]

    if not arquivos_imagem:
        print("[UPLOAD] Nenhuma imagem encontrada na pasta especificada.")
        return

    # Prepara arquivos (multipart/form-data)
    files = []
    for nome_arquivo in arquivos_imagem:
        caminho_arquivo = os.path.join(pasta_imagens, nome_arquivo)
        files.append(('client_files', open(caminho_arquivo, 'rb')))

    data = {
        "image_quality": 70
    }

    r = session.post(url, data=data, files=files)

    # Fecha os arquivos abertos
    for _, f in files:
        f.close()

    if r.status_code == 202:
        print(f"[UPLOAD] {len(arquivos_imagem)} imagens enviadas com sucesso para a task {task_id}.")
    else:
        print("[UPLOAD] Falha ao enviar imagens.")
        print("Status code:", r.status_code)
        print("Detalhes:", r.text)


def main():
    # Se a sua instalação for realmente "http://localhost:8080/",
    # a API costuma ficar em "http://localhost:8080/api/v1".
    # Ajuste conforme sua versão do CVAT.
    BASE_URL = "http://localhost:8080/api/v1"

    # Credenciais
    USERNAME = "lipesamorim"
    PASSWORD = "Aplopes1952"

    # Autentica (login) via cookies
    session = autenticar_cvat(BASE_URL, USERNAME, PASSWORD)
    if not session:
        return  # Aborta se não conseguir logar

    # Pergunta ao usuário o nome do projeto
    nome_projeto = input("Digite o nome do projeto: ")
    # E as labels (separadas por vírgulas)
    labels_str = input("Digite as labels separadas por vírgulas: ")
    labels = [lbl.strip() for lbl in labels_str.split(",") if lbl.strip()]

    # Cria o projeto
    projeto_id = criar_projeto(session, BASE_URL, nome_projeto, labels)
    if not projeto_id:
        return

    # Cria uma task
    nome_task = f"{nome_projeto}-task"
    task_id = criar_task_no_projeto(session, BASE_URL, projeto_id, nome_task)
    if not task_id:
        return

    # Pede o caminho da pasta com as imagens
    pasta_imagens = input("Digite o caminho da pasta com as imagens: ")

    # Faz upload das imagens
    upload_imagens_task(session, BASE_URL, task_id, pasta_imagens)


if __name__ == "__main__":
    main()
