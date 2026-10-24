class_name GideonAvatarController
extends Node3D

## Controlador visual, esquelético e comportamental avançado da Gideon (Godot 4).
## Integra:
## - Articulação anatômica real de Skeleton3D (Head, Neck, Spine2, LeftShoulder, RightShoulder, LeftEye, RightEye)
## - Interpolação contínua de 72 blendshapes (52 ARKit + 15 Visemas Oculus)
## - Máquina de 7 estados comportamentais (Idle, Listening, Thinking, Speaking, Executing, Observing, Error)
## - Consciência espacial da área de trabalho (acompanhamento suave de cursor e troca de janelas)
## - Sincronização labial fonética multi-visema cravada na onda sonora real
## - Governador dinâmico de FPS otimizado para AMD Radeon RX 580 8GB

@export var ws_client: Node
@export var mesh_avatar: MeshInstance3D
@export var anim_player: AnimationPlayer
@export var caminho_modelo_glb: String = "res://modelos/gideon.glb"

enum ModoJanela { COMPACTO, CONVERSA, FOCO, OPERACIONAL, OCULTO }
enum EstadoIA { IDLE, LISTENING, THINKING, SPEAKING, EXECUTING, OBSERVING, ERROR }

var modo_atual: ModoJanela = ModoJanela.CONVERSA
var estado_ia_atual: EstadoIA = EstadoIA.IDLE
var _nome_estado_ia: String = "idle"

# Malhas faciais, materiais holográficos e esqueleto anatômico
var _malhas_faciais: Array[MeshInstance3D] = []
var _materiais_holograma: Array[ShaderMaterial] = []
var _pivo_cabeca: Node3D = null
var _esqueleto: Skeleton3D = null
var _ossos_idx: Dictionary = {}
var _ossos_rest: Dictionary = {}
var _shader_holograma: Shader = preload("res://shaders/holograma.gdshader")

# Governador de desempenho (RX 580 8GB: 60 FPS ativo, 30 FPS em repouso, 10 FPS oculto)
var _fps_ativo: int = 60
var _fps_ocioso: int = 30
var _timer_telemetria: float = 1.5

# Controle de presença e customização no desktop
var _opacidade_usuario: float = 0.94
var _escala_usuario: float = 1.0
var _progresso_materializacao: float = 0.0
var _alvo_materializacao: float = 1.0

# Micro-idle: Piscar natural com intervalos variáveis e piscadas duplas ocasionais
var _timer_proximo_piscar: float = 2.6
var _duracao_piscar: float = 0.13
var _piscando: bool = false
var _tempo_piscar_atual: float = 0.0
var _piscada_dupla_pendente: bool = false

# Controle contextual do olhar (Cursor + Janelas + Câmera + Sacadas Oculares)
var _olhar_atual: Vector2 = Vector2.ZERO
var _olhar_sacada: Vector2 = Vector2.ZERO
var _olhar_externo_alvo: Vector2 = Vector2.ZERO
var _timer_sacada_olhos: float = 2.0
var _timer_foco_janela: float = 0.0

# Postura corporal e movimentos autônomos de cabeça, pescoço e ombros
var _tempo_acumulado: float = 0.0
var _rotacao_cabeca_atual: Vector3 = Vector3.ZERO
var _rotacao_cabeca_alvo: Vector3 = Vector3.ZERO
var _timer_postura_idle: float = 3.5

# Interpolação suave de expressões faciais (nunca troca de forma brusca)
var _emocao_alvo: String = "neutra"
var _intensidade_emocao: float = 1.0
var _pesos_expressao_alvo: Dictionary = {}
var _pesos_expressao_atual: Dictionary = {}

const BLENDSHAPES_EXPRESSAO: Array[String] = [
    "mouthSmileLeft", "mouthSmileRight",
    "mouthDimpleLeft", "mouthDimpleRight",
    "cheekSquintLeft", "cheekSquintRight",
    "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "browDownLeft", "browDownRight",
    "eyeWideLeft", "eyeWideRight",
    "eyeSquintLeft", "eyeSquintRight",
    "mouthFrownLeft", "mouthFrownRight",
    "mouthPressLeft", "mouthPressRight",
]

