import os
import json
import time
import logging
import threading
import subprocess
import sys
import numpy as np
import cv2
from datetime import datetime
from typing import List, Dict, Optional

from pika.exceptions import AMQPConnectionError
import pika
from ultralytics import YOLO

# =============================================================================
# Variáveis de Ambiente e Constantes
# =============================================================================

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')  # Default para 'localhost' se não definido
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'admin')       # Default para 'admin'
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'admin')       # Default para 'admin'

QUEUE_SEND = 'fila_envio'
QUEUE_RECEIVE = 'fila_recebimento'

BASE_PATH = os.path.dirname(os.path.abspath(__file__))

YOLO_MODEL_BASE_PATH = os.getenv('YOLO_MODEL_BASE_PATH', f'{BASE_PATH}/modelostreinados/')

IP_OCULOS = "192.168.0.80"

FPS = 15
PROCESSING_LIMIT_SECONDS = 5
PROCESSING_LIMIT_FRAMES = FPS * PROCESSING_LIMIT_SECONDS  # quantos frames processar antes de enviar mensagem mesmo não batendo a contagem

# ADICIONE ESTA LINHA: variável de ambiente para o dispositivo de vídeo.
VIDEO_DEVICE = os.getenv('VIDEO_DEVICE', '/dev/video2')

# =============================================================================
# Configuração de Logging
# =============================================================================

def configurar_logging():
    """
    Configura o logging para armazenar logs em uma pasta de acordo com a data atual
    e exibí-los no console.
    """
    now = datetime.now()
    data_atual = now.strftime('%Y-%m-%d')

    # Define o diretório de logs baseado na data
    diretorio_logs = os.path.join('logs', data_atual)
    os.makedirs(diretorio_logs, exist_ok=True)

    # Define o caminho do arquivo de log
    log_file = os.path.join(diretorio_logs, f'rabbitmq_logs_{data_atual}.log')

    # Configura o logging básico (arquivo)
    logging.basicConfig(
        filename=log_file,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.ERROR  # Default para armazenar erros no arquivo
    )

    # Handler para console (opcional, nível INFO)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

# =============================================================================
# Monitor de Warnings do OpenCV
# =============================================================================

class OpenCVWarningMonitor:
    """
    Monitor para capturar mensagens de warning do OpenCV em tempo de execução.
    Se um aviso específico for detectado, chama handle_disconnection no objeto 'processor'.
    """

    def __init__(self, processor):
        self.processor = processor
        self.original_stderr = sys.stderr
        self.pipe_r, self.pipe_w = os.pipe()
        self.pipe_reader = os.fdopen(self.pipe_r)
        sys.stderr = os.fdopen(self.pipe_w, 'w')

        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._monitor)
        self.thread.daemon = True
        self.thread.start()

    def _monitor(self):
        """
        Thread que monitora a saída de erro do OpenCV em busca de avisos específicos.
        """
        # Montamos as strings de warning dinamicamente usando a variável de ambiente
        timeout_warning = f"tryIoctl VIDEOIO(V4L2:{VIDEO_DEVICE}): select() timeout"
        open_warning = f"open VIDEOIO(V4L2:{VIDEO_DEVICE}): can't open camera by index"

        while not self.stop_event.is_set():
            line = self.pipe_reader.readline()
            if not line:
                break
            if timeout_warning in line:
                print("Aviso do OpenCV detectado (timeout): Reconectando dispositivo.")
                self.processor.handle_disconnection()
            if open_warning in line:
                print("Aviso do OpenCV detectado (não é possível abrir câmera): Reconectando dispositivo.")
                self.processor.handle_disconnection()

    def stop(self):
        """
        Encerra o monitoramento de warnings do OpenCV.
        """
        self.stop_event.set()
        sys.stderr = self.original_stderr
        self.pipe_reader.close()

# =============================================================================
# Classe Principal para Processamento YOLO e Integração RabbitMQ
# =============================================================================

