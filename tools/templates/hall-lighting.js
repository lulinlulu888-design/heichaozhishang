import * as THREE from 'three';

// Original UE4_lm decoding from APK default_functions.hlsl + function.hlsl.
// Only the diffuse multiplication is adapted; this is not the original BRDF.
export async function installHallLighting(root, {baseUrl = './lighting/'} = {}) {
  const url = new URL(baseUrl, globalThis.location?.href || import.meta.url);
  const response = await fetch(new URL('lighting.json', url));
  if (!response.ok) throw new Error(`Hall lighting manifest HTTP ${response.status}`);
  const report = await response.json();
  if (report.schema !== 1) throw new Error('Unsupported hall lighting manifest');
  const loader = new THREE.TextureLoader();
  const textures = await Promise.all(report.images.map(path => loader.loadAsync(new URL(path, url).href)));
  for (const texture of textures) {
    texture.colorSpace = THREE.NoColorSpace;
    texture.flipY = false;
    texture.generateMipmaps = false;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
  }
  const bindings = new Map(report.bindings.map(row => [row.uuid, row]));
  const seen = new Set(), entries = [];
  let enabled = false;
  try {
    root.traverse(mesh => {
      if (!mesh.isMesh) return;
      let owner = mesh;
      while (owner && !owner.userData.sourceInstance) owner = owner.parent;
      const uuid = owner?.userData.sourceInstance?.UUID;
      const row = bindings.get(uuid);
      if (!row) return;
      if (seen.has(uuid)) throw new Error(`Ambiguous hall lightmap owner ${uuid}`);
      const uv = mesh.geometry.getAttribute('uv1');
      if (!uv || uv.count !== row.uv_count || Array.isArray(mesh.material)) {
        throw new Error(`Hall lightmap geometry mismatch ${row.name}`);
      }
      const p = row.parameters;
      if (p.UE4_lm !== 'true' || p.encode_type !== '4') throw new Error('Unsupported lightmap encoding');
      const vec = (key, count) => {
        const values = p[key].split(',').map(Number).slice(0, count);
        if (values.length !== count || !values.every(Number.isFinite)) throw new Error(`Invalid ${key}`);
        return values;
      };
      const old = mesh.material, material = old.clone();
      material.defines = {...material.defines, USE_UV1: ''};
      material.onBeforeCompile = shader => {
        Object.assign(shader.uniforms, {
          originalLightmap: {value: textures[Number(p.texture_index)]},
          lmScale: {value: new THREE.Vector3(...vec('lightmap_scale', 3))},
          lmAdd: {value: new THREE.Vector3(...vec('lightmap_add', 3))},
          lmUVScale: {value: new THREE.Vector2(...vec('uv_scale', 2))},
          lmUVOffset: {value: new THREE.Vector2(...vec('uv_ofs', 2))},
        });
        if (!shader.vertexShader.includes('#include <uv_vertex>') ||
            !shader.fragmentShader.includes('#include <opaque_fragment>')) {
          throw new Error('Three shader hooks changed');
        }
        shader.vertexShader = 'varying vec2 originalLMUV; uniform vec2 lmUVScale; uniform vec2 lmUVOffset;\n' + shader.vertexShader;
        shader.vertexShader = shader.vertexShader.replace('#include <uv_vertex>',
          '#include <uv_vertex>\noriginalLMUV=uv1*lmUVScale+lmUVOffset;');
        shader.fragmentShader = 'varying vec2 originalLMUV; uniform sampler2D originalLightmap; uniform vec3 lmScale; uniform vec3 lmAdd;\n' + shader.fragmentShader;
        shader.fragmentShader = shader.fragmentShader.replace('#include <opaque_fragment>', `
          vec3 encodedLight = texture2D(originalLightmap, originalLMUV).rgb * lmScale + lmAdd;
          float logL = dot(vec3(0.299, 0.587, 0.114), encodedLight);
          float luma = (exp2(logL * 16.0 - 8.0) - 0.00390625) * 0.6;
          outgoingLight *= encodedLight * (luma / max(logL, 0.00001));
          #include <opaque_fragment>`);
      };
      material.customProgramCacheKey = () => 'hczs-hall-source-baked-v1';
      entries.push({mesh, old, material});
      seen.add(uuid);
    });
    if (seen.size !== bindings.size) throw new Error(`Hall lightmap bindings ${seen.size}/${bindings.size}`);
  } catch (error) {
    entries.forEach(entry => entry.material.dispose());
    textures.forEach(texture => texture.dispose());
    throw error;
  }
  return {
    report: {...report, installed_instances: entries.length},
    get enabled() { return enabled; },
    setEnabled(value) {
      enabled = Boolean(value);
      for (const entry of entries) entry.mesh.material = enabled ? entry.material : entry.old;
    },
    dispose() {
      for (const entry of entries) {
        entry.mesh.material = entry.old;
        entry.material.dispose();
      }
      textures.forEach(texture => texture.dispose());
      enabled = false;
    },
  };
}
