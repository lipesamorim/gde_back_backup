#!/usr/bin/env bash
#[ WARN:0@2838.333] global cap_v4l.cpp:1136 tryIoctl VIDEOIO(V4L2:/dev/video2): select() timeout.
 #2024-11-08 11:30:44,919 - ERROR - Falha ao capturar o quadro

# Script para instalação e configuração do scrcpy com suporte a v4l2loopback

function add_log() {
  message="$1"
  log_type="$2"
  operation_code="$3"
  dt=$(date '+%d/%m/%Y %H:%M:%S')

  # Define o status da operação com base no código
  declare -A operation_statuses=(
    [0]="Sucesso"
    [1]="Erro."
    [2]="Aviso"
    [3]="Diretório não encontrado"
    [4]="Arquivo não encontrado"
    [5]="Comando não encontrado"
    [6]="Permissão negada"
    [7]="Já instalado"
    [8]="Dispositivo não encontrado"
    [9]="Finalizado"
  )
  operation_status=${operation_statuses[$operation_code]:-"Erro desconhecido"}

  # Prepara o payload
  payload=$(cat <<EOF
{
  "shell-log": "$message",
  "shell-log-type": "$log_type",
  "shell-log-date": "$dt",
  "shell-operation-status": "$operation_status",
  "shell-operation-code": $operation_code
}
EOF
)

  # Publica a mensagem usando rabbitmqadmin
#  ./rabbitmqadmin -V / -u admin -p admin --host 10.42.0.1 publish exchange=amq.default routing_key=fila_logs payload="$payload" properties="{\"delivery_mode\":1,\"expiration\":\"90000\"}" >/dev/null 2>&1

#  if [ $? -eq 0 ]; then
#    echo > /dev/null
#  else
#    echo "Erro ao enviar log para o servidor. RabbitMQ não encontrado."
#  fi
}
function setup_rabbitmqadmin() {
  log_file_name="setup-rabbitmqadmin"

  if [ ! -f "./rabbitmqadmin" ]; then
    if curl -s -u admin:admin http://10.42.0.1:15672/cli/rabbitmqadmin -o rabbitmqadmin; then
      chmod +x rabbitmqadmin
      echo "rabbitmqadmin baixado e configurado com sucesso"
      add_log "rabbitmqadmin baixado e configurado com sucesso." "$log_file_name" 0
    else
      add_log "Erro ao baixar rabbitmqadmin." "$log_file_name" 1
      echo "Erro: Não foi possível baixar o rabbitmqadmin."
      exit 1
    fi
  else
    echo "rabbitmqadmin já está configurado."
    add_log "rabbitmqadmin já está configurado." "$log_file_name" 7
  fi
}

function verify_command() {
  local cmd="$1"
  local pkg="$2"
  local log_file_name="$cmd"

  if command -v "$cmd" >/dev/null; then
    echo "$cmd já está instalado."
    add_log "$cmd já está instalado." "$log_file_name" 7
  else
    if sudo apt install -qqy "$pkg"; then
      echo "$cmd instalado com sucesso."
      add_log "$cmd instalado com sucesso." "$log_file_name" 0
    else
      echo "Erro ao instalar $cmd."
      add_log "Erro ao instalar $cmd." "$log_file_name" 1
    fi
  fi
}

function update_os() {
  log_file_name="os-update"
  echo "Atualizando Sistema operacional."
  if sudo apt update -qqy && sudo apt upgrade -qqy && sudo apt autoremove -qqy && sudo apt autoclean -qqy; then
    add_log "Sistema operacional atualizado." "$log_file_name" 0
    echo "Sistema operacional atualizado."
  else
    add_log "Erro ao atualizar o sistema operacional." "$log_file_name" 2
    echo "Erro ao atualizar o sistema operacional."
  fi
}

function install_required_packages() {
  log_file_name="install-packages"
  packages=(
    ffmpeg libsdl2-2.0-0 adb wget gcc git pkg-config meson ninja-build libsdl2-dev
    libavcodec-dev libavdevice-dev libavformat-dev libavutil-dev libswresample-dev
    libusb-1.0-0 libusb-1.0-0-dev v4l2loopback-dkms v4l-utils openjdk-17-jdk cmake
    python3 curl
  )

  echo "Atualizando Pacotes."

  if sudo apt install -qqy "${packages[@]}"; then
    add_log "Pacotes necessários instalados com sucesso." "$log_file_name" 0
    echo "Pacotes necessários instalados com sucesso."
  else
    add_log "Erro ao instalar os pacotes necessários." "$log_file_name" 1
    echo "Erro ao instalar os pacotes necessários."
  fi
}

function clone_and_install_scrcpy() {
  log_file_name="scrcpy-install"
  echo "scrcpy está sendo instalado."
  if [ -d "scrcpy" ]; then
    cd scrcpy || exit
    git pull
  else
    git clone https://github.com/Genymobile/scrcpy
    cd scrcpy || exit
  fi

  if ./install_release.sh; then
    add_log "scrcpy instalado com sucesso." "$log_file_name" 0
    echo "scrcpy instalado com sucesso."
  else
    add_log "Erro ao instalar scrcpy." "$log_file_name" 1
    echo "Erro ao instalar scrcpy."
  fi
  cd ..
}

function configure_v4l2loopback() {
  log_file_name="v4l2loopback"
#    if lsmod | grep -q v4l2loopback; then
#      add_log "v4l2loopback já está carregado." "$log_file_name" 7
#      echo "v4l2loopback já está carregado."
#    else
      sudo modprobe -r v4l2loopback
      if sudo modprobe v4l2loopback exclusive_caps=1; then
        add_log "v4l2loopback configurado com sucesso." "$log_file_name" 0
        echo "v4l2loopback configurado com sucesso."
      else
        add_log "Erro ao configurar v4l2loopback." "$log_file_name" 1
        echo "Erro ao configurar v4l2loopback."
      fi
#    fi
}

function restart_adb_server() {
  log_file_name="adb-server"

  adb kill-server >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "Servidor ADB finalizado com sucesso."
    add_log "Servidor ADB finalizado com sucesso." "$log_file_name" 0
  else
    add_log "Aviso: Não foi possível finalizar o servidor ADB. Ele pode não estar em execução." "$log_file_name" 2
  fi

  adb start-server >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "Servidor ADB iniciado com sucesso."
    add_log "Servidor ADB iniciado com sucesso." "$log_file_name" 0
  else
    add_log "Erro ao iniciar o servidor ADB." "$log_file_name" 1
    echo "Erro: Não foi possível iniciar o servidor ADB."
    exit 1
  fi
}

function get_wireless_debug_port() {
  log_file_name="get-wireless-debug-port"

  # Usa 'adb shell dumpsys mdns' para obter a porta de depuração sem fio
  #port=$(adb shell dumpsys mdns | grep "port=" | grep "serviceType=_adb-tls-connect._tcp." | awk -F'=' '{print $NF}' | tr -d '\r')
  port=40121
  if [[ -z "$port" || "$port" == "null" ]]; then
    add_log "Não foi possível obter a porta de depuração sem fio." "$log_file_name" 1
    echo "Erro: Não foi possível obter a porta de depuração sem fio."
    exit 1
  else
    add_log "Porta de depuração sem fio obtida: $port" "$log_file_name" 0
    echo "Porta de depuração sem fio obtida: $port"
  fi
}

function connect_to_device() {
  log_file_name="connect-device"

  # Obtém o endereço IP do dispositivo
  #ip_address=$(adb shell ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d / -f 1)
  ip_address=192.168.1.62
  # Chama a função para obter a porta de depuração sem fio
  get_wireless_debug_port

  # Tenta conectar ao dispositivo usando o IP e a porta obtidos
  if adb connect "${ip_address}:${port}" >/dev/null; then
    echo "Conectado ao dispositivo via TCP/IP na porta $port."
    add_log "Conectado ao dispositivo via TCP/IP na porta $port." "$log_file_name" 0
  else
    add_log "Erro ao conectar ao dispositivo na porta $port." "$log_file_name" 1
    echo "Erro: Falha ao conectar ao dispositivo na porta $port."
    exit 1
  fi
  sleep 2
}

function execute_scrcpy_otg() {
  log_file_name="scrcpy-otg"

  if scrcpy --otg; then
    add_log "scrcpy --otg executado com sucesso." "$log_file_name" 0
    echo "scrcpy --otg executado. Você pode usar o mouse e teclado para configurar o dispositivo."
  else
    add_log "Erro ao executar scrcpy --otg." "$log_file_name" 1
    echo "Erro ao executar scrcpy --otg."
    exit 1
  fi
}

function wait_for_usb_removal() {
  log_file_name="usb-removal"

  echo "Aguardando a remoção do cabo USB..."

  while true; do
    if adb devices | grep -q "device$"; then
      # Dispositivo ainda conectado via USB
      sleep 5
    else
      add_log "Cabo USB removido." "$log_file_name" 0
      echo "Cabo USB removido."
      break
    fi
  done
}

