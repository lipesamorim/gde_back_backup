import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import threading
import os
import signal
import subprocess

# Função para executar scripts em uma thread separada
def execute_in_thread(target_function, *args, **kwargs):
    thread = threading.Thread(target=target_function, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()

# Função para rodar o core_back.py
def run_core_back():
    try:
        # Configurações de ambiente para evitar problemas com Wayland
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "xcb"  # Força o uso do backend "xcb" em vez de "wayland"

        process = subprocess.Popen(
            ["python", "core_back.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        stdout, stderr = process.communicate()  # Captura a saída do processo
        if process.returncode == 0:
            messagebox.showinfo("Sucesso", "Detecção concluída com sucesso!")
        else:
            stderr_message = stderr.decode().strip()
            messagebox.showerror("Erro", f"Falha ao executar core_back.py:\n{stderr_message}")
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao executar core_back.py:\n{e}")


# Função para parar processos específicos
def stop_core_back():
    try:
        processos = ["core_back.py", "adb", "scrcpy", "defeitos_deteccao.py","defeitos_deteccao.py"]

        for processo in processos:
            result = subprocess.run(["pgrep", "-f", processo], capture_output=True, text=True)
            if result.returncode == 0:  # Se encontrou processos
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    os.kill(int(pid), signal.SIGKILL)

        messagebox.showinfo("Sucesso", "Processos finalizados com sucesso!")
    except Exception as e:
        messagebox.showerror("Erro", f"Falha ao finalizar processos:\n{e}")


# Função para parar o processo core_back.py e liberar o dispositivo da câmera
# def stop_core_back():
#     try:
#         # Liberar o dispositivo da câmera
#         subprocess.run(["sudo", "fuser", "-k", "/dev/video2"], check=True)
#
#         # Finalizar o processo core_back.py
#         result = subprocess.run(["pgrep", "-f", "core_back.py"], capture_output=True, text=True)
#         if result.returncode == 0:  # Processos encontrados
#             pids = result.stdout.strip().split('\n')  # Obtém todos os PIDs
#             for pid in pids:
#                 os.kill(int(pid), signal.SIGKILL)  # Envia SIGKILL para cada PID
#             messagebox.showinfo("Sucesso", "Processo core_back.py finalizado com sucesso!")
#         else:
#             messagebox.showinfo("Informação", "Nenhum processo core_back.py em execução.")
#
#     except Exception as e:
#         messagebox.showerror("Erro", f"Falha ao finalizar core_back.py ou liberar a câmera:\n{e}")

# Função para iniciar outros scripts
def run_script(script_name, success_message, error_message):
    try:
        subprocess.run(["python", script_name], check=True)
        messagebox.showinfo("Sucesso", success_message)
    except Exception as e:
        messagebox.showerror("Erro", f"{error_message}:\n{e}")

# Função para iniciar os scripts específicos
def run_rename():
    run_script("rename.py", "Renomeação concluída com sucesso!", "Falha ao executar rename.py")

def run_train_models():
    run_script("treinar_modelos.py", "Treinamento concluído com sucesso!", "Falha ao executar treinar_modelos.py")

def start_front():
    run_script("start_front.py", "Ambientes front-end iniciados com sucesso!", "Falha ao iniciar o front-end")

def start_cvat_server():
    run_script("cvat.py", "Servidor CVAT iniciado com sucesso!", "Falha ao iniciar o servidor CVAT")

def create_dataset():
    run_script("criar_dataset.py", "Dataset criado com sucesso!", "Falha ao criar o dataset")

# Criação da interface
root = tk.Tk()
root.title("GDE")
root.geometry("720x520")
root.configure(bg="#FFFFFF")

# Adicionar a imagem
try:
    image_path = "gde.png"
    image = Image.open(image_path)
    image = image.resize((200, 100), Image.LANCZOS)
    photo = ImageTk.PhotoImage(image)

    label_image = tk.Label(root, image=photo, bg="#FFFFFF")
    label_image.image = photo
    label_image.pack(pady=20)
except Exception as e:
    print(f"Erro ao carregar a imagem: {e}")

# Frame para os botões
frame_left = tk.Frame(root, bg="#FFFFFF")
frame_left.pack(side="left", padx=10, pady=10, fill="both", expand=True)

frame_right = tk.Frame(root, bg="#FFFFFF")
frame_right.pack(side="right", padx=10, pady=10, fill="both", expand=True)

# Botões lado esquerdo
tk.Label(frame_left, text="Reconhecimento", font=("Helvetica", 14, "bold"), bg="#FFFFFF", fg="#2C3E50").pack(pady=10)

btn_start_front = tk.Button(
    frame_left, text="Iniciar Front-end",
    command=lambda: execute_in_thread(start_front),
    width=30, height=2, bg="#1D3557", fg="white",
    font=("Helvetica", 12, "bold"), relief="raised", bd=5
)
btn_start_front.pack(pady=10)

btn_core_back = tk.Button(
    frame_left, text="Executar Detecção",
    command=lambda: execute_in_thread(run_core_back),
    width=30, height=2, bg="#457B9D", fg="white",
    font=("Helvetica", 12, "bold"), relief="raised", bd=5
)
btn_core_back.pack(pady=10)

btn_stop_core_back = tk.Button(
    frame_left, text="Reiniciar Câmera",
    command=stop_core_back, width=20, height=1,
    bg="#E63946", fg="white", font=("Helvetica", 10),
    relief="raised", bd=3
)
btn_stop_core_back.pack(side="bottom", anchor="w", padx=10, pady=10)

# Botões lado direito
tk.Label(frame_right, text="Treinamento", font=("Helvetica", 14, "bold"), bg="#FFFFFF", fg="#2C3E50").pack(pady=10)

btn_cvat_server = tk.Button(
    frame_right, text="Iniciar Servidor CVAT",
    command=lambda: execute_in_thread(start_cvat_server),
    width=30, height=2, bg="#1D3557", fg="white",
    font=("Helvetica", 12, "bold"), relief="raised", bd=5
)
btn_cvat_server.pack(pady=10)

btn_rename = tk.Button(
    frame_right, text="Renomear Arquivos",
    command=lambda: execute_in_thread(run_rename),
    width=30, height=2, bg="#457B9D", fg="white",
    font=("Helvetica", 12, "bold"), relief="raised", bd=5
)
btn_rename.pack(pady=10)

btn_create_dataset = tk.Button(
    frame_right, text="Criar Dataset",
    command=lambda: execute_in_thread(create_dataset),
    width=30, height=2, bg="#457B9D", fg="white",
    font=("Helvetica", 12, "bold"), relief="raised", bd=5
)
btn_create_dataset.pack(pady=10)

btn_train_models = tk.Button(
    frame_right, text="Treinar Modelos",
    command=lambda: execute_in_thread(run_train_models),
    width=30, height=2, bg="#457B9D", fg="white",
    font=("Helvetica", 12, "bold"), relief="raised", bd=5
)
btn_train_models.pack(pady=10)

root.mainloop()