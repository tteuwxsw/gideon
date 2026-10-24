class_name GideonWSClient
extends Node

## Cliente WebSocket para comunicação bidirecional com o backend Python da Gideon.

signal conectado()
signal desconectado()
signal evento_recebido(tipo: String, dados: Dictionary)

signal emocao_alterada(nome: String, intensidade: float)
signal fala_iniciada(texto: String)
signal fala_chunk(texto: String)
signal fala_finalizada()
signal pensando_alterado(ativo: bool)
signal modo_alterado(modo: String)

@export var url_servidor: String = "ws://127.0.0.1:8000/ws"
@export var caminho_token: String = "../dados/auth_token.txt"
@export var reconectar_automatico: bool = true
@export var intervalo_reconexao: float = 3.0

var _socket: WebSocketPeer = WebSocketPeer.new()
var _conectado: bool = false
var _token: String = ""
var _timer_reconexao: float = 0.0


func _ready() -> void:
    _carregar_token()
    conectar_servidor()


func _carregar_token() -> void:
    # Tenta carregar o token local gerado pelo servidor Python
    if FileAccess.file_exists(caminho_token):
        var arquivo = FileAccess.open(caminho_token, FileAccess.READ)
        if arquivo:
            _token = arquivo.get_as_text().strip_edges()
            print("[Gideon WS] Token carregado com sucesso.")


func conectar_servidor() -> void:
    var url_completa = url_servidor
    if not _token.is_empty():
        url_completa += "?token=" + _token.uri_encode()

    print("[Gideon WS] Conectando a: ", url_servidor)
    var err = _socket.connect_to_url(url_completa)
    if err != OK:
        push_warning("[Gideon WS] Falha ao iniciar conexão: " + str(err))


func _process(delta: float) -> void:
    _socket.poll()
    var estado = _socket.get_ready_state()

    if estado == WebSocketPeer.STATE_OPEN:
        if not _conectado:
            _conectado = true
            print("[Gideon WS] Conexão estabelecida com sucesso!")
            conectado.emit()
            enviar_evento("pronto", {"cliente": "godot_avatar", "versao": "0.2.0"})

        while _socket.get_available_packet_count() > 0:
            var pacote = _socket.get_packet()
            var texto = pacote.get_string_from_utf8()
            _processar_mensagem(texto)

    elif estado == WebSocketPeer.STATE_CLOSED:
        if _conectado:
            _conectado = false
            print("[Gideon WS] Conexão encerrada.")
            desconectado.emit()

        if reconectar_automatico:
            _timer_reconexao += delta
            if _timer_reconexao >= intervalo_reconexao:
                _timer_reconexao = 0.0
                conectar_servidor()


func _processar_mensagem(texto_json: String) -> void:
    var json = JSON.new()
    var parse_err = json.parse(texto_json)
    if parse_err != OK:
        return

    var dados = json.get_data()
    if typeof(dados) != TYPE_DICTIONARY:
        return

    var tipo = dados.get("tipo", "")
    var payload: Dictionary = dados
    if dados.has("dados") and typeof(dados["dados"]) == TYPE_DICTIONARY:
        payload = dados["dados"]

    evento_recebido.emit(tipo, payload)

    match tipo:
        "emocao":
            var nome = payload.get("nome", dados.get("nome", "neutra"))
            var intensidade = float(payload.get("intensidade", dados.get("intensidade", 1.0)))
            emocao_alterada.emit(nome, intensidade)

        "fala_inicio":
            var texto = payload.get("texto", dados.get("texto", ""))
            fala_iniciada.emit(texto)

        "fala_chunk":
            var texto = str(payload.get("texto", dados.get("texto", "")))
            fala_chunk.emit(texto)

        "fala_fim":
            fala_finalizada.emit()

        "pensando":
            var ativo = bool(payload.get("ativo", dados.get("ativo", false)))
            pensando_alterado.emit(ativo)

        "modo":
            var modo = payload.get("modo", payload.get("nome", dados.get("nome", "conversa")))
            modo_alterado.emit(modo)


func enviar_evento(tipo: String, dados: Dictionary = {}) -> void:
    if not _conectado or _socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
        return

    var msg = {"tipo": tipo}
    for chave in dados:
        msg[chave] = dados[chave]

    var json_str = JSON.stringify(msg)
    _socket.send_text(json_str)
