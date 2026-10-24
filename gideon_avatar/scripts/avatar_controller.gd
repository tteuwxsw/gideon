class_name GideonAvatarController
extends Node3D

## Controlador principal do avatar holográfico da Gideon.
## Gerencia micro-animações locais (piscar, respiração, olhar),
## sincronização com WebSocket, controle de expressões e arrastar da janela.

@export var ws_client: GideonWSClient
@export var mesh_avatar: MeshInstance3D
@export var anim_player: AnimationPlayer

# Modos de exibição da janela do Windows
enum ModoJanela { COMPACTO, CONVERSA, FOCO, OPERACIONAL, OCULTO }
var modo_atual: ModoJanela = ModoJanela.CONVERSA

# Controle de arrastar da janela
var _arrastando_janela: bool = false
var _posicao_clique_inicial: Vector2i = Vector2i.ZERO

# Micro-idle: Piscar natural independente do cérebro
var _timer_proximo_piscar: float = 3.5
var _duracao_piscar: float = 0.15
var _piscando: bool = false
var _tempo_piscar_atual: float = 0.0

# Micro-idle: Olhar e respiração sutil
var _tempo_acumulado: float = 0.0
var _alvo_rotacao_cabeca: Vector3 = Vector3.ZERO
var _timer_mudar_olhar: float = 5.0

# Expressão facial atual
var _emocao_alvo: String = "neutra"
var _intensidade_emocao: float = 1.0

# Estado de fala
var _falando: bool = false
var _abertura_boca: float = 0.0


func _ready() -> void:
    _configurar_janela()

    if ws_client:
        ws_client.emocao_alterada.connect(_on_emocao_alterada)
        ws_client.fala_iniciada.connect(_on_fala_iniciada)
        ws_client.fala_chunk.connect(_on_fala_chunk)
        ws_client.fala_finalizada.connect(_on_fala_finalizada)
        ws_client.pensando_alterado.connect(_on_pensando_alterado)
        ws_client.modo_alterado.connect(_on_modo_alterado)


func _configurar_janela() -> void:
    # Janela 100% transparente, sem bordas, sempre visível e INTANGÍVEL (cliques passam direto)
    var janela_id = DisplayServer.MAIN_WINDOW_ID
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_TRANSPARENT, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, true, janela_id)
    
    # Cliques do mouse atravessam o holograma — ela é uma entidade puramente visual
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH, true, janela_id)


func _input(_event: InputEvent) -> void:
    # Nenhuma interação por mouse: controle 100% por voz e inteligência da Gideon
    pass


func _process(delta: float) -> void:
    _tempo_acumulado += delta

    _atualizar_micro_idle(delta)
    _atualizar_piscar(delta)
    _atualizar_fala(delta)


func _atualizar_micro_idle(delta: float) -> void:
    # 1. Flutuação suave (respiração holográfica)
    var flutuacao_y = sin(_tempo_acumulado * 1.5) * 0.015
    position.y = flutuacao_y

    # 2. Variação sutil de olhar/inclinação de cabeça a cada 4 a 8 segundos
    _timer_mudar_olhar -= delta
    if _timer_mudar_olhar <= 0.0:
        _timer_mudar_olhar = randf_range(4.0, 8.0)
        _alvo_rotacao_cabeca = Vector3(
            deg_to_rad(randf_range(-3.0, 3.0)),
            deg_to_rad(randf_range(-6.0, 6.0)),
            deg_to_rad(randf_range(-2.0, 2.0))
        )

    # Interpolação suave para a rotação alvo
    rotation.x = lerp_angle(rotation.x, _alvo_rotacao_cabeca.x, delta * 2.0)
    rotation.y = lerp_angle(rotation.y, _alvo_rotacao_cabeca.y, delta * 2.0)
    rotation.z = lerp_angle(rotation.z, _alvo_rotacao_cabeca.z, delta * 2.0)


func _atualizar_piscar(delta: float) -> void:
    if not _piscando:
        _timer_proximo_piscar -= delta
        if _timer_proximo_piscar <= 0.0:
            _piscando = true
            _tempo_piscar_atual = 0.0
            _timer_proximo_piscar = randf_range(3.0, 6.5)
    else:
        _tempo_piscar_atual += delta
        var progresso = _tempo_piscar_atual / _duracao_piscar

        if progresso >= 1.0:
            _piscando = false
            _aplicar_blendshape("eyeBlinkLeft", 0.0)
            _aplicar_blendshape("eyeBlinkRight", 0.0)
        else:
            # Sobe até 1.0 na metade do tempo, desce até 0.0 na outra
            var peso_piscar = sin(progresso * PI)
            _aplicar_blendshape("eyeBlinkLeft", peso_piscar)
            _aplicar_blendshape("eyeBlinkRight", peso_piscar)


func _atualizar_fala(delta: float) -> void:
    if _falando:
        # Simula movimento labial natural sincronizado com as sílabas
        _abertura_boca = (sin(_tempo_acumulado * 14.0) + 1.0) * 0.5 * 0.8
        _aplicar_blendshape("jawOpen", _abertura_boca)
    else:
        _abertura_boca = lerp(_abertura_boca, 0.0, delta * 10.0)
        _aplicar_blendshape("jawOpen", _abertura_boca)


func _aplicar_blendshape(nome: String, peso: float) -> void:
    if mesh_avatar and mesh_avatar.mesh:
        var idx = mesh_avatar.find_blend_shape_by_name(nome)
        if idx >= 0:
            mesh_avatar.set_blend_shape_value(idx, clamp(peso, 0.0, 1.0))


# ─── Sinais do WebSocket ──────────────────────────────────────

func _on_emocao_alterada(nome: String, intensidade: float) -> void:
    _emocao_alvo = nome
    _intensidade_emocao = intensidade
    print("[Gideon Avatar] Expressando emoção: ", nome, " (intensidade: ", intensidade, ")")

    match nome:
        "amigavel", "satisfacao":
            _aplicar_blendshape("mouthSmileLeft", 0.6 * intensidade)
            _aplicar_blendshape("mouthSmileRight", 0.6 * intensidade)
        "curiosidade", "duvida":
            _aplicar_blendshape("browInnerUp", 0.7 * intensidade)
            _alvo_rotacao_cabeca.z = deg_to_rad(6.0) # Inclina levemente a cabeça
        "surpresa":
            _aplicar_blendshape("eyeWideLeft", 0.8 * intensidade)
            _aplicar_blendshape("eyeWideRight", 0.8 * intensidade)
        "neutra":
            _aplicar_blendshape("mouthSmileLeft", 0.0)
            _aplicar_blendshape("mouthSmileRight", 0.0)
            _aplicar_blendshape("browInnerUp", 0.0)


func _on_fala_iniciada(_texto: String) -> void:
    _falando = true


func _on_fala_chunk(_texto: String) -> void:
    _falando = true


func _on_fala_finalizada() -> void:
    _falando = false


func _on_pensando_alterado(ativo: bool) -> void:
    if ativo:
        # Vira levemente o olhar para cima enquanto processa a resposta
        _alvo_rotacao_cabeca = Vector3(deg_to_rad(-4.0), deg_to_rad(3.0), 0.0)
    else:
        _alvo_rotacao_cabeca = Vector3.ZERO


# Controle de movimentação suave da janela (Tween)
var _tween_janela: Tween


func mover_janela_suave(pos_destino: Vector2i, tamanho_destino: Vector2i = Vector2i.ZERO, duracao: float = 0.8) -> void:
    """Desliza suavemente a janela da Gideon pela tela como um holograma flutuante."""
    var janela_id = DisplayServer.MAIN_WINDOW_ID
    var pos_atual = DisplayServer.window_get_position(janela_id)
    var tam_atual = DisplayServer.window_get_size(janela_id)

    if tamanho_destino == Vector2i.ZERO:
        tamanho_destino = tam_atual

    if _tween_janela and _tween_janela.is_valid():
        _tween_janela.kill()

    _tween_janela = create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
    
    # Interpola a posição
    _tween_janela.tween_method(
        func(p: Vector2): DisplayServer.window_set_position(Vector2i(p), janela_id),
        Vector2(pos_atual), Vector2(pos_destino), duracao
    )
    # Interpola o tamanho
    _tween_janela.tween_method(
        func(s: Vector2): DisplayServer.window_set_size(Vector2i(s), janela_id),
        Vector2(tam_atual), Vector2(tamanho_destino), duracao
    )


func _on_modo_alterado(modo: String) -> void:
    var tela_tamanho = DisplayServer.screen_get_size()

    match modo.to_lower():
        "compacto", "canto":
            modo_atual = ModoJanela.COMPACTO
            var pos = Vector2i(tela_tamanho.x - 300, tela_tamanho.y - 420)
            mover_janela_suave(pos, Vector2i(280, 360), 0.7)

        "conversa", "centro_direita":
            modo_atual = ModoJanela.CONVERSA
            var pos = Vector2i(tela_tamanho.x - 480, tela_tamanho.y - 720)
            mover_janela_suave(pos, Vector2i(450, 650), 0.6)

        "foco", "centro":
            modo_atual = ModoJanela.FOCO
            var pos = Vector2i((tela_tamanho.x - 600) / 2, (tela_tamanho.y - 850) / 2)
            mover_janela_suave(pos, Vector2i(600, 850), 0.9)

        "canto_esquerdo":
            var pos = Vector2i(40, tela_tamanho.y - 420)
            mover_janela_suave(pos, Vector2i(280, 360), 0.7)

        "canto_superior_direito":
            var pos = Vector2i(tela_tamanho.x - 300, 40)
            mover_janela_suave(pos, Vector2i(280, 360), 0.7)

        "oculto":
            modo_atual = ModoJanela.OCULTO
            visible = false
            return

    visible = true