const LISTA_VISEMAS: Array[String] = [
    "viseme_sil", "viseme_PP", "viseme_FF", "viseme_TH", "viseme_DD",
    "viseme_kk", "viseme_CH", "viseme_SS", "viseme_nn", "viseme_RR",
    "viseme_aa", "viseme_E", "viseme_I", "viseme_O", "viseme_U",
]

# Sincronização labial fonética e coarticulação em tempo real
var _falando: bool = false
var _energia_voz: float = 0.0
var _energia_voz_alvo: float = 0.0
var _abertura_boca_atual: float = 0.0
var _abertura_boca_alvo: float = 0.0
var _arredondamento_atual: float = 0.0
var _arredondamento_alvo: float = 0.0
var _enfase_sobrancelha_fala: float = 0.0
var _visema_principal_alvo: String = "viseme_sil"
var _visema_secundario_alvo: String = "viseme_sil"
var _peso_visema_principal: float = 0.0
var _peso_visema_secundario: float = 0.0
var _pesos_visemas_atuais: Dictionary = {}

var _tween_janela: Tween


func _ready() -> void:
    _inicializar_tabelas_pesos()
    _configurar_janela()
    _carregar_modelo_realista()
    _atualizar_governador_fps()

    if ws_client:
        ws_client.emocao_alterada.connect(_on_emocao_alterada)
        ws_client.fala_iniciada.connect(_on_fala_iniciada)
        ws_client.fala_chunk.connect(_on_fala_chunk)
        ws_client.fala_finalizada.connect(_on_fala_finalizada)
        ws_client.pensando_alterado.connect(_on_pensando_alterado)
        ws_client.modo_alterado.connect(_on_modo_alterado)
        ws_client.evento_recebido.connect(_on_evento_recebido)
        if ws_client.has_signal("estado_ia_alterado"):
            ws_client.estado_ia_alterado.connect(_on_estado_ia_alterado)
        if ws_client.has_signal("olhar_alterado"):
            ws_client.olhar_alterado.connect(_on_olhar_alterado)
        if ws_client.has_signal("atencao_desktop_recebida"):
            ws_client.atencao_desktop_recebida.connect(_on_atencao_desktop_recebida)
        if ws_client.has_signal("config_holograma_recebida"):
            ws_client.config_holograma_recebida.connect(_on_config_holograma_recebida)

    # Modo de diagnóstico visual: `godot --path gideon_avatar -- --captura`
    if "--captura" in OS.get_cmdline_user_args():
        _executar_captura_diagnostico()


func _executar_captura_diagnostico() -> void:
    Engine.max_fps = 60
    await get_tree().create_timer(4.0).timeout
    var img = get_viewport().get_texture().get_image()
    var destino = ProjectSettings.globalize_path("res://../dados/captura_avatar.png")
    img.save_png(destino)
    print("[Diagnostico] captura=", destino)
    print("[Diagnostico] fps=", Performance.get_monitor(Performance.TIME_FPS))
    print("[Diagnostico] vram_mb=", snappedf(Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0, 0.1))
    print("[Diagnostico] ram_estatica_mb=", snappedf(Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0, 0.1))
    print("[Diagnostico] draw_calls=", Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))
    print("[Diagnostico] objetos=", Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME))
    get_tree().quit()


func _inicializar_tabelas_pesos() -> void:
    for nome in BLENDSHAPES_EXPRESSAO:
        _pesos_expressao_alvo[nome] = 0.0
        _pesos_expressao_atual[nome] = 0.0
    for vis in LISTA_VISEMAS:
        _pesos_visemas_atuais[vis] = 0.0


func _configurar_janela() -> void:
    get_window().transparent = true
    get_viewport().transparent_bg = true
    var janela_id = DisplayServer.MAIN_WINDOW_ID
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_TRANSPARENT, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_BORDERLESS, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, true, janela_id)
    DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH, true, janela_id)


