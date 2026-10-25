import unreal

mel = unreal.MaterialEditingLibrary
mat_path = "/Game/Gideon/Materials/M_GideonHologram"
mat = unreal.EditorAssetLibrary.load_asset(mat_path)

if not mat:
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MaterialFactoryNew()
    mat = tools.create_asset("M_GideonHologram", "/Game/Gideon/Materials", unreal.Material, factory)

mat.modify()
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
mat.set_editor_property("two_sided", True)

# Clear old expressions
mel.delete_all_material_expressions(mat)

# 1. Texture parameter for facial skin / hair / eyes diffuse
tex_param = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, -800, -200)
tex_param.set_editor_property("parameter_name", "BaseColorTexture")
default_tex = unreal.EditorAssetLibrary.load_asset("/Game/Gideon/gideon/Textures/baseColor1")
if default_tex:
    tex_param.set_editor_property("texture", default_tex)

# 2. Cor Holograma (STAR Labs Cyan)
col_hologram = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -800, 100)
col_hologram.set_editor_property("parameter_name", "CorHolograma")
col_hologram.set_editor_property("default_value", unreal.LinearColor(0.08, 0.68, 0.98, 1.0))

# 3. PreservarDefinicaoFacial scalar
fac_def = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -800, 300)
fac_def.set_editor_property("parameter_name", "PreservarDefinicaoFacial")
fac_def.set_editor_property("default_value", 0.85)

# 4. Multiply Tex * Hologram Color
mul_tex_holo = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -500, -100)
mel.connect_material_expressions(tex_param, "", mul_tex_holo, "A")
mel.connect_material_expressions(col_hologram, "", mul_tex_holo, "B")

# Boost constant 1.8
boost_const = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -500, 50)
boost_const.set_editor_property("r", 1.8)
mul_boost = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -350, -50)
mel.connect_material_expressions(mul_tex_holo, "", mul_boost, "A")
mel.connect_material_expressions(boost_const, "", mul_boost, "B")

# 5. Lerp(CorHolograma, BoostedFacial, PreservarDefinicaoFacial)
lerp_face = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -200, 0)
mel.connect_material_expressions(col_hologram, "", lerp_face, "A")
mel.connect_material_expressions(mul_boost, "", lerp_face, "B")
mel.connect_material_expressions(fac_def, "", lerp_face, "Alpha")

# 6. Fresnel Rim (Electric cyan rim)
fresnel_exp = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -800, 500)
fresnel_exp.set_editor_property("parameter_name", "FresnelExponent")
fresnel_exp.set_editor_property("default_value", 2.6)

fresnel = mel.create_material_expression(mat, unreal.MaterialExpressionFresnel, -500, 450)
mel.connect_material_expressions(fresnel_exp, "", fresnel, "Exponent")

col_fresnel = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -500, 600)
col_fresnel.set_editor_property("parameter_name", "CorFresnel")
col_fresnel.set_editor_property("default_value", unreal.LinearColor(0.52, 0.95, 1.0, 1.0))

mul_rim = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -300, 500)
mel.connect_material_expressions(fresnel, "", mul_rim, "A")
mel.connect_material_expressions(col_fresnel, "", mul_rim, "B")

# Rim intensity boost (2.2)
rim_boost = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 650)
rim_boost.set_editor_property("r", 2.2)
mul_rim_boost = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -150, 550)
mel.connect_material_expressions(mul_rim, "", mul_rim_boost, "A")
mel.connect_material_expressions(rim_boost, "", mul_rim_boost, "B")

# Add Facial + Rim
add_emissive = mel.create_material_expression(mat, unreal.MaterialExpressionAdd, 0, 100)
mel.connect_material_expressions(lerp_face, "", add_emissive, "A")
mel.connect_material_expressions(mul_rim_boost, "", add_emissive, "B")

# 7. Materialization Progress
prog_mat = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, 0, 350)
prog_mat.set_editor_property("parameter_name", "ProgressoMaterializacao")
prog_mat.set_editor_property("default_value", 1.0)

final_emissive = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, 150, 150)
mel.connect_material_expressions(add_emissive, "", final_emissive, "A")
mel.connect_material_expressions(prog_mat, "", final_emissive, "B")

# Connect Emissive Color
mel.connect_material_property(final_emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

# 8. Opacity = OpacidadeGeral * (0.8 + Fresnel * 0.2) * ProgressoMaterializacao
opac_param = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -300, 800)
opac_param.set_editor_property("parameter_name", "OpacidadeGeral")
opac_param.set_editor_property("default_value", 0.94)

fresnel_scale = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 950)
fresnel_scale.set_editor_property("r", 0.2)
mul_fresnel_opac = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -150, 900)
mel.connect_material_expressions(fresnel, "", mul_fresnel_opac, "A")
mel.connect_material_expressions(fresnel_scale, "", mul_fresnel_opac, "B")

base_opac_const = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -150, 1000)
base_opac_const.set_editor_property("r", 0.8)
add_opac = mel.create_material_expression(mat, unreal.MaterialExpressionAdd, 0, 900)
mel.connect_material_expressions(mul_fresnel_opac, "", add_opac, "A")
mel.connect_material_expressions(base_opac_const, "", add_opac, "B")

mul_opac_final = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, 150, 850)
mel.connect_material_expressions(opac_param, "", mul_opac_final, "A")
mel.connect_material_expressions(add_opac, "", mul_opac_final, "B")

mul_opac_prog = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, 300, 850)
mel.connect_material_expressions(mul_opac_final, "", mul_opac_prog, "A")
mel.connect_material_expressions(prog_mat, "", mul_opac_prog, "B")

mel.connect_material_property(mul_opac_prog, "", unreal.MaterialProperty.MP_OPACITY)

# Layout and compile
mel.layout_material_expressions(mat)
mel.recompile_material(mat)
unreal.EditorAssetLibrary.save_loaded_asset(mat)
unreal.log("=== M_GideonHologram SHADER GRAPH BUILT & COMPILED SUCCESSFULLY ===")
