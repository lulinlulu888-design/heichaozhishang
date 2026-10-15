export function formatTime(value: number | null | undefined, compact = false) {
  if (value === null || value === undefined) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: compact ? undefined : 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value))
}
export function shortId(value: string) { return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-4)}` : value }
export const battleStatus = (value: string) => ({ 'player-turn': '本方回合', 'enemy-turn': '敌方回合', active: '进行中', won: '胜利', victory: '胜利', lost: '失败', defeat: '失败', finished: '已结束' }[value] ?? value)
