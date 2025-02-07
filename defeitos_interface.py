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

# Função para rodar o defeitos_deteccao.py
def run_defeitos_deteccao():
    try:
        # Configurações de ambiente para evitar problemas com Wayland
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "xcb"  # Força o uso do backend "xcb" em vez de "wayland"

        process = subprocess.Popen(
            ["python", "defeitos_deteccao.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env
        )
        stdout, stderr = process.communicate()  # Captura a saída do processo
        if process.returncode == 0:
            messagebox.showinfo("Sucesso", "Detecção concluída com sucesso!")
        else:
            stderr_message = stderr.decode().strip()
            messagebox.showerror("Erro", f"Falha ao executar defeitos_deteccao.py:\n{stderr_message}")
    except Exception as e:
        messagebox.showerror("Erro", f"Erro ao executar defeitos_deteccao.py:\n{e}")

# Função para parar processos específicos
def stop_defeitos_deteccao():
    try:
        processos = ["core_back.py", "adb", "scrcpy", "defeitos_deteccao.py"]

        for processo in processos:
            result = subprocess.run(["pgrep", "-f", processo], capture_output=True, text=True)
            if result.returncode == 0:  # Se encontrou processos
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    os.kill(int(pid), signal.SIGKILL)

        messagebox.showinfo("Sucesso", "Processos finalizados com sucesso!")
    except Exception as e:
        messagebox.showerror("Erro", f"Falha ao finalizar processos:\n{e}")

# Função para iniciar outros scripts
def run_script(script_name, success_message, error_message):
    try:
        subprocess.run(["python", script_name], check=True)
        messagebox.showinfo("Sucesso", success_message)
    except Exception as e:
        messagebox.showerror("Erro", f"{error_message}:\n{e}")

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

btn_defeitos_deteccao = tk.Button(
    text="Iniciar Deteccao de Defeitos",
    command=lambda: execute_in_thread(run_defeitos_deteccao),  # Correção aqui
    width=30, height=2, bg="#1D3557", fg="white",
    font=("Helvetica", 12, "bold"), relief="raised", bd=5
)
btn_defeitos_deteccao.pack(pady=10)

btn_stop_defeitos_deteccao = tk.Button(
    text="Reiniciar Câmera",
    command=stop_defeitos_deteccao,  # Correção aqui
    width=20, height=1,
    bg="#E63946", fg="white", font=("Helvetica", 10),
    relief="raised", bd=3
)
btn_stop_defeitos_deteccao.pack(side="bottom", anchor="w", padx=10, pady=10)

root.mainloop()