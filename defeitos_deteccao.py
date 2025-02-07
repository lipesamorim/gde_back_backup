import os
import subprocess
import logging
import time
import threading
import cv2
from ultralytics import YOLO  # <-- Importação do YOLOv8

import tkinter as tk  # <-- Usado para exibir a janelinha de pausa

# =========================================================================
# Constantes
# =========================================================================
IP_OCULOS = "10.42.0.217"
VIDEO_DEVICE = "/dev/video2"
SCRCPY_SERVER_PATH = "scrcpy-server"
YOLO_MODEL_PATH = "/home/amorim/PycharmProjects/gde_back/modelostreinados/VW216-LD.pt"

# =========================================================================
# Classe principal: RealWearConnector
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
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        devices_output = result.stdout.strip().splitlines()
        for line in devices_output:
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
        ret = subprocess.run(["nmap", "-p", "37000-44000", IP_OCULOS],
                             capture_output=True, text=True)
        outputs = ret.stdout.strip().split("\n")
        for line in outputs:
            if "/tcp" in line and "open" in line:
                port = line.split("/")[0].strip()
                if port.isdigit():
                    self._try_connect(port)

    def _configure_v4l2loopback(self):
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
        if not os.path.isfile(SCRCPY_SERVER_PATH):
            print(f"Aviso: Arquivo {SCRCPY_SERVER_PATH} não encontrado.")
            print("Dependendo da sua versão do scrcpy, pode não ser necessário.")
            # exit(1)

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
    Quando o botão é clicado, a janela fecha e a função retorna,
    permitindo que o loop no main continue.
    """
    root = tk.Tk()
    root.title("Pausa - Classe Incorreta Detectada")

    # Centraliza minimamente a janela (opcional)
    # Pode-se personalizar melhor posicionamento e tamanho
    w = 300
    h = 150
    ws = root.winfo_screenwidth()
    hs = root.winfo_screenheight()
    x = (ws//2) - (w//2)
    y = (hs//2) - (h//2)
    root.geometry(f"{w}x{h}+{x}+{y}")

    label = tk.Label(root, text="Foi detectada uma classe incorreta!\nClique em 'Continuar' para retomar.")
    label.pack(pady=10)

    def on_continue():
        root.destroy()

    button_continuar = tk.Button(root, text="Continuar", command=on_continue)
    button_continuar.pack(pady=10)

    root.mainloop()

# =========================================================================
# Exemplo de uso: incorporando YOLOv8 com “pausa”
# =========================================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Solicita ao usuário o nome da classe que ele deseja monitorar
    classe_desejada = input("Digite o NOME DA CLASSE que deve ser considerada 'correta': ").strip()

    # Garante que a pasta logsdefeitos exista
    os.makedirs("logsdefeitos", exist_ok=True)

    # Carrega o modelo YOLOv8 uma única vez
    model = YOLO(YOLO_MODEL_PATH)

    connector = RealWearConnector()

    # Inicia uma thread para conectar ao RealWear e configurar a câmera virtual
    def connect_loop():
        connector.connect_oculos()

    t = threading.Thread(target=connect_loop, daemon=True)
    t.start()

    print("Aguardando conexão do dispositivo...")

    while True:
        # Espera até que a conexão esteja estabelecida
        if connector.device_connected_event.is_set() and connector.cap:
            ret, frame = connector.cap.read()
            if not ret:
                print("Falha ao ler frame. Pode ter havido desconexão.")
                time.sleep(1)
                continue

            # 1) Corrige a imagem que vem “de cabeça para baixo”, rotacionando 180 graus
            frame = cv2.rotate(frame, cv2.ROTATE_180)

            # 2) Faz inferência YOLOv8
            results = model.predict(frame, conf=0.75)
            annotated_frame = results[0].plot()  # desenha as boxes e labels

            # 3) Verifica se há classes diferentes da desejada
            if len(results) > 0 and len(results[0].boxes) > 0:
                detected_classes = [model.model.names[int(cls_idx)] for cls_idx in results[0].boxes.cls]
                for c in detected_classes:
                    if c != classe_desejada:
                        # =========== NOVA LÓGICA: EXIBIR A CÂMERA POR MAIS 3 SEGUNDOS ===========
                        start_time = time.time()  # Marca o tempo inicial
                        while time.time() - start_time < 2:  # Mantém capturando por 2 segundos
                            ret, frame = connector.cap.read()
                            if not ret:
                                print("Erro ao capturar frame durante o delay.")
                                break
                            frame = cv2.rotate(frame, cv2.ROTATE_180)
                            cv2.imshow("RealWear + YOLOv8", frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break

                        # =========== SALVA O FRAME ATUALIZADO COM AS ANOTAÇÕES ===========
                        filename = f"logsdefeitos/{time.strftime('%Y%m%d-%H%M%S')}_{c}.jpg"
                        cv2.imwrite(filename, annotated_frame)  # Salva o frame anotado
                        print(f"[ALERTA] Classe diferente detectada: {c}. Frame salvo em {filename}")

                        # =========== PAUSA O PROCESSAMENTO ===========
                        print("Pausando detecção para que o usuário possa decidir continuar...")
                        mostrar_janela_continuar()
                        print("Detecção retomada após clique no botão.\n")

            # 4) Exibe a imagem anotada
            cv2.imshow("RealWear + YOLOv8", annotated_frame)

            # Tecla 'q' para sair
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            else:
                time.sleep(1)

    # Finalização
    if connector.cap:
        connector.cap.release()
    cv2.destroyAllWindows()
