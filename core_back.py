import os
import json
import time
import logging
import threading
from datetime import datetime
from typing import List, Dict, Optional
import subprocess
import sys
import numpy as np

from pika.exceptions import AMQPConnectionError
import pika
import cv2
from ultralytics import YOLO

# Configurações do RabbitMQ a partir das variáveis de ambiente
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')  # Default para 'localhost' se não definido
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')     # Default para 'admin'
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'admin')     # Default para 'admin'

# Nomes das filas
QUEUE_SEND = 'fila_envio'
QUEUE_RECEIVE = 'fila_recebimento'

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# Caminho base do modelo YOLO a partir das variáveis de ambiente
YOLO_MODEL_BASE_PATH = os.getenv('YOLO_MODEL_BASE_PATH', f'{BASE_PATH}/modelostreinados/')

IP_OCULOS = "10.42.0.217"

FPS = 15
PROCESSING_LIMIT_SECONDS = 5
PROCESSING_LIMIT_FRAMES = FPS * PROCESSING_LIMIT_SECONDS

# Configuração de logging
def configurar_logging():
    """
    Configura o logging para armazenar logs em uma pasta com a data atual.
    """
    now = datetime.now()
    data_atual = now.strftime('%Y-%m-%d')

    # Definir o diretório de logs baseado na data
    diretorio_logs = os.path.join('logs', data_atual)
    os.makedirs(diretorio_logs, exist_ok=True)

    # Definir o caminho do arquivo de log com a data no nome
    log_file = os.path.join(diretorio_logs, f'rabbitmq_logs_{data_atual}.log')

    # Configurar o logging
    logging.basicConfig(
        filename=log_file,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.ERROR
    )

    # Adicionar handler para console (opcional)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

class OpenCVWarningMonitor:
    """
    Monitor de mensagens de warning do OpenCV para reagir a eventos específicos.
    """
    def __init__(self, processor):
        self.processor = processor
        self.original_stderr = sys.stderr
        self.pipe_r, self.pipe_w = os.pipe()
        self.pipe_reader = os.fdopen(self.pipe_r)
        sys.stderr = os.fdopen(self.pipe_w, 'w')

        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.monitor)
        self.thread.daemon = True
        self.thread.start()

    def monitor(self):
        while not self.stop_event.is_set():
            line = self.pipe_reader.readline()
            if not line:
                break
            if "tryIoctl VIDEOIO(V4L2:/dev/video2): select() timeout" in line:
                print("Aviso detectado: Reconectando dispositivo.")
                self.processor.handle_disconnection()
            if "open VIDEOIO(V4L2:/dev/video2): can't open camera by index" in line:
                print("Aviso detectado: Reconectando dispositivo.")
                self.processor.handle_disconnection()

    def stop(self):
        self.stop_event.set()
        sys.stderr = self.original_stderr
        self.pipe_reader.close()

