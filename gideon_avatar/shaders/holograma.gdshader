shader_type spatial;
render_mode blend_add, depth_draw_opaque, cull_back, unshaded;

// Parâmetros configuráveis no editor Godot
uniform vec4 cor_holograma : source_color = vec4(0.0, 0.6, 1.0, 0.7);
uniform vec4 cor_fresnel : source_color = vec4(0.1, 0.95, 1.0, 1.0);
uniform float forca_fresnel : hint_range(0.5, 8.0) = 2.5;

uniform float densidade_scanlines : hint_range(10.0, 500.0) = 140.0;
uniform float velocidade_scanlines : hint_range(0.1, 10.0) = 1.8;
uniform float intensidade_scanlines : hint_range(0.0, 1.0) = 0.25;

uniform float velocidade_pulso : hint_range(0.0, 5.0) = 1.2;
uniform float intensidade_pulso : hint_range(0.0, 0.5) = 0.08;

uniform float opacidade_geral : hint_range(0.0, 1.0) = 0.85;

void fragment() {
    // 1. Cálculo do Efeito Fresnel (brilho nas bordas do modelo)
    float dot_vn = dot(VIEW, NORMAL);
    float fresnel = pow(1.0 - clamp(dot_vn, 0.0, 1.0), forca_fresnel);

    // 2. Scanlines holográficas móveis
    float scanline = sin((SCREEN_UV.y * densidade_scanlines) + (TIME * velocidade_scanlines));
    scanline = (scanline + 1.0) * 0.5; // Normaliza para [0, 1]
    scanline = mix(1.0 - intensidade_scanlines, 1.0, scanline);

    // 3. Pulso sutil de energia digital
    float pulso = sin(TIME * velocidade_pulso) * intensidade_pulso;

    // 4. Composição de cor
    vec3 cor_final = mix(cor_holograma.rgb, cor_fresnel.rgb, fresnel) * scanline;
    cor_final += cor_fresnel.rgb * pulso;

    // 5. Transparência: centro mais translúcido, bordas brilhantes
    float alpha_base = cor_holograma.a * scanline;
    float alpha_fresnel = fresnel * cor_fresnel.a;
    float alpha_final = clamp(alpha_base + alpha_fresnel, 0.0, 1.0) * opacidade_geral;

    ALBEDO = cor_final;
    EMISSION = cor_final * 1.5; // Emissão para efeito Bloom/Glow no WorldEnvironment
    ALPHA = alpha_final;
}
