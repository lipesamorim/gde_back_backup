import requests
import os
import logging
from tkinter import filedialog, ttk, messagebox, scrolledtext
import tkinter as tk

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class CVATUploaderApp:
    def __init__(self, master):
        self.master = master
        master.title("CVAT Bulk Upload")

        # Configurações do servidor
        self.CVAT_URL = "http://localhost:8080/api"
        self.USERNAME = "lipesamorim"
        self.PASSWORD = "Aplopes1952"
        self.SEGMENT_SIZE = 150

        # Interface
        self.create_widgets()

    def create_widgets(self):
        # Frame principal
        main_frame = ttk.Frame(self.master, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Componentes da interface (mantido igual)
        ttk.Label(main_frame, text="Pasta de Imagens:").grid(row=0, column=0, sticky=tk.W)
        self.folder_path = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.folder_path, width=50).grid(row=0, column=1)
        ttk.Button(main_frame, text="Procurar", command=self.browse_folder).grid(row=0, column=2)

        ttk.Label(main_frame, text="Nome do Projeto:").grid(row=1, column=0, sticky=tk.W)
        self.project_name = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.project_name, width=50).grid(row=1, column=1, columnspan=2, sticky=tk.W)

        ttk.Label(main_frame, text="Labels (separadas por vírgula):").grid(row=2, column=0, sticky=tk.W)
        self.labels_entry = ttk.Entry(main_frame, width=50)
        self.labels_entry.grid(row=2, column=1, columnspan=2, sticky=tk.W)

        self.console = scrolledtext.ScrolledText(main_frame, height=10, width=70)
        self.console.grid(row=4, column=0, columnspan=3, pady=10)

        ttk.Button(main_frame, text="Enviar para CVAT", command=self.start_upload).grid(row=5, column=1, pady=10)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            self.log(f"Pasta selecionada: {folder}")

    def log(self, message):
        self.console.insert(tk.END, message + "\n")
        self.console.see(tk.END)
        self.master.update_idletasks()

    def start_upload(self):
        if not all([self.folder_path.get(), self.project_name.get(), self.labels_entry.get()]):
            messagebox.showerror("Erro", "Preencha todos os campos!")
            return

        labels = [label.strip() for label in self.labels_entry.get().split(',')]
        image_folder = self.folder_path.get()

        try:
            self.upload_to_cvat(
                image_folder=image_folder,
                project_name=self.project_name.get(),
                labels=labels
            )
            messagebox.showinfo("Sucesso", "Upload concluído com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro", str(e))
            self.log(f"ERRO: {str(e)}")

    def upload_to_cvat(self, image_folder, project_name, labels):
        session = requests.Session()
        self.log("Conectando ao CVAT...")

        try:
            # Autenticação
            login_data = {"username": self.USERNAME, "password": self.PASSWORD}
            response = session.post(f"{self.CVAT_URL}/auth/login", json=login_data)

            if response.status_code != 200:
                raise Exception(f"Falha na autenticação: {response.text}")

            csrf_token = session.cookies.get("csrftoken")
            session.headers.update({
                "X-CSRFToken": csrf_token,
                "Referer": self.CVAT_URL
            })

            # Criar projeto
            self.log("Criando projeto...")
            project_data = {
                "name": project_name,
                "labels": [{"name": label, "attributes": []} for label in labels]
            }
            response = session.post(f"{self.CVAT_URL}/projects", json=project_data)

            if response.status_code != 201:
                raise Exception(f"Erro ao criar projeto: {response.text}")

            project_id = response.json()["id"]
            self.log(f"Projeto criado (ID: {project_id})")

            # Coletar imagens
            image_files = []
            valid_extensions = ('.jpg', '.png', '.jpeg')
            for filename in os.listdir(image_folder):
                if filename.lower().endswith(valid_extensions):
                    image_files.append(os.path.join(image_folder, filename))

            if not image_files:
                raise Exception("Nenhuma imagem válida encontrada na pasta")

            self.log(f"Encontradas {len(image_files)} imagens válidas")

            # Upload das imagens
            self.log("Iniciando upload...")
            upload_url = f"{self.CVAT_URL}/data"

            # Iterar sobre as imagens e fazer upload em partes
            for img_path in image_files:
                try:
                    self.upload_image_in_chunks(session, img_path, upload_url, csrf_token)
                except Exception as e:
                    self.log(f"Erro ao enviar {img_path}: {str(e)}")
                    continue

            self.log(f"Upload concluído para {len(image_files)} imagens!")

            # Criar tarefa
            self.log("Criando tarefa...")
            task_data = {
                "name": f"Task - {project_name}",
                "project_id": project_id,
                "segment_size": self.SEGMENT_SIZE
            }
            response = session.post(f"{self.CVAT_URL}/tasks", json=task_data)

            if response.status_code != 201:
                raise Exception(f"Erro ao criar tarefa: {response.text}")

            task_id = response.json()["id"]
            self.log(f"Tarefa criada (ID: {task_id})")

        except Exception as e:
            logger.error("Erro durante o processo:", exc_info=True)
            raise

    def upload_image_in_chunks(self, session, img_path, upload_url, csrf_token):
        """Upload a single image in chunks."""
        file_size = os.path.getsize(img_path)
        chunk_size = 1024 * 1024  # 1 MB per chunk
        file_name = os.path.basename(img_path)

        # Iniciar o upload
        with open(img_path, "rb") as f:
            chunk_index = 0
            while chunk := f.read(chunk_size):
                self.log(f"Enviando chunk {chunk_index + 1} para {file_name}")
                headers = {
                    "X-CSRFToken": csrf_token,
                    "Upload-Length": str(file_size),
                    "Upload-Offset": str(chunk_index * chunk_size),
                    "Upload-Name": file_name,
                }

                response = session.put(upload_url, headers=headers, data=chunk)
                if response.status_code != 200:
                    raise Exception(f"Erro no upload do chunk: {response.text}")
                chunk_index += 1
                self.log(f"Chunk {chunk_index} enviado com sucesso.")

            # Finalizar upload após o envio de todos os chunks
            headers["Upload-Finish"] = "true"
            response = session.put(upload_url, headers=headers)
            if response.status_code != 200:
                raise Exception(f"Erro ao finalizar upload: {response.text}")
            self.log(f"Upload finalizado para {file_name}.")


if __name__ == "__main__":
    root = tk.Tk()
    app = CVATUploaderApp(root)
    root.mainloop()
