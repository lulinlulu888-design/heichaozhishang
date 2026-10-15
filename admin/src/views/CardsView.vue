<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, Collection } from '@element-plus/icons-vue'
import { useAdminStore } from '../stores/admin'
import type { CardRecord } from '../api/types'

const store = useAdminStore()
const query = ref('')
const cost = ref<number | undefined>()
const page = ref(1)
const detailOpen = ref(false)
const selected = ref<CardRecord | null>(null)
const costs = computed(() => [...new Set(store.catalog?.cards.map(card => card.cost) ?? [])].sort((a,b) => a-b))
const filtered = computed(() => (store.catalog?.cards ?? []).filter(card => `${card.id} ${card.name} ${card.skillId}`.includes(query.value.trim()) && (cost.value === undefined || card.cost === cost.value)))
const rows = computed(() => filtered.value.slice((page.value - 1) * 12, page.value * 12))
function detail(card: CardRecord) { selected.value = card; detailOpen.value = true }
</script>

<template>
  <section class="page"><div class="page-heading"><div><span class="eyebrow">GAME CONTENT · CARDS</span><h1>卡牌目录</h1><p>查看当前内容库提供的卡牌属性、技能引用和原始描述。</p></div><el-tag effect="plain" class="heading-tag">内容样本</el-tag></div><section class="panel heroes-panel"><div class="table-toolbar"><div class="catalog-count"><el-icon><Collection /></el-icon><strong>{{ store.catalog?.cards.length ?? '—' }}</strong><span>个卡牌记录</span></div><div class="content-filters"><el-select v-model="cost" placeholder="全部消耗" clearable style="width:140px" @change="page = 1"><el-option v-for="value in costs" :key="value" :value="value" :label="`消耗 ${value}`" /></el-select><el-input v-model="query" class="search-input" placeholder="搜索名称 / 卡牌或技能 ID" :prefix-icon="Search" clearable @input="page = 1" /></div></div><el-table :data="rows" v-loading="store.loading" class="clean-table"><el-table-column prop="id" label="卡牌 ID" width="120" /><el-table-column label="卡牌名称" min-width="170"><template #default="{ row }"><div class="table-profile"><span class="card-monogram"><el-icon><Collection /></el-icon></span><strong>{{ row.name }}</strong></div></template></el-table-column><el-table-column prop="cost" label="能量消耗" width="110" /><el-table-column prop="level" label="等级" width="82" /><el-table-column prop="skillId" label="技能 ID" width="118" /><el-table-column prop="story" label="原始描述" min-width="270" show-overflow-tooltip /><el-table-column label="详情" width="80" align="right"><template #default="{ row }"><el-button link type="primary" @click="detail(row)">查看</el-button></template></el-table-column><template #empty>没有符合条件的卡牌</template></el-table><div class="table-footer"><span>共 {{ filtered.length }} 个卡牌</span><el-pagination v-model:current-page="page" :page-size="12" :total="filtered.length" layout="prev, pager, next" /></div></section><p class="content-source-note">当前 catalog 提供 {{ store.catalog?.cards.length ?? '—' }} 个原始卡牌样本；源卡牌表包含 {{ store.catalog?.sources.cards.sourceRowCount ?? '—' }} 行。样本不等于完整卡库，技能 ID 不是已求值伤害，未添加推测的攻击数值。</p><el-drawer v-model="detailOpen" title="卡牌内容详情" size="480px"><div v-if="selected" class="hero-detail"><div class="hero-detail-heading"><span class="hero-initial"><el-icon><Collection /></el-icon></span><div><h2>{{ selected.name }}</h2><span>CARD #{{ selected.id }}</span></div></div><el-descriptions :column="1" border><el-descriptions-item label="卡牌 ID">{{ selected.id }}</el-descriptions-item><el-descriptions-item label="能量消耗">{{ selected.cost }}</el-descriptions-item><el-descriptions-item label="等级">{{ selected.level }}</el-descriptions-item><el-descriptions-item label="技能 ID">{{ selected.skillId }}</el-descriptions-item><el-descriptions-item label="图像资源路径">{{ selected.characterImagePath }}</el-descriptions-item></el-descriptions><h3>原始描述</h3><p class="evidence-text">{{ selected.story }}</p><h3>源表</h3><code class="hash-block">{{ store.catalog?.sources.cards.module }}</code></div></el-drawer></section>
</template>
