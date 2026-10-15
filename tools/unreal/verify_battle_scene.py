"""Read-only UE battle readback; never loads/saves a level or starts an engine.

Full Editor must already have L_TutorialBattle open. The parent task owns native
frame capture. Ordinary Python --plan checks the pinned handoff and expected
camera projection only; it is not native engine execution evidence.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import struct
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'analysis/unreal/battle-inputs'
PROJECT = ROOT / 'clients/unreal5 5.8/Hczs.uproject'
MAP = '/Game/Recovered/Battle/Maps/L_TutorialBattle'
DATA = '/Game/Recovered/Battle/BattleSceneAssets'
FRAME = BASE / 'battle-native-frame.png'
sys.path.insert(0, str(ROOT / 'tools/unreal'))
from import_recovered_assets import read_glb, glb_summary


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def write(name, report):
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / name).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def minus(a, b):
    return [x - y for x, y in zip(a, b)]


def normalized(value):
    length = math.sqrt(dot(value, value))
    if length <= 1e-12 or not math.isfinite(length):
        raise ValueError('Degenerate camera basis')
    return [x / length for x in value]


def project(point, camera):
    """Perspective UV uses the *actual* UE camera right/up/forward vectors.

    UV is inside the camera's constrained aspect-ratio rectangle, not an
    arbitrary editor viewport with possible bars. X=0 is left, Y=0 is top.
    """
    delta = minus(point, camera['position'])
    depth, right, up = [dot(delta, camera[key]) for key in ('forward', 'right', 'up')]
    if depth <= 1e-6:
        return dict(world=point, depth=depth, camera_right=right, camera_up=up,
                    uv=None, inside=False, behind_camera=True)
    tangent_x = math.tan(math.radians(camera['horizontal_fov']) / 2)
    tangent_y = tangent_x / camera['aspect_ratio']
    uv = [.5 + right / (2 * depth * tangent_x), .5 - up / (2 * depth * tangent_y)]
    return dict(world=point, depth=depth, camera_right=right, camera_up=up,
                uv=uv, inside=all(0 <= v <= 1 for v in uv), behind_camera=False)


def converted(position):
    x, y, z = position
    return [-x * 100, z * 100, y * 100]


def input_plan():
    payload = (BASE / 'manifest.json').read_bytes()
    manifest = json.loads(payload)
    if manifest['schema'] != 'hczs-unreal-battle-inputs-v1' or manifest['map'] != MAP:
        raise ValueError('Unsupported battle input manifest')
    layout_bytes = (BASE / manifest['layout_file']).read_bytes()
    if sha(layout_bytes) != manifest['layout_sha256']:
        raise ValueError('Layout hash changed')
    rows = {}
    for row in manifest['assets']:
        path = (BASE / row['file']).resolve()
        if not path.is_relative_to(BASE.resolve()):
            raise ValueError('Staged input escapes battle directory')
        original = (ROOT / row['source_file']).resolve()
        if not original.is_relative_to(ROOT.resolve()):
            raise ValueError('Recovered source escapes project')
        data = path.read_bytes()
        if sha(data) != row['sha256'] or len(data) != row['bytes']:
            raise ValueError('Staged input changed: ' + row['id'])
        if sha(original.read_bytes()) != row['source_sha256']:
            raise ValueError('Recovered source changed: ' + row['id'])
        document = read_glb(data)
        if glb_summary(document) != row['geometry']:
            raise ValueError('Input geometry inventory changed')
        rows[row['id']] = dict(record=row, document=document)
    if set(rows) != {'stage', 'player', 'enemy', 'weapon'}:
        raise ValueError('Incomplete battle handoff')
    mapping_bytes = (BASE / 'animation-mapping.json').read_bytes()
    mapping = json.loads(mapping_bytes)
    for filename, expected in mapping['source_pins'].items():
        if sha((ROOT / filename).read_bytes()) != expected:
            raise ValueError('Original animation mapping changed: ' + filename)
    return dict(manifest_sha256=sha(payload), mapping_sha256=sha(mapping_bytes),
                manifest=manifest, layout=json.loads(layout_bytes), rows=rows, mapping=mapping)


def planned_projection(plan):
    layout = plan['layout']
    spec = layout['camera']
    position, target = converted(spec['inspection_position']), converted(spec['inspection_target'])
    forward = normalized(minus(target, position))
    # Roll=0 for the inspection camera. This is source metadata math only.
    right = normalized([-forward[1], forward[0], 0])
    up = [forward[1] * right[2] - forward[2] * right[1],
          forward[2] * right[0] - forward[0] * right[2],
          forward[0] * right[1] - forward[1] * right[0]]
    hfov = math.degrees(2 * math.atan(math.tan(math.radians(spec['vertical_fov']) / 2) * spec['aspect_ratio']))
    camera = dict(position=position, forward=forward, right=right, up=up,
                  horizontal_fov=hfov, vertical_fov=spec['vertical_fov'], aspect_ratio=spec['aspect_ratio'])
    projections = {side: project(converted(layout[side]['position']), camera) for side in ('player', 'enemy')}
    if not all(row['inside'] for row in projections.values()):
        raise ValueError('Planned combatant origins outside primary camera')
    if projections['player']['uv'][0] >= projections['enemy']['uv'][0]:
        raise ValueError('Planned camera projects own side to wrong side')
    return dict(schema='hczs-battle-projection-plan-v1', evidence='ordinary Python source-metadata math',
                native_editor_executed=False, original_projection_runtime_verified=False,
                original_tutorial_stage_recovered=False, manifest_sha256=plan['manifest_sha256'],
                camera=camera, combatant_origins=projections,
                left_right_basis='camera right dot displacement / positive camera-forward depth',
                frame_path=FRAME.as_posix(), frame_class='UE5.8 Development Editor native game frame; not a packaged-platform test',
                planned_frame_dimensions=[1600, 900], passed=True)


def transform_row(transform):
    q = transform.rotation
    return dict(translation=vec(transform.translation), rotation=[q.x, q.y, q.z, q.w],
                scale=vec(transform.scale3d))


def obj_path(obj):
    return obj.get_path_name() if obj is not None else None


def safe_property(obj, key):
    try:
        value = obj.get_editor_property(key)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
    except Exception as exc:
        return dict(unavailable=str(exc))


def content_hashes():
    folder = PROJECT.parent / 'Content/Recovered/Battle'
    return {path.relative_to(folder).as_posix(): sha(path.read_bytes())
            for path in sorted(folder.rglob('*')) if path.is_file()}


def frame_row():
    record = dict(path=FRAME.as_posix(), exists=FRAME.exists(), captured_by_this_script=False,
                  visually_reviewed=False, frame_class='UE5.8 Development Editor native game frame')
    if FRAME.exists():
        payload = FRAME.read_bytes()
        if len(payload) < 24 or payload[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Expected native frame path is not a PNG')
        record.update(sha256=sha(payload), dimensions=list(struct.unpack_from('>II', payload, 16)), bytes=len(payload))
    return record


def material_readback(unreal, interface):
    if interface is None:
        return dict(path=None, available=False)
    result = dict(path=obj_path(interface), class_name=interface.get_class().get_name(), available=True)
    effective = {}
    current = interface
    chain = []
    while current is not None:
        row = dict(path=obj_path(current), class_name=current.get_class().get_name())
        if isinstance(current, unreal.MaterialInstance):
            overrides = current.get_editor_property('base_property_overrides')
            fields = {}
            for key, native in (('blend_mode', 'BlendMode'), ('two_sided', 'TwoSided'),
                                ('shading_model', 'ShadingModel'), ('opacity_mask_clip_value', 'OpacityMaskClipValue')):
                flag = safe_property(overrides, 'bOverride_' + native)
                value = safe_property(overrides, native)
                fields[key] = dict(override=flag, value=value)
                if flag is True and key not in effective:
                    effective[key] = value
            row['base_property_overrides'] = fields
            current = current.get_editor_property('parent')
        elif isinstance(current, unreal.Material):
            for key in ('blend_mode', 'two_sided', 'shading_model', 'opacity_mask_clip_value'):
                value = safe_property(current, key)
                row[key] = value
                effective.setdefault(key, value)
            current = None
        else:
            row['unavailable'] = 'Unsupported material interface subclass'
            current = None
        chain.append(row)
        if len(chain) > 16:
            raise ValueError('Material parent chain too long')
    result.update(parent_chain=chain, effective_properties=effective,
                  original_neox_shader_verified=False)
    return result


def source_material_name(name):
    return re.sub('[^A-Za-z0-9_]', '_', name)


def alpha_checks(readback, source):
    """Compare staged display-material semantics, not original NeoX shaders."""
    actual = readback.get('effective_properties', {})
    mode = source.get('alphaMode', 'OPAQUE')
    expected = {'OPAQUE':'BLEND_OPAQUE', 'MASK':'BLEND_MASKED', 'BLEND':'BLEND_TRANSLUCENT'}[mode]
    rows = [dict(name='staged_alpha_mode', passed=expected in str(actual.get('blend_mode')),
                 actual=actual.get('blend_mode'), expected=expected),
            dict(name='staged_two_sided', passed=actual.get('two_sided') is source.get('doubleSided',False),
                 actual=actual.get('two_sided'), expected=source.get('doubleSided',False))]
    if mode == 'MASK':
        clip = actual.get('opacity_mask_clip_value')
        expected_clip = source.get('alphaCutoff', .5)
        rows.append(dict(name='staged_alpha_cutoff', passed=isinstance(clip,(int,float)) and abs(clip-expected_clip)<1e-5,
                         actual=clip, expected=expected_clip))
    if 'KHR_materials_unlit' in source.get('extensions', {}):
        rows.append(dict(name='staged_unlit_reference', passed='MSM_UNLIT' in str(actual.get('shading_model')),
                         actual=actual.get('shading_model'), expected='MSM_UNLIT'))
    return rows


def pose_readback(unreal, mesh, animation, document):
    options = unreal.AnimPoseEvaluationOptions()
    for key, value in dict(evaluation_type=unreal.AnimDataEvalType.COMPRESSED,
                           should_retarget=False, extract_root_motion=False,
                           incorporate_root_motion_into_pose=True, optional_skeletal_mesh=mesh).items():
        options.set_editor_property(key, value)
    source_names = [document['nodes'][node]['name'].replace(' ', '-') for node in document['skins'][0]['joints']]
    anchors = [name for name in ('bip001', 'bip001-pelvis', 'bip001-head', 'bip001-l-foot', 'bip001-r-foot',
                                'bip001-prop1') if name in source_names]
    if not anchors:
        anchors = source_names[:6]
    result = dict(animation=obj_path(animation), evaluation='COMPRESSED', retarget=False, samples=[],
                  pose_correspondence_to_original_acl_verified=False)
    previous = None
    maximum_motion = 0.
    for time in (0., animation.get_play_length() * .37, animation.get_play_length() * .71):
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_time(animation, time, options)
        if not unreal.AnimPoseExtensions.is_valid(pose):
            raise RuntimeError('Native compressed AnimPose invalid')
        actual_names = {str(name) for name in unreal.AnimPoseExtensions.get_bone_names(pose)}
        if not set(source_names).issubset(actual_names):
            raise RuntimeError('Native pose lost original skeletal bone names: ' + str(set(source_names) - actual_names))
        bones = {name: transform_row(unreal.AnimPoseExtensions.get_bone_pose(pose, name, unreal.AnimPoseSpaces.WORLD))
                 for name in source_names}
        flattened = [number for record in bones.values() for values in record.values() for number in values]
        if not all(math.isfinite(number) for number in flattened):
            raise RuntimeError('Native pose contains non-finite transforms')
        if previous is not None:
            maximum_motion = max(maximum_motion, max(abs(a - b) for a, b in zip(previous, flattened)))
        previous = flattened
        result['samples'].append(dict(time_seconds=time, actual_bone_count=len(actual_names),
                                      anchors={name: bones[name] for name in anchors}))
    result['sampled_pose_changes'] = maximum_motion > 1e-5
    result['maximum_component_transform_delta'] = maximum_motion
    return result


def verify_native():
    plan = input_plan()
    import unreal
    result = dict(schema='hczs-battle-native-readback-v1', read_only=True, checks=[], warnings=[],
                  manifest_sha256=plan['manifest_sha256'], original_tutorial_stage_recovered=False,
                  original_hit_timing_verified=False, original_neox_shaders_verified=False,
                  native_platforms_verified=False, gameplay_loop_verified=False,
                  frame=frame_row(), passed=False)
    before = content_hashes()
    def check(name, condition, detail=None):
        result['checks'].append(dict(name=name, passed=bool(condition), detail=detail))
    try:
        result['engine_version'] = unreal.SystemLibrary.get_engine_version()
        result['project'] = unreal.Paths.get_project_file_path()
        check('converted_project_and_engine', Path(result['project']).resolve() == PROJECT.resolve()
              and result['engine_version'].startswith('5.8.'))
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        actual_map = world.get_path_name().split('.')[0] if world else None
        result['map'] = actual_map
        if actual_map != MAP:
            raise RuntimeError('Open the dedicated battle map before readback; this script does not load/change maps')
        actor_list = list(unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors())
        mode = world.get_world_settings().get_editor_property('default_game_mode')
        result['game_mode'] = obj_path(mode)
        check('native_battle_mode', result['game_mode'] == '/Script/Hczs.HczsBattleMode')
        check('dynamic_no_baked_lighting', world.get_world_settings().get_editor_property('force_no_precomputed_lighting') is True)
        tags = {**plan['layout']['actor_tags'], 'camera':plan['layout']['camera']['primary_tag'],
                'presentation':'HCZSBattlePresentation'}
        tagged = {}
        result['tag_inventory'] = {}
        for key, tag in tags.items():
            matches = [actor for actor in actor_list if tag in {str(value) for value in actor.get_editor_property('tags')}]
            result['tag_inventory'][tag] = [obj_path(actor) for actor in matches]
            check('one_actor_' + tag, len(matches) == 1)
            if len(matches) != 1:
                raise RuntimeError('Required actor tag missing/ambiguous: ' + tag)
            tagged[key] = matches[0]
        adapters = [actor for actor in actor_list if actor.get_actor_label() == 'HCZSBattleCoordinateAdapter']
        check('one_coordinate_adapter', len(adapters) == 1)
        if len(adapters) != 1:
            raise RuntimeError('Coordinate adapter missing/ambiguous')
        adapter = adapters[0]
        result['coordinate_adapter'] = transform_row(adapter.get_actor_transform())
        result['coordinate_adapter']['mobility'] = str(adapter.get_editor_property('root_component').get_editor_property('mobility'))
        check('fixed_static_coordinate_adapter', 'STATIC' in result['coordinate_adapter']['mobility'])
        scale = vec(adapter.get_actor_scale3d())
        check('one_explicit_x_reflection', all(abs(a - b) < 1e-6 for a,b in zip(scale, [-1,1,1])), scale)
        r = adapter.get_actor_rotation()
        check('no_extra_global_rotation', abs(r.pitch) + abs(r.yaw) + abs(r.roll) < 1e-5)
        scene = tagged['presentation'].get_editor_property('SceneAssets')
        if obj_path(scene) not in (DATA, DATA + '.BattleSceneAssets'):
            raise RuntimeError('Presentation references another scene DataAsset')
        check('scene_manifest_hash', scene.get_editor_property('SourceManifestSHA256') == plan['manifest_sha256'])
        check('scene_mapping_hash', scene.get_editor_property('SourceMappingSHA256') == plan['mapping_sha256'])
        check('tutorial_stage_not_claimed_recovered', scene.get_editor_property('bOriginalTutorialStageRecovered') is False)
        check('supported_combatants', scene.get_editor_property('SupportedEncounterId') == 'tutorial-5000'
              and scene.get_editor_property('PlayerId') == '1' and scene.get_editor_property('EnemyId') == '991')
        queues = {str(key): list(value.get_editor_property('Clips')) for key,value in scene.get_editor_property('CardAnimationQueues').items()}
        skills = {str(key): str(value) for key,value in scene.get_editor_property('EnemySkillClips').items()}
        check('card_source_mapping', queues == plan['mapping']['card_animation_queues'], queues)
        check('enemy_source_mapping', skills == plan['mapping']['enemy_skill_clips'], skills)
        camera_component = tagged['camera'].get_component_by_class(unreal.CameraComponent)
        if not camera_component:
            raise RuntimeError('Tagged primary camera has no CameraComponent')
        camera = dict(position=vec(camera_component.get_world_transform().translation),
                      forward=vec(camera_component.get_forward_vector()), right=vec(camera_component.get_right_vector()),
                      up=vec(camera_component.get_up_vector()), horizontal_fov=camera_component.get_editor_property('field_of_view'),
                      aspect_ratio=camera_component.get_editor_property('aspect_ratio'),
                      constrain_aspect_ratio=camera_component.get_editor_property('constrain_aspect_ratio'))
        camera['vertical_fov'] = math.degrees(2 * math.atan(math.tan(math.radians(camera['horizontal_fov'])/2) / camera['aspect_ratio']))
        camera['rotation'] = transform_row(camera_component.get_world_transform())['rotation']
        result['camera'] = camera
        check('orthonormal_camera_axes', all(abs(dot(camera[key], camera[key])-1) < 1e-5 for key in ('forward','right','up'))
              and all(abs(dot(camera[a],camera[b]))<1e-5 for a,b in (('forward','right'),('forward','up'),('right','up'))))
        check('constrained_primary_aspect', camera['constrain_aspect_ratio'] is True and abs(camera['aspect_ratio']-16/9)<1e-6)
        components = {}
        result['combatants'] = {}
        for side, field in (('player','Player'), ('enemy','Enemy')):
            actor = tagged[side]
            component = actor.get_component_by_class(unreal.SkeletalMeshComponent)
            if not component:
                raise RuntimeError('Native combatant has no SkeletalMeshComponent')
            components[side] = component
            mesh = scene.get_editor_property(field + 'Mesh')
            clips = {str(key):value for key,value in scene.get_editor_property(field + 'Animations').items()}
            doc = plan['rows'][side]['document']
            expected_clips = {source['name']:doc['accessors'][source['samplers'][0]['input']]['max'][0]
                              for source in doc['animations']}
            check(side + '_exact_animation_keys', set(clips) == set(expected_clips))
            check(side + '_exact_mesh_reference', component.get_skinned_asset() == mesh)
            check(side + '_source_bone_count', component.get_num_bones() == len(doc['skins'][0]['joints']))
            check(side + '_under_coordinate_adapter', actor.get_attach_parent_actor() == adapter)
            row = dict(actor=obj_path(actor), transform=transform_row(actor.get_actor_transform()),
                       component_transform=transform_row(component.get_world_transform()), mesh=obj_path(mesh),
                       animation_refs={}, materials=[], bone_count=component.get_num_bones(),
                       origin_projection=project(vec(actor.get_actor_location()), camera))
            for name, animation in clips.items():
                duration = animation.get_play_length() if isinstance(animation, unreal.AnimSequence) else None
                check(side + '_animation_' + name, duration is not None and name in expected_clips
                      and abs(duration-expected_clips[name])<1e-4
                      and animation.get_editor_property('skeleton') == mesh.get_editor_property('skeleton'))
                row['animation_refs'][name] = dict(path=obj_path(animation), duration=duration,
                                                   skeleton=obj_path(animation.get_editor_property('skeleton')))
            idle = plan['layout'][side]['normal_idle']
            anim_data = component.get_editor_property('animation_data')
            check(side + '_saved_source_looping_idle', anim_data.get_editor_property('AnimToPlay') == clips[idle]
                  and anim_data.get_editor_property('bSavedLooping') is True
                  and anim_data.get_editor_property('bSavedPlaying') is True)
            row['idle_pose'] = pose_readback(unreal, mesh, clips[idle], doc)
            check(side + '_native_idle_moves', row['idle_pose']['sampled_pose_changes'])
            # Current sockets expose the actual component transform including
            # negative parent scale. Original pose is also evaluated separately.
            if side == 'player':
                points = {name:vec(component.get_socket_location(name)) for name in
                          ('bip001-head','bip001-l-foot','bip001-r-foot','bip001-prop1')}
                row['current_bone_projections'] = {name:project(point,camera) for name,point in points.items()}
                foot = [(a+b)/2 for a,b in zip(points['bip001-l-foot'],points['bip001-r-foot'])]
                delta = minus(points['bip001-head'], foot)
                right_height = dot(delta,camera['right'])
                up_height = dot(delta,camera['up'])
                row['current_head_foot_lean_degrees'] = math.degrees(math.atan2(right_height,up_height))
                row['lean_note'] = 'Native source idle stance; no corrective rotation imposed by this verifier'
            for index in range(component.get_num_materials()):
                interface = component.get_material(index)
                material = material_readback(unreal, interface)
                material['slot'] = index
                candidates = [source for source in doc['materials'] if interface and
                              source_material_name(source['name']) == interface.get_name()]
                check(side + '_material_source_identity_' + str(index), len(candidates) == 1)
                material['staged_source_material'] = candidates[0] if len(candidates)==1 else None
                if len(candidates)==1:
                    material['staged_semantic_checks'] = alpha_checks(material,candidates[0])
                    for item in material['staged_semantic_checks']:
                        check(side + '_material_' + str(index) + '_' + item['name'],item['passed'],item)
                row['materials'].append(material)
            origin, extent, radius = unreal.SystemLibrary.get_component_bounds(component)
            row['bounds'] = dict(origin=vec(origin), extent=vec(extent), sphere_radius=radius)
            corners = [[a+s*b for a,b,s in zip(vec(origin),vec(extent),signs)] for signs in itertools.product((-1,1),repeat=3)]
            corner_uvs = [project(point,camera)['uv'] for point in corners]
            row['bounds_camera_uv'] = dict(minimum=[min(p[i] for p in corner_uvs if p is not None) for i in (0,1)],
                                                maximum=[max(p[i] for p in corner_uvs if p is not None) for i in (0,1)])
            row['bounds_center_projection'] = project(vec(origin),camera)
            result['combatants'][side] = row
        player, enemy = (result['combatants'][side] for side in ('player','enemy'))
        check('primary_camera_projects_player_left_enemy_right',
              player['origin_projection']['inside'] and enemy['origin_projection']['inside']
              and player['origin_projection']['uv'][0] < enemy['origin_projection']['uv'][0],
              dict(player=player['origin_projection'], enemy=enemy['origin_projection']))
        check('visible_bounds_centers_preserve_side', player['bounds_center_projection']['inside']
              and enemy['bounds_center_projection']['inside']
              and player['bounds_center_projection']['uv'][0] < enemy['bounds_center_projection']['uv'][0])
        weapon = tagged['weapon'].get_component_by_class(unreal.StaticMeshComponent)
        parent = weapon.get_attach_parent() if weapon else None
        socket = str(weapon.get_attach_socket_name()) if weapon else None
        check('weapon_attached_to_original_prop_bone', parent == components['player'] and socket == 'bip001-prop1')
        result['weapon'] = dict(mesh=obj_path(weapon.get_editor_property('static_mesh')),
            parent_component=obj_path(parent), socket=socket, world_transform=transform_row(weapon.get_world_transform()),
            materials=[material_readback(unreal,weapon.get_material(i)) for i in range(weapon.get_num_materials())],
            native_bind_type_semantics_verified=False, native_bone_aabb_verified=False)
        stage = plan['rows']['stage']
        stage_doc = stage['document']
        mesh_names = {source_material_name(mesh['name']):mesh for mesh in stage_doc['meshes']}
        stage_instances = []
        for actor in actor_list:
            component = actor.get_component_by_class(unreal.StaticMeshComponent)
            if not component or actor == tagged['weapon']:
                continue
            mesh = component.get_editor_property('static_mesh')
            if not mesh or mesh.get_name() not in mesh_names:
                continue
            ancestors = []
            current = actor.get_attach_parent_actor()
            while current is not None:
                ancestors.append(current.get_path_name())
                if len(ancestors)>32:
                    raise RuntimeError('Scene actor parent chain too long')
                current = current.get_attach_parent_actor()
            source = mesh_names[mesh.get_name()]
            check('stage_under_adapter_' + actor.get_actor_label(), adapter.get_path_name() in ancestors)
            check('stage_mesh_source_hash_' + actor.get_actor_label(),
                unreal.EditorAssetLibrary.get_metadata_tag(mesh,'HczsBattleInputSHA256') == stage['record']['sha256'])
            check('stage_material_slot_count_' + actor.get_actor_label(),
                  component.get_num_materials() == len(source['primitives']))
            record = dict(actor=obj_path(actor), mesh=obj_path(mesh), transform=transform_row(actor.get_actor_transform()),
                          mobility=str(component.get_editor_property('mobility')), materials=[])
            for index in range(component.get_num_materials()):
                material = material_readback(unreal,component.get_material(index))
                if index < len(source['primitives']):
                    expected = stage_doc['materials'][source['primitives'][index]['material']]
                    material['staged_source_material'] = expected
                    material['staged_semantic_checks'] = alpha_checks(material,expected)
                    for item in material['staged_semantic_checks']:
                        check('stage_' + actor.get_actor_label() + '_' + str(index) + '_' + item['name'],item['passed'],item)
                record['materials'].append(material)
            stage_instances.append(record)
        result['stage_instances'] = stage_instances
        check('all_original_stage_mesh_instances_present', len(stage_instances) ==
              sum('mesh' in node for node in stage_doc['nodes']),len(stage_instances))
        result['render_settings'] = {name:unreal.SystemLibrary.get_console_variable_int_value(name)
            for name in ('r.AntiAliasingMethod','r.PostProcessAAQuality','r.MSAACount','r.Mobile.AntiAliasing')}
        result['render_settings']['r.ScreenPercentage'] = unreal.SystemLibrary.get_console_variable_float_value('r.ScreenPercentage')
        result['render_settings']['read_only'] = True
        result['warnings'].extend(['Source colour-reference materials are unlit; original NeoX shading/VFX are not verified.',
            'Metadata projection is numerical proof; native frame still requires visual review for occlusion/alpha artifacts.',
            'Native BindType263 and weapon auxiliary bone-AABB differences remain unresolved.'])
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        after = content_hashes()
        check('saved_battle_content_bytes_unchanged', before == after)
        result['passed'] = 'error' not in result and all(row['passed'] for row in result['checks'])
        write('native-readback.json', result)
    if not result['passed']:
        unreal.log_error('HCZS battle readback failed; inspect ' + str(BASE/'native-readback.json'))
        raise RuntimeError(result.get('error', 'One or more native readback checks failed'))
    unreal.log('HCZS read-only battle readback passed: ' + str(BASE/'native-readback.json'))


if __name__ == '__main__':
    if '--plan' in sys.argv:
        report = planned_projection(input_plan())
        write('projection-plan.json', report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        verify_native()
