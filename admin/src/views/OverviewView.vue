<script setup lang="ts">
import { computed } from 'vue'
import { User, Connection, Collection, ArrowRight, CircleCheck, Clock, MapLocation, Setting, Document } from '@element-plus/icons-vue'
import { useAdminStore } from '../stores/admin'
import { formatTime } from '../utils/format'
import { auditSummary } from '../utils/audit'

const store = useAdminStore()
const active = computed(() => store.config?.active)
const battleMode = computed(() => ({ 'city-reconstruction-preview': '时之城', 'explicit-reconstruction': '序章', 'custom-content': '自定义' }[store.overview?.service.battleMode ?? ''] ?? '未启用'))
const recentPlayers = computed(() => [...store.profiles].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 4))
const defaultEncounter = computed(() => store.encounters?.encounters.find(item => item.id === active.value?.settings.defaultEncounterId)?.title ?? '未启用关卡')
const counters = computed(() => [
  { label: '本地玩家', value: store.overview?.counts.profiles, unit: '位', icon: User, color: 'purple', caption: '当前数据库中的独立玩家' },
  { label: '战斗记录', value: store.overview?.counts.battles, unit: '场', icon: Collection, color: 'blue', caption: '保存的完整本地战斗状态' },
  { label: '可用关卡', value: store.encounters?.encounters.length, unit: '个', icon: MapLocation, color: 'green', caption: '当前服务启用的场景' },
  { label: '生效配置', value: active.value?.version, unit: '版', icon: Setting, color: 'orange', caption: active.value?.version === 0 ? '系统初始配置' : active.value?.publishedAt ? `${formatTime(active.value.publishedAt, true)} 发布` : '等待配置数据' },
])
</script>

<template>
  <section class="page">
    <div class="page-heading"><div><span class="eyebrow">GAME OPERATIONS</span><h1>运营总览</h1><p>管理玩家、游戏内容和生效中的服务配置。</p></div><span class="environment-tag">LOCAL ENVIRONMENT</span></div>
    <div class="welcome-banner operations-banner">
      <div class="banner-copy"><span class="banner-kicker">SERVICE OVERVIEW</span><h2>{{ active?.settings.serverName || '黑潮之上 · 本地服务' }}</h2><p>{{ active?.settings.motd || '暂无服务器公告。可在运营配置中保存草稿并发布。' }}</p><router-link to="/config" class="banner-link">管理运营配置 <el-icon><ArrowRight /></el-icon></router-link></div>
      <div class="banner-art" aria-hidden="true"><span class="orb orb-one"></span><span class="orb orb-two"></span><span class="orbit orbit-one"></span><span class="orbit orbit-two"></span><svg class="tide-symbol" viewBox="0 0 100 100"><path d="M21 74V27h12v17l30-17h21L42 53l42 21H60L33 60v14z" fill="currentColor" /></svg><span class="art-caption">ABOVE THE TIDE</span></div>
    </div>
    <div class="metric-grid"><article v-for="item in counters" :key="item.label" class="metric-card"><div class="metric-top"><span>{{ item.label }}</span><span class="metric-icon" :class="item.color"><el-icon :size="21"><component :is="item.icon" /></el-icon></span></div><div class="metric-value">{{ item.value ?? '—' }}<small>{{ item.unit }}</small></div><div class="metric-caption">{{ item.caption }}</div></article></div>
    <div class="overview-grid">
      <section class="panel service-panel"><div class="panel-heading"><h2>服务运行状态</h2><span class="tiny-label">Node.js + MongoDB</span></div><div class="system-row"><span class="system-icon purple"><el-icon :size="22"><Connection /></el-icon></span><div class="system-copy"><strong>{{ store.overview?.service.service ?? '本地游戏服务' }}</strong><small>API v{{ store.overview?.service.apiVersion ?? '—' }} · {{ store.overview?.service.storage ?? '—' }}</small></div><el-tag :type="store.loaded && !store.error ? 'success' : 'info'">{{ store.loaded && !store.error ? '运行中' : '等待连接' }}</el-tag></div><div class="detail-lines"><div><span>玩家创建</span><strong :class="active?.settings.allowNewProfiles ? 'text-green' : 'text-muted'">{{ active ? active.settings.allowNewProfiles ? '已开放' : '已关闭' : '—' }}</strong></div><div><span>新战斗创建</span><strong :class="active?.settings.allowNewBattles ? 'text-green' : 'text-muted'">{{ active ? active.settings.allowNewBattles ? '已开放' : '已关闭' : '—' }}</strong></div><div><span>默认关卡</span><strong>{{ defaultEncounter }}</strong></div></div><div class="client-note"><span class="mini-dot"></span><div><strong>当前服务模式：{{ battleMode }}本地重建</strong><p>本地玩家和战斗数据不等于实时在线人数。客户端主线为 Unreal Engine 5。</p></div></div></section>
      <section class="panel service-panel"><div class="panel-heading"><h2>最近管理操作</h2><router-link to="/logs" class="text-link">全部日志 <el-icon><ArrowRight /></el-icon></router-link></div><template v-if="store.logs?.logs.length"><div v-for="log in store.logs.logs.slice(0, 4)" :key="log.id" class="audit-preview-row"><span class="summary-icon purple"><el-icon><Document /></el-icon></span><div><strong>{{ auditSummary(log) }}</strong><small>{{ formatTime(log.occurredAt) }} · {{ log.actor }}</small></div></div></template><div v-else class="empty-audit"><el-icon :size="30"><CircleCheck /></el-icon><p>{{ store.loaded ? '暂无管理操作记录' : '等待日志数据' }}</p><small>保存配置、发布版本或修改玩家后自动记录</small></div></section>
    </div>
    <section class="panel recent-panel"><div class="panel-heading"><h2>最近更新的玩家</h2><router-link to="/profiles" class="text-link">玩家管理 <el-icon><ArrowRight /></el-icon></router-link></div><el-table :data="recentPlayers" class="clean-table"><el-table-column label="玩家昵称" min-width="180"><template #default="{ row }"><div class="table-profile"><span class="small-avatar">{{ row.displayName.slice(0, 1) }}</span><strong>{{ row.displayName }}</strong></div></template></el-table-column><el-table-column label="目录角色" min-width="150"><template #default="{ row }">{{ store.heroName(row.selectedCharacterId) }}</template></el-table-column><el-table-column label="资料版本" width="110"><template #default="{ row }">r{{ row.revision }}</template></el-table-column><el-table-column label="最近更新" min-width="170"><template #default="{ row }"><span class="date-cell"><el-icon><Clock /></el-icon>{{ formatTime(row.updatedAt) }}</span></template></el-table-column><el-table-column label="操作" width="95"><template #default="{ row }"><router-link :to="`/profiles?id=${row.id}`" class="text-link">查看玩家</router-link></template></el-table-column><template #empty>{{ store.loading ? '正在读取玩家…' : '暂无本地玩家' }}</template></el-table></section>
  </section>
</template>