func _carregar_modelo_realista() -> void:
    var caminho_absoluto = ProjectSettings.globalize_path(caminho_modelo_glb)
    if not FileAccess.file_exists(caminho_absoluto) and not FileAccess.file_exists(caminho_modelo_glb):
        if mesh_avatar:
            _malhas_faciais.append(mesh_avatar)
        return

    var doc = GLTFDocument.new()
    var state = GLTFState.new()
    var err = doc.append_from_file(caminho_absoluto, state)
    if err != OK:
        if mesh_avatar:
            _malhas_faciais.append(mesh_avatar)
        return

    var cena_modelo = doc.generate_scene(state)
    if not cena_modelo:
        return

    if mesh_avatar:
        mesh_avatar.visible = false

    # Pivô centralizado para enquadrar rosto, pescoço e início dos ombros (busto holográfico de The Flash)
    _pivo_cabeca = Node3D.new()
    _pivo_cabeca.name = "PivoCabecaRealista"
    add_child(_pivo_cabeca)

    cena_modelo.position = Vector3(0.0, -1.565, 0.0)
    _pivo_cabeca.add_child(cena_modelo)

    _configurar_nos_modelo(cena_modelo)
    _definir_alvos_expressao("neutra", 1.0)
    print("[Gideon Avatar] Busto holográfico carregado com ", _malhas_faciais.size(), " malhas faciais e ", _ossos_idx.size(), " ossos articulados.")


func _configurar_nos_modelo(no: Node) -> void:
    if no is Skeleton3D:
        _esqueleto = no
        for nome_osso in ["Head", "Neck", "Spine2", "Spine1", "LeftShoulder", "RightShoulder", "LeftEye", "RightEye"]:
            var idx = _esqueleto.find_bone(nome_osso)
            if idx >= 0:
                _ossos_idx[nome_osso] = idx
                _ossos_rest[nome_osso] = _esqueleto.get_bone_rest(idx)

    if no is MeshInstance3D:
        var nome_no = no.name
        # Oculta óculos, roupa e parte inferior; o busto termina em fade volumétrico no pescoço/ombros
        if nome_no in ["Wolf3D_Glasses", "Wolf3D_Outfit_Bottom", "Wolf3D_Outfit_Footwear", "Wolf3D_Outfit_Top"]:
            no.visible = false
        else:
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

        mat_holo.set_shader_parameter("cor_holograma", Color(0.10, 0.64, 0.96, 0.86))
        mat_holo.set_shader_parameter("cor_fresnel", Color(0.42, 0.95, 1.0, 1.0))
        mat_holo.set_shader_parameter("forca_fresnel", 3.2)
        mat_holo.set_shader_parameter("densidade_scanlines", 340.0)
        mat_holo.set_shader_parameter("velocidade_scanlines", 1.1)
        mat_holo.set_shader_parameter("intensidade_scanlines", 0.045)
        mat_holo.set_shader_parameter("intensidade_pulso", 0.022)
        mat_holo.set_shader_parameter("intensidade_particulas", 0.06)
        mat_holo.set_shader_parameter("intensidade_distorcao", 0.008)
        mat_holo.set_shader_parameter("opacidade_geral", _opacidade_usuario)
        mat_holo.set_shader_parameter("progresso_materializacao", _progresso_materializacao)
        mat_holo.set_shader_parameter("corte_pescoco_min", -0.30)
        mat_holo.set_shader_parameter("corte_pescoco_max", -0.14)
        mat_holo.set_shader_parameter("topo_cabeca", 0.32)

        if mat_orig is BaseMaterial3D and mat_orig.albedo_texture:
            mat_holo.set_shader_parameter("textura_base", mat_orig.albedo_texture)
            if malha.name == "Wolf3D_Hair":
                # Cabelo desenhado ANTES do rosto: a pele (quase opaca) cobre as mechas de trás
                mat_holo.render_priority = -1
                mat_holo.set_shader_parameter("preservar_detalhes_rosto", 0.70)
            else:
                mat_holo.set_shader_parameter("preservar_detalhes_rosto", 0.74)

        malha.set_surface_override_material(i, mat_holo)
        _materiais_holograma.append(mat_holo)


func _process(delta: float) -> void:
    _tempo_acumulado += delta

    _atualizar_materializacao(delta)
    _atualizar_postura_e_ossos(delta)
    _atualizar_olhar_contextual(delta)
    _atualizar_expressoes_suaves(delta)
    _atualizar_piscar(delta)
    _atualizar_fala_multivisema(delta)
    _reportar_telemetria_periodica(delta)


