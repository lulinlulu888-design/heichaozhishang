import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { adminApi } from '../api/admin'
import type { EncounterDirectory, HeroDirectory, Overview, Profile, Catalog, OperationalConfig, AuditLogs } from '../api/types'

export const useAdminStore = defineStore('admin', () => {
  const heroes = ref<HeroDirectory | null>(null)
  const profiles = ref<Profile[]>([])
  const encounters = ref<EncounterDirectory | null>(null)
  const overview = ref<Overview | null>(null)
  const catalog = ref<Catalog | null>(null)
  const config = ref<OperationalConfig | null>(null)
  const logs = ref<AuditLogs | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref('')
  const lastLoadedAt = ref<number | null>(null)
  const hallReady = computed(() => heroes.value?.heroes.filter(hero => hero.availability.hallPreview === 'verified') ?? [])
  const ueReady = computed(() => hallReady.value.filter(hero => hero.hallPreviewVerification?.renderer === 'unreal-editor'))
  let inFlight: Promise<void> | null = null

  async function refresh() {
    if (inFlight) return inFlight
    inFlight = (async () => {
      loading.value = true
      error.value = ''
      try {
        const [nextHeroes, nextProfiles, nextEncounters, nextOverview, nextCatalog, nextConfig, nextLogs] = await Promise.all([
          adminApi.heroes(), adminApi.profiles(), adminApi.encounters(), adminApi.overview(),
          adminApi.cards(), adminApi.config(), adminApi.logs(),
        ])
        heroes.value = nextHeroes
        profiles.value = nextProfiles.profiles
        encounters.value = nextEncounters
        overview.value = nextOverview
        catalog.value = nextCatalog
        config.value = nextConfig
        logs.value = nextLogs
        loaded.value = true
        lastLoadedAt.value = Date.now()
      } catch (cause) {
        error.value = cause instanceof Error ? cause.message : '读取管理数据失败'
      } finally { loading.value = false; inFlight = null }
    })()
    return inFlight
  }

  async function refreshProfiles() { profiles.value = (await adminApi.profiles()).profiles }
  async function refreshConfig() { config.value = await adminApi.config(); return config.value }
  async function refreshLogs() { logs.value = await adminApi.logs() }
  function heroName(id: number | null) { return id === null ? '未选择' : heroes.value?.heroes.find(hero => hero.id === id)?.name ?? `角色 #${id}` }
  return { heroes, profiles, encounters, overview, catalog, config, logs, loading, loaded, error, lastLoadedAt, hallReady, ueReady, refresh, refreshProfiles, refreshConfig, refreshLogs, heroName }
})
