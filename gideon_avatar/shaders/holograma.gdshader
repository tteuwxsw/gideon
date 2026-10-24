shader_type spatial;
render_mode depth_draw_always, cull_back, unshaded;

// Passagem 1 (Hardware Z-Buffer 100% Ativo no Rosto, Crânio e Olhos):
// Renderiza toda a região sólida do holograma (visibilidade >= 0.99) na fila opaca com
// Z-buffer de hardware completo, eliminando qualquer vazamento da cavidade bucal ou órbitas
// e sem nenhum pontilhado (dither). A faixa de transição suave do pescoço é desenhada na Passagem 2.

uniform sampler2D textura_base : source_color, hint_default_white;
uniform float preservar_detalhes_rosto : hint_range(0.0, 1.0) = 0.82;
// 0 = Cabeça/Pele Holográfica (The Flash Time Vault), 1 = Olhos Luminosos, 2 = Dentes
uniform int modo_componente : hint_range(0, 2) = 0;

uniform vec4 cor_holograma : source_color = vec4(0.10, 0.68, 0.98, 0.95);
uniform vec4 cor_fresnel : source_color = vec4(0.55, 0.96, 1.0, 1.0);
uniform float forca_fresnel : hint_range(0.5, 8.0) = 2.9;

uniform float densidade_scanlines : hint_range(50.0, 800.0) = 380.0;
uniform float velocidade_scanlines : hint_range(0.1, 10.0) = 1.1;
uniform float intensidade_scanlines : hint_range(0.0, 0.5) = 0.042;

uniform float velocidade_pulso : hint_range(0.0, 5.0) = 1.15;
uniform float intensidade_pulso : hint_range(0.0, 0.3) = 0.022;
uniform float intensidade_particulas : hint_range(0.0, 0.5) = 0.055;
uniform float intensidade_distorcao : hint_range(0.0, 0.2) = 0.006;

uniform float opacidade_geral : hint_range(0.0, 1.0) = 0.96;
uniform float progresso_materializacao : hint_range(0.0, 1.0) = 1.0;
uniform float corte_pescoco_min : hint_range(-1.0, 1.0) = -0.128;
uniform float corte_pescoco_max : hint_range(-1.0, 1.0) = -0.052;
uniform float topo_cabeca : hint_range(-1.0, 1.0) = 0.22;

varying float v_altura_local;
varying vec3 v_pos_local;

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

void vertex() {
	v_altura_local = (MODEL_MATRIX * vec4(VERTEX, 1.0)).y;
	v_pos_local = VERTEX;

	float gatilho_glitch = step(0.994, sin(TIME * 3.7) * cos(TIME * 2.3));
	float desvio_x = sin(VERTEX.y * 45.0 + TIME * 24.0) * intensidade_distorcao * gatilho_glitch * 0.012;
	VERTEX.x += desvio_x;
}