func _atualizar_materializacao(delta: float) -> void:
    if abs(_progresso_materializacao - _alvo_materializacao) > 0.002:
        _progresso_materializacao = move_toward(_progresso_materializacao, _alvo_materializacao, delta * 1.8)
        for mat in _materiais_holograma:
            mat.set_shader_parameter("progresso_materializacao", _progresso_materializacao)
        if _progresso_materializacao <= 0.01 and _alvo_materializacao == 0.0:
            visible = false


func _atualizar_postura_e_ossos(delta: float) -> void:
    # 1. Respiração orgânica e flutuação sutil
    var fase_resp = _tempo_acumulado * 1.45
    var flutuacao_y = sin(fase_resp) * 0.0045
    position.y = flutuacao_y

    # 2. Alvos de postura da cabeça conforme estado da IA
    _timer_postura_idle -= delta
    if _timer_postura_idle <= 0.0:
        _timer_postura_idle = randf_range(3.2, 6.4)
        match estado_ia_atual:
            EstadoIA.LISTENING:
                _rotacao_cabeca_alvo = Vector3(deg_to_rad(1.8), deg_to_rad(randf_range(-1.5, 1.5)), deg_to_rad(2.4))
            EstadoIA.THINKING:
                _rotacao_cabeca_alvo = Vector3(deg_to_rad(-2.8), deg_to_rad(4.2), deg_to_rad(-1.5))
            EstadoIA.EXECUTING:
                _rotacao_cabeca_alvo = Vector3(
                    deg_to_rad(clamp(-_olhar_atual.y * 25.0, -4.0, 4.0)),
                    deg_to_rad(clamp(-_olhar_atual.x * 35.0, -6.0, 6.0)),
                    deg_to_rad(1.0)
                )
            _:
                _rotacao_cabeca_alvo = Vector3(
                    deg_to_rad(randf_range(-2.0, 2.2)),
                    deg_to_rad(randf_range(-4.5, 4.5)),
                    deg_to_rad(randf_range(-1.8, 1.8))
                )

    # Durante a fala, adiciona micro-acenos naturais acompanhando a prosódia da voz
    var aceno_fala_x = 0.0
    var aceno_fala_z = 0.0
    if _falando and _energia_voz > 0.05:
        aceno_fala_x = sin(_tempo_acumulado * 6.5) * deg_to_rad(1.8) * _energia_voz
        aceno_fala_z = cos(_tempo_acumulado * 4.2) * deg_to_rad(1.1) * _energia_voz

    # Influência sutil do olhar sobre a rotação da cabeça (a cabeça acompanha apenas 20% do olhar)
    var acompanhamento_olhar_y = -_olhar_atual.x * deg_to_rad(14.0)
    var acompanhamento_olhar_x = _olhar_atual.y * deg_to_rad(10.0)

    var alvo_combinado = Vector3(
        _rotacao_cabeca_alvo.x + aceno_fala_x + acompanhamento_olhar_x,
        _rotacao_cabeca_alvo.y + acompanhamento_olhar_y,
        _rotacao_cabeca_alvo.z + aceno_fala_z
    )

    _rotacao_cabeca_atual.x = lerp_angle(_rotacao_cabeca_atual.x, alvo_combinado.x, delta * 2.6)
    _rotacao_cabeca_atual.y = lerp_angle(_rotacao_cabeca_atual.y, alvo_combinado.y, delta * 2.6)
    _rotacao_cabeca_atual.z = lerp_angle(_rotacao_cabeca_atual.z, alvo_combinado.z, delta * 2.6)

    # 3. Se o esqueleto 3D estiver disponível, articula pescoço, cabeça e ombros anatomicamente
    if _esqueleto and _ossos_idx.has("Head") and _ossos_idx.has("Neck"):
        _aplicar_rotacao_osso_euler("Neck", _rotacao_cabeca_atual * 0.42)
        _aplicar_rotacao_osso_euler("Head", _rotacao_cabeca_atual * 0.58)

        var elevacao_ombro = sin(fase_resp) * deg_to_rad(0.85)
        if _ossos_idx.has("LeftShoulder"):
            _aplicar_rotacao_osso_euler("LeftShoulder", Vector3(0.0, 0.0, elevacao_ombro))
        if _ossos_idx.has("RightShoulder"):
            _aplicar_rotacao_osso_euler("RightShoulder", Vector3(0.0, 0.0, -elevacao_ombro))
    else:
        var alvo_no = _pivo_cabeca if _pivo_cabeca else self
        alvo_no.rotation = _rotacao_cabeca_atual


