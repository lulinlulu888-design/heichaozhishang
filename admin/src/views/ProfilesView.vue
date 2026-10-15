<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Search, Refresh, FolderOpened, CopyDocument, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '../api/admin'
import { ApiError } from '../api/http'
import type { ProfileDetail } from '../api/types'
import { useAdminStore } from '../stores/admin'
import { battleStatus, formatTime, shortId } from '../utils/format'

const store = useAdminStore()
const route = useRoute()
const router = useRouter()
const query = ref('')
const selectedId = ref('')
const detail = ref<ProfileDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const saveError = ref('')
const nameDraft = ref('')
const heroDraft = ref<number | null>(null)
const heroSelection = computed({ get: () => heroDraft.value ?? 0, set: (value: number) => { heroDraft.value = value === 0 ? null : value } })
const savingName = ref(false)
const savingHero = ref(false)
const createOpen = ref(false)
const createName = ref('')
const creating = ref(false)
const createError = ref('')
const busy = computed(() => savingName.value || savingHero.value)
const filteredProfiles = computed(() => store.profiles.filter(profile => `${profile.displayName} ${profile.id}`.includes(query.value.trim())))
let readSequence = 0
let hallAttempt: { key: string; requestId: string } | null = null

async function loadDetail(id: string, preserveDrafts = false) {
  const sequence = ++readSequence
  detailLoading.value = true
  detailError.value = ''
  if (!preserveDrafts) { detail.value = null; saveError.value = ''; hallAttempt = null }
  try {
    const next = await adminApi.profile(id)
    if (sequence !== readSequence) return
    detail.value = next
    if (!preserveDrafts) { nameDraft.value = next.profile.displayName; heroDraft.value = next.hall?.selectedHeroId ?? null }
  } catch (cause) {
    if (sequence === readSequence) detailError.value = cause instanceof Error ? cause.message : '读取玩家失败'
  } finally { if (sequence === readSequence) detailLoading.value = false }
}

function select(id: string) {
  if (busy.value || selectedId.value === id) return
  selectedId.value = id
  void router.replace({ path: '/profiles', query: { id } })
  void loadDetail(id)
}

watch(() => [store.loaded, route.query.id], () => {
  if (!store.loaded || busy.value) return
  const requestedId = typeof route.query.id === 'string' ? route.query.id : null
  const candidate = requestedId && store.profiles.some(profile => profile.id === requestedId) ? requestedId : selectedId.value || store.profiles[0]?.id
  if (candidate && candidate !== selectedId.value) select(candidate)
}, { immediate: true })

async function rename() {
  if (!detail.value || !nameDraft.value.trim() || busy.value) return
  const id = detail.value.profile.id
  savingName.value = true
  saveError.value = ''
  try {
    await adminApi.renameProfile(id, detail.value.profile.revision, nameDraft.value.trim())
    await loadDetail(id)
    await store.refreshProfiles()
    ElMessage.success('玩家昵称已保存')
    void store.refresh()
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'REVISION_CONFLICT') {
      await loadDetail(id, true)
      await store.refreshProfiles()
    }
    saveError.value = cause instanceof Error ? cause.message : '保存玩家失败'
  } finally { savingName.value = false }
}

async function saveHall() {
  if (!detail.value?.hall || busy.value) return
  const id = detail.value.profile.id
  const revision = detail.value.hall.revision
  const key = `${id}:${revision}:${heroDraft.value}`
  if (!hallAttempt || hallAttempt.key !== key) hallAttempt = { key, requestId: crypto.randomUUID() }
  savingHero.value = true
  saveError.value = ''
  try {
    await adminApi.selectHallHero(id, revision, heroDraft.value, hallAttempt.requestId)
    hallAttempt = null
    await loadDetail(id)
    ElMessage.success('大厅角色选择已保存')
    void store.refresh()
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'REVISION_CONFLICT') { hallAttempt = null; await loadDetail(id, true) }
    saveError.value = cause instanceof Error ? cause.message : '保存大厅角色失败'
  } finally { savingHero.value = false }
}

async function create() {
  if (!createName.value.trim() || creating.value || store.config?.active.settings.allowNewProfiles === false) return
  creating.value = true
  createError.value = ''
  try {
    const result = await adminApi.createProfile(createName.value.trim())
    await store.refreshProfiles()
    createOpen.value = false
    createName.value = ''
    select(result.profile.id)
    ElMessage.success('本地玩家已创建')
    void store.refresh()
  } catch (cause) { createError.value = cause instanceof Error ? cause.message : '创建玩家失败' }
  finally { creating.value = false }
}
async function copyId() {
  if (!detail.value) return
  try { await navigator.clipboard.writeText(detail.value.profile.id); ElMessage.success('玩家 ID 已复制') }
  catch { ElMessage.error('复制失败，请手动选择复制') }
}
</script>

