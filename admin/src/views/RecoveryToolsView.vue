<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, CopyDocument, User, CircleCheck, Clock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAdminStore } from '../stores/admin'
import type { Hero } from '../api/types'

const store = useAdminStore()
const query = ref('')
const filter = ref('all')
const currentPage = ref(1)
const selectedHero = ref<Hero | null>(null)
const detailOpen = ref(false)
const filtered = computed(() => (store.heroes?.heroes ?? []).filter(hero => {
  const search = `${hero.name} ${hero.id}`.includes(query.value.trim())
  return search && (filter.value === 'all' || (filter.value === 'hall' ? hero.availability.hallPreview === 'verified' : hero.availability.hallPreview !== 'verified'))
}))
const pageRows = computed(() => filtered.value.slice((currentPage.value - 1) * 12, currentPage.value * 12))
function openDetail(hero: Hero) { selectedHero.value = hero; detailOpen.value = true }
async function copy(value: string) { try { await navigator.clipboard.writeText(value); ElMessage.success('已复制') } catch { ElMessage.error('复制失败，请手动选择复制') } }
function resetPage() { currentPage.value = 1 }
</script>

<template>
  <section class="page">
    <div class="page-heading"><div><span class="eyebrow">CHARACTER RECOVERY</span><h1>角色恢复</h1><p>以 APK 原始角色目录为基础，区分资源目录和已验证能力。</p></div><el-tag class="heading-tag" effect="plain">UseRole = 1</el-tag></div>
    <div class="summary-strip"><div><span class="summary-icon purple"><el-icon><User /></el-icon></span><strong>{{ store.heroes?.heroes.length ?? '—' }}</strong><span>目录角色</span></div><div><span class="summary-icon green"><el-icon><CircleCheck /></el-icon></span><strong>{{ store.loaded ? store.ueReady.length : '—' }}</strong><span>UE 大厅已接入</span></div><div><span class="summary-icon orange"><el-icon><Clock /></el-icon></span><strong>{{ store.heroes?.heroes.filter(h => h.availability.hallPreview !== 'verified').length ?? '—' }}</strong><span>大厅待接入</span></div></div>
    <section class="panel heroes-panel">
      <div class="table-toolbar"><div class="filter-tabs"><button :class="{ active: filter === 'all' }" @click="filter = 'all'; resetPage()">全部角色</button><button :class="{ active: filter === 'hall' }" @click="filter = 'hall'; resetPage()">已验证预览</button><button :class="{ active: filter === 'pending' }" @click="filter = 'pending'; resetPage()">待接入</button></div><el-input v-model="query" class="search-input" placeholder="搜索角色名称 / ID" :prefix-icon="Search" clearable @input="resetPage" /></div>
      <el-table :data="pageRows" v-loading="store.loading" class="clean-table"><el-table-column prop="id" label="ID" width="76" /><el-table-column label="角色" min-width="190"><template #default="{ row }"><div class="table-profile"><span class="small-avatar" :class="{ pink: row.id === 33 }">{{ row.name.slice(0, 1) }}</span><strong>{{ row.name }}</strong><span v-if="row.id === 1" class="priority-pill">当前优先</span></div></template></el-table-column><el-table-column label="大厅状态" min-width="145"><template #default="{ row }"><el-tag :type="row.availability.hallPreview === 'verified' ? 'success' : 'info'" effect="light">{{ row.availability.hallPreview === 'verified' ? '已验证预览' : '待接入' }}</el-tag></template></el-table-column><el-table-column label="已验证环境" min-width="180"><template #default="{ row }">{{ row.hallPreviewVerification?.renderer === 'unreal-editor' ? 'UE 编辑器 · Windows' : row.hallPreviewVerification ? '历史 Web 参考' : '—' }}</template></el-table-column><el-table-column label="完整战斗" min-width="130"><template #default="{ row }"><span class="text-muted">{{ row.availability.fullBattle === 'verified' ? '已验证' : '尚未验证' }}</span></template></el-table-column><el-table-column label="证据" width="98" align="right"><template #default="{ row }"><el-button link type="primary" @click="openDetail(row)">查看</el-button></template></el-table-column><template #empty>{{ store.loading ? '正在读取原始目录…' : '没有符合条件的角色' }}</template></el-table>
      <div class="table-footer"><span>共 {{ filtered.length }} 位角色</span><el-pagination v-model:current-page="currentPage" :page-size="12" :total="filtered.length" layout="prev, pager, next" /></div>
    </section>
    <div class="source-note"><el-icon><CopyDocument /></el-icon><span>源目录：{{ store.heroes?.sources.module ?? '等待服务数据' }} · 原表 {{ store.heroes?.sources.sourceRowCount ?? '—' }} 行，筛选 {{ store.heroes?.sources.selectedRowCount ?? '—' }} 位角色。目录不表示角色所有权或解锁状态。</span></div>
    <el-drawer v-model="detailOpen" title="角色恢复证据" size="480px">
      <div v-if="selectedHero" class="hero-detail"><div class="hero-detail-heading"><span class="hero-initial">{{ selectedHero.name.slice(0, 1) }}</span><div><h2>{{ selectedHero.name }}</h2><span>CHARACTER #{{ selectedHero.id }}</span></div></div><el-descriptions :column="1" border><el-descriptions-item label="大厅预览">{{ selectedHero.availability.hallPreview === 'verified' ? '已验证' : '尚未接入' }}</el-descriptions-item><el-descriptions-item label="完整战斗">{{ selectedHero.availability.fullBattle === 'verified' ? '已验证' : '尚未验证' }}</el-descriptions-item><el-descriptions-item label="渲染器">{{ selectedHero.hallPreviewVerification?.renderer ?? '—' }}</el-descriptions-item><el-descriptions-item label="平台">{{ selectedHero.hallPreviewVerification?.platform ?? '—' }}</el-descriptions-item><el-descriptions-item label="原始动作">{{ selectedHero.hallPreviewVerification?.sourceAnimation ?? '—' }}</el-descriptions-item></el-descriptions><template v-if="selectedHero.hallPreviewVerification"><h3>验证范围</h3><p class="evidence-text">{{ selectedHero.hallPreviewVerification.verification }}</p><h3>证据引用</h3><code class="hash-block">{{ selectedHero.hallPreviewVerification.evidence }}</code><template v-if="selectedHero.hallPreviewVerification.sourceModelSha256"><h3>模型 SHA-256</h3><code class="hash-block">{{ selectedHero.hallPreviewVerification.sourceModelSha256 }}</code><el-button text type="primary" :icon="CopyDocument" @click="copy(selectedHero.hallPreviewVerification!.sourceModelSha256!)">复制模型哈希</el-button></template></template><h3>APK SHA-256</h3><code class="hash-block">{{ store.heroes?.sources.apkSha256 }}</code><el-alert class="drawer-note" title="这是资源恢复和预览验证记录，不代表原版完整运行、全平台打包或战斗恢复。" type="info" :closable="false" /></div>
    </el-drawer>
  </section>
</template>