func _aplicar_rotacao_osso_euler(nome_osso: String, euler_offset: Vector3) -> void:
    if not _esqueleto or not _ossos_idx.has(nome_osso):
        return
    var idx: int = _ossos_idx[nome_osso]
    var rest: Transform3D = _ossos_rest[nome_osso]
    var q_offset = Quaternion.from_euler(euler_offset)
    _esqueleto.set_bone_pose_rotation(idx, rest.basis.get_rotation_quaternion() * q_offset)


func _atualizar_olhar_contextual(delta: float) -> void:
    if _timer_foco_janela > 0.0:
        _timer_foco_janela -= delta

    # Micro-sacadas oculares naturais
    _timer_sacada_olhos -= delta
    if _timer_sacada_olhos <= 0.0:
        _timer_sacada_olhos = randf_range(1.4, 3.6)
        var amp = 0.025 if estado_ia_atual in [EstadoIA.LISTENING, EstadoIA.SPEAKING] else 0.045
        _olhar_sacada = Vector2(randf_range(-amp, amp), randf_range(-amp * 0.7, amp * 0.7))

    var base_olhar: Vector2 = Vector2.ZERO
    match estado_ia_atual:
        EstadoIA.LISTENING, EstadoIA.SPEAKING:
            # Quando conversa com o Henry, mantém contato visual direto com a câmera
            base_olhar = Vector2.ZERO
        EstadoIA.THINKING:
            # Em processamento, desvia suavemente o olhar de forma reflexiva
            base_olhar = Vector2(0.08, 0.05)
        _:
            # Em Idle, Observing ou Executing, acompanha suavemente o cursor ou a janela ativa
            base_olhar = _olhar_externo_alvo

    var alvo_final = (base_olhar + _olhar_sacada).clamp(Vector2(-0.16, -0.11), Vector2(0.16, 0.11))
    _olhar_atual = _olhar_atual.lerp(alvo_final, delta * 6.0)

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


func _atualizar_expressoes_suaves(delta: float) -> void:
    var vel = 7.0 * delta
    for nome in BLENDSHAPES_EXPRESSAO:
        var alvo: float = float(_pesos_expressao_alvo.get(nome, 0.0))
        # Adiciona micro-ênfase de sobrancelha durante sílabas tônicas na fala
        if nome == "browInnerUp" and _falando:
            alvo = clamp(alvo + _enfase_sobrancelha_fala, 0.0, 0.45)
        var atual: float = float(_pesos_expressao_atual.get(nome, 0.0))
        if abs(atual - alvo) > 0.001:
            atual = lerp(atual, alvo, vel)
            _pesos_expressao_atual[nome] = atual
            _aplicar_blendshape(nome, atual)


func _atualizar_piscar(delta: float) -> void:
    if not _piscando:
        _timer_proximo_piscar -= delta
        if _timer_proximo_piscar <= 0.0:
            _piscando = true
            _tempo_piscar_atual = 0.0
            if _piscada_dupla_pendente:
                _piscada_dupla_pendente = false
                _timer_proximo_piscar = randf_range(3.0, 5.8)
            else:
                _piscada_dupla_pendente = randf() < 0.18
                _timer_proximo_piscar = 0.18 if _piscada_dupla_pendente else randf_range(2.4, 5.4)
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


