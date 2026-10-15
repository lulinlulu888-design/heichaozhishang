<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, ArrowRight } from '@element-plus/icons-vue'
import { useAdminStore } from '../stores/admin'
import type { Hero } from '../api/types'

const store = useAdminStore()
const query = ref('')
const page = ref(1)
const selected = ref<Hero | null>(null)
const detailOpen = ref(false)
const filtered = computed(() => (store.heroes?.heroes ?? []).filter(hero => `${hero.id} ${hero.name}`.includes(query.value.trim())))
const rows = computed(() => filtered.value.slice((page.value - 1) * 12, page.value * 12))
const character = computed(() => store.catalog?.characters.find(item => item.id === selected.value?.id))
const englishName = (id: number) => store.catalog?.characters.find(item => item.id === id)?.englishName ?? '—'
function detail(hero: Hero) { selected.value = hero; detailOpen.value = true }
</script>

<template>
  <section class="page"><div class="page-heading"><div><span class="eyebrow">GAME CONTENT · CHARACTERS</span><h1>角色目录</h1><p>查看角色名称、ID 和当前提供的原始内容资料。</p></div><router-link to="/tools/recovery" class="text-link">资源恢复工具 <el-icon><ArrowRight /></el-icon></router-link></div><section class="panel heroes-panel"><div class="table-toolbar"><div class="catalog-count"><strong>{{ store.heroes?.heroes.length ?? '—' }}</strong><span>个角色记录</span></div><el-input v-model="query" class="search-input" placeholder="搜索角色名称 / ID" :prefix-icon="Search" clearable @input="page = 1" /></div><el-table :data="rows" v-loading="store.loading" class="clean-table"><el-table-column prop="id" label="角色 ID" width="100" /><el-table-column label="角色名称" min-width="230"><template #default="{ row }"><div class="table-profile"><span class="small-avatar" :class="{ pink: row.id === 33 }">{{ row.name.slice(0, 1) }}</span><strong>{{ row.name }}</strong><span v-if="row.id === 1" class="priority-pill">当前客户端优先</span></div></template></el-table-column><el-table-column label="英文名称" min-width="220"><template #default="{ row }"><span>{{ englishName(row.id) }}</span></template></el-table-column><el-table-column label="内容类型" min-width="130"><template #default>角色目录</template></el-table-column><el-table-column label="详情" width="90" align="right"><template #default="{ row }"><el-button type="primary" link @click="detail(row)">查看</el-button></template></el-table-column><template #empty>{{ store.loading ? '正在读取目录…' : '没有符合条件的角色' }}</template></el-table><div class="table-footer"><span>共 {{ filtered.length }} 个角色</span><el-pagination v-model:current-page="page" :page-size="12" :total="filtered.length" layout="prev, pager, next" /></div></section><p class="content-source-note">角色目录来自 APK 原始数据。未提供的属性保持空缺；角色所有权、初始发放及完整战斗能力不由目录记录推断。</p><el-drawer v-model="detailOpen" title="角色内容详情" size="480px"><div v-if="selected" class="hero-detail"><div class="hero-detail-heading"><span class="hero-initial">{{ selected.name.slice(0, 1) }}</span><div><h2>{{ selected.name }}</h2><span>CHARACTER #{{ selected.id }}</span></div></div><el-descriptions :column="1" border><el-descriptions-item label="原始角色 ID">{{ selected.id }}</el-descriptions-item><el-descriptions-item label="名称">{{ selected.name }}</el-descriptions-item><el-descriptions-item label="英文名称">{{ character?.englishName ?? '源投影暂未提供' }}</el-descriptions-item><el-descriptions-item label="头像资源路径">{{ character?.portraitPath ?? '源投影暂未提供' }}</el-descriptions-item><el-descriptions-item label="客户端优先级">{{ selected.id === 1 ? '艾尔莎 · 当前优先接入' : '—' }}</el-descriptions-item><el-descriptions-item label="初始发放规则">未验证，不推断为默认拥有</el-descriptions-item></el-descriptions><h3>当前内容来源</h3><p class="evidence-text">角色表目录包含 {{ store.heroes?.heroes.length }} 个 UseRole=1 角色。英文名称与头像路径由当前 catalog 投影提供，仅覆盖 {{ store.catalog?.characters.length ?? '—' }} 个记录；其他角色字段继续等待真实内容导入。</p><router-link to="/tools/recovery" class="text-link" @click="detailOpen = false">查看恢复进度与逆向证据 <el-icon><ArrowRight /></el-icon></router-link></div></el-drawer></section>
</template>
