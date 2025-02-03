import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import subprocess
import threading
import os
import webbrowser

# Função para executar scripts em uma thread separada
def execute_in_thread(target_function, *args, **kwargs):
    thread = threading.Thread(target=target_function, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()

# Funções para controlar os containers do CVAT
def iniciar_servidor(diretorio_cvat, log_text, status_label):
    try:
        if not os.path.exists(diretorio_cvat):
            messagebox.showerror("Erro", f"O diretório {diretorio_cvat} não existe.")
            log_text.insert(tk.END, f"[Erro] O diretório {diretorio_cvat} não existe.\n")
            return
        os.chdir(diretorio_cvat)
        subprocess.run(["docker-compose", "up", "-d"], check=True)
        messagebox.showinfo("Sucesso", "Servidor CVAT iniciado com sucesso!")
        log_text.insert(tk.END, "[Info] Servidor CVAT iniciado com sucesso!\n")
        status_label.config(text="Status: Servidor Iniciado")

        # Abre a página do CVAT no navegador
        webbrowser.open("http://localhost:8080", new=2)  # new=2 abre a URL em uma nova aba do navegador

    except subprocess.CalledProcessError as e:
        messagebox.showerror("Erro", f"Erro ao iniciar o servidor: {e}")
        log_text.insert(tk.END, f"[Erro] Falha ao iniciar o servidor: {e}\n")
    except FileNotFoundError:
        messagebox.showerror("Erro", "O comando docker-compose não foi encontrado. Certifique-se de que o Docker está instalado.")
        log_text.insert(tk.END, "[Erro] O comando docker-compose não foi encontrado.\n")

def parar_servidor(diretorio_cvat, log_text, status_label):
    try:
        if not os.path.exists(diretorio_cvat):
            messagebox.showerror("Erro", f"O diretório {diretorio_cvat} não existe.")
            log_text.insert(tk.END, f"[Erro] O diretório {diretorio_cvat} não existe.\n")
            return
        os.chdir(diretorio_cvat)
        subprocess.run(["docker-compose", "down"], check=True)
        messagebox.showinfo("Sucesso", "Servidor CVAT parado com sucesso!")
        log_text.insert(tk.END, "[Info] Servidor CVAT parado com sucesso!\n")
        status_label.config(text="Status: Servidor Parado")
    except subprocess.CalledProcessError as e:
        messagebox.showerror("Erro", f"Erro ao parar o servidor: {e}")
        log_text.insert(tk.END, f"[Erro] Falha ao parar o servidor: {e}\n")
    except FileNotFoundError:
        messagebox.showerror("Erro", "O comando docker-compose não foi encontrado. Certifique-se de que o Docker está instalado.")
        log_text.insert(tk.END, "[Erro] O comando docker-compose não foi encontrado.\n")

# Criação da interface
root = tk.Tk()
root.title("Controle CVAT")
root.geometry("720x400")  # Janela maior e retangular
root.configure(bg="#FFFFFF")  # Fundo branco

# Adicionar a imagem
try:
    image_path = "gde.png"  # Caminho para a imagem (substitua por seu arquivo de imagem)
    image = Image.open(image_path)
    image = image.resize((200, 100), Image.LANCZOS)
    photo = ImageTk.PhotoImage(image)

    label_image = tk.Label(root, image=photo, bg="#FFFFFF")
    label_image.image = photo
    label_image.pack(pady=20)  # Adicionar um espaçamento inferior
except Exception as e:
    print(f"Erro ao carregar a imagem: {e}")

# Frame para os painéis (esquerdo e direito)
frame_left = tk.Frame(root, bg="#FFFFFF")
frame_left.pack(side="left", padx=10, pady=10, fill="both", expand=True)

frame_right = tk.Frame(root, bg="#FFFFFF")
frame_right.pack(side="right", padx=10, pady=10, fill="both", expand=True)

# Título no lado esquerdo
label_iniciar = tk.Label(frame_left, text="Iniciar Servidor", font=("Helvetica", 14, "bold"), bg="#FFFFFF")
label_iniciar.pack(pady=10)

# Botões no lado esquerdo (para iniciar o servidor)
btn_iniciar = tk.Button(
    frame_left,
    text="Iniciar Servidor",
    command=lambda: execute_in_thread(iniciar_servidor, "/home/amorim/Documentos/cvat", log_text, label_status),  # Alterado para label_status
    width=30,
    height=2,
    bg="#1B4F72",  # Azul mais escuro
    fg="white",
    font=("Helvetica", 12, "bold"),
    relief="raised",  # Efeito 3D
    bd=5  # Borda mais espessa para criar a sombra
)
btn_iniciar.pack(pady=10)

# Botão para parar o servidor
btn_parar = tk.Button(
    frame_left,
    text="Parar Servidor",
    command=lambda: execute_in_thread(parar_servidor, "/home/amorim/Documentos/cvat", log_text, label_status),  # Alterado para label_status
    width=30,
    height=2,
    bg="#5DADE2",  # Azul claro
    fg="white",
    font=("Helvetica", 12, "bold"),
    relief="raised",  # Efeito 3D
    bd=5  # Borda mais espessa para criar a sombra
)
btn_parar.pack(pady=10)

# Título no lado direito
label_status = tk.Label(frame_right, text="Status: Servidor Parado", font=("Helvetica", 14, "bold"), bg="#FFFFFF")
label_status.pack(pady=10)

# Área de log
log_text = tk.Text(frame_right, width=40, height=10, font=("Helvetica", 12), bg="#f5f5f5")
log_text.pack(pady=10)

# Rodar a interface
root.mainloop()
