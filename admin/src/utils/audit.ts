import type { AuditLog } from '../api/types'

export function auditAction(action: string) {
  return ({ 'profile.create': '创建玩家', 'profile.rename': '修改昵称', 'hall.select': '修改大厅角色', 'config.draft': '保存配置草稿', 'config.publish': '发布配置', 'config.rollback': '回滚配置' }[action] ?? action)
}

export function auditSummary(log: AuditLog) {
  const data = log.summary
  switch (log.action) {
    case 'profile.create': return `创建玩家 ${data.displayName ?? log.targetId} · r${data.revision}`
    case 'profile.rename': return `昵称改为 ${data.displayName ?? '—'} · r${data.revision}`
    case 'hall.select': return `${data.selectedHeroId === null ? '清空大厅角色选择' : `选择大厅角色 #${data.selectedHeroId}`} · r${data.revision}`
    case 'config.draft': return `保存草稿 r${data.revision} · ${data.settings?.serverName ?? ''}`
    case 'config.publish': return `发布配置 v${data.version} · ${data.settings?.serverName ?? ''}`
    case 'config.rollback': return `使用 v${data.sourceVersion} 回滚发布 v${data.version} · ${data.settings?.serverName ?? ''}`
    default: return JSON.stringify(data)
  }
}
