<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Upload, DocumentChecked, Refresh, RefreshLeft, CircleCheck } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { adminApi } from '../api/admin'
import { ApiError } from '../api/http'
import { useAdminStore } from '../stores/admin'
import type { ConfigRelease, OperationalConfig, OperationalSettings } from '../api/types'
import { formatTime } from '../utils/format'

const store = useAdminStore()
const form = reactive<OperationalSettings>({ serverName: '', motd: '', allowNewProfiles: false, allowNewBattles: false, defaultEncounterId: null })
const baseSettings = ref<OperationalSettings | null>(null)
const baseRevision = ref(0)
const initialized = ref(false)
const working = ref(false)
const error = ref('')
const publishOpen = ref(false)
const rollbackOpen = ref(false)
const rollbackRelease = ref<ConfigRelease | null>(null)
const supported = computed(() => store.config?.supported === true)
const dirty = computed(() => baseSettings.value !== null && !equal(form, baseSettings.value))
const valid = computed(() => !!form.serverName.trim() && [...form.serverName.trim()].length <= 64 && [...form.motd].length <= 1000)
const encounterSelection = computed({ get: () => form.defaultEncounterId ?? '', set: (value: string) => { form.defaultEncounterId = value || null } })
const releaseRows = computed(() => store.config?.releases ?? [])
let attempt: { key: string; requestId: string } | null = null

function equal(a: OperationalSettings, b: OperationalSettings) {
  return a.serverName === b.serverName && a.motd === b.motd && a.allowNewProfiles === b.allowNewProfiles && a.allowNewBattles === b.allowNewBattles && a.defaultEncounterId === b.defaultEncounterId
}
function copySettings(value: OperationalSettings): OperationalSettings {
  return { serverName: value.serverName, motd: value.motd, allowNewProfiles: value.allowNewProfiles, allowNewBattles: value.allowNewBattles, defaultEncounterId: value.defaultEncounterId }
}
function apply(state: OperationalConfig, preserveInput = false) {
  store.config = state
  baseRevision.value = state.draft.revision
  baseSettings.value = copySettings(state.draft.settings)
  if (!preserveInput) Object.assign(form, copySettings(state.draft.settings))
  initialized.value = true
}
watch(() => store.config, next => { if (next && (!initialized.value || (!dirty.value && !working.value))) apply(next) }, { immediate: true })

async function reload() {
  working.value = true
  error.value = ''
  try { apply(await adminApi.config()); attempt = null }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '读取运营配置失败' }
  finally { working.value = false }
}
async function handleError(cause: unknown, preserveInput = true) {
  if (cause instanceof ApiError && ['REVISION_CONFLICT','CONFIG_REVISION_CONFLICT'].includes(cause.code)) {
    attempt = null
    try { apply(await adminApi.config(), preserveInput) }
    catch (reloadError) { error.value = reloadError instanceof Error ? reloadError.message : '读取最新配置失败'; return }
  }
  error.value = cause instanceof Error ? cause.message : '运营配置请求失败'
}
async function saveDraft() {
  if (!supported.value || !valid.value || !dirty.value || working.value) return
  working.value = true
  error.value = ''
  try {
    const settings = copySettings(form)
    settings.serverName = settings.serverName.trim()
    apply(await adminApi.saveConfigDraft(baseRevision.value, settings))
    attempt = null
    ElMessage.success('草稿已保存，尚未发布生效')
    await store.refreshLogs()
  } catch (cause) { await handleError(cause) }
  finally { working.value = false }
}
function getRequestId(key: string) { if (!attempt || attempt.key !== key) attempt = { key, requestId: crypto.randomUUID() }; return attempt.requestId }
async function publish() {
  if (!supported.value || dirty.value || working.value) return
  working.value = true
  error.value = ''
  try {
    await adminApi.publishConfig(baseRevision.value, getRequestId(`publish:${baseRevision.value}`))
    // An idempotent replay returns its historical receipt; read the current active version.
    apply(await adminApi.config())
    attempt = null
    publishOpen.value = false
    ElMessage.success(`发布已完成，当前生效 v${store.config?.active.version}`)
    await store.refreshLogs()
  } catch (cause) { await handleError(cause); publishOpen.value = false }
  finally { working.value = false }
}
function openRollback(release: ConfigRelease) { rollbackRelease.value = release; rollbackOpen.value = true }
async function rollback() {
  if (!supported.value || dirty.value || working.value || !rollbackRelease.value) return
  working.value = true
  error.value = ''
  const version = rollbackRelease.value.version
  try {
    await adminApi.rollbackConfig(baseRevision.value, version, getRequestId(`rollback:${baseRevision.value}:${version}`))
    apply(await adminApi.config())
    attempt = null
    rollbackOpen.value = false
    ElMessage.success(`已使用 v${version} 的设置回滚，当前生效 v${store.config?.active.version}`)
    await store.refreshLogs()
  } catch (cause) { await handleError(cause); rollbackOpen.value = false }
  finally { working.value = false }
}
function encounterName(id: string | null) { return id === null ? '未启用关卡' : store.encounters?.encounters.find(item => item.id === id)?.title ?? id }
function kindName(kind: string) { return ({ initial: '系统初始', publish: '发布', rollback: '回滚发布', system: '系统初始' }[kind] ?? kind) }
</script>

