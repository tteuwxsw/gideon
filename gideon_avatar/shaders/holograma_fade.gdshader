shader_type spatial;
render_mode blend_mix, cull_back, unshaded;

// Passagem 2 (Transição Alpha 100% Contínua na Base do Pescoço e Materialização):
// Utiliza exatamente a mesma equação fotométrica da Passagem 1 para que a fronteira
// entre a região sólida (>= 0.998) e o gradiente de dissolução (< 0.998) seja invisível.

uniform vec4 cor_holograma : source_color = vec4(0.10, 0.68, 0.98, 0.95);
uniform vec4 cor_fresnel : source_color = vec4(0.55, 0.96, 1.0, 1.0);
uniform float forca_fresnel : hint_range(0.5, 8.0) = 2.9;
uniform float preservar_detalhes_rosto : hint_range(0.0, 1.0) = 0.82;

uniform float densidade_scanlines : hint_range(50.0, 800.0) = 380.0;
uniform float velocidade_scanlines : hint_range(0.1, 10.0) = 1.1;
uniform float intensidade_scanlines : hint_range(0.0, 0.5) = 0.042;
uniform float velocidade_pulso : hint_range(0.0, 5.0) = 1.15;
uniform float intensidade_pulso : hint_range(0.0, 0.3) = 0.022;
uniform float intensidade_distorcao : hint_range(0.0, 0.2) = 0.006;
uniform float opacidade_geral : hint_range(0.0, 1.0) = 0.96;
uniform float progresso_materializacao : hint_range(0.0, 1.0) = 1.0;
uniform float corte_pescoco_min : hint_range(-1.0, 1.0) = -0.128;
uniform float corte_pescoco_max : hint_range(-1.0, 1.0) = -0.052;
uniform float topo_cabeca : hint_range(-1.0, 1.0) = 0.22;

varying float v_altura_local;
varying vec3 v_pos_local;

void vertex() {
	v_altura_local = (MODEL_MATRIX * vec4(VERTEX, 1.0)).y;
	v_pos_local = VERTEX;

	float gatilho_glitch = step(0.994, sin(TIME * 3.7) * cos(TIME * 2.3));
	float desvio_x = sin(VERTEX.y * 45.0 + TIME * 24.0) * intensidade_distorcao * gatilho_glitch * 0.012;
	VERTEX.x += desvio_x;
}

void fragment() {
	float limite_mat = mix(corte_pescoco_min - 0.05, topo_cabeca, progresso_materializacao);
	if (v_altura_local < corte_pescoco_min || v_altura_local > limite_mat + 0.02) {
		discard;
	}

	float fade_busto = smoothstep(corte_pescoco_min, corte_pescoco_max, v_altura_local);
	float fade_materializacao = 1.0 - smoothstep(limite_mat - 0.05, limite_mat + 0.015, v_altura_local);
	float visibilidade = fade_busto * fade_materializacao;

	if (visibilidade >= 0.998) {
		discard;
	}

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

	// Mesma equação exata da pele lisa da Passagem 1 (lum_pele_lisa = 0.72)
	vec3 tom_esculpido = mix(
		vec3(0.04, 0.34, 0.66),
		vec3(0.34, 0.87, 1.0),
		smoothstep(0.12, 0.88, 0.72)
	);
	vec3 pele_holografica = mix(
		cor_holograma.rgb * 0.78,
		tom_esculpido,
		preservar_detalhes_rosto
	) * sombreamento_3d + vec3(spec * 0.55, spec * 0.92, spec * 1.15);

	float feixe_vertical = 0.92 + 0.08 * sin(v_pos_local.x * 36.0 + TIME * 1.4);
	float pulso = sin(TIME * velocidade_pulso) * intensidade_pulso;
	vec3 cor_final = mix(pele_holografica, cor_fresnel.rgb, fresnel * 0.50) * scanline * feixe_vertical;
	cor_final += cor_fresnel.rgb * pulso;

	float borda_materializacao = smoothstep(limite_mat - 0.035, limite_mat, v_altura_local) * fade_materializacao;
	cor_final += cor_fresnel.rgb * (borda_materializacao * 0.85);

	ALBEDO = cor_final;
	EMISSION = cor_final * 0.28 + (cor_fresnel.rgb * fresnel * 0.26);
	ALPHA = clamp(visibilidade, 0.0, 1.0);
}
