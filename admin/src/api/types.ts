export interface Hero {
  id: number
  name: string
  availability: { hallPreview: 'verified' | 'not-integrated'; fullBattle: 'not-verified' | 'verified' }
  hallPreviewVerification?: {
    renderer: string
    platform: string
    sourceAnimation?: string
    evidence?: string
    verification?: string
    sourceModelSha256?: string
  }
}

export interface HeroDirectory {
  schemaVersion: number
  contentId: string
  recoveryPolicy: string
  sources: { apkSha256: string; module: string; sourceRowCount: number; selectedRowCount: number; filter: string }
  heroes: Hero[]
}

export interface Profile {
  id: string
  displayName: string
  selectedCharacterId: number | null
  revision: number
  createdAt: number
  updatedAt: number
}

export interface Hall {
  profileId: string
  revision: number
  selectedHeroId: number | null
  updatedAt: number | null
}

export interface BattleSummary {
  id: string
  revision: number
  definitionId: string
  status: string
  round: number
  createdAt: number
  updatedAt: number
}

export interface ProfileDetail { profile: Profile; hall: Hall | null; battles: BattleSummary[] }

export interface Encounter {
  id: string
  title: string
  notice: string
  definitionId: string
  classification: string
  source: { challengeId?: number; battleId?: number } | null
  player: { id: number | string; name: string }
  enemy: { id: number | string; name: string }
}

export interface EncounterDirectory {
  schemaVersion: number
  contentId: string
  defaultEncounterId: string
  originalUnlockBehaviorVerified: boolean
  rewardsImplemented: boolean
  encounters: Encounter[]
}

export interface Overview {
  service: {
    service: string
    apiVersion: number
    saveSchemaVersion: number
    storage: string
    capabilities: string[]
    gameplayReady: boolean
    battleMode: string | null
  }
  counts: { profiles: number; battles: number; heroes: number; hallVerified: number }
  content: { catalogId: string; heroesId: string | null; encountersId: string | null }
  policy: { access: string; authentication: string; legacyProtocolCompatible: boolean }
  generatedAt: number
}

export interface CardRecord {
  id: number
  name: string
  cost: number
  level: number
  story: string
  characterImagePath: string
  skillId: number
}

export interface CharacterRecord { id: number; name: string; englishName: string; portraitPath: string }
export interface Catalog {
  schemaVersion: number
  contentId: string
  scope: string
  characters: CharacterRecord[]
  cards: CardRecord[]
  sources: Record<'characters' | 'cards', { module: string; npkIndex: number; decodedSha256: string; sourceRowCount: number }>
}

export interface OperationalSettings {
  serverName: string
  motd: string
  allowNewProfiles: boolean
  allowNewBattles: boolean
  defaultEncounterId: string | null
}
export interface ConfigDraft { revision: number; settings: OperationalSettings; updatedAt: number | null }
export interface ConfigRelease {
  version: number
  settings: OperationalSettings
  publishedAt: number | null
  kind: string
  sourceVersion: number | null
}
export interface OperationalConfig {
  supported: boolean
  draft: ConfigDraft
  active: ConfigRelease
  releases: ConfigRelease[]
}
export interface AuditLog {
  id: string
  action: string
  actor: string
  targetType: string
  targetId: string
  summary: {
    displayName?: string
    revision: number
    selectedHeroId?: number | null
    requestId?: string
    version?: number
    sourceVersion?: number | null
    settings?: OperationalSettings
  }
  occurredAt: number
}
export interface AuditLogs { supported: boolean; logs: AuditLog[] }