<template>
  <section class="page"><div class="page-heading"><div><span class="eyebrow">OPERATIONAL CONFIGURATION</span><h1>运营配置</h1><p>编辑草稿、发布生效版本，并从历史设置创建回滚版本。</p></div><el-button :icon="Refresh" :disabled="working" @click="reload">重新读取</el-button></div><el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="form-alert config-alert" /><el-alert v-if="store.config && !supported" title="当前存储仅提供初始配置读取，不支持草稿、发布、回滚和操作日志。请使用 MongoDB。" type="info" :closable="false" class="config-alert" />
    <div class="config-layout"><section class="panel config-editor" v-loading="!initialized && store.loading"><div class="panel-heading"><h2>配置草稿</h2><span class="draft-badge">r{{ initialized ? baseRevision : '—' }}<span v-if="dirty"> · 未保存</span></span></div><el-form label-position="top" :disabled="!supported || working"><el-form-item label="服务器名称"><el-input v-model="form.serverName" maxlength="64" show-word-limit placeholder="输入服务器显示名称" /></el-form-item><el-form-item label="服务器公告"><el-input v-model="form.motd" type="textarea" :rows="4" maxlength="1000" show-word-limit placeholder="玩家可见的本地服务器公告，可留空" /></el-form-item><div class="config-switch-row"><div><strong>允许创建新玩家</strong><p>发布后控制新玩家注册；已有玩家资料继续保留。</p></div><el-switch v-model="form.allowNewProfiles" aria-label="允许创建新玩家" /></div><div class="config-switch-row"><div><strong>允许创建新战斗</strong><p>发布后控制新战斗建立，不改写已保存的战斗状态。</p></div><el-switch v-model="form.allowNewBattles" aria-label="允许创建新战斗" /></div><el-form-item label="默认关卡" class="default-encounter-field"><el-select v-model="encounterSelection" style="width:100%" placeholder="未启用关卡"><el-option :value="''" label="未启用关卡" :disabled="(store.encounters?.encounters.length ?? 0) > 0" /><el-option v-for="encounter in store.encounters?.encounters ?? []" :key="encounter.id" :value="encounter.id" :label="encounter.title" /></el-select></el-form-item></el-form><div class="config-actions"><span>{{ dirty ? '草稿有未保存变更，保存后再发布。' : '草稿已与本次读取的服务版本一致。' }}</span><el-button :icon="DocumentChecked" :loading="working" :disabled="!supported || !dirty || !valid || working" @click="saveDraft">保存草稿</el-button><el-button type="primary" :icon="Upload" :disabled="!supported || dirty || working || !initialized" @click="publishOpen = true">发布配置</el-button></div></section>
    <aside class="panel active-config"><div class="panel-heading"><h2>当前生效</h2><el-tag type="success"><el-icon><CircleCheck /></el-icon> v{{ store.config?.active.version ?? '—' }}</el-tag></div><template v-if="store.config"><h3>{{ store.config.active.settings.serverName }}</h3><div class="active-announcement">{{ store.config.active.settings.motd || '暂无公告' }}</div><div class="detail-lines"><div><span>新玩家创建</span><strong :class="store.config.active.settings.allowNewProfiles ? 'text-green' : 'text-muted'">{{ store.config.active.settings.allowNewProfiles ? '开放' : '关闭' }}</strong></div><div><span>新战斗创建</span><strong :class="store.config.active.settings.allowNewBattles ? 'text-green' : 'text-muted'">{{ store.config.active.settings.allowNewBattles ? '开放' : '关闭' }}</strong></div></div><div class="active-config-line"><span>默认关卡</span><strong>{{ encounterName(store.config.active.settings.defaultEncounterId) }}</strong></div><div class="active-config-line"><span>发布时间</span><strong>{{ store.config.active.version === 0 ? '系统初始化' : formatTime(store.config.active.publishedAt) }}</strong></div><div class="active-config-line"><span>版本来源</span><strong>{{ kindName(store.config.active.kind) }}{{ store.config.active.sourceVersion !== null ? ` · v${store.config.active.sourceVersion}` : '' }}</strong></div></template><p class="config-version-note">保存草稿不立即改变服务行为。发布生成新版本；回滚也生成新版本，保留完整发布历史。</p></aside></div>
    <section class="panel release-panel"><div class="panel-heading"><h2>发布历史</h2><span class="tiny-label">{{ releaseRows.length }} 个版本</span></div><el-table :data="releaseRows" class="clean-table"><el-table-column label="版本" width="95"><template #default="{ row }"><strong>v{{ row.version }}</strong></template></el-table-column><el-table-column label="来源" min-width="125"><template #default="{ row }">{{ kindName(row.kind) }}{{ row.sourceVersion !== null ? ` · v${row.sourceVersion}` : '' }}</template></el-table-column><el-table-column label="服务器名称" min-width="170"><template #default="{ row }">{{ row.settings.serverName }}</template></el-table-column><el-table-column label="发布时间" min-width="170"><template #default="{ row }">{{ row.version === 0 ? '系统初始化' : formatTime(row.publishedAt) }}</template></el-table-column><el-table-column label="状态" width="110"><template #default="{ row }"><el-tag :type="row.version === store.config?.active.version ? 'success' : 'info'">{{ row.version === store.config?.active.version ? '当前生效' : '历史版本' }}</el-tag></template></el-table-column><el-table-column label="操作" width="130" align="right"><template #default="{ row }"><el-button link type="primary" :icon="RefreshLeft" :disabled="row.version === store.config?.active.version || dirty || working || !supported" @click="openRollback(row)">回滚到此版本</el-button></template></el-table-column><template #empty>暂无发布历史</template></el-table></section>
    <el-dialog v-model="publishOpen" title="发布运营配置" width="500px" :close-on-click-modal="!working" :show-close="!working"><p class="dialog-description">将已保存的草稿 r{{ baseRevision }} 发布为新的生效版本。</p><div class="release-review"><div><span>服务器</span><strong>{{ form.serverName }}</strong></div><div><span>新玩家</span><strong>{{ form.allowNewProfiles ? '开放' : '关闭' }}</strong></div><div><span>新战斗</span><strong>{{ form.allowNewBattles ? '开放' : '关闭' }}</strong></div><div><span>默认关卡</span><strong>{{ encounterName(form.defaultEncounterId) }}</strong></div></div><template #footer><el-button :disabled="working" @click="publishOpen = false">取消</el-button><el-button type="primary" :loading="working" :disabled="dirty" @click="publish">发布生效</el-button></template></el-dialog>
    <el-dialog v-model="rollbackOpen" title="回滚运营配置" width="500px" :close-on-click-modal="!working" :show-close="!working"><template v-if="rollbackRelease"><p class="dialog-description">使用历史 v{{ rollbackRelease.version }} 的设置创建一个新的生效版本，现有发布历史继续保留。</p><div class="release-review"><div><span>服务器</span><strong>{{ rollbackRelease.settings.serverName }}</strong></div><div><span>新玩家</span><strong>{{ rollbackRelease.settings.allowNewProfiles ? '开放' : '关闭' }}</strong></div><div><span>新战斗</span><strong>{{ rollbackRelease.settings.allowNewBattles ? '开放' : '关闭' }}</strong></div><div><span>默认关卡</span><strong>{{ encounterName(rollbackRelease.settings.defaultEncounterId) }}</strong></div></div></template><template #footer><el-button :disabled="working" @click="rollbackOpen = false">取消</el-button><el-button type="primary" :loading="working" :disabled="dirty" @click="rollback">回滚并发布新版本</el-button></template></el-dialog>
  </section>
</template>
