import { request } from './http'
import type { EncounterDirectory, HeroDirectory, Overview, Profile, ProfileDetail, Hall, Catalog, OperationalConfig, OperationalSettings, AuditLogs } from './types'

const profilePath = (id: string) => `/profiles/${encodeURIComponent(id)}`
export const adminApi = {
  overview: () => request<Overview>('/overview'),
  heroes: () => request<HeroDirectory>('/heroes'),
  profiles: () => request<{ profiles: Profile[] }>('/profiles'),
  profile: (id: string) => request<ProfileDetail>(profilePath(id)),
  encounters: () => request<EncounterDirectory>('/encounters'),
  cards: () => request<Catalog>('/cards'),
  config: () => request<OperationalConfig>('/config'),
  logs: () => request<AuditLogs>('/logs'),
  saveConfigDraft: (expectedRevision: number, settings: OperationalSettings) => request<OperationalConfig>('/config/draft', { method: 'PATCH', body: { expectedRevision, settings } }),
  publishConfig: (expectedRevision: number, requestId: string) => request<{ config: OperationalConfig; replayed: boolean }>('/config/publish', { method: 'POST', body: { expectedRevision, requestId } }),
  rollbackConfig: (expectedRevision: number, version: number, requestId: string) => request<{ config: OperationalConfig; replayed: boolean }>('/config/rollback', { method: 'POST', body: { expectedRevision, version, requestId } }),
  createProfile: (displayName: string) => request<{ profile: Profile }>('/profiles', { method: 'POST', body: { displayName } }),
  renameProfile: (id: string, expectedRevision: number, displayName: string) => request<{ profile: Profile }>(profilePath(id), { method: 'PATCH', body: { expectedRevision, displayName } }),
  selectHallHero: (id: string, expectedRevision: number, selectedHeroId: number | null, requestId: string) => request<{ hall: Hall; replayed: boolean }>(`${profilePath(id)}/hall`, { method: 'PATCH', body: { expectedRevision, selectedHeroId, requestId } }),
}