<template>
  <section class="page">
    <div class="page-heading"><div><span class="eyebrow">PLAYER MANAGEMENT</span><h1>玩家管理</h1><p>管理本地玩家资料、大厅偏好和战斗记录。</p></div><el-button type="primary" :icon="Plus" :disabled="!store.loaded || store.config?.active.settings.allowNewProfiles === false" @click="createOpen = true; createError = ''">创建玩家</el-button></div>
    <div class="profiles-layout">
      <section class="panel profile-list-panel"><div class="panel-heading"><h2>玩家列表</h2><span class="count-pill">{{ store.loaded ? store.profiles.length : '—' }}</span></div><el-input v-model="query" placeholder="搜索玩家昵称 / ID" :prefix-icon="Search" clearable class="profile-search" /><div class="profile-list"><button v-for="profile in filteredProfiles" :key="profile.id" class="profile-list-item" :class="{ selected: selectedId === profile.id }" :disabled="busy" @click="select(profile.id)"><span class="profile-avatar">{{ profile.displayName.slice(0, 1) }}</span><span class="profile-list-copy"><strong>{{ profile.displayName }}</strong><small>{{ formatTime(profile.updatedAt, true) }} 更新</small></span><el-icon v-if="selectedId === profile.id" class="selection-check"><Check /></el-icon></button><el-empty v-if="!filteredProfiles.length" :description="store.loading ? '读取中' : '暂无玩家'" :image-size="60" /></div><div class="profile-list-foot">数据存储于本项目的本地数据库</div></section>
      <section class="panel profile-detail-panel" v-loading="detailLoading">
        <template v-if="detail"><div class="profile-detail-top"><div><span class="eyebrow">PLAYER DETAILS</span><h2>{{ detail.profile.displayName }}</h2><div class="profile-id"><code>{{ detail.profile.id }}</code><el-button text :icon="CopyDocument" aria-label="复制玩家 ID" @click="copyId" /></div></div><el-button :icon="Refresh" :disabled="busy || detailLoading" @click="loadDetail(selectedId)">重新读取</el-button></div>
          <div class="profile-meta"><div><span>玩家资料版本</span><strong>r{{ detail.profile.revision }}</strong></div><div><span>创建时间</span><strong>{{ formatTime(detail.profile.createdAt) }}</strong></div><div><span>最近更新</span><strong>{{ formatTime(detail.profile.updatedAt) }}</strong></div></div>
          <el-alert v-if="saveError" :title="saveError" type="error" :closable="false" show-icon class="form-alert" />
          <div class="edit-section"><div class="edit-section-title"><h3>基础信息</h3><span>按玩家资料版本保存</span></div><el-form label-position="top" @submit.prevent="rename"><el-form-item label="玩家昵称"><div class="inline-form"><el-input v-model="nameDraft" maxlength="32" show-word-limit :disabled="busy" @keyup.enter="rename" /><el-button type="primary" :loading="savingName" :disabled="busy && !savingName || !nameDraft.trim() || nameDraft.trim() === detail.profile.displayName" @click="rename">保存昵称</el-button></div></el-form-item></el-form></div>
          <div class="edit-section"><div class="edit-section-title"><h3>大厅角色</h3><span>独立大厅版本 r{{ detail.hall?.revision ?? '—' }}</span></div><el-form label-position="top" @submit.prevent="saveHall"><el-form-item label="选择已验证的大厅预览角色"><div class="inline-form"><el-select v-model="heroSelection" placeholder="未选择" :disabled="busy || !detail.hall" style="width: 100%"><el-option :value="0" label="未选择" /><el-option v-for="hero in store.hallReady" :key="hero.id" :value="hero.id" :label="`${hero.name} · ${hero.hallPreviewVerification?.renderer === 'unreal-editor' ? 'UE 编辑器' : '历史 Web 参考'}`" /></el-select><el-button type="primary" plain :loading="savingHero" :disabled="busy && !savingHero || !detail.hall || heroDraft === detail.hall?.selectedHeroId" @click="saveHall">保存选择</el-button></div></el-form-item></el-form><p class="form-help">保存本地大厅偏好；不会赋予角色所有权，也不会自动切换当前运行的 UE 编辑器画面。</p><p v-if="!detail.hall" class="form-help">当前服务未提供大厅状态。</p></div>
          <div class="edit-section battles-section"><div class="edit-section-title"><h3>战斗存档</h3><span>{{ detail.battles.length }} 场</span></div><el-table :data="detail.battles" class="clean-table compact-table"><el-table-column label="战斗 ID" min-width="140"><template #default="{ row }"><code :title="row.id">{{ shortId(row.id) }}</code></template></el-table-column><el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="['won','victory'].includes(row.status) ? 'success' : ['lost','defeat'].includes(row.status) ? 'danger' : 'info'" effect="light">{{ battleStatus(row.status) }}</el-tag></template></el-table-column><el-table-column prop="round" label="回合" width="72" /><el-table-column label="版本" width="72"><template #default="{ row }">r{{ row.revision }}</template></el-table-column><el-table-column label="更新" min-width="142"><template #default="{ row }">{{ formatTime(row.updatedAt, true) }}</template></el-table-column><template #empty>此玩家还没有战斗存档</template></el-table></div>
        </template>
        <div v-else class="empty-detail"><el-icon :size="46"><FolderOpened /></el-icon><h2>{{ detailError ? '无法读取玩家' : '选择一个玩家' }}</h2><p>{{ detailError || '从左侧选择玩家，查看大厅偏好和战斗存档。' }}</p><el-button v-if="detailError" @click="loadDetail(selectedId)">重试</el-button></div>
      </section>
    </div>
    <el-dialog v-model="createOpen" title="创建本地玩家" width="460px" :close-on-click-modal="!creating" :show-close="!creating"><p class="dialog-description">创建独立本地玩家及游玩存档，已有玩家数据会继续保留。</p><el-form label-position="top" @submit.prevent="create"><el-form-item label="玩家昵称"><el-input v-model="createName" maxlength="32" show-word-limit placeholder="输入玩家昵称" :disabled="creating" @keyup.enter="create" /></el-form-item></el-form><el-alert v-if="createError" :title="createError" type="error" :closable="false" /><template #footer><el-button :disabled="creating" @click="createOpen = false">取消</el-button><el-button type="primary" :loading="creating" :disabled="!createName.trim() || store.config?.active.settings.allowNewProfiles === false" @click="create">创建玩家</el-button></template></el-dialog>
  </section>
</template>
