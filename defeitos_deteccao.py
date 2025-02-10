import os
import subprocess
import logging
import time
import threading
import cv2
from ultralytics import YOLO  # <-- Importação do YOLOv8
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox

# =========================================================================
# Constantes iniciais
# =========================================================================
IP_OCULOS = "10.42.0.217"
VIDEO_DEVICE = "/dev/video2"
SCRCPY_SERVER_PATH = "scrcpy-server"
BASE_MODEL_PATH = "/home/amorim/PycharmProjects/gde_back/modelostreinados"  # pasta base dos modelos


# =========================================================================
# Classe responsável pela conexão e captura de vídeo do RealWear
# =========================================================================
class RealWearConnector:
    def __init__(self):
        self.cap = None
        self.device_connected_event = threading.Event()

    def inicializar_camera(self) -> cv2.VideoCapture:
        cap = cv2.VideoCapture(VIDEO_DEVICE)
        if not cap.isOpened():
            logging.error(f"Não foi possível acessar a câmera em {VIDEO_DEVICE}.")
            raise IOError("Falha ao abrir a câmera.")
        return cap

    def handle_disconnection(self):
        self.device_connected_event.clear()
        self._restart_adb_server()
        if self.cap:
            self.cap.release()
            self.cap = None

    def _restart_adb_server(self):
        result = subprocess.run(["adb", "kill-server"], capture_output=True)
        if result.returncode == 0:
            print("Servidor ADB finalizado com sucesso.")
        else:
            print("Aviso: Não foi possível finalizar o servidor ADB. Ele pode não estar em execução.")

        result = subprocess.run(["adb", "start-server"], capture_output=True)
        if result.returncode == 0:
            print("Servidor ADB iniciado com sucesso.")
        else:
            print("Erro: Não foi possível iniciar o servidor ADB.")
            exit(1)

    def _is_device_connected(self, ip_address: str) -> bool:
        """
        Verifica se há algum dispositivo conectado via ADB.
        Se tiver status 'device', retornamos True.
        Se tiver status 'offline', tentamos desconectar.
        """
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        devices_output = result.stdout.strip().splitlines()

        # O primeiro item costuma ser apenas: "List of devices attached"
        for line in devices_output[1:]:
            if '\t' in line:
                device, status = line.strip().split('\t')
                if status == 'device':
                    return True
                elif status == 'offline':
                    subprocess.run(["adb", "disconnect", ip_address],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        return False

    def _try_connect(self, port: str):
        subprocess.run(
            ["adb", "connect", f"{IP_OCULOS}:{port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )

    def _connect(self):
        """
        Tenta encontrar portas abertas no óculos (via nmap) e se conectar via ADB.
        """
        ret = subprocess.run(["nmap", "-p", "37000-44000", IP_OCULOS],
                             capture_output=True, text=True)
        outputs = ret.stdout.strip().split("\n")
        for line in outputs:
            if "/tcp" in line and "open" in line:
                port = line.split("/")[0].strip()
                if port.isdigit():
                    self._try_connect(port)

    def _configure_v4l2loopback(self):
        """
        Verifica se o módulo v4l2loopback está carregado.
        Caso contrário, carrega com `modprobe`.
        """
        try:
            result = subprocess.run(["lsmod"], capture_output=True, text=True)
            if "v4l2loopback" in result.stdout:
                print("v4l2loopback já está carregado.")
            else:
                result = subprocess.run(["sudo", "/sbin/modprobe", "v4l2loopback", "exclusive_caps=1"])
                if result.returncode != 0:
                    print("Erro ao configurar v4l2loopback.")
                else:
                    print("v4l2loopback configurado com sucesso.")
        except Exception as e:
            print(f"Erro ao configurar v4l2loopback: {e}")

    def _start_camera(self):
        """
        Inicia o scrcpy direcionando a saída de vídeo para um dispositivo virtual (VIDEO_DEVICE).
        """
        if not os.path.isfile(SCRCPY_SERVER_PATH):
            print(f"Aviso: Arquivo {SCRCPY_SERVER_PATH} não encontrado.")
            print("Dependendo da sua versão do scrcpy, pode não ser necessário.")

        self._configure_v4l2loopback()

        result = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        v4l2_device = None
        for i, line in enumerate(lines):
            if "Dummy video device" in line:
                v4l2_device = lines[i + 1].strip()
                break

        if not v4l2_device:
            print("Erro: Dispositivo v4l2 (Dummy video device) não encontrado.")
            return

        try:
            env = os.environ.copy()
            env['SCRCPY_SERVER_PATH'] = os.path.abspath(SCRCPY_SERVER_PATH)

            subprocess.Popen(
                [
                    "scrcpy",
                    "--video-source=camera",
                    "--camera-facing=back",
                    f"--v4l2-sink={VIDEO_DEVICE}",
                    "--no-audio",
                    "--camera-size=1280x720",
                    "--no-window",
                    "-e"
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"Iniciando captura de vídeo (scrcpy -> {VIDEO_DEVICE}).")
            time.sleep(5)
        except Exception as e:
            print(f"Erro ao iniciar a câmera via scrcpy: {e}")

    def connect_oculos(self):
        """
        Loop que monitora se o dispositivo está conectado.
        Se desconectar, tenta reconectar. Se conectar, inicia a captura.
        """
        previous_connected_state = False
        while True:
            connected = self._is_device_connected(IP_OCULOS)
            if connected and not previous_connected_state:
                print("Dispositivo conectado!")
                self._start_camera()
                try:
                    self.cap = self.inicializar_camera()
                    self.device_connected_event.set()
                except IOError:
                    self.device_connected_event.clear()

            elif not connected and previous_connected_state:
                print("Dispositivo desconectado!")
                self.handle_disconnection()

            previous_connected_state = connected

            if not connected:
                self._connect()

            time.sleep(1)


# =========================================================================
# Função auxiliar para exibir a janela de “Pausa” com botão de "Continuar"
# =========================================================================
def mostrar_janela_continuar():
    """
    Abre uma pequena janela Tkinter com um botão "Continuar".
    Quando o botão é clicado, a janela fecha e a função retorna.
    """
    root = tk.Tk()
    root.title("Pausa - Irregularidade Detectada")

    w = 300
    h = 150
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws // 2) - (w // 2)
    y = (hs // 2) - (h // 2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    label = tk.Label(root, bg="white", text="Foi detectada uma irregularidade!\nClique em 'Continuar' para retomar.")
    label.pack(pady=10)

    def on_continue():
        root.destroy()

    button_continuar = tk.Button(root, text="Continuar", command=on_continue, bg="#1D3557", fg="white")
    button_continuar.pack(pady=10)

    root.mainloop()


# =========================================================================
# Classe principal de Aplicação Tkinter
# =========================================================================
class App:
    def __init__(self, master):
        self.master = master
        self.master.title("Detecção YOLOv8 RealWear")

        # Aumentando o tamanho da janela principal
        self.master.geometry("700x500")  # Ajuste conforme necessidade

        self.connector = RealWearConnector()
        self.model = None

        # ========== [ADICIONANDO LOGO e DIMINUINDO TAMANHO] ==========
        # Carrega a imagem
        self.logo_image = tk.PhotoImage(file="gde.png")
        # Reduz o tamanho usando subsample (por exemplo, dividindo largura e altura por 3)
        self.logo_image = self.logo_image.subsample(3, 3)

        self.label_logo = tk.Label(self.master, image=self.logo_image)
        self.label_logo.pack(pady=5)

        # Variável para armazenar o nome da classe desejada
        self.classe_desejada_var = tk.StringVar()

        # Layout simples para inserir a classe
        lbl = tk.Label(master, text="Digite o item a ser inspecionado:")
        lbl.pack(pady=5)

        self.entry_classe = tk.Entry(master, textvariable=self.classe_desejada_var, width=30)
        self.entry_classe.pack(pady=5)

        # Forçar texto em maiúsculo
        self.classe_desejada_var.trace_add("write", self._forcar_maiusculo)

        # Botão para iniciar a detecção (usando tk.Button para poder definir bg/fg)
        self.btn_iniciar = tk.Button(
            master,
            text="Iniciar Detecção",
            command=self.iniciar_deteccao,
            bg="#1D3557",
            fg="white"
        )
        self.btn_iniciar.pack(pady=10)

        # Área de log (opcional)
        self.log_text = tk.Text(master, height=10, width=50)
        self.log_text.pack(pady=5)

        # Para controle de thread
        self.detection_thread = None

    def _forcar_maiusculo(self, *args):
        texto_atual = self.classe_desejada_var.get()
        # Converte para maiúsculo e atualiza a variável
        self.classe_desejada_var.set(texto_atual.upper())

    def log(self, message: str):
        """
        Função auxiliar para exibir mensagens em um Text widget de log.
        """
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        print(message)  # também imprime no console

    def iniciar_deteccao(self):
        """
        Callback ao clicar no botão "Iniciar Detecção".
        - Pega a classe digitada
        - Monta o caminho do modelo
        - Dispara a thread de conexão e detecção
        """
        classe_desejada = self.classe_desejada_var.get().strip()
        if not classe_desejada:
            messagebox.showerror("Erro", "Por favor, digite o nome do item.")
            return

        # Ajusta caminho do modelo e define classe desejada
        yolo_model_path = os.path.join(BASE_MODEL_PATH, f"{classe_desejada}.pt")

        if not os.path.exists(yolo_model_path):
            msg = (
                f"Modelo '{yolo_model_path}' não encontrado.\n"
                f"Verifique se o arquivo existe nessa pasta."
            )
            messagebox.showerror("Erro", msg)
            return

        self.log(f"Iniciando detecção usando o modelo: {yolo_model_path}")
        self.log(f"Item para inspeção: {classe_desejada}")

        # Carrega o modelo YOLO
        try:
            self.model = YOLO(yolo_model_path)
        except Exception as e:
            messagebox.showerror("Erro ao carregar modelo", str(e))
            return

        # Cria pasta para logs de defeitos, se não existir
        os.makedirs("logsdefeitos", exist_ok=True)

        # Inicia a thread de conexão com o RealWear e detecção YOLO
        self.detection_thread = threading.Thread(
            target=self.loop_deteccao,
            args=(classe_desejada,),
            daemon=True
        )
        self.detection_thread.start()

    def loop_deteccao(self, classe_desejada):
        """
        Função que roda em thread separada:
        1. Inicia o loop de conexão do RealWear
        2. Quando conectado, faz a leitura dos frames e aplica YOLO
        3. Exibe e salva detecções incorretas, faz “pausa” via janela Tkinter
        """
        # Inicia uma thread para conectar ao RealWear e configurar a câmera virtual
        def connect_loop():
            self.connector.connect_oculos()

        t_connect = threading.Thread(target=connect_loop, daemon=True)
        t_connect.start()

        self.log("Aguardando conexão do dispositivo...")

        while True:
            # Espera até que a conexão esteja estabelecida
            if self.connector.device_connected_event.is_set() and self.connector.cap:
                ret, frame = self.connector.cap.read()
                if not ret:
                    self.log("Falha ao ler frame. Pode ter havido desconexão.")
                    time.sleep(1)
                    continue

                # Corrige a imagem que vem “de cabeça para baixo”: rotaciona 180 graus
                frame = cv2.rotate(frame, cv2.ROTATE_180)

                # Faz inferência YOLOv8
                results = self.model.predict(frame, conf=0.73)
                annotated_frame = results[0].plot()  # desenha as boxes e labels

                # Verifica se há classes diferentes da desejada
                if len(results) > 0 and len(results[0].boxes) > 0:
                    detected_classes = [
                        self.model.model.names[int(cls_idx)]
                        for cls_idx in results[0].boxes.cls
                    ]
                    for c in detected_classes:
                        if c != classe_desejada:
                            # Captura mais 2 segundos de vídeo antes de pausar
                            start_time = time.time()
                            while time.time() - start_time < 2:
                                ret2, frame2 = self.connector.cap.read()
                                if not ret2:
                                    self.log("Erro ao capturar frame durante o delay.")
                                    break
                                frame2 = cv2.rotate(frame2, cv2.ROTATE_180)
                                cv2.imshow("RealWear + YOLOv8", frame2)
                                if cv2.waitKey(1) & 0xFF == ord('q'):
                                    break

                            # Salva o frame anotado
                            filename = f"logsdefeitos/{time.strftime('%Y%m%d-%H%M%S')}_{c}.jpg"
                            cv2.imwrite(filename, annotated_frame)
                            msg_log = f"[ALERTA] Irregularidade Detectada: {c}. Frame salvo em {filename}"
                            self.log(msg_log)

                            # Pausa a detecção até clicar em "Continuar"
                            self.log("Pausando detecção (janela de alerta)...")
                            mostrar_janela_continuar()
                            self.log("Detecção retomada.\n")

                # Exibe a imagem anotada
                cv2.imshow("RealWear + YOLOv8", annotated_frame)

                # Tecla 'q' para sair
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    self.log("Encerrando detecção por comando do usuário (q).")
                    break
                else:
                    time.sleep(1)

        # Finalização
        if self.connector.cap:
            self.connector.cap.release()
        cv2.destroyAllWindows()
        self.log("Detecção finalizada.")


# =========================================================================
# Função principal
# =========================================================================
def main():
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
