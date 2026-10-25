import unreal

mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
eal = unreal.EditorAssetLibrary
master_mat = eal.load_asset("/Game/Gideon/Materials/M_GideonHologram")

def create_mi(name, texture_path):
    pkg_path = f"/Game/Gideon/Materials/{name}"
    if eal.does_asset_exist(pkg_path):
        mi = eal.load_asset(pkg_path)
    else:
        factory = unreal.MaterialInstanceConstantFactoryNew()
        mi = tools.create_asset(name, "/Game/Gideon/Materials", unreal.MaterialInstanceConstant, factory)
    
    mi.modify()
    mel.set_material_instance_parent(mi, master_mat)
    tex = eal.load_asset(texture_path)
    if tex:
        mel.set_material_instance_texture_parameter_value(mi, "BaseColorTexture", tex)
    
    eal.save_loaded_asset(mi)
    unreal.log(f"Material instance created/configured: {name} -> {mi}")
    return mi

mi_head = create_mi("MI_Gideon_Head", "/Game/Gideon/gideon/Textures/baseColor1")
mi_hair = create_mi("MI_Gideon_Hair", "/Game/Gideon/gideon/Textures/baseColor")
mi_eye = create_mi("MI_Gideon_Eye", "/Game/Gideon/gideon/Textures/baseColor2")
mi_teeth = create_mi("MI_Gideon_Teeth", "/Game/Gideon/gideon/Textures/Wolf3D_Teeth")
mi_torso = create_mi("MI_Gideon_Torso", "/Game/Gideon/gideon/Textures/outfit-f-indiangym-01-v2-top-D")

# Assign to Skeletal Meshes
def assign_mat_to_skm(skm_path, mi):
    skm = eal.load_asset(skm_path)
    if skm:
        skm.modify()
        for i in range(len(skm.materials)):
            skm.materials[i].material_interface = mi
        eal.save_loaded_asset(skm)
        unreal.log(f"Assigned {mi.get_name()} to {skm_path}")

assign_mat_to_skm("/Game/Gideon/gideon/SkeletalMeshes/Wolf3D_Head", mi_head)
assign_mat_to_skm("/Game/Gideon/gideon/SkeletalMeshes/Wolf3D_Hair", mi_hair)
assign_mat_to_skm("/Game/Gideon/gideon/SkeletalMeshes/Wolf3D_Teeth", mi_teeth)
assign_mat_to_skm("/Game/Gideon/gideon/SkeletalMeshes/Wolf3D_Outfit_Top", mi_torso)
assign_mat_to_skm("/Game/Gideon/gideon/SkeletalMeshes/EyeLeft", mi_eye)
assign_mat_to_skm("/Game/Gideon/gideon/SkeletalMeshes/EyeRight", mi_eye)
unreal.log("=== ALL HOLOGRAPHIC MATERIAL INSTANCES ASSIGNED SUCCESSFULLY ===")