void fragment() {
	float limite_mat = mix(corte_pescoco_min - 0.05, topo_cabeca, progresso_materializacao);
	float fade_busto = smoothstep(corte_pescoco_min, corte_pescoco_max, v_altura_local);
	float fade_materializacao = 1.0 - smoothstep(limite_mat - 0.05, limite_mat + 0.015, v_altura_local);
	float visibilidade = fade_busto * fade_materializacao;

	// A região de fade suave na base do pescoço (< 0.998) é delegada à Passagem 2 (blend_mix suave)
	if (visibilidade < 0.998) {
		discard;
	}

	vec4 tex = texture(textura_base, UV);
	float luminancia = dot(tex.rgb, vec3(0.299, 0.587, 0.114));

	vec3 dir_key = normalize(vec3(0.18, 0.34, 0.92));
	vec3 dir_fill = normalize(vec3(-0.38, 0.20, 0.78));
	float diff_key = clamp(dot(NORMAL, dir_key), 0.0, 1.0);
	float diff_fill = clamp(dot(NORMAL, dir_fill), 0.0, 1.0) * 0.45;
	float sombreamento_3d = mix(0.54, 1.15, clamp(diff_key + diff_fill, 0.0, 1.0));

	vec3 half_vec = normalize(dir_key + VIEW);
	float spec = pow(clamp(dot(NORMAL, half_vec), 0.0, 1.0), 30.0) * 0.22;

	float dot_vn = clamp(dot(VIEW, NORMAL), 0.0, 1.0);
	float fresnel = pow(1.0 - dot_vn, forca_fresnel);

	float scanline = sin((SCREEN_UV.y * densidade_scanlines) + (TIME * velocidade_scanlines));
	scanline = mix(1.0 - intensidade_scanlines, 1.0, (scanline + 1.0) * 0.5);

	vec3 cor_final;

	if (modo_componente == 1) {
		// OLHOS HOLOGRÁFICOS EXPRESSIVOS (Íris ciano-luminosa detalhada, pupila profunda e reflexo corneano)
		float dist_centro = distance(UV, vec2(0.5, 0.5));
		float mascara_iris = 1.0 - smoothstep(0.18, 0.215, dist_centro);
		float mascara_pupila = 1.0 - smoothstep(0.065, 0.088, dist_centro);
		float reflexo_cornea = smoothstep(0.58, 0.88, luminancia) * mascara_iris;

		vec3 esclera_holo = mix(vec3(0.18, 0.65, 0.94), vec3(0.62, 0.94, 1.0), clamp(sombreamento_3d * 0.85, 0.0, 1.0));
		float fibras_iris = clamp((luminancia - 0.08) * 2.6, 0.0, 1.0);
		vec3 iris_holo = mix(vec3(0.03, 0.36, 0.72), vec3(0.42, 0.96, 1.0), fibras_iris);
		vec3 pupila_holo = vec3(0.01, 0.07, 0.16);

		vec3 olho_base = mix(esclera_holo, iris_holo, mascara_iris);
		olho_base = mix(olho_base, pupila_holo, mascara_pupila * (1.0 - reflexo_cornea));
		olho_base += vec3(0.88, 0.99, 1.0) * (reflexo_cornea * 0.95 + spec * 1.4);
		cor_final = olho_base * scanline;
	} else if (modo_componente == 2) {
		cor_final = mix(cor_holograma.rgb * 0.50, cor_fresnel.rgb * 0.82, clamp(luminancia, 0.0, 1.0)) * sombreamento_3d;
	} else {
		// CABEÇA E BUSTO ESCULPIDO DE LUZ (GIDEON - THE FLASH / STAR LABS TIME VAULT)
		vec2 uv_rosto = (UV - vec2(0.50, 0.385)) / vec2(0.19, 0.165);
		float mascara_feicoes = 1.0 - smoothstep(0.68, 0.98, length(uv_rosto));

		float lum_pele_lisa = 0.72;
		float lum_efetiva = mix(lum_pele_lisa, luminancia, mascara_feicoes);

		vec2 uv_labios = (UV - vec2(0.50, 0.485)) / vec2(0.085, 0.042);
		float mascara_labios = 1.0 - smoothstep(0.55, 1.0, length(uv_labios));

		vec3 tom_esculpido = mix(
			vec3(0.04, 0.34, 0.66),
			vec3(0.34, 0.87, 1.0),
			smoothstep(0.12, 0.88, lum_efetiva)
		);
		tom_esculpido = mix(tom_esculpido, tom_esculpido * vec3(0.76, 0.88, 1.08), mascara_labios * 0.42);

		vec3 pele_holografica = mix(
			cor_holograma.rgb * 0.78,
			tom_esculpido,
			preservar_detalhes_rosto
		) * sombreamento_3d + vec3(spec * 0.55, spec * 0.92, spec * 1.15);

		vec2 grade_part = floor(vec2(UV.x * 55.0, (UV.y - TIME * 0.06) * 55.0));
		float semente_part = hash21(grade_part);
		float particula = step(0.988, semente_part) * fresnel * intensidade_particulas;

		float feixe_vertical = 0.92 + 0.08 * sin(v_pos_local.x * 36.0 + TIME * 1.4);
		float pulso = sin(TIME * velocidade_pulso) * intensidade_pulso;

		cor_final = mix(pele_holografica, cor_fresnel.rgb, fresnel * 0.50) * scanline * feixe_vertical;
		cor_final += cor_fresnel.rgb * (pulso + particula);
	}

	ALBEDO = cor_final;
	EMISSION = cor_final * 0.28 + (cor_fresnel.rgb * fresnel * 0.26);
}