class YOLOProcessor:
    """
    Responsável por:
    - Processamento de imagens usando YOLO.
    - Detecção de marcadores ArUco.
    - Interação com RabbitMQ (envio e recebimento de mensagens).
    - Conexão e desconexão de dispositivo (óculos RealWear).
    - Captura de vídeo através de scrcpy -> v4l2loopback.
    """

    def __init__(self):
        """
        Construtor da classe YOLOProcessor.
        - Configura os dicionários e parâmetros de detecção ArUco.
        - Inicializa variáveis de controle de captura, modelo YOLO e sincronização.
        - Inicia o monitor de warnings do OpenCV.
        """
        # Inicialização da detecção ArUco
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
        self.aruco_parameters = cv2.aruco.DetectorParameters()
        self._configurar_parametros_aruco()
        self.aruco_detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_parameters)

        # Variáveis de captura e de estado
        self.cap = None
        self.model = None
        self.model_loaded = False
        self.model_lock = threading.Lock()

        # Variáveis de objeto esperado (itemId) e contagem
        self.expected_object: Optional[str] = None
        self.expected_quantity: Optional[int] = None
        self.expected_filename: Optional[str] = None
        self.sent_flag: bool = False
        self.expected_object_lock = threading.Lock()
        self.expected_filename_lock = threading.Lock()

        # Contador de frames para limitar processamento
        self.frame_count: int = 0

        # Eventos de sincronização
        self.device_connected_event = threading.Event()
        self.new_message_event = threading.Event()

        # Iniciar logging
        configurar_logging()

        # Iniciar monitoramento de warnings do OpenCV
        self.opencv_warning_monitor = OpenCVWarningMonitor(self)

    def _configurar_parametros_aruco(self):
        """
        Ajusta parâmetros de detecção ArUco para melhorar a sensibilidade.
        """
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

    # =========================================================================
    # Métodos de Câmera
    # =========================================================================

    def inicializar_camera(self) -> cv2.VideoCapture:
        """
        Tenta inicializar a captura de vídeo usando a variável de ambiente VIDEO_DEVICE.
        Retorna o objeto de captura se bem-sucedido.
        Lança IOError em caso de falha.
        """
        cap = cv2.VideoCapture(VIDEO_DEVICE)
        if not cap.isOpened():
            logging.error(f"Não foi possível acessar a câmera em {VIDEO_DEVICE}.")
            raise IOError("Falha ao abrir a câmera.")
        return cap

    def handle_disconnection(self):
        """
        Lida com a desconexão do dispositivo.
        - Seta o evento de dispositivo desconectado.
        - Reinicia o servidor ADB.
        - Fecha o objeto de captura se aberto.
        """
        self.device_connected_event.clear()
        self._restart_adb_server()
        if self.cap:
            self.cap.release()
            self.cap = None

    # =========================================================================
    # Métodos Internos de Conexão (ADB/Scrcpy)
    # =========================================================================

    def _restart_adb_server(self):
        """
        Reinicia o servidor ADB para tentar se reconectar ao dispositivo.
        """
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
        Verifica se o dispositivo no IP informado está conectado via ADB.
        Retorna True/False.
        """
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        devices_output = result.stdout.strip().splitlines()
        for line in devices_output:
            if '\t' in line:
                device, status = line.strip().split('\t')
                if status == 'device':
                    return True
                elif status == 'offline':
                    # Desconecta o dispositivo offline do ADB
                    subprocess.run(["adb", "disconnect", ip_address], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return False

    def _try_connect(self, port: str):
        """
        Tenta conectar ao dispositivo (óculos) em determinada porta via ADB connect,
        suprimindo a saída.
        """
        subprocess.run(
            ["adb", "connect", f"{IP_OCULOS}:{port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )

    def _connect(self):
        """
        Verifica quais portas estão abertas usando nmap, para então tentar conectar
        via ADB em cada porta que esteja 'open'.
        """
        ret = subprocess.run(["nmap", "-p", "37000-44000", IP_OCULOS], capture_output=True, text=True)
        outputs = ret.stdout.strip().split("\n")
        for line in outputs:
            if "/tcp" in line and "open" in line:
                port = line.split("/")[0].strip()
                if port.isdigit():
                    self._try_connect(port)

    # def _configure_v4l2loopback(self):
    #     """
    #     Carrega o módulo v4l2loopback se ainda não estiver carregado.
    #     """
    #     try:
    #         result = subprocess.run(["lsmod"], capture_output=True, text=True)
    #         if "v4l2loopback" in result.stdout:
    #             print("v4l2loopback já está carregado.")
    #         else:
    #             result = subprocess.run(["sudo", "modprobe", "v4l2loopback", "exclusive_caps=1"])
    #             if result.returncode != 0:
    #                 print("Erro ao configurar v4l2loopback.")
    #     except Exception as e:
    #         print(f"Erro ao configurar v4l2loopback: {e}")


    def _start_camera(self):
        """
        Inicia a captura de vídeo no dispositivo via scrcpy,
        direcionando a saída para o dispositivo configurado em VIDEO_DEVICE.
        """
        SCRCPY_SERVER_PATH = "scrcpy-server"
        if not os.path.isfile(SCRCPY_SERVER_PATH):
            print(f"Erro: Arquivo {SCRCPY_SERVER_PATH} não encontrado no diretório atual.")
            exit(1)

        self._configure_v4l2loopback()

        result = subprocess.run(["v4l2-ctl", "--list-devices"], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        v4l2_device = None
        for i, line in enumerate(lines):
            if "Dummy video device" in line:
                # Dispositivo está na linha seguinte
                v4l2_device = lines[i + 1].strip()
                break

        if not v4l2_device:
            print("Erro: Dispositivo v4l2 não encontrado.")
            exit(1)

        try:
            # Configura a variável de ambiente SCRCPY_SERVER_PATH
            env = os.environ.copy()
            env['SCRCPY_SERVER_PATH'] = os.path.abspath(SCRCPY_SERVER_PATH)

            # Substituímos "/dev/video2" pela variável VIDEO_DEVICE
            subprocess.Popen(
                [
                    "scrcpy",
                    "--video-source=camera",
                    "--camera-facing=back",
                    f"--v4l2-sink={VIDEO_DEVICE}",
                    "--no-audio",
                    "--camera-size=1280x720",
                    "--no-window",
                    "--lock-video-orientation=180",
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
        Loop que verifica continuamente se o dispositivo está conectado.
        - Se desconectado, tenta reconectar usando nmap e adb connect.
        - Se conectado, inicia a câmera e seta o evento device_connected_event.
        """
        previous_connected_state = False
        while True:
            connected = self._is_device_connected(IP_OCULOS)

            if connected and not previous_connected_state:
                # Dispositivo acabou de conectar
                print("Dispositivo conectado!")
                self._start_camera()
                try:
                    self.cap = self.inicializar_camera()
                    self.device_connected_event.set()
                except IOError:
                    # Se não for possível abrir a câmera, limpamos o evento
                    self.device_connected_event.clear()

            elif not connected and previous_connected_state:
                # Dispositivo acabou de desconectar
                print("Dispositivo desconectado!")
                self.handle_disconnection()

            previous_connected_state = connected

            if not connected:
                # Tentar conectar novamente
                self._connect()

            time.sleep(1)

    # =========================================================================
    # Métodos de Envio e Recebimento de Mensagens (RabbitMQ)
    # =========================================================================

    def _log_message(self, ip: str, queue: str, message: Dict, status: str) -> None:
        """
        Registra mensagens de log (ENVIO ou RECEBIMENTO), com informações de IP, fila e status.
        """
        try:
            message_json = json.dumps(message)
        except TypeError:
            message_json = str(message)

        log_entry = f"{ip} - {queue} - {message_json} - {status}"
        logging.info(log_entry)
        print(f"Log registrado: {log_entry}")

    def enviar_mensagem(self, ip: str, queue: str, message: Dict) -> None:
        """
        Envia uma mensagem para a fila especificada no RabbitMQ.
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
                    properties=pika.BasicProperties(delivery_mode=2)  # Mensagem persistente
                )

            self._log_message(ip, queue, message, "ENVIADA")

        except AMQPConnectionError as e:
            logging.error(f"Erro de conexão com o RabbitMQ: {e}")
        except Exception as e:
            logging.exception("Erro ao enviar mensagem")

    def receber_mensagens(self) -> None:
        """
        Inicia o consumo de mensagens da fila de recebimento (fila_recebimento).
        Atualiza o objeto esperado e carrega (ou mantém) o modelo YOLO conforme as mensagens.
        """
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials, heartbeat=600)

            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_RECEIVE, durable=True)

            # Prefetch para controlar quantas mensagens não confirmadas podem ser enviadas ao consumidor
            channel.basic_qos(prefetch_count=1)

            print(' [*] Aguardando mensagens em fila_recebimento. Pressione CTRL+C para sair.')

            def callback(ch, method, properties, body):
                """
                Função de callback chamada quando chega uma mensagem na fila.
                """
                try:
                    print(body)
                    mensagem = json.loads(body.decode())
                    item_id = mensagem.get('itemId').lower()
                    quantity = mensagem.get('quantity')
                    model_name = mensagem.get('model')     # Pode ou não existir
                    filename = mensagem.get('fileName')    # Pode ou não existir

                    # Valida campos principais
                    if isinstance(item_id, str) and isinstance(quantity, int):
                        print(f" [x] Recebido itemId: {item_id}, quantity: {quantity}")

                        # Atualiza variáveis compartilhadas
                        with self.expected_object_lock:
                            self.expected_object = item_id
                            self.expected_quantity = quantity
                            self.expected_filename = filename
                            self.sent_flag = False  # reset flag de envio

                        self._log_message(RABBITMQ_HOST, QUEUE_RECEIVE, mensagem, "RECEBIDA")

                        # Se houver nome de modelo, carrega
                        if model_name:
                            self.carregar_modelo(model_name)
                            if self.model_loaded:
                                self.new_message_event.set()
                                print("Processamento de imagem liberado!")
                        else:
                            # Se for a primeira mensagem e não houver modelo, é um problema
                            if not self.model_loaded:
                                logging.error("Primeira mensagem recebida sem modelo. Modelo é obrigatório.")
                                print("Erro: Primeira mensagem sem modelo especificado. Modelo é obrigatório.")
                                # Mesmo assim, damos ack para não reentregar infinitamente
                                ch.basic_ack(delivery_tag=method.delivery_tag)
                                return
                            else:
                                # Continua com o modelo anterior
                                logging.info("Mensagem recebida sem 'model'. Usando modelo anterior.")
                                print("Mensagem recebida sem especificar modelo: usando modelo anterior.")
                                self.new_message_event.set()
                                print("Processamento de imagem liberado!")

                        # Confirma recebimento da mensagem
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    else:
                        logging.error("Dados inválidos na mensagem (itemId ou quantity).")
                        ch.basic_ack(delivery_tag=method.delivery_tag)

                except json.JSONDecodeError:
                    logging.error("Mensagem recebida não é um JSON válido.")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logging.exception("Erro ao processar mensagem recebida")
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue=QUEUE_RECEIVE, on_message_callback=callback, auto_ack=False)
            channel.start_consuming()

        except AMQPConnectionError as e:
            logging.error(f"Erro de conexão com o RabbitMQ: {e}")
        except Exception as e:
            logging.exception("Erro ao receber mensagens")

    # =========================================================================
    # Métodos de Modelo YOLO
    # =========================================================================

    def carregar_modelo(self, model_name: str) -> None:
        """
        Carrega o modelo YOLO a partir de seu nome (model_name), buscando o arquivo .pt.
        Em caso de falha, model_loaded fica False.
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

                self.model = YOLO(model_path)
                self.model_loaded = True
                print("Modelo YOLO carregado com sucesso.")

                self._log_message(RABBITMQ_HOST, 'YOLO', {'model': model_name}, "MODELO_CARREGADO")
            except Exception as e:
                logging.exception("Erro ao carregar modelo YOLO")
                self.model_loaded = False

    def _processar_resultados_yolo(self, results) -> List[Dict]:
        """
        Processa os resultados do modelo YOLO (boxes, scores, classes) e retorna
        uma lista de dicionários com label, confiança e bounding box.
        """
        detections = []
        with self.model_lock:
            current_model = self.model

        if not current_model:
            return detections

        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls_idx = int(box.cls[0])
                label = current_model.names[cls_idx]
                confidence = float(box.conf[0])
                bbox = box.xyxy[0].tolist()

                detections.append({
                    'label': label,
                    'cls': cls_idx,
                    'confidence': confidence,
                    'bbox': bbox
                })
        return detections

    # =========================================================================
    # Loop Principal de Processamento
    # =========================================================================

    def processar_imagem(self) -> None:
        """
        Thread principal que:
        - Aguarda a câmera estar conectada (device_connected_event).
        - Captura frames, faz a rotação de 180°, realiza inferência YOLO.
        - Se encontra o objeto esperado na contagem correta, envia mensagem para a fila de envio.
        - Tempo limite de frames para enviar mensagem mesmo sem bater a contagem exata.
        - Identifica Marcadores ArUco caso o objeto seja 'blister' (aguarda até 5s).
        """
        try:
            # Imagem padrão (fallback) se a câmera estiver desconectada
            default_image = np.zeros((480, 640, 3), dtype=np.uint8)

            while True:
                # Verifica conexão do dispositivo
                if self.device_connected_event.is_set():
                    if self.cap is None:
                        try:
                            self.cap = self.inicializar_camera()
                        except IOError:
                            logging.error("Não foi possível inicializar a câmera após reconexão.")
                            self.device_connected_event.clear()
                            continue

                    # Captura frame
                    ret, frame = self.cap.read()
                    if not ret:
                        logging.error("Falha ao capturar quadro. Usando imagem padrão.")
                        frame = default_image.copy()
                    else:
                        # Rotaciona o frame em 180° para ficar correto
                        frame = cv2.rotate(frame, cv2.ROTATE_180)

                    # Se o modelo estiver carregado, faz a inferência
                    if self.model_loaded:
                        results = self.model.predict(source=frame, save=False, conf=0.70, verbose=False)
                        detections = self._processar_resultados_yolo(results)

                        # Bloqueia para ler estado do objeto esperado
                        with self.expected_object_lock:
                            current_expected_object = self.expected_object
                            current_expected_quantity = self.expected_quantity
                            current_expected_filename = self.expected_filename
                            current_sent_flag = self.sent_flag

                        # Se temos algum objeto esperado, filtra detecções
                        if current_expected_object:
                            deteccoes_esperadas = [
                                d for d in detections if d['label'] == current_expected_object
                            ]
                            # Desenho das detecções somente do objeto esperado
                            self._desenhar_deteccoes(frame, deteccoes_esperadas)

                            # Exibir frame para visualização
                            cv2.imshow('GDE EMBALAGEM', frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break

                            if current_expected_quantity is not None and not current_sent_flag:
                                detected_count = len(deteccoes_esperadas)
                                print(f"Objeto esperado '{current_expected_object}' detectado {detected_count} vezes.")

                                # Se a contagem bater exata
                                if detected_count == current_expected_quantity:
                                    self._enviar_contagem_e_marcador(frame, current_expected_object, detected_count)
                                else:
                                    # Se não bater, contamos frames até o limite
                                    self.frame_count += 1
                                    if self.frame_count >= PROCESSING_LIMIT_FRAMES:
                                        self._enviar_contagem_parcial(frame, current_expected_object, detected_count)
                        else:
                            # Se não temos objeto definido, apenas exibe
                            cv2.imshow('GDE EMBALAGEM', frame)
                            if cv2.waitKey(1) & 0xFF == ord('q'):
                                break
                    else:
                        # Modelo não carregado: apenas exibe mensagem e continua
                        logging.warning("Modelo YOLO não carregado. Aguardando...")
                        cv2.imshow('GDE EMBALAGEM', frame)
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            break
                        self.new_message_event.clear()
                        time.sleep(0.01)

                else:
                    # Dispositivo não conectado: mostra imagem padrão
                    frame = default_image.copy()
                    cv2.putText(frame, 'AGUARDANDO DISPOSITIVO...', (50, default_image.shape[0] // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    cv2.imshow('GDE EMBALAGEM', frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break

                    # Libera captura se aberta
                    if self.cap:
                        self.cap.release()
                        self.cap = None

                    time.sleep(0.01)

            cv2.destroyAllWindows()

        except Exception as e:
            logging.exception("Erro no loop principal de processamento de imagem")

    # =========================================================================
    # Métodos Auxiliares para Envio de Mensagem e Salvamento de Frame
    # =========================================================================

    def _enviar_contagem_e_marcador(self, frame, objeto_esperado: str, contagem: int):
        """
        Quando a contagem de objetos esperados bate exata, envia mensagem com o itemId e count.
        Se for 'blister', tenta ler marcador ArUco por até 5 segundos.
        Também salva frame, se houver filename especificado.
        """
        mensagem = {
            'itemId': objeto_esperado.upper(),
            'count': contagem
        }
        # Verifica se 'blister' está no nome do objeto esperado
        if 'blister' in objeto_esperado.lower():
            start_time = time.time()
            id_marker = None
            while time.time() - start_time < 5:
                ret, frame_temp = self.cap.read()
                if not ret:
                    logging.error("Falha ao capturar quadro durante detecção ArUco.")
                    continue

                frame_temp = cv2.rotate(frame_temp, cv2.ROTATE_180)
                corners, ids, _ = self.aruco_detector.detectMarkers(frame_temp)
                if ids is not None and len(ids) > 0:
                    id_marker = int(ids[0][0])
                    print('Código do marcador ArUco:', id_marker)
                    # Desenha e exibe por 1s
                    cv2.aruco.drawDetectedMarkers(frame_temp, corners, ids)
                    cv2.imshow('GDE EMBALAGEM', frame_temp)
                    cv2.waitKey(1)
                    time.sleep(1)
                    break
                else:
                    cv2.imshow('GDE EMBALAGEM', frame_temp)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                time.sleep(0.05)

            if id_marker is not None:
                mensagem['code'] = str(id_marker)
            else:
                print("Nenhum marcador ArUco detectado após 5 segundos para 'blister'.")

        # Salva frame se houver filename
        with self.expected_filename_lock:
            if self.expected_filename is not None:
                self._salvar_frame_com_desenho(self.expected_filename, frame, objeto_esperado)

        self.frame_count = 0
        with self.expected_object_lock:
            self.sent_flag = True

        # Envio para RabbitMQ
        time.sleep(0.3)
        self.enviar_mensagem(RABBITMQ_HOST, QUEUE_SEND, mensagem)
        print("Análise completa (contagem exata). Aguardando novo item para análise.")
        self.new_message_event.clear()

    def _enviar_contagem_parcial(self, frame, objeto_esperado: str, contagem: int):
        """
        Se atingimos o limite de frames sem bater a contagem exata, enviamos a contagem parcial mesmo assim.
        """
        mensagem = {
            'itemId': objeto_esperado.upper(),
            'count': contagem
        }
        # Exceção especial para 'CAIXA 520X320X170 TRIPLEX' (força count=1)
        if objeto_esperado.upper() == 'CAIXA 520X320X170 TRIPLEX':
            mensagem['count'] = 1

        with self.expected_filename_lock:
            if self.expected_filename is not None:
                self._salvar_frame_com_desenho(self.expected_filename, frame, objeto_esperado)

        self.frame_count = 0
        with self.expected_object_lock:
            self.sent_flag = True

        time.sleep(0.3)
        self.enviar_mensagem(RABBITMQ_HOST, QUEUE_SEND, mensagem)
        print("Análise completa (contagem parcial). Aguardando novo item para análise.")
        self.new_message_event.clear()

    def _desenhar_deteccoes(self, frame, deteccoes: List[Dict]):
        """
        Desenha bounding box e label no frame para cada detecção informada.
        """
        for d in deteccoes:
            x1, y1, x2, y2 = map(int, d['bbox'])
            label = d['label']
            confidence = d['confidence']
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(
                frame,
                f'{label} {confidence:.2f}',
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (0, 255, 0),
                2
            )

    def _salvar_frame_com_desenho(self, filename: str, frame, objeto_esperado: str):
        """
        Filtra as detecções do objeto esperado para desenhar e então salva o frame com bounding boxes.
        """
        try:
            # Faz novamente a inferência no frame, caso ele esteja "cru"
            results = self.model.predict(source=frame, save=False, conf=0.70, verbose=False)
            detections = self._processar_resultados_yolo(results)
            deteccoes_esperadas = [d for d in detections if d['label'] == objeto_esperado]

            frame_desenhado = frame.copy()
            self._desenhar_deteccoes(frame_desenhado, deteccoes_esperadas)
            self._salvar_frame(filename, frame_desenhado)
        except Exception as e:
            logging.exception("Erro ao desenhar e salvar frame")

    def _salvar_frame(self, filename: str, frame):
        """
        Salva a imagem no diretório de logs do dia com o nome especificado.
        """
        now = datetime.now()
        data_atual = now.strftime('%Y-%m-%d')

        diretorio_logs = os.path.join('logs', data_atual)
        os.makedirs(diretorio_logs, exist_ok=True)

        nome_arquivo = f'{filename}.jpg'
        caminho_arquivo = os.path.join(diretorio_logs, nome_arquivo)

        cv2.imwrite(caminho_arquivo, frame)
        print(f"Frame salvo em: {caminho_arquivo}")
        self._log_message(RABBITMQ_HOST, 'SALVAR_FRAME', {'file': nome_arquivo}, "SALVO")

    # =========================================================================
    # Execução Principal (Threads)
    # =========================================================================

    def run(self) -> None:
        """
        Inicia as threads:
        - Thread para receber mensagens do RabbitMQ.
        - Thread de processamento de imagem (YOLO).
        - Thread que tenta conectar/desconectar do dispositivo (óculos).
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

# =============================================================================
# Execução (Entry Point)
# =============================================================================

if __name__ == '__main__':
    processor = YOLOProcessor()
    processor.run()