func _atualizar_fala_multivisema(delta: float) -> void:
    var vel_labios = delta * 22.0
    if _falando and _energia_voz_alvo > 0.01:
        _energia_voz = lerp(_energia_voz, _energia_voz_alvo, vel_labios)
        _abertura_boca_atual = lerp(_abertura_boca_atual, _abertura_boca_alvo, vel_labios)
        _arredondamento_atual = lerp(_arredondamento_atual, _arredondamento_alvo, vel_labios)
    else:
        _energia_voz = lerp(_energia_voz, 0.0, delta * 15.0)
        _abertura_boca_atual = lerp(_abertura_boca_atual, 0.0, delta * 15.0)
        _arredondamento_atual = lerp(_arredondamento_atual, 0.0, delta * 15.0)
        _visema_principal_alvo = "viseme_sil"
        _visema_secundario_alvo = "viseme_sil"
        _peso_visema_principal = 0.0
        _peso_visema_secundario = 0.0
        _enfase_sobrancelha_fala = lerp(_enfase_sobrancelha_fala, 0.0, delta * 10.0)

    _aplicar_blendshape("jawOpen", _abertura_boca_atual)
    _aplicar_blendshape("mouthFunnel", _arredondamento_atual)

    for vis in LISTA_VISEMAS:
        var alvo_v = 0.0
        if vis == _visema_principal_alvo:
            alvo_v = _peso_visema_principal
        elif vis == _visema_secundario_alvo:
            alvo_v = _peso_visema_secundario
        var atual_v = float(_pesos_visemas_atuais.get(vis, 0.0))
        if abs(atual_v - alvo_v) > 0.002:
            atual_v = lerp(atual_v, alvo_v, vel_labios)
            _pesos_visemas_atuais[vis] = atual_v
            _aplicar_blendshape(vis, atual_v)


func _aplicar_blendshape(nome: String, peso: float) -> void:
    var valor = clamp(peso, 0.0, 1.0)
    for malha in _malhas_faciais:
        if malha and malha.mesh:
            var idx = malha.find_blend_shape_by_name(nome)
            if idx >= 0:
                malha.set_blend_shape_value(idx, valor)


func _definir_alvos_expressao(nome: String, intensidade: float) -> void:
    for ch in BLENDSHAPES_EXPRESSAO:
        _pesos_expressao_alvo[ch] = 0.0

    var k = clamp(intensidade, 0.2, 1.0)
    match nome:
        "amigavel", "satisfacao", "humor":
            _pesos_expressao_alvo["mouthSmileLeft"] = 0.22 * k
            _pesos_expressao_alvo["mouthSmileRight"] = 0.22 * k
            _pesos_expressao_alvo["mouthDimpleLeft"] = 0.10 * k
            _pesos_expressao_alvo["mouthDimpleRight"] = 0.10 * k
            _pesos_expressao_alvo["cheekSquintLeft"] = 0.11 * k
            _pesos_expressao_alvo["cheekSquintRight"] = 0.11 * k
            _pesos_expressao_alvo["browInnerUp"] = 0.06 * k
        "curiosidade", "duvida":
            _pesos_expressao_alvo["browInnerUp"] = 0.24 * k
            _pesos_expressao_alvo["browOuterUpRight"] = 0.18 * k
            _pesos_expressao_alvo["eyeSquintLeft"] = 0.08 * k
            _pesos_expressao_alvo["mouthSmileLeft"] = 0.05 * k
        "surpresa":
            _pesos_expressao_alvo["eyeWideLeft"] = 0.16 * k
            _pesos_expressao_alvo["eyeWideRight"] = 0.16 * k
            _pesos_expressao_alvo["browInnerUp"] = 0.30 * k
            _pesos_expressao_alvo["browOuterUpLeft"] = 0.18 * k
            _pesos_expressao_alvo["browOuterUpRight"] = 0.18 * k
        "concentracao":
            _pesos_expressao_alvo["browDownLeft"] = 0.20 * k
            _pesos_expressao_alvo["browDownRight"] = 0.20 * k
            _pesos_expressao_alvo["eyeSquintLeft"] = 0.10 * k
            _pesos_expressao_alvo["eyeSquintRight"] = 0.10 * k
        "preocupacao":
            _pesos_expressao_alvo["browInnerUp"] = 0.26 * k
            _pesos_expressao_alvo["browDownLeft"] = 0.12 * k
            _pesos_expressao_alvo["browDownRight"] = 0.12 * k
            _pesos_expressao_alvo["mouthFrownLeft"] = 0.08 * k
            _pesos_expressao_alvo["mouthFrownRight"] = 0.08 * k
        "neutra", _:
            _pesos_expressao_alvo["mouthSmileLeft"] = 0.07
            _pesos_expressao_alvo["mouthSmileRight"] = 0.07
            _pesos_expressao_alvo["browInnerUp"] = 0.04


