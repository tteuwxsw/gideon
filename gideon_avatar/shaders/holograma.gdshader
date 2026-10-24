shader_type spatial;
render_mode blend_mix, depth_prepass_alpha, cull_back, unshaded;

// Textura original realista do modelo 3D (pele, poros, lábios, sobrancelhas, cabelo)
uniform sampler2D textura_base : source_color, hint_default_white;
uniform float preservar_detalhes_rosto : hint_range(0.0, 1.0) = 0.82;

// Paleta STAR Labs / Time Vault (tons suaves de azul e ciano sem esconder o rosto)
uniform vec4 cor_holograma : source_color = vec4(0.10, 0.64, 0.96, 0.86);
uniform vec4 cor_fresnel : source_color = vec4(0.42, 0.95, 1.0, 1.0);
uniform float forca_fresnel : hint_range(0.5, 8.0) = 3.2;

// Linhas de varredura (scanlines) muito sutis de alta definição
uniform float densidade_scanlines : hint_range(50.0, 800.0) = 340.0;
uniform float velocidade_scanlines : hint_range(0.1, 10.0) = 1.1;
uniform float intensidade_scanlines : hint_range(0.0, 0.5) = 0.045;

// Pulso de energia vital e feixe volumétrico
uniform float velocidade_pulso : hint_range(0.0, 5.0) = 1.1;
uniform float intensidade_pulso : hint_range(0.0, 0.3) = 0.022;
uniform float intensidade_particulas : hint_range(0.0, 0.5) = 0.06;
uniform float intensidade_distorcao : hint_range(0.0, 0.2) = 0.008;

// Transparência controlada, materialização e dissolução suave no busto/ombros
uniform float opacidade_geral : hint_range(0.0, 1.0) = 0.84;
uniform float progresso_materializacao : hint_range(0.0, 1.0) = 1.0;
// Limites em espaço de mundo (o rosto fica em torno de y=0; o topo da cabeça em ~+0.2)
uniform float corte_pescoco_min : hint_range(-1.0, 1.0) = -0.30;
uniform float corte_pescoco_max : hint_range(-1.0, 1.0) = -0.14;
uniform float topo_cabeca : hint_range(-1.0, 1.0) = 0.32;

varying float v_altura_local;
varying vec3 v_pos_local;

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

void vertex() {
    // Altura em espaço de mundo: independe da escala/offset interno do GLB (Ready Player Me usa nós escalados)
    v_altura_local = (MODEL_MATRIX * vec4(VERTEX, 1.0)).y;
    v_pos_local = VERTEX;

    // Micro-distorção eletrônica ocasional e extremamente sutil
    float gatilho_glitch = step(0.992, sin(TIME * 3.7) * cos(TIME * 2.3));
    float desvio_x = sin(VERTEX.y * 45.0 + TIME * 24.0) * intensidade_distorcao * gatilho_glitch * 0.015;
    VERTEX.x += desvio_x;
}

void fragment() {
    // 1. Leitura da textura humana realista (pele, contorno labial, sobrancelhas, cílios)
    vec4 tex = texture(textura_base, UV);
    float luminancia = dot(tex.rgb, vec3(0.299, 0.587, 0.114));
    float contraste_facial = smoothstep(0.04, 0.96, luminancia);

    // 2. Iluminação 3D realista de 3 pontos (Key Light + Fill Light + Specular suave na pele/lábios)
    vec3 dir_key = normalize(vec3(0.22, 0.38, 0.89));
    vec3 dir_fill = normalize(vec3(-0.45, 0.15, 0.65));
    float diff_key = clamp(dot(NORMAL, dir_key), 0.0, 1.0);
    float diff_fill = clamp(dot(NORMAL, dir_fill), 0.0, 1.0) * 0.35;
    float sombreamento_3d = mix(0.54, 1.18, clamp(diff_key + diff_fill, 0.0, 1.0));

    // Brilho especular suave para dar vida à pele, nariz, maçãs do rosto e lábios
    vec3 half_vec = normalize(dir_key + VIEW);
    float spec = pow(clamp(dot(NORMAL, half_vec), 0.0, 1.0), 28.0) * 0.16;

    // 3. Efeito Fresnel (bordas levemente iluminadas em ciano)
    float dot_vn = clamp(dot(VIEW, NORMAL), 0.0, 1.0);
    float fresnel = pow(1.0 - dot_vn, forca_fresnel);

    // 4. Linhas de varredura (scanlines) muito sutis
    float scanline = sin((SCREEN_UV.y * densidade_scanlines) + (TIME * velocidade_scanlines));
    scanline = mix(1.0 - intensidade_scanlines, 1.0, (scanline + 1.0) * 0.5);

    // 5. Pequenas partículas luminosas ascendentes discretas nas bordas
    vec2 grade_part = floor(vec2(UV.x * 55.0, (UV.y - TIME * 0.06) * 55.0));
    float semente_part = hash21(grade_part);
    float particula = step(0.986, semente_part) * fresnel * intensidade_particulas;

    // 6. Feixe de projeção volumétrica simulada na base dos ombros/pescoço
    float feixe_vertical = 0.88 + 0.12 * sin(v_pos_local.x * 38.0 + TIME * 1.5);

    // 7. Equilíbrio entre realismo humano e projeção holográfica azul/ciano de The Flash
    vec3 base_holografica = cor_holograma.rgb * mix(0.42, 1.28, contraste_facial) * sombreamento_3d;
    vec3 pele_holografica = tex.rgb * vec3(0.76, 0.96, 1.16) * sombreamento_3d + vec3(spec * 0.65, spec * 0.90, spec);
    vec3 rosto_realista = mix(base_holografica, pele_holografica, preservar_detalhes_rosto);

    float pulso = sin(TIME * velocidade_pulso) * intensidade_pulso;
    vec3 cor_final = mix(rosto_realista, cor_fresnel.rgb, fresnel * 0.52) * scanline * feixe_vertical;
    cor_final += cor_fresnel.rgb * (pulso + particula);

    // 8. Dissolução volumétrica no busto e animação de materialização
    float fade_busto = smoothstep(corte_pescoco_min, corte_pescoco_max, v_altura_local);
    float limite_mat = mix(corte_pescoco_min - 0.05, topo_cabeca, progresso_materializacao);
    float fade_materializacao = 1.0 - smoothstep(limite_mat - 0.06, limite_mat + 0.02, v_altura_local);
    float borda_materializacao = smoothstep(limite_mat - 0.04, limite_mat, v_altura_local) * fade_materializacao;
    cor_final += cor_fresnel.rgb * borda_materializacao * 0.85;

    float alpha_final = clamp(mix(cor_holograma.a, 0.98, fresnel * 0.6), 0.0, 1.0)
        * opacidade_geral
        * fade_busto
        * fade_materializacao
        * tex.a;

    ALBEDO = cor_final;
    EMISSION = cor_final * 0.24 + (cor_fresnel.rgb * fresnel * 0.30);
    ALPHA = alpha_final;
}
