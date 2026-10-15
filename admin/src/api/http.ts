const prefix = '/api/admin/v1'

const errorLabels: Record<string, string> = {
  REVISION_CONFLICT: '数据已被其他操作更新，已重新读取最新版本。请核对后再次保存。',
  PROFILE_NOT_FOUND: '该本地档案已不存在，请刷新列表。',
  HALL_HERO_UNAVAILABLE: '该角色尚未接入大厅预览，暂时无法选择。',
  UNKNOWN_CHARACTER: '角色不在已恢复目录中。',
  INVALID_INPUT: '提交的数据不符合要求，请检查后重试。',
  INVALID_NAME: '档案名称须为 1–32 个可见字符，不能包含控制字符。',
  ADMIN_ORIGIN_REJECTED: '管理请求来源不被允许，请使用本地管理页面。',
  ORIGIN_NOT_ALLOWED: '管理请求来源不被允许，请使用本地管理页面。',
  ADMIN_UNAVAILABLE: '管理接口暂未启用。',
  REQUEST_ID_CONFLICT: '本次操作标识已使用，请重新保存。',
  CONFIG_REVISION_CONFLICT: '配置已被其他操作更新，已重新读取最新版本。请核对后再次保存。',
  OPERATIONAL_STORAGE_UNSUPPORTED: '当前存储不支持运营配置和操作日志，请使用 MongoDB。',
  INVALID_CONFIG: '配置字段不符合要求，请检查服务器名称、公告或默认关卡。',
  INVALID_SETTINGS: '配置字段不符合要求，请检查服务器名称、公告或默认关卡。',
  PROFILE_CREATION_DISABLED: '当前运营配置关闭了新玩家创建。',
  BATTLE_CREATION_DISABLED: '当前运营配置关闭了新战斗创建。',
  ENCOUNTER_UNAVAILABLE: '该关卡未在当前服务启用，请重新读取关卡目录。',
  CONFIG_VERSION_NOT_FOUND: '该发布版本已不存在，请重新读取发布历史。',
  NEW_PROFILES_DISABLED: '当前运营配置关闭了新玩家创建。',
  NEW_BATTLES_DISABLED: '当前运营配置关闭了新战斗创建。',
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, public readonly detail: string) {
    super(`${errorLabels[code] ?? detail ?? '请求失败'}${code ? `（${code}）` : ''}`)
  }
}

export async function request<T>(path: string, options: { method?: 'GET' | 'POST' | 'PATCH'; body?: unknown } = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 20000)
  try {
    const response = await fetch(`${prefix}${path}`, {
      method: options.method ?? 'GET',
      headers: { Accept: 'application/json', ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
      credentials: 'same-origin',
      signal: controller.signal,
      cache: 'no-store',
    })
    const raw = await response.text()
    let payload: unknown
    try { payload = JSON.parse(raw) }
    catch { throw new ApiError(response.status, 'INVALID_RESPONSE', '服务器返回了无法解析的响应') }
    if (!response.ok) {
      const data = payload as { error?: { code?: string; message?: string }; code?: string; message?: string }
      throw new ApiError(response.status, data.error?.code ?? data.code ?? `HTTP_${response.status}`, data.error?.message ?? data.message ?? '管理请求失败')
    }
    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted) throw new ApiError(0, 'TIMEOUT', '本地服务响应超时，请检查服务状态')
    throw new ApiError(0, 'NETWORK_ERROR', '无法连接本地管理服务，请确认服务端正在运行')
  } finally { window.clearTimeout(timeout) }
}