class YOLOProcessor:
    """
    Classe responsável por processar imagens usando o modelo YOLO e interagir com o RabbitMQ.
    """

    def __init__(self):
        # Variáveis compartilhadas
        # Inicializa o dicionário e o detector ArUco
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
        self.aruco_parameters = cv2.aruco.DetectorParameters()
        self.aruco_parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self.aruco_parameters.adaptiveThreshWinSizeMin = 3
        self.aruco_parameters.adaptiveThreshWinSizeMax = 23
        self.aruco_parameters.adaptiveThreshWinSizeStep = 10
        self.aruco_parameters.adaptiveThreshConstant = 9
        self.aruco_parameters.minMarkerPerimeterRate = 0.03
        self.aruco_parameters.maxMarkerPerimeterRate = 4.0
        self.aruco_parameters.minCornerDistanceRate = 0.05
        self.aruco_parameters.minDistanceToBorder = 3
        self.aruco_parameters.minMarkerDistanceRate = 0.05
        self.aruco_parameters.polygonalApproxAccuracyRate = 0.03
        self.aruco_parameters.errorCorrectionRate = 0.62
        self.aruco_detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_parameters)

        self.cap = None
        self.expected_object: Optional[str] = None
        self.expected_quantity: Optional[int] = None
        self.expected_filename: Optional[str] = None
        self.sent_flag: bool = False
        self.model: Optional[YOLO] = None
        self.model_lock = threading.Lock()
        self.expected_object_lock = threading.Lock()
        self.expected_filename_lock = threading.Lock()
        self.frame_count: int = 0

        # Flag para indicar se um modelo foi carregado
        self.model_loaded: bool = False

        # Eventos para sincronização
        self.device_connected_event = threading.Event()
        self.new_message_event = threading.Event()

        # Configurar logging
        configurar_logging()

        # Iniciar monitoramento de warnings do OpenCV
        self.opencv_warning_monitor = OpenCVWarningMonitor(self)

    def inicializar_camera(self) -> cv2.VideoCapture:
        """
        Inicializa a captura de vídeo em /dev/video2.
        """
        cap = cv2.VideoCapture("/dev/video2")
        if not cap.isOpened():
            logging.error("Não foi possível acessar a câmera em /dev/video2.")
            raise IOError("Falha ao abrir a câmera.")
        return cap

    def log_message(self, ip: str, queue: str, message: Dict, status: str) -> None:
        try:
            message_json = json.dumps(message)
        except TypeError:
            message_json = str(message)

        log_entry = f"{ip} - {queue} - {message_json} - {status}"
        logging.info(log_entry)
        print(f"Log registrado: {log_entry}")

    def enviar_mensagem(self, ip: str, queue: str, message: Dict) -> None:
        """
        Envia uma mensagem para a fila especificada.
        """
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            parameters = pika.ConnectionParameters(host=ip, credentials=credentials, heartbeat=600)

            with pika.BlockingConnection(parameters) as connection:
                channel = connection.channel()
                channel.queue_declare(queue=queue, durable=True)
                channel.basic_publish(
                    exchange='',
                    routing_key=queue,
                    body=json.dumps(message),
                    properties=pika.BasicProperties(delivery_mode=2,)
                )

            self.log_message(ip, queue, message, "ENVIADA")
        except AMQPConnectionError as e:
            logging.error(f"Erro de conexão com o RabbitMQ: {e}")
        except Exception as e:
            logging.exception("Erro ao enviar mensagem")

    def carregar_modelo(self, model_name: str) -> None:
        """
        Carrega o modelo YOLO especificado.
        """
        with self.model_lock:
            try:
                model_path = os.path.join(YOLO_MODEL_BASE_PATH, f'{model_name}.pt')
                print(f"Carregando modelo YOLO de: {model_path}")

                if not os.path.isfile(model_path):
                    logging.error(f"Arquivo do modelo não encontrado: {model_path}")
                    print(f"Erro: Arquivo do modelo não encontrado: {model_path}")
                    self.model_loaded = False
                    return

                self.model = YOLO(model_path).to('cuda')
                self.model_loaded = True
                print("Modelo YOLO carregado com sucesso.")

                self.log_message(RABBITMQ_HOST, 'YOLO', {'model': model_name}, "MODELO_CARREGADO")
            except Exception as e:
                logging.exception("Erro ao carregar modelo")
                self.model_loaded = False

    def receber_mensagens(self) -> None:
        """
        Recebe mensagens da fila de recebimento e atualiza o objeto esperado e o modelo.
        """
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials, heartbeat=600)

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_RECEIVE, durable=True)
            channel.basic_qos(prefetch_count=1)

            print(' [*] Aguardando mensagens na fila_recebimento. Para sair, pressione CTRL+C')

            def callback(ch, method, properties, body):
                try:
                    print(body)
                    mensagem = json.loads(body.decode())
                    item_id = mensagem.get('itemId').lower()
                    quantity = mensagem.get('quantity')
                    model_name = mensagem.get('model')  # Campo opcional
                    filename = mensagem.get('fileName')  # Campo opcional

                    if isinstance(item_id, str) and isinstance(quantity, int):
                        print(f" [x] Recebido itemId: {item_id}, quantity: {quantity}")

                        with self.expected_object_lock:
                            self.expected_object = item_id
                            self.expected_quantity = quantity
                            self.expected_filename = filename
                            self.sent_flag = False
                        self.log_message(RABBITMQ_HOST, QUEUE_RECEIVE, mensagem, "RECEBIDA")

                        if model_name:
                            self.carregar_modelo(model_name)
                            if self.model_loaded:
                                self.new_message_event.set()
                        else:
                            if not self.model_loaded:
                                logging.error("Primeira mensagem sem especificação de modelo. Modelo é obrigatório.")
                                print("Erro: Primeira mensagem sem especificação de modelo. Modelo é obrigatório.")
                                ch.basic_ack(delivery_tag=method.delivery_tag)
                                return
                            else:
                                logging.info("Mensagem sem modelo. Usando modelo anterior.")
                                self.new_message_event.set()

                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    else:
                        logging.error("Dados inválidos recebidos na mensagem.")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                except json.JSONDecodeError:
                    logging.error("Mensagem recebida não é um JSON válido.")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logging.exception("Erro ao processar mensagem recebida")
                    # ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            channel.basic_consume(queue=QUEUE_RECEIVE, on_message_callback=callback, auto_ack=False)
            channel.start_consuming()

        except AMQPConnectionError as e:
            logging.error(f"Erro de conexão com o RabbitMQ: {e}")
        except Exception as e:
            logging.exception("Erro ao receber mensagens")

    def processar_imagem(self) -> None:
        """
        Captura vídeo, detecta objetos usando YOLO e envia mensagens quando a contagem esperada é alcançada.
        """
        try:
            default_image = np.zeros((480, 640, 3), dtype=np.uint8)

            while True:
                # Verifica se a câmera está conectada
                if self.device_connected_event.is_set():
                    if self.cap is None:
                        try:
                            self.cap = self.inicializar_camera()
                        except IOError:
                            logging.error("Não foi possível inicializar a câmera.")
                            self.device_connected_event.clear()
                            continue

                    ret, frame = self.cap.read()
                    if not ret:
                        logging.error("Falha ao capturar o quadro. Usando imagem padrão.")
                        frame = default_image.copy()
                    else:
                        # Rotaciona 180 graus, caso seja necessário
                        frame = cv2.rotate(frame, cv2.ROTATE_180)

                        with self.model_lock:
                            current_model = self.model

                        # Só processa se o modelo estiver carregado
                        if current_model is not None:
                            results = current_model.predict(source=frame, conf=0.70, verbose=False, device='cuda')
                            detections = self.processar_resultados(results, current_model)

                            with self.expected_object_lock:
                                current_expected_object = self.expected_object
                                current_expected_quantity = self.expected_quantity
                                current_expected_filename = self.expected_filename
                                current_sent_flag = self.sent_flag

                            # Desenha no frame
                            if current_expected_object:
                                deteccoes_esperadas = [d for d in detections if d['label'] == current_expected_object]
                            else:
                                deteccoes_esperadas = []

                            for d in deteccoes_esperadas:
                                label = d['label']
                                confidence = d['confidence']
                                x1, y1, x2, y2 = map(int, d['bbox'])
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                                cv2.putText(frame, f'{label} {confidence:.2f}',
                                            (x1, y1 - 10),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

                            cv2.imshow('GDE EMBALAGEM', frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break

                            # Verifica contagem
                            if current_expected_object and current_expected_quantity and not current_sent_flag:
                                detected_count = len(deteccoes_esperadas)
                                print(f"Objeto esperado (itemId: {current_expected_object}) detectado {detected_count} vezes.")

                                if detected_count == current_expected_quantity:
                                    mensagem = {
                                        'itemId': current_expected_object.upper(),
                                        'count': detected_count
                                    }

                                    # Se tiver 'blister' no nome, tenta ler o ArUco
                                    if 'blister' in current_expected_object.lower():
                                        start_time = time.time()
                                        id_marker = None
                                        while time.time() - start_time < 5:
                                            ret2, frame2 = self.cap.read()
                                            if not ret2:
                                                logging.error("Falha ao capturar quadro ao procurar ArUco.")
                                                continue

                                            frame2 = cv2.rotate(frame2, cv2.ROTATE_180)

                                            corners, ids, rejected = self.aruco_detector.detectMarkers(frame2)
                                            if ids is not None and len(ids) > 0:
                                                cv2.aruco.drawDetectedMarkers(frame2, corners, ids)
                                                id_marker = int(ids[0][0])
                                                print('Código decimal do ArUco:', id_marker)
                                                cv2.imshow('GDE EMBALAGEM', frame2)
                                                cv2.waitKey(1)
                                                time.sleep(1)
                                                break
                                            else:
                                                cv2.imshow('GDE EMBALAGEM', frame2)
                                                if cv2.waitKey(1) & 0xFF == ord('q'):
                                                    break
                                            time.sleep(0.05)

                                        if id_marker is not None:
                                            mensagem['code'] = str(id_marker)
                                        else:
                                            print("Nenhum ArUco detectado após 5 segundos.")

                                    if current_expected_filename is not None:
                                        self.salvar_frame_com_desenho(current_expected_filename, frame,
                                                                      detections, current_expected_object)

                                    self.frame_count = 0
                                    with self.expected_object_lock:
                                        self.sent_flag = True

                                    time.sleep(0.3)
                                    self.enviar_mensagem(RABBITMQ_HOST, QUEUE_SEND, mensagem)
                                    print("Análise completa. Aguardando novo item.")
                                    self.new_message_event.clear()
                                else:
                                    self.frame_count += 1
                                    if self.frame_count >= PROCESSING_LIMIT_FRAMES and not current_sent_flag:
                                        mensagem = {
                                            'itemId': current_expected_object.upper(),
                                            'count': detected_count
                                        }
                                        # Caso especial para 'CAIXA 520X320X170 TRIPLEX'
                                        if current_expected_object.upper() == 'CAIXA 520X320X170 TRIPLEX':
                                            mensagem['count'] = 1

                                        self.frame_count = 0
                                        with self.expected_object_lock:
                                            self.sent_flag = True

                                        time.sleep(0.3)
                                        self.enviar_mensagem(RABBITMQ_HOST, QUEUE_SEND, mensagem)
                                        print("Análise completa. Aguardando novo item.")
                                        self.new_message_event.clear()
                        else:
                            logging.warning("Modelo não carregado. Aguardando...")
                            self.new_message_event.clear()
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break
                else:
                    # Se não estiver conectado, mostra tela padrão
                    frame = default_image.copy()
                    cv2.putText(frame, 'INICIANDO....',
                                (50, default_image.shape[0] // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.imshow('GDE EMBALAGEM', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                    if self.cap:
                        self.cap.release()
                        self.cap = None

                time.sleep(0.01)

            cv2.destroyAllWindows()

        except Exception as e:
            logging.exception("Erro ao processar imagem")

    def processar_resultados(self, results, current_model) -> List[Dict]:
        detections = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                label = current_model.names[cls]
                confidence = float(box.conf[0])
                bbox = box.xyxy[0].tolist()
                detections.append({
                    'label': label,
                    'cls': cls,
                    'confidence': confidence,
                    'bbox': bbox
                })
        return detections

    def salvar_frame_com_desenho(self, current_filename, frame, detections: List[Dict], expected_object_id: str) -> None:
        try:
            frame_com_desenho = frame.copy()
            deteccoes_esperadas = [d for d in detections if d['label'] == expected_object_id]

            for d in deteccoes_esperadas:
                label = d['label']
                confidence = d['confidence']
                bbox = d['bbox']
                x1, y1, x2, y2 = map(int, bbox)
                cv2.rectangle(frame_com_desenho, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame_com_desenho, f'{label} {confidence:.2f}', (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

            self.salvar_frame(current_filename, frame_com_desenho)
        except Exception as e:
            logging.exception("Erro ao desenhar e salvar frame")

    def salvar_frame(self, current_filename, frame) -> None:
        try:
            now = datetime.now()
            data_atual = now.strftime('%Y-%m-%d')
            timestamp = now.strftime('%Y-%m-%d_%H-%M-%S')

            diretorio_logs = os.path.join('logs', data_atual)
            os.makedirs(diretorio_logs, exist_ok=True)

            nome_arquivo = f'{current_filename}.jpg'
            caminho_arquivo = os.path.join(diretorio_logs, nome_arquivo)

            cv2.imwrite(caminho_arquivo, frame)
            print(f"Frame salvo em: {caminho_arquivo}")
            self.log_message(RABBITMQ_HOST, 'SALVAR_FRAME', {'file': nome_arquivo}, "SALVO")
        except Exception as e:
            logging.exception("Erro ao salvar frame")

    def is_device_connected(self, ip_address):
        """
        Verifica via 'adb devices' se o dispositivo está conectado como 'device'.
        """
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        devices_output = result.stdout.strip().splitlines()
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

    def try_connect(self, port):
        """
        Tenta conectar ao óculos em determinada porta.
        """
        subprocess.run(["adb", "connect", f"{IP_OCULOS}:{port}"],
                       stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       timeout=2)

    def connect(self):
        """
        Verifica as portas abertas com nmap e tenta conectar via adb.
        """
        ret = subprocess.run(["nmap", "-p", "37000-44000", IP_OCULOS],
                             capture_output=True, text=True)
        outputs = ret.stdout.strip().split("\n")
        for line in outputs:
            if "/tcp" in line and "open" in line:
                port = line.split("/")[0].strip()
                if port.isdigit():
                    print(f"Tentando conectar na porta {port}")
                    self.try_connect(port)

    def connect_oculos(self):
        """
        Loop para manter a conexão com o dispositivo.
        Se conectado, inicia scrcpy + camera.
        """
        previous_connected_state = False
        while True:
            connected = self.is_device_connected(IP_OCULOS)

            if connected and not previous_connected_state:
                print("Dispositivo conectado!")
                self.start_camera()
                # Aguarda alguns segundos para o scrcpy criar o /dev/video2
                time.sleep(5)

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
                print("Tentando conectar no óculos...")
                self.connect()

            time.sleep(1)

    def restart_adb_server(self):
        """
        Reinicia o servidor adb.
        """
        result = subprocess.run(["adb", "kill-server"], capture_output=True)
        if result.returncode == 0:
            print("Servidor ADB finalizado com sucesso.")
        else:
            print("Aviso: Não foi possível finalizar o servidor ADB. Talvez não estivesse em execução.")

        result = subprocess.run(["adb", "start-server"], capture_output=True)
        if result.returncode == 0:
            print("Servidor ADB iniciado com sucesso.")
        else:
            print("Erro: Não foi possível iniciar o servidor ADB.")
            exit(1)

    def configure_v4l2loopback(self):
        """
        Verifica se v4l2loopback já está carregado.
        Se não estiver, carrega com modprobe.
        """
        try:
            result = subprocess.run(["lsmod"], capture_output=True, text=True)
            if "v4l2loopback" in result.stdout:
                print("v4l2loopback já está carregado.")
            else:
                print("Carregando v4l2loopback...")
                result = subprocess.run(["sudo", "modprobe", "v4l2loopback", "exclusive_caps=1"])
                if result.returncode != 0:
                    print("Erro ao configurar v4l2loopback.")
                else:
                    print("v4l2loopback configurado com sucesso.")
        except Exception as e:
            print(f"Erro ao configurar v4l2loopback: {e}")

    def start_camera(self):
        """
        Inicia o scrcpy direcionando a saída de vídeo para /dev/video2.
        """
        if not os.path.isfile("scrcpy-server"):
            print("Arquivo 'scrcpy-server' não encontrado (dependendo da versão do scrcpy, isso pode ser opcional).")

        self.configure_v4l2loopback()

        # Só para debug, verificar se /dev/video2 existe após v4l2loopback
        result = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True)
        print(result.stdout)

        try:
            env = os.environ.copy()
            env['SCRCPY_SERVER_PATH'] = os.path.abspath("scrcpy-server")

            subprocess.Popen(
                [
                    "scrcpy",
                    "--video-source=camera",
                    "--camera-facing=back",
                    "--camera-size=1920x1080",
                    "--v4l2-sink=/dev/video2",
                    "--no-audio",
                    "--no-window",
                    "-e"
                ],
                env=env
            )
            print("Iniciando captura de vídeo (scrcpy) com parâmetros ajustados...")
        except Exception as e:
            print(f"Erro ao iniciar a câmera via scrcpy: {e}")

    def handle_disconnection(self):
        """
        Trata desconexão do dispositivo.
        """
        self.device_connected_event.clear()
        self.restart_adb_server()
        if self.cap:
            self.cap.release()
            self.cap = None

    def run(self) -> None:
        """
        Inicia as threads de recebimento de mensagens e processamento de imagens.
        """
        thread_receber = threading.Thread(target=self.receber_mensagens, daemon=True)
        thread_processar = threading.Thread(target=self.processar_imagem, daemon=True)
        thread_conectar = threading.Thread(target=self.connect_oculos, daemon=True)

        thread_conectar.start()
        thread_receber.start()
        thread_processar.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Encerrando a aplicação.")
            self.device_connected_event.set()
            self.new_message_event.set()
            self.opencv_warning_monitor.stop()
            thread_processar.join()
            thread_receber.join()
            thread_conectar.join()

if __name__ == '__main__':
    processor = YOLOProcessor()
    processor.run()
