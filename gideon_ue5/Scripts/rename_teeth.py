import json
import unreal

with open('c:/Users/henry/Documents/jarvis/gideon_avatar/modelos/gideon.glb', 'rb') as f:
    f.seek(12)
    chunk_len = int.from_bytes(f.read(4), 'little')
    f.seek(20)
    data = json.loads(f.read(chunk_len).decode('utf-8'))
    target_names = data['meshes'][3]['extras']['targetNames']

teeth = unreal.EditorAssetLibrary.load_asset("/Game/Gideon/gideon/SkeletalMeshes/Wolf3D_Teeth")
if teeth:
    teeth.modify()
    renamed_count = 0
    for mt in teeth.morph_targets:
        curr_name = mt.get_name()
        if "gideon_mesh_3_" in curr_name:
            parts = curr_name.split("_")
            idx = int(parts[3])
            if 0 <= idx < len(target_names):
                real_name = target_names[idx]
                try:
                    mt.rename(real_name)
                    renamed_count += 1
                except Exception as e:
                    unreal.log_warning(f"Could not rename {curr_name} to {real_name}: {e}")
    
    unreal.log(f"Renamed {renamed_count} teeth morph targets.")
    saved = unreal.EditorAssetLibrary.save_loaded_asset(teeth)
    unreal.log(f"Teeth saved: {saved}")
