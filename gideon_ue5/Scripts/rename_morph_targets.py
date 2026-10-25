import json
import unreal

# Load the glTF metadata to get exact target names
with open('c:/Users/henry/Documents/jarvis/gideon_avatar/modelos/gideon.glb', 'rb') as f:
    f.seek(12)
    chunk_len = int.from_bytes(f.read(4), 'little')
    f.seek(20)
    data = json.loads(f.read(chunk_len).decode('utf-8'))
    target_names = data['meshes'][2]['extras']['targetNames']

unreal.log(f"Target names loaded: {len(target_names)}")

head = unreal.EditorAssetLibrary.load_asset("/Game/Gideon/gideon/SkeletalMeshes/Wolf3D_Head")
if head:
    head.modify()
    renamed_count = 0
    for mt in head.morph_targets:
        curr_name = mt.get_name()
        # format: gideon_mesh_2_{index}_MorphTarget
        if "gideon_mesh_2_" in curr_name:
            parts = curr_name.split("_")
            idx = int(parts[3])
            if 0 <= idx < len(target_names):
                real_name = target_names[idx]
                try:
                    mt.rename(real_name)
                    renamed_count += 1
                except Exception as e:
                    unreal.log_warning(f"Could not rename {curr_name} to {real_name}: {e}")
    
    unreal.log(f"Renamed {renamed_count} morph targets.")
    saved = unreal.EditorAssetLibrary.save_loaded_asset(head)
    unreal.log(f"Asset saved: {saved}")

    # Verify
    new_names = [m.get_name() for m in head.morph_targets]
    unreal.log(f"First 10 new names: {new_names[:10]}")
    unreal.log(f"Has mouthSmileLeft: {'mouthSmileLeft' in new_names}")
    unreal.log(f"Has viseme_aa: {'viseme_aa' in new_names}")
