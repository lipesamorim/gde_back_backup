import os
import shutil
import random
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk


class DatasetCreatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YOLO Dataset Creator")
        self.root.geometry("720x450")
        self.root.configure(bg="white")  # Fundo branco

        # Variáveis para armazenar os inputs
        self.pasta_origem = tk.StringVar()
        self.nome_pasta = tk.StringVar()
        self.nc = tk.IntVar()
        self.names = tk.StringVar()

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding=20, style="White.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Logo
        try:
            image = Image.open("gde.png")
            image = image.resize((120, 50), Image.LANCZOS)
            self.logo = ImageTk.PhotoImage(image)
            logo_label = tk.Label(main_frame, image=self.logo, bg="white")
            logo_label.grid(row=0, column=0, columnspan=3, pady=(0, 15))
        except Exception as e:
            print("Erro ao carregar logo:", e)

        # Estilo
        style = ttk.Style()
        style.configure("White.TFrame", background="white")
        style.configure("White.TLabel", background="white", font=("Arial", 10))
        style.configure("Blue.TButton", background="#007BFF", foreground="white", font=("Arial", 10, "bold"), padding=5)

        # Seção de seleção da pasta de origem
        ttk.Label(main_frame, text="Pasta com Arquivos YOLO:", style="White.TLabel").grid(row=1, column=0, sticky=tk.W)
        ttk.Entry(main_frame, textvariable=self.pasta_origem, width=40).grid(row=1, column=1)
        ttk.Button(main_frame, text="Selecionar", command=self.selecionar_pasta, style="Blue.TButton").grid(row=1, column=2)

        # Seção de nome da pasta de destino
        ttk.Label(main_frame, text="Nome da Pasta Destino:", style="White.TLabel").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.nome_pasta, width=40).grid(row=2, column=1)

        # Seção de número de classes
        ttk.Label(main_frame, text="Número de Classes (nc):", style="White.TLabel").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.nc, width=10).grid(row=3, column=1, sticky=tk.W)

        # Seção de nomes das classes
        ttk.Label(main_frame, text="Nomes das Classes (separados por vírgula):", style="White.TLabel").grid(row=4, column=0, sticky=tk.W)
        ttk.Entry(main_frame, textvariable=self.names, width=40).grid(row=4, column=1)

        # Botão de processamento
        ttk.Button(main_frame, text="Criar Dataset", command=self.processar, style="Blue.TButton").grid(row=5, column=1, pady=20)

        # Configurar grid
        for child in main_frame.winfo_children():
            child.grid_configure(padx=5, pady=5)

    def selecionar_pasta(self):
        pasta = filedialog.askdirectory(title='Selecione a pasta com os arquivos YOLO')
        if pasta:
            self.pasta_origem.set(pasta)

    def processar(self):
        messagebox.showinfo("Sucesso", "Processo finalizado!")  # Apenas para teste


if __name__ == "__main__":
    root = tk.Tk()
    app = DatasetCreatorApp(root)
    root.mainloop()
