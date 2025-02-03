import os
import tkinter as tk
from tkinter import filedialog
import re


def selecionar_diretorio():
    root = tk.Tk()
    root.withdraw()
    return filedialog.askdirectory(title="Selecione a pasta com as fotos")


def obter_maior_indice(diretorio, prefixo):
    padrao = re.compile(rf"^{re.escape(prefixo)}_(\d+)\..+")
    maior_indice = 0

    for arquivo in os.listdir(diretorio):
        correspondencia = padrao.match(arquivo)
        if correspondencia:
            indice = int(correspondencia.group(1))
            maior_indice = max(maior_indice, indice)

    return maior_indice


def renomear_arquivos(diretorio, prefixo):
    maior_indice = obter_maior_indice(diretorio, prefixo)
    numero = maior_indice + 1

    for arquivo in sorted(os.listdir(diretorio)):
        caminho_antigo = os.path.join(diretorio, arquivo)

        if os.path.isfile(caminho_antigo):
            extensao = os.path.splitext(arquivo)[1]

            # Verifica se o arquivo já está renomeado e evita duplicação
            if re.match(rf"^{re.escape(prefixo)}_\d+\..+", arquivo):
                print(f"Arquivo {arquivo} já está renomeado, ignorando...")
                continue

            novo_nome = f"{prefixo}_{numero}{extensao}"
            caminho_novo = os.path.join(diretorio, novo_nome)

            if not os.path.exists(caminho_novo):
                os.rename(caminho_antigo, caminho_novo)
                print(f"Arquivo renomeado: {arquivo} -> {novo_nome}")
                numero += 1
            else:
                print(f"Arquivo {novo_nome} já existe, pulando renomeação para {arquivo}")


# Seleção do diretório
diretorio = selecionar_diretorio()

if diretorio:
    prefixo = input("Digite o prefixo para os arquivos: ")
    renomear_arquivos(diretorio, prefixo)
else:
    print("Nenhum diretório foi selecionado.")