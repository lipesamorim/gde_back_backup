import gc
import torch
import threading
from ultralytics import YOLO
import tkinter as tk
from tkinter import messagebox, Listbox, MULTIPLE, Scrollbar, END, ttk
import os
from concurrent.futures import ThreadPoolExecutor

BASE_PATH_PROJECT = os.path.dirname(os.path.abspath(__file__))

def train_model(model_name, base_path, results_path, log_text, epochs, img_size, batch_size, model_type, model_size):
    """
    Função para treinar um modelo individualmente.
    """
    try:
        model_path = os.path.join(base_path, model_name)
        custom_results_dir = os.path.join(results_path, model_name)

        if not os.path.exists(custom_results_dir):
            os.makedirs(custom_results_dir)

        # Carregar pesos conforme o tipo e tamanho
        weights_path = os.path.join(model_path, f'{model_size}.pt')
        if not os.path.exists(weights_path):
            log_text.insert(tk.END, f"[AVISO] Pesos {weights_path} não encontrados. Usando pesos padrão.\n")
            weights_path = f'{model_size}.pt'  # Certifique-se de que esses pesos padrão estão disponíveis

        data_path = os.path.join(model_path, 'dataset', 'data.yaml')
        if not os.path.exists(data_path):
            log_text.insert(tk.END, f"[ERRO] Dados {data_path} não encontrados. Pulando {model_name}.\n")
            return

        log_text.insert(tk.END, f"Treinando modelo: {model_name} ({model_type} - {model_size})\n")
        log_text.see(END)

        # Determinar o tipo de tarefa
        task = 'segment' if model_type == 'yolov8-seg' else 'detect'

        # Inicia o treinamento
        model = YOLO(weights_path)
        model.train(
            data=data_path,
            epochs=epochs,
            imgsz=img_size,
            batch=batch_size,
            task=task,
            project=custom_results_dir,
            amp=True
        )

        log_text.insert(tk.END, f"[SUCESSO] Treinamento concluído para {model_name}.\n")
        log_text.see(END)

    except Exception as e:
        log_text.insert(tk.END, f"[ERRO] Erro ao treinar {model_name}: {e}\n")
        log_text.see(END)
    finally:
        # Libera memória da GPU
        gc.collect()
        torch.cuda.empty_cache()


def train_all_models(base_path, results_path, selected_models, log_text, epochs, img_size, batch_size, model_type, model_size, progress_bar):
    """
    Função para treinar todos os modelos selecionados.
    """
    log_text.insert(tk.END, "Iniciando treinamento dos modelos...\n")
    log_text.see(END)

    total_models = len(selected_models)
    progress_bar["maximum"] = total_models

    with ThreadPoolExecutor() as executor:
        for i, model_name in enumerate(selected_models):
            executor.submit(train_model, model_name, base_path, results_path, log_text, epochs, img_size, batch_size, model_type, model_size)
            progress_bar["value"] = i + 1
            root.update_idletasks()

    log_text.insert(tk.END, "Treinamento finalizado.\n")
    messagebox.showinfo("Concluído", "Treinamento finalizado!")
    progress_bar["value"] = 0  # Resetar barra de progresso


def get_models(base_path):
    return [folder for folder in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, folder))]


def start_training():
    selected_indices = listbox_models.curselection()
    selected_models = [listbox_models.get(i) for i in selected_indices]

    if not selected_models:
        messagebox.showwarning("Aviso", "Selecione pelo menos um modelo para treinar.")
        return

    try:
        epochs = int(entry_epochs.get())
        img_size = int(entry_img_size.get())
        batch_size = int(entry_batch_size.get())
        model_type = model_type_var.get()
        model_size = model_size_var.get()
    except ValueError:
        messagebox.showwarning("Aviso", "Por favor, insira valores válidos para os parâmetros.")
        return

    btn_train.config(state=tk.DISABLED)
    threading.Thread(target=train_all_models, args=(base_path, results_path, selected_models, log_text, epochs, img_size, batch_size, model_type, model_size, progress_bar)).start()
    btn_train.config(state=tk.NORMAL)


# Configurações de caminhos fixos
base_path = f'{BASE_PATH_PROJECT}/treinamento'
results_path = f'{BASE_PATH_PROJECT}/resultadotreinamento'

# Criar interface gráfica
root = tk.Tk()
root.title("Painel de Treinamento - YOLOv8")
root.geometry("1000x800")
root.configure(bg="#FFFFFF")

label_title = tk.Label(root, text="Treinamento de Modelos YOLOv8",
                       font=("Helvetica", 20, "bold"),
                       bg="#FFFFFF", fg="#1B4F72")
label_title.pack(pady=20)

label_models = tk.Label(root, text="Modelos disponíveis:",
                        bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 14))
label_models.pack(pady=5)

frame_listbox = tk.Frame(root, bg="#FFFFFF")
frame_listbox.pack(pady=10)

listbox_models = Listbox(frame_listbox, selectmode=MULTIPLE, width=50, height=10, font=("Helvetica", 12))
scrollbar = Scrollbar(frame_listbox, orient="vertical", command=listbox_models.yview)
listbox_models.config(yscrollcommand=scrollbar.set)
listbox_models.pack(side="left", fill="y")
scrollbar.pack(side="right", fill="y")

# Preencher a lista com os modelos
models = get_models(base_path)
for model in models:
    listbox_models.insert(END, model)

# Configurações de parâmetros do treinamento
label_config = tk.Label(root, text="Configurações de Treinamento:",
                        bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 14))
label_config.pack(pady=10)

frame_config = tk.Frame(root, bg="#FFFFFF")
frame_config.pack(pady=10)

label_epochs = tk.Label(frame_config, text="Épocas:", bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 12))
label_epochs.grid(row=0, column=0, padx=5, pady=5)
entry_epochs = tk.Entry(frame_config, font=("Helvetica", 12))
entry_epochs.grid(row=0, column=1, padx=5, pady=5)
entry_epochs.insert(tk.END, "100")

label_img_size = tk.Label(frame_config, text="Tamanho da Imagem:", bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 12))
label_img_size.grid(row=1, column=0, padx=5, pady=5)
entry_img_size = tk.Entry(frame_config, font=("Helvetica", 12))
entry_img_size.grid(row=1, column=1, padx=5, pady=5)
entry_img_size.insert(tk.END, "704")

label_batch_size = tk.Label(frame_config, text="Tamanho do Batch:", bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 12))
label_batch_size.grid(row=2, column=0, padx=5, pady=5)
entry_batch_size = tk.Entry(frame_config, font=("Helvetica", 12))
entry_batch_size.grid(row=2, column=1, padx=5, pady=5)
entry_batch_size.insert(tk.END, "16")

label_model_type = tk.Label(frame_config, text="Tipo de Modelo:", bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 12))
label_model_type.grid(row=4, column=0, padx=5, pady=5)
model_type_var = tk.StringVar()
model_type_menu = tk.OptionMenu(frame_config, model_type_var, 'yolov8', 'yolov8-seg', 'yolov8-pose', 'yolov8-obb', 'yolov8-cls')
model_type_menu.grid(row=4, column=1, padx=5, pady=5)
model_type_var.set('yolov8')

label_model_size = tk.Label(frame_config, text="Tamanho do Modelo:", bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 12))
label_model_size.grid(row=5, column=0, padx=5, pady=5)
model_size_var = tk.StringVar()
model_size_menu = tk.OptionMenu(frame_config, model_size_var, 'yolov8n', 'yolov8s', 'yolov8m', 'yolov8l', 'yolov8x')
model_size_menu.grid(row=5, column=1, padx=5, pady=5)
model_size_var.set('yolov8x')

btn_train = tk.Button(
    root,
    text="Iniciar Treinamento",
    command=start_training,
    bg="#2874A6",
    fg="white",
    font=("Helvetica", 14, "bold"),
    height=2,
    width=20
)
btn_train.pack(pady=20)

progress_bar = ttk.Progressbar(root, orient="horizontal", length=400, mode="determinate")
progress_bar.pack(pady=10)

label_log = tk.Label(root, text="Log de Treinamento:",
                     bg="#FFFFFF", fg="#1B4F72", font=("Helvetica", 14))
label_log.pack(pady=5)

log_text = tk.Text(root, wrap="word", height=15, width=80,
                   font=("Helvetica", 12), bg="#ecf0f1")
log_text.pack(pady=10)

root.mainloop()