function check_device_connection() {
  log_file_name="device-connection"
  attempts=0
  max_attempts=10

  while [ $attempts -lt $max_attempts ]; do
    # Obtém o endereço IP do dispositivo
    ip_address=$(adb shell ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d / -f 1)

    if adb devices | grep -q "${ip_address}"; then
      add_log "Dispositivo já conectado via Wi-Fi." "$log_file_name" 0
      echo "Dispositivo já conectado via Wi-Fi."
      break
    else
      add_log "Dispositivo não conectado via Wi-Fi." "$log_file_name" 1
      echo "Dispositivo não está conectado via Wi-Fi."
    fi

    if adb devices | grep -q "device$"; then
      add_log "Dispositivo encontrado via USB." "$log_file_name" 0
      echo "Dispositivo conectado via USB."

      # Executa scrcpy --otg
      execute_scrcpy_otg

      # Após executar o scrcpy --otg, aguarda a remoção do cabo USB
      wait_for_usb_removal

      # Após a remoção do USB, tenta conectar via Wi-Fi
      connect_to_device

      # Verifica se a conexão Wi-Fi foi estabelecida
#      ip_address=$(adb shell ip addr show wlan0 | grep 'inet ' | awk '{print $2}' | cut -d / -f 1) # Local
      ip_address=$(adb shell ip addr show wlp0s20f3 | grep 'inet ' | awk '{print $2}' | cut -d / -f 1)  # TCP
      if adb devices | grep -q "${ip_address}"; then
        add_log "Conexão Wi-Fi estabelecida com sucesso." "$log_file_name" 0
        echo "Conexão Wi-Fi estabelecida com sucesso."
        break
      else
        add_log "Falha ao estabelecer conexão Wi-Fi." "$log_file_name" 1
        echo "Erro: Não foi possível estabelecer conexão Wi-Fi. Tentativa $(($attempts + 1)) de $max_attempts."
      fi
    else
      add_log "Dispositivo não detectado via USB. Tentando novamente em 10 segundos..." "$log_file_name" 8
      echo "Dispositivo não detectado via USB. Tentando novamente em 10 segundos..."
      sleep 10
    fi

    attempts=$((attempts + 1))
  done

  if [ $attempts -ge $max_attempts ]; then
    add_log "Falha ao conectar via Wi-Fi após $max_attempts tentativas." "$log_file_name" 1
    echo "Falha ao conectar via Wi-Fi após $max_attempts tentativas. Encerrando o script."
    exit 1
  fi
}


function start_camera() {
  log_file_name="camera"
  SCRCPY_SERVER_PATH="scrcpy-server"

  # Verifica se o arquivo scrcpy-server existe no diretório atual
  if [ -f "$SCRCPY_SERVER_PATH" ]; then
    add_log "Arquivo $SCRCPY_SERVER_PATH encontrado." "$log_file_name" 0
  else
    add_log "Arquivo $SCRCPY_SERVER_PATH não encontrado no diretório atual." "$log_file_name" 4
    echo "Erro: O arquivo $SCRCPY_SERVER_PATH não foi encontrado no diretório atual."
    exit 1
  fi

  # Encontra o dispositivo v4l2
  v4l2_device=$(v4l2-ctl --list-devices | grep -A 1 "Dummy video device" | tail -n1 | awk '{print $1}')
  if [ -z "$v4l2_device" ]; then
    add_log "Dispositivo v4l2 não encontrado." "$log_file_name" 4
    echo "Erro: Dispositivo v4l2 não encontrado."
    exit 1
  fi
  # Inicia o scrcpy com as opções especificadas
  #SCRCPY_SERVER_PATH="$SCRCPY_SERVER_PATH" scrcpy --video-source=camera --camera-facing=back --v4l2-sink="$v4l2_device" --no-window  --no-playback --no-audio --camera-size=1920x1080 >/dev/null; then

  # Inicia o scrcpy com as opções especificadas
#  scrcpy --capture-orientation=180 --video-source=camera --v4l2-sink=/dev/video0 --camera-size=1920x1080 -d > /dev/null
   SCRCPY_SERVER_PATH="scrcpy-server" scrcpy --video-codec=h265 --display-orientation=180 --video-source=camera --v4l2-sink=/dev/video2 --camera-size=1920x1080 --no-audio --no-window -e > /dev/null

  if pgrep -f "scrcpy" && pgrep -f "adb" >/dev/null; then
    add_log "Câmera iniciada com sucesso no dispositivo $v4l2_device." "$log_file_name" 9
    echo "Câmera iniciada com sucesso no dispositivo."
  else
    add_log "Erro ao iniciar a câmera." "$log_file_name" 1
    echo "Erro: Falha ao iniciar o scrcpy com as configurações especificadas."
    exit 1
  fi
}


function main() {
#  verify_command "curl" "curl"
  #setup_rabbitmqadmin
#  update_os
#  install_required_packages
#  clone_and_install_scrcpy
  configure_v4l2loopback
  restart_adb_server
  connect_to_device
  #check_device_connection
  start_camera
}

main