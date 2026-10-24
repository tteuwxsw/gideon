class_name GideonAvatarController
extends Node3D

## Controlador principal do avatar holográfico provisório da Gideon.
## Carrega a malha feminina com blendshapes ARKit/Oculus,
## aplica o shader holográfico preservando olhos, lábios e feições,
## e gerencia micro-animações humanas (piscar, sacadas oculares, respiração e lip-sync).

@export var ws_client: Node
@export var mesh_avatar: MeshInstance3D
@export var anim_player: AnimationPlayer
@export var caminho_modelo_glb: String = "res://modelos/gideon.glb"

# Modos de exibição da janela do Windows
enum ModoJanela { COMPACTO, CONVERSA, FOCO, OPERACIONAL, OCULTO }
var modo_atual: ModoJanela = ModoJanela.CONVERSA

# Malhas com blendshapes faciais (Wolf3D_Head, EyeLeft, EyeRight, Wolf3D_Teeth)
var _malhas_faciais: Array[MeshInstance3D] = []
var _pivo_cabeca: Node3D = null
var _shader_holograma: Shader = preload("res://shaders/holograma.gdshader")

# Micro-idle: Piscar natural independente do cérebro
var _timer_proximo_piscar: float = 2.8
var _duracao_piscar: float = 0.14
var _piscando: bool = false
var _tempo_piscar_atual: float = 0.0

# Micro-idle: Sacadas oculares (movimento vivo dos olhos)
var _timer_sacada_olhos: float = 2.0
var _olhar_alvo: Vector2 = Vector2.ZERO
var _olhar_atual: Vector2 = Vector2.ZERO

# Micro-idle: Inclinação de cabeça e respiração sutil
var _tempo_acumulado: float = 0.0
var _alvo_rotacao_cabeca: Vector3 = Vector3.ZERO
var _timer_mudar_olhar: float = 4.5

# Expressão facial atual
var _emocao_alvo: String = "neutra"
var _intensidade_emocao: float = 1.0

# Estado de fala e sincronia labial multi-visema
var _falando: bool = false
var _energia_voz: float = 0.0
var _energia_voz_alvo: float = 0.0
var _abertura_boca: float = 0.0

# Controle de movimentação suave da janela (Tween)
var _tween_janela: Tween


func _ready() -> void:
    _configurar_janela()
    _carregar_modelo_realista()

    if ws_client:
        ws_client.emocao_alterada.connect(_on_emocao_alterada)
        ws_client.fala_iniciada.connect(_on_fala_iniciada)
        ws_client.fala_chunk.connect(_on_fala_chunk)
        ws_client.fala_finalizada.connect(_on_fala_finalizada)
        ws_client.pensando_alterado.connect(_on_pensando_alterado)
        ws_client.modo_alterado.connect(_on_modo_alterado)
        ws_client.evento_recebido.connect(_on_evento_recebido)


func _configurar_janela() -> void:
    # Janela 100% transparente, sem bordas, sempre visível e INTANGÍVEL (cliques passam direto)
    get_window().transparent = true
    get_viewport().transparent_bg = true
    var janela_id = DisplayServer.MAIN_WINDOW_ID
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_TRANSPARENT, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH, true, janela_id)
    print("[Gideon Avatar] Transparência de janela suportada: ", DisplayServer.has_feature(DisplayServer.FEATURE_WINDOW_TRANSPARENCY))


func _carregar_modelo_realista() -> void:
    var caminho_absoluto = ProjectSettings.globalize_path(caminho_modelo_glb)
    if not FileAccess.file_exists(caminho_absoluto) and not FileAccess.file_exists(caminho_modelo_glb):
        print("[Gideon Avatar] Modelo GLB não encontrado, usando malha base.")
        if mesh_avatar:
            _malhas_faciais.append(mesh_avatar)
        return

    var doc = GLTFDocument.new()
    var state = GLTFState.new()
    var err = doc.append_from_file(caminho_absoluto, state)
    if err != OK:
        push_warning("[Gideon Avatar] Falha ao carregar GLB: " + str(err))
        if mesh_avatar:
            _malhas_faciais.append(mesh_avatar)
        return

    var cena_modelo = doc.generate_scene(state)
    if not cena_modelo:
        return

    # Oculta a esfera placeholder
    if mesh_avatar:
        mesh_avatar.visible = false

    # Cria pivô centralizado na altura do rosto (Y = 1.585m na malha original)
    _pivo_cabeca = Node3D.new()
    _pivo_cabeca.name = "PivoCabecaRealista"
    add_child(_pivo_cabeca)

    cena_modelo.position = Vector3(0.0, -1.585, 0.0)
    _pivo_cabeca.add_child(cena_modelo)

    _configurar_nos_modelo(cena_modelo)
    # Aplica expressão serena inicial da Gideon (leve sorriso acolhedor)
    _aplicar_expressao_base()
    print("[Gideon Avatar] Rosto feminino 3D carregado com ", _malhas_faciais.size(), " camadas faciais e 72 blendshapes.")


func _configurar_nos_modelo(no: Node) -> void:
    if no is MeshInstance3D:
        var nome_no = no.name
        # Oculta óculos e corpo inferior para exibir apenas o busto/rosto flutuante como em The Flash
        if nome_no in ["Wolf3D_Glasses", "Wolf3D_Outfit_Bottom", "Wolf3D_Outfit_Footwear", "Wolf3D_Body", "Wolf3D_Outfit_Top"]:
            no.visible = false
        else:
            # Olhos e dentes conservam o PBR original. Aplicar Fresnel emissivo
            # nessas geometrias esféricas criava olhos em forma de anéis.
            if nome_no not in ["EyeLeft", "EyeRight", "Wolf3D_Teeth"]:
                _aplicar_material_holografico(no)
            if no.get_blend_shape_count() > 0:
                _malhas_faciais.append(no)

    for filho in no.get_children():
        _configurar_nos_modelo(filho)


func _aplicar_material_holografico(malha: MeshInstance3D) -> void:
    if not malha.mesh:
        return

    var qtd_superficies = malha.mesh.get_surface_count()
    for i in range(qtd_superficies):
        var mat_orig = malha.mesh.surface_get_material(i)
        var mat_holo = ShaderMaterial.new()
        mat_holo.shader = _shader_holograma

        # Parâmetros padrão do holograma Time Vault
        mat_holo.set_shader_parameter("cor_holograma", Color(0.06, 0.58, 0.95, 0.72))
        mat_holo.set_shader_parameter("cor_fresnel", Color(0.35, 0.96, 1.0, 1.0))
        mat_holo.set_shader_parameter("forca_fresnel", 3.5)
        mat_holo.set_shader_parameter("densidade_scanlines", 260.0)
        mat_holo.set_shader_parameter("velocidade_scanlines", 1.4)
        mat_holo.set_shader_parameter("intensidade_scanlines", 0.09)
        mat_holo.set_shader_parameter("intensidade_pulso", 0.03)
        mat_holo.set_shader_parameter("opacidade_geral", 0.68)
        mat_holo.set_shader_parameter("corte_pescoco_min", 1.43)
        mat_holo.set_shader_parameter("corte_pescoco_max", 1.49)

        # Preserva a textura realista dos olhos, íris, lábios e pele sob o feixe holográfico
        if mat_orig is BaseMaterial3D and mat_orig.albedo_texture:
            mat_holo.set_shader_parameter("textura_base", mat_orig.albedo_texture)
            if malha.name == "Wolf3D_Hair":
                mat_holo.set_shader_parameter("preservar_detalhes_rosto", 0.55)
                mat_holo.set_shader_parameter("opacidade_geral", 0.58)
            else:
                mat_holo.set_shader_parameter("preservar_detalhes_rosto", 0.66)

        malha.set_surface_override_material(i, mat_holo)


func _aplicar_expressao_base() -> void:
    # Semblante sereno, vivo e acolhedor característico da Gideon
    _aplicar_blendshape("mouthSmileLeft", 0.08)
    _aplicar_blendshape("mouthSmileRight", 0.08)
    _aplicar_blendshape("browInnerUp", 0.04)


func _input(_event: InputEvent) -> void:
    # Controle 100% por voz e inteligência da Gideon
    pass


func _process(delta: float) -> void:
    _tempo_acumulado += delta

    _atualizar_micro_idle(delta)
    _atualizar_olhar_vivo(delta)
    _atualizar_piscar(delta)
    _atualizar_fala(delta)


func _atualizar_micro_idle(delta: float) -> void:
    # 1. Flutuação suave (respiração holográfica)
    var flutuacao_y = sin(_tempo_acumulado * 1.5) * 0.008
    position.y = flutuacao_y

    # 2. Variação sutil de olhar/inclinação de cabeça a cada 4 a 7 segundos
    _timer_mudar_olhar -= delta
    if _timer_mudar_olhar <= 0.0:
        _timer_mudar_olhar = randf_range(3.8, 7.2)
        _alvo_rotacao_cabeca = Vector3(
            deg_to_rad(randf_range(-2.5, 2.5)),
            deg_to_rad(randf_range(-5.5, 5.5)),
            deg_to_rad(randf_range(-2.0, 2.0))
        )

    var alvo_no = _pivo_cabeca if _pivo_cabeca else self
    alvo_no.rotation.x = lerp_angle(alvo_no.rotation.x, _alvo_rotacao_cabeca.x, delta * 2.2)
    alvo_no.rotation.y = lerp_angle(alvo_no.rotation.y, _alvo_rotacao_cabeca.y, delta * 2.2)
    alvo_no.rotation.z = lerp_angle(alvo_no.rotation.z, _alvo_rotacao_cabeca.z, delta * 2.2)


func _atualizar_olhar_vivo(delta: float) -> void:
    # Micro-sacadas oculares naturais para que os olhos pareçam humanos e atentos
    _timer_sacada_olhos -= delta
    if _timer_sacada_olhos <= 0.0:
        _timer_sacada_olhos = randf_range(1.5, 4.0)
        _olhar_alvo = Vector2(randf_range(-0.06, 0.06), randf_range(-0.04, 0.04))

    _olhar_atual = _olhar_atual.lerp(_olhar_alvo, delta * 5.0)

    var olhando_dir = max(0.0, _olhar_atual.x)
    var olhando_esq = max(0.0, -_olhar_atual.x)
    var olhando_cima = max(0.0, _olhar_atual.y)
    var olhando_baixo = max(0.0, -_olhar_atual.y)

    _aplicar_blendshape("eyeLookOutRight", olhando_dir)
    _aplicar_blendshape("eyeLookInLeft", olhando_dir)
    _aplicar_blendshape("eyeLookOutLeft", olhando_esq)
    _aplicar_blendshape("eyeLookInRight", olhando_esq)
    _aplicar_blendshape("eyeLookUpLeft", olhando_cima)
    _aplicar_blendshape("eyeLookUpRight", olhando_cima)
    _aplicar_blendshape("eyeLookDownLeft", olhando_baixo)
    _aplicar_blendshape("eyeLookDownRight", olhando_baixo)


func _atualizar_piscar(delta: float) -> void:
    if not _piscando:
        _timer_proximo_piscar -= delta
        if _timer_proximo_piscar <= 0.0:
            _piscando = true
            _tempo_piscar_atual = 0.0
            _timer_proximo_piscar = randf_range(2.6, 5.8)
    else:
        _tempo_piscar_atual += delta
        var progresso = _tempo_piscar_atual / _duracao_piscar

        if progresso >= 1.0:
            _piscando = false
            _aplicar_blendshape("eyeBlinkLeft", 0.0)
            _aplicar_blendshape("eyeBlinkRight", 0.0)
        else:
            var peso_piscar = sin(progresso * PI)
            _aplicar_blendshape("eyeBlinkLeft", peso_piscar)
            _aplicar_blendshape("eyeBlinkRight", peso_piscar)


func _atualizar_fala(delta: float) -> void:
    if _falando:
        _energia_voz = lerp(_energia_voz, _energia_voz_alvo, delta * 18.0)
        # Até existir alinhamento fonético, usa apenas a mandíbula. Empilhar
        # jawOpen, mouthOpen e quatro visemas deformava lábios e dentes.
        var intensidade = clamp(_energia_voz, 0.0, 1.0)
        _abertura_boca = intensidade * 0.24

        _aplicar_blendshape("jawOpen", _abertura_boca)
        _aplicar_blendshape("mouthOpen", 0.0)
        _aplicar_blendshape("viseme_aa", 0.0)
        _aplicar_blendshape("viseme_O", 0.0)
        _aplicar_blendshape("viseme_E", 0.0)
        _aplicar_blendshape("viseme_SS", 0.0)
    else:
        _abertura_boca = lerp(_abertura_boca, 0.0, delta * 12.0)
        _energia_voz = lerp(_energia_voz, 0.0, delta * 12.0)
        _aplicar_blendshape("jawOpen", _abertura_boca)
        _aplicar_blendshape("mouthOpen", 0.0)
        _aplicar_blendshape("viseme_aa", 0.0)
        _aplicar_blendshape("viseme_O", 0.0)
        _aplicar_blendshape("viseme_E", 0.0)
        _aplicar_blendshape("viseme_SS", 0.0)


