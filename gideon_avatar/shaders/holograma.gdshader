shader_type spatial;
render_mode blend_mix, depth_prepass_alpha, cull_back, unshaded;

// Textura original realista do modelo 3D (pele, olhos, íris, lábios, sobrancelhas)
uniform sampler2D textura_base : source_color, hint_default_white;
uniform float preservar_detalhes_rosto : hint_range(0.0, 1.0) = 0.72;

// Cores da projeção holográfica (Time Vault / STAR Labs)
uniform vec4 cor_holograma : source_color = vec4(0.06, 0.58, 0.95, 0.72);
uniform vec4 cor_fresnel : source_color = vec4(0.35, 0.96, 1.0, 1.0);
uniform float forca_fresnel : hint_range(0.5, 8.0) = 3.5;

// Scanlines holográficas sutis de alta definição
uniform float densidade_scanlines : hint_range(10.0, 600.0) = 260.0;
uniform float velocidade_scanlines : hint_range(0.1, 10.0) = 1.4;
uniform float intensidade_scanlines : hint_range(0.0, 1.0) = 0.09;

// Pulso de energia vital
uniform float velocidade_pulso : hint_range(0.0, 5.0) = 1.2;
uniform float intensidade_pulso : hint_range(0.0, 0.5) = 0.03;

// Transparência e dissolução suave na base do pescoço
uniform float opacidade_geral : hint_range(0.0, 1.0) = 0.68;
uniform float corte_pescoco_min : hint_range(1.0, 1.7) = 1.43;
uniform float corte_pescoco_max : hint_range(1.0, 1.7) = 1.49;

varying float v_altura_local;

void vertex() {
    v_altura_local = VERTEX.y;
}

void fragment() {
    // 1. Leitura da textura realista do rosto (olhos, pupilas, lábios, sobrancelhas)
    vec4 tex = texture(textura_base, UV);
    float luminancia = dot(tex.rgb, vec3(0.299, 0.587, 0.114));
    // Realça contraste de olhos, cílios, sobrancelhas e contorno labial
    float contraste = smoothstep(0.05, 0.95, luminancia);

    // 2. Iluminação volumétrica suave para destacar relevo 3D (nariz, maçãs do rosto, lábios)
    vec3 dir_luz = normalize(vec3(0.2, 0.35, 0.9));
    float luz_direcional = clamp(dot(NORMAL, dir_luz), 0.0, 1.0);
    float sombreamento_3d = mix(0.45, 1.15, luz_direcional);

    // 3. Efeito Fresnel (halo luminoso nas bordas do rosto e cabelo)
    float dot_vn = clamp(dot(VIEW, NORMAL), 0.0, 1.0);
    float fresnel = pow(1.0 - dot_vn, forca_fresnel);

    // 4. Scanlines holográficas finas
    float scanline = sin((SCREEN_UV.y * densidade_scanlines) + (TIME * velocidade_scanlines));
    scanline = (scanline + 1.0) * 0.5;
    scanline = mix(1.0 - intensidade_scanlines, 1.0, scanline);

    // 5. Pulso sutil de energia
    float pulso = sin(TIME * velocidade_pulso) * intensidade_pulso;

    // 6. Fusão entre realismo humano e projeção holográfica azul da Gideon
    vec3 base_holografica = cor_holograma.rgb * mix(0.35, 1.35, contraste) * sombreamento_3d;
    vec3 rosto_humanizado = mix(base_holografica, tex.rgb * vec3(0.55, 0.92, 1.25) * sombreamento_3d, preservar_detalhes_rosto * 0.55);

    vec3 cor_final = mix(rosto_humanizado, cor_fresnel.rgb, fresnel * 0.75) * scanline;
    cor_final += cor_fresnel.rgb * pulso;

    // 7. Dissolução suave na base do pescoço (flutuação holográfica no ar)
    float fade_pescoco = smoothstep(corte_pescoco_min, corte_pescoco_max, v_altura_local);

    // 8. Opacidade final
    float alpha_final = clamp(mix(cor_holograma.a, 1.0, fresnel), 0.0, 1.0) * opacidade_geral * fade_pescoco * tex.a;

    ALBEDO = cor_final;
    EMISSION = cor_final * 0.3 + (cor_fresnel.rgb * fresnel * 0.4);
    ALPHA = alpha_final;
}
