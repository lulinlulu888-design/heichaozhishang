// Reconstruction profile adapter. No original account/session is implied.
const HEAD = 'uires/HallMainPanel/NewHallPanel/PlayerHeadArea_ext.csb';
const TOP = 'uires/HallMainPanel/NewHallPanel/HomeTopNew_ext.csb';
const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;

function validateProfile(profile) {
  if (!profile || !UUID.test(profile.id) || typeof profile.displayName !== 'string' ||
      !profile.displayName.trim() || [...profile.displayName].length > 32 ||
      /[\u0000-\u001f\u007f]/u.test(profile.displayName) ||
      !Number.isSafeInteger(profile.revision) || profile.revision < 1) {
    throw Error('本地档案格式不受支持');
  }
  return { id: profile.id, displayName: profile.displayName, revision: profile.revision,
    selectedCharacterId: profile.selectedCharacterId ?? null };
}

/** Explicit port, GET only, no credentials and no automatic profile selection. */
export async function listHallProfiles(port, { fetchImpl = globalThis.fetch, signal } = {}) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('本地服务端口无效');
  const response = await fetchImpl(`http://127.0.0.1:${port}/api/rebuild/v1/profiles`,
    { method: 'GET', credentials: 'omit', cache: 'no-store', signal });
  if (!response.ok) throw Error(`读取本地档案失败 (${response.status})`);
  const body = await response.json();
  if (!Array.isArray(body.profiles)) throw Error('本地档案列表无效');
  const profiles = body.profiles.map(validateProfile);
  if (new Set(profiles.map(p => p.id)).size !== profiles.length) throw Error('本地档案 ID 重复');
  return profiles;
}

/** Call only after the user chooses an entry. Missing selection never picks the first save. */
export function createHallLocalState(profiles, selectedId) {
  const selected = selectedId == null ? null : profiles.find(p => p.id === selectedId);
  if (selectedId != null && !selected) throw Error('所选本地档案不存在，请重新读取');
  const profile = selected ? validateProfile(selected) : null;
  const patch = (layout, path, values, reason) => ({ layout, path, values, reason });
  return {
    mode: 'local-reconstruction-profile', profile,
    growth: { status: 'unrestored', level: null, experience: null },
    // This is a local product policy, NOT execution of old event predicates.
    activities: { status: 'unrestored', available: false },
    patches: [
      patch(HEAD, 'Panel_Top.Panel_VX.PlayerName', { text: profile?.displayName ?? '选择本地档案', visible: true }, 'local-profile-name'),
      patch(HEAD, 'Panel_Top.Panel_VX.LvBg', { visible: false }, 'growth-unrestored'),
      patch(HEAD, 'Panel_Top.Panel_VX.BarBg', { visible: false }, 'growth-unrestored'),
      patch(HEAD, 'Panel_Top.Panel_VX.Panel_1', { visible: false }, 'account-avatar-unrestored'),
      patch(TOP, 'SysBtn', { visible: false }, 'online-activities-unrestored'),
    ],
  };
}

/** Clone the source layout; fail on drift/ambiguity instead of changing a same-named node elsewhere. */
export function applyHallLocalState(layouts, state) {
  const copy = structuredClone(layouts);
  for (const patch of state.patches) {
    const rows = copy.layouts.filter(row => row.path === patch.layout);
    if (rows.length !== 1) throw Error(`大厅布局定位失败: ${patch.layout}`);
    let node = rows[0].tree;
    for (const name of patch.path.split('.')) {
      const matches = (node.children || []).filter(child => child.name === name);
      if (matches.length !== 1) throw Error(`大厅控件定位失败: ${patch.path}`);
      node = matches[0];
    }
    Object.assign(node, patch.values);
  }
  return copy;
}