func _atualizar_governador_fps() -> void:
    if modo_atual == ModoJanela.OCULTO:
        Engine.max_fps = 10
    elif estado_ia_atual in [EstadoIA.SPEAKING, EstadoIA.LISTENING, EstadoIA.THINKING, EstadoIA.EXECUTING]:
        Engine.max_fps = _fps_ativo
    else:
        Engine.max_fps = _fps_ocioso


func _reportar_telemetria_periodica(delta: float) -> void:
    _timer_telemetria -= delta
    if _timer_telemetria <= 0.0:
        _timer_telemetria = 2.0
        if ws_client and ws_client.has_method("enviar_evento"):
            ws_client.enviar_evento("telemetria_avatar", {
                "fps": int(Engine.get_frames_per_second()),
                "estado_ia": _nome_estado_ia,
                "emocao": _emocao_alvo,
                "visema_ativo": _visema_principal_alvo,
                "olhar_x": snappedf(_olhar_atual.x, 0.001),
                "olhar_y": snappedf(_olhar_atual.y, 0.001),
                "modo": ModoJanela.keys()[modo_atual].to_lower(),
            })


# ─── Sinais do WebSocket ──────────────────────────────────────

func _on_evento_recebido(tipo: String, dados: Dictionary) -> void:
    if tipo == "fala_chunk":
        _energia_voz_alvo = float(dados.get("intensidade", 0.0))
        _visema_principal_alvo = str(dados.get("visema", "viseme_aa" if _energia_voz_alvo > 0.05 else "viseme_sil"))
        _visema_secundario_alvo = str(dados.get("visema_secundario", "viseme_sil"))
        _peso_visema_principal = float(dados.get("peso_visema", _energia_voz_alvo * 0.55))
        _peso_visema_secundario = float(dados.get("peso_secundario", 0.0))
        _abertura_boca_alvo = float(dados.get("abertura_mandibula", _energia_voz_alvo * 0.22))
        _arredondamento_alvo = float(dados.get("arredondamento", 0.0))
        _enfase_sobrancelha_fala = float(dados.get("enfase_sobrancelha", 0.0))
    elif tipo == "ouvindo":
        var ouvindo_ativo = bool(dados.get("ativo", false))
        if ouvindo_ativo:
            _on_estado_ia_alterado("listening")


func _on_estado_ia_alterado(estado: String) -> void:
    _nome_estado_ia = estado.to_lower().strip_edges()
    match _nome_estado_ia:
        "listening":
            estado_ia_atual = EstadoIA.LISTENING
            _olhar_externo_alvo = Vector2.ZERO
            _rotacao_cabeca_alvo = Vector3(deg_to_rad(1.5), 0.0, deg_to_rad(2.2))
            _definir_alvos_expressao("curiosidade", 0.55)
        "thinking":
            estado_ia_atual = EstadoIA.THINKING
            _rotacao_cabeca_alvo = Vector3(deg_to_rad(-2.5), deg_to_rad(3.5), 0.0)
            _definir_alvos_expressao("concentracao", 0.65)
        "speaking":
            estado_ia_atual = EstadoIA.SPEAKING
            _olhar_externo_alvo = Vector2.ZERO
        "executing":
            estado_ia_atual = EstadoIA.EXECUTING
            _definir_alvos_expressao("concentracao", 0.75)
        "observing":
            estado_ia_atual = EstadoIA.OBSERVING
            _definir_alvos_expressao("curiosidade", 0.50)
        "error":
            estado_ia_atual = EstadoIA.ERROR
            _definir_alvos_expressao("preocupacao", 0.80)
        "idle", _:
            estado_ia_atual = EstadoIA.IDLE
            _definir_alvos_expressao(_emocao_alvo, _intensidade_emocao)

    _atualizar_governador_fps()


func _on_olhar_alterado(alvo: String, x: float, y: float) -> void:
    if alvo == "usuario":
        _olhar_externo_alvo = Vector2.ZERO
        return
    if _timer_foco_janela <= 0.0:
        _olhar_externo_alvo = Vector2(x, y)