func _aplicar_blendshape(nome: String, peso: float) -> void:
    var valor = clamp(peso, 0.0, 1.0)
    for malha in _malhas_faciais:
        if malha and malha.mesh:
            var idx = malha.find_blend_shape_by_name(nome)
            if idx >= 0:
                malha.set_blend_shape_value(idx, valor)


# ─── Sinais do WebSocket ──────────────────────────────────────

func _on_evento_recebido(tipo: String, dados: Dictionary) -> void:
    if tipo == "fala_chunk":
        if dados.has("intensidade"):
            _energia_voz_alvo = float(dados.get("intensidade", 0.65))
        else:
            _energia_voz_alvo = 0.0


func _on_emocao_alterada(nome: String, intensidade: float) -> void:
    _emocao_alvo = nome
    _intensidade_emocao = intensidade
    print("[Gideon Avatar] Expressando emoção: ", nome, " (intensidade: ", intensidade, ")")

    _zerar_expressao_anterior()
    match nome:
        "amigavel", "satisfacao", "humor":
            _aplicar_blendshape("mouthSmileLeft", 0.25 * intensidade)
            _aplicar_blendshape("mouthSmileRight", 0.25 * intensidade)
            _aplicar_blendshape("cheekSquintLeft", 0.12 * intensidade)
            _aplicar_blendshape("cheekSquintRight", 0.12 * intensidade)
        "curiosidade", "duvida":
            _aplicar_blendshape("browInnerUp", 0.28 * intensidade)
            _aplicar_blendshape("browOuterUpRight", 0.2 * intensidade)
            _alvo_rotacao_cabeca.z = deg_to_rad(3.0)
        "surpresa":
            _aplicar_blendshape("eyeWideLeft", 0.18 * intensidade)
            _aplicar_blendshape("eyeWideRight", 0.18 * intensidade)
            _aplicar_blendshape("browInnerUp", 0.35 * intensidade)
        "concentracao", "preocupacao":
            _aplicar_blendshape("browDownLeft", 0.25 * intensidade)
            _aplicar_blendshape("browDownRight", 0.25 * intensidade)
        "neutra", _:
            _aplicar_blendshape("mouthSmileLeft", 0.08)
            _aplicar_blendshape("mouthSmileRight", 0.08)
            _aplicar_blendshape("browInnerUp", 0.04)
            _aplicar_blendshape("browDownLeft", 0.0)
            _aplicar_blendshape("browDownRight", 0.0)
            _aplicar_blendshape("eyeWideLeft", 0.0)
            _aplicar_blendshape("eyeWideRight", 0.0)


func _zerar_expressao_anterior() -> void:
    for nome in [
        "mouthSmileLeft", "mouthSmileRight",
        "cheekSquintLeft", "cheekSquintRight",
        "browInnerUp", "browOuterUpRight",
        "browDownLeft", "browDownRight",
        "eyeWideLeft", "eyeWideRight",
    ]:
        _aplicar_blendshape(nome, 0.0)


func _on_fala_iniciada(_texto: String) -> void:
    _falando = true
    _energia_voz_alvo = 0.0


func _on_fala_chunk(_texto: String) -> void:
    _falando = true


func _on_fala_finalizada() -> void:
    _falando = false
    _energia_voz_alvo = 0.0


func _on_pensando_alterado(ativo: bool) -> void:
    if ativo:
        _alvo_rotacao_cabeca = Vector3(deg_to_rad(-3.5), deg_to_rad(3.0), 0.0)
    else:
        _alvo_rotacao_cabeca = Vector3.ZERO


func mover_janela_suave(pos_destino: Vector2i, tamanho_destino: Vector2i = Vector2i.ZERO, duracao: float = 0.8) -> void:
    var janela_id = DisplayServer.MAIN_WINDOW_ID
    var pos_atual = DisplayServer.window_get_position(janela_id)
    var tam_atual = DisplayServer.window_get_size(janela_id)

    if tamanho_destino == Vector2i.ZERO:
        tamanho_destino = tam_atual

    if _tween_janela and _tween_janela.is_valid():
        _tween_janela.kill()

    _tween_janela = create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

    _tween_janela.tween_method(
        func(p: Vector2): DisplayServer.window_set_position(Vector2i(p), janela_id),
        Vector2(pos_atual), Vector2(pos_destino), duracao
    )
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
