<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { DataBoard, User, Avatar, MapLocation, Refresh, Connection, ArrowRight, Monitor, Setting, Document, Collection, Tools } from '@element-plus/icons-vue'
import { useAdminStore } from './stores/admin'
import { formatTime } from './utils/format'

const route = useRoute()
const store = useAdminStore()
const groups = [
  { title: '运营管理', items: [
    { path: '/overview', title: '运营总览', icon: DataBoard },
    { path: '/profiles', title: '玩家管理', icon: User },
    { path: '/config', title: '运营配置', icon: Setting },
    { path: '/logs', title: '操作日志', icon: Document },
  ] },
  { title: '游戏内容', items: [
    { path: '/heroes', title: '角色目录', icon: Avatar },
    { path: '/cards', title: '卡牌目录', icon: Collection },
    { path: '/encounters', title: '关卡目录', icon: MapLocation },
  ] },
  { title: '开发工具', items: [{ path: '/tools/recovery', title: '资源恢复', icon: Tools }] },
]
onMounted(() => store.refresh())
</script>

<template>
  <div class="admin-shell">
    <aside class="sidebar">
      <router-link to="/overview" class="brand">
        <span class="brand-mark"><svg viewBox="0 0 40 40" aria-hidden="true"><path d="M10 27V13h4v5l9-5h6l-13 8 13 6h-7l-8-4v4z" fill="currentColor" /></svg></span>
        <span><strong>黑潮之上</strong><small>GAME OPERATIONS</small></span>
      </router-link>
      <nav aria-label="管理导航">
        <template v-for="group in groups" :key="group.title">
        <div class="nav-label">{{ group.title }}</div>
        <router-link v-for="item in group.items" :key="item.path" :to="item.path" class="nav-item">
          <el-icon :size="19"><component :is="item.icon" /></el-icon><span>{{ item.title }}</span>
          <span v-if="item.path === '/heroes' && store.heroes" class="nav-count">{{ store.heroes.heroes.length }}</span>
        </router-link>
        </template>
      </nav>
      <div class="sidebar-bottom">
        <div class="local-badge"><span class="status-dot"></span>个人本地环境</div>
        <p>Unreal Engine 5 客户端<br />Node.js · MongoDB 服务端</p>
        <div class="sidebar-version">游戏管理后台 <span>v0.1</span></div>
      </div>
    </aside>
    <div class="main-shell">
      <header class="topbar">
        <div class="breadcrumbs"><span>{{ route.meta.section }}</span><el-icon><ArrowRight /></el-icon><strong>{{ route.meta.title }}</strong></div>
        <div class="topbar-actions">
          <span class="api-status" :class="{ offline: !!store.error }"><el-icon><Connection /></el-icon>{{ store.error ? '服务连接异常' : store.loaded ? '本地服务已连接' : '连接中' }}</span>
          <el-button class="refresh-button" :icon="Refresh" :loading="store.loading" @click="store.refresh()">刷新数据</el-button>
          <span class="admin-avatar" title="本地管理模式"><el-icon :size="19"><Monitor /></el-icon></span>
        </div>
      </header>
      <main>
        <div v-if="store.error" class="global-error" role="alert">
          <el-alert :title="store.error" type="error" show-icon :closable="false" />
        </div>
        <router-view />
      </main>
      <footer class="app-footer"><span>黑潮之上 · 本地游戏管理后台</span><span>{{ store.lastLoadedAt ? `最近读取 ${formatTime(store.lastLoadedAt)}` : '等待真实服务数据' }}</span></footer>
    </div>
  </div>
</template>