func _on_atencao_desktop_recebida(_evento: String, _titulo: String, x: float, y: float) -> void:
    _olhar_externo_alvo = Vector2(x, y)
    _timer_foco_janela = 3.0
    if estado_ia_atual == EstadoIA.IDLE:
        estado_ia_atual = EstadoIA.OBSERVING
        _atualizar_governador_fps()


func _on_config_holograma_recebida(dados: Dictionary) -> void:
    var janela_id = DisplayServer.MAIN_WINDOW_ID
    if dados.has("opacidade"):
        _opacidade_usuario = clamp(float(dados["opacidade"]), 0.2, 1.0)
    if dados.has("opacidade_delta"):
        _opacidade_usuario = clamp(_opacidade_usuario + float(dados["opacidade_delta"]), 0.25, 1.0)
    for mat in _materiais_holograma:
        mat.set_shader_parameter("opacidade_geral", _opacidade_usuario)

    if dados.has("escala"):
        _escala_usuario = clamp(float(dados["escala"]), 0.6, 1.6)
        scale = Vector3.ONE * _escala_usuario
    if dados.has("escala_delta"):
        _escala_usuario = clamp(_escala_usuario + float(dados["escala_delta"]), 0.6, 1.6)
        scale = Vector3.ONE * _escala_usuario

    if dados.has("click_through"):
        DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH, bool(dados["click_through"]), janela_id)
    if dados.has("sempre_visivel"):
        DisplayServer.window_set_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP, bool(dados["sempre_visivel"]), janela_id)
    if dados.has("fps_ativo"):
        _fps_ativo = clampi(int(dados["fps_ativo"]), 24, 120)
    if dados.has("fps_ocioso"):
        _fps_ocioso = clampi(int(dados["fps_ocioso"]), 10, 60)
    if dados.has("posicao_x") and dados.has("posicao_y"):
        mover_janela_suave(Vector2i(int(dados["posicao_x"]), int(dados["posicao_y"])))

    _atualizar_governador_fps()


func _on_emocao_alterada(nome: String, intensidade: float) -> void:
    _emocao_alvo = nome
    _intensidade_emocao = intensidade
    _definir_alvos_expressao(nome, intensidade)


func _on_fala_iniciada(_texto: String) -> void:
    _falando = true
    _on_estado_ia_alterado("speaking")


func _on_fala_chunk(_texto: String) -> void:
    _falando = true


func _on_fala_finalizada() -> void:
    _falando = false
    _energia_voz_alvo = 0.0
    _abertura_boca_alvo = 0.0
    _arredondamento_alvo = 0.0
    _on_estado_ia_alterado("idle")


func _on_pensando_alterado(ativo: bool) -> void:
    if ativo:
        _on_estado_ia_alterado("thinking")
    elif not _falando:
        _on_estado_ia_alterado("idle")


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
            var pos = Vector2i(tela_tamanho.x - 320, tela_tamanho.y - 440)
            mover_janela_suave(pos, Vector2i(300, 380), 0.7)

        "conversa", "centro_direita":
            modo_atual = ModoJanela.CONVERSA
            var pos = Vector2i(tela_tamanho.x - 480, tela_tamanho.y - 720)
            mover_janela_suave(pos, Vector2i(450, 650), 0.6)

        "foco", "centro":
            modo_atual = ModoJanela.FOCO
            var pos = Vector2i((tela_tamanho.x - 600) / 2, (tela_tamanho.y - 850) / 2)
            mover_janela_suave(pos, Vector2i(600, 850), 0.9)

        "operacional":
            modo_atual = ModoJanela.OPERACIONAL
            var pos = Vector2i(tela_tamanho.x - 380, 60)
            mover_janela_suave(pos, Vector2i(340, 460), 0.7)

        "canto_esquerdo":
            var pos = Vector2i(40, tela_tamanho.y - 440)
            mover_janela_suave(pos, Vector2i(300, 380), 0.7)

        "canto_superior_direito":
            var pos = Vector2i(tela_tamanho.x - 320, 40)
            mover_janela_suave(pos, Vector2i(300, 380), 0.7)

        "oculto":
            modo_atual = ModoJanela.OCULTO
            _alvo_materializacao = 0.0
            _atualizar_governador_fps()
            return

    visible = true
    _alvo_materializacao = 1.0
    _atualizar_governador_fps()
