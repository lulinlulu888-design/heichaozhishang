<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, Refresh, Document } from '@element-plus/icons-vue'
import { useAdminStore } from '../stores/admin'
import { formatTime } from '../utils/format'
import { auditAction, auditSummary } from '../utils/audit'
import type { AuditLog } from '../api/types'

const store = useAdminStore()
const query = ref('')
const page = ref(1)
const loading = ref(false)
const error = ref('')
const selected = ref<AuditLog | null>(null)
const detailOpen = ref(false)
const filtered = computed(() => (store.logs?.logs ?? []).filter(log => `${log.action} ${auditSummary(log)} ${JSON.stringify(log.summary)} ${log.targetId} ${log.targetType} ${log.actor}`.includes(query.value.trim())).map(log => ({...log, summaryText: auditSummary(log)})))
const rows = computed(() => filtered.value.slice((page.value - 1) * 20, page.value * 20))
async function refresh() { loading.value = true; error.value = ''; try { await store.refreshLogs() } catch (cause) { error.value = cause instanceof Error ? cause.message : '读取操作日志失败' } finally { loading.value = false } }
function detail(log: AuditLog) { selected.value = log; detailOpen.value = true }
</script>

<template>
  <section class="page"><div class="page-heading"><div><span class="eyebrow">ADMINISTRATION AUDIT</span><h1>操作日志</h1><p>查看服务端持久化的管理操作，按时间倒序展示最近 100 条。</p></div><el-button :icon="Refresh" :loading="loading" @click="refresh">刷新日志</el-button></div><el-alert v-if="error" :title="error" type="error" :closable="false" class="config-alert" /><section class="panel heroes-panel"><div class="table-toolbar"><div class="catalog-count"><el-icon><Document /></el-icon><strong>{{ store.logs?.logs.length ?? '—' }}</strong><span>条真实操作记录</span></div><el-input v-model="query" class="search-input" placeholder="搜索操作 / 对象 / 描述" :prefix-icon="Search" clearable @input="page = 1" /></div><el-table :data="rows" v-loading="loading || store.loading" class="clean-table"><el-table-column label="时间" min-width="170"><template #default="{ row }">{{ formatTime(row.occurredAt) }}</template></el-table-column><el-table-column label="操作" min-width="145"><template #default="{ row }"><el-tag type="info">{{ auditAction(row.action) }}</el-tag></template></el-table-column><el-table-column label="操作人" width="125"><template #default="{ row }">{{ row.actor === 'local-admin' ? '本地管理员' : row.actor }}</template></el-table-column><el-table-column label="对象" min-width="185" show-overflow-tooltip><template #default="{ row }">{{ row.targetType }} / {{ row.targetId }}</template></el-table-column><el-table-column prop="summaryText" label="操作内容" min-width="260" show-overflow-tooltip /><el-table-column label="详情" width="70" align="right"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">查看</el-button></template></el-table-column><template #empty>{{ store.logs?.supported === false ? '当前存储不支持操作日志' : '暂无管理操作记录' }}</template></el-table><div class="table-footer"><span>当前筛选 {{ filtered.length }} 条</span><el-pagination v-model:current-page="page" :page-size="20" :total="filtered.length" layout="prev, pager, next" /></div></section><p class="content-source-note">日志来自服务端审计集合。未记录的历史行为不补造为日志；重复请求回放不应产生新的管理操作记录。</p><el-drawer v-model="detailOpen" title="操作记录详情" size="480px"><div v-if="selected"><el-descriptions :column="1" border><el-descriptions-item label="操作">{{ auditAction(selected.action) }}</el-descriptions-item><el-descriptions-item label="时间">{{ formatTime(selected.occurredAt) }}</el-descriptions-item><el-descriptions-item label="操作人">{{ selected.actor }}</el-descriptions-item><el-descriptions-item label="目标">{{ selected.targetType }} / {{ selected.targetId }}</el-descriptions-item><el-descriptions-item label="记录 ID">{{ selected.id }}</el-descriptions-item></el-descriptions><h3 class="audit-detail-title">操作摘要</h3><p class="evidence-text">{{ auditSummary(selected) }}</p><pre class="hash-block audit-json">{{ JSON.stringify(selected.summary, null, 2) }}</pre></div></el-drawer></section>
</template>
