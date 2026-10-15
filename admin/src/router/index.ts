import { createRouter, createWebHashHistory } from 'vue-router'

export default createRouter({
  history: createWebHashHistory(),
  scrollBehavior: (to, from) => to.path === from.path ? false : { top: 0, left: 0 },
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', component: () => import('../views/OverviewView.vue'), meta: { title: '运营总览', section: '运营管理' } },
    { path: '/heroes', component: () => import('../views/HeroesView.vue'), meta: { title: '角色目录', section: '游戏内容' } },
    { path: '/profiles', component: () => import('../views/ProfilesView.vue'), meta: { title: '玩家管理', section: '运营管理' } },
    { path: '/cards', component: () => import('../views/CardsView.vue'), meta: { title: '卡牌目录', section: '游戏内容' } },
    { path: '/config', component: () => import('../views/ConfigView.vue'), meta: { title: '运营配置', section: '运营管理' } },
    { path: '/logs', component: () => import('../views/LogsView.vue'), meta: { title: '操作日志', section: '运营管理' } },
    { path: '/tools/recovery', component: () => import('../views/RecoveryToolsView.vue'), meta: { title: '资源恢复', section: '开发工具' } },
    { path: '/encounters', component: () => import('../views/EncountersView.vue'), meta: { title: '关卡目录', section: '游戏内容' } },
    { path: '/:pathMatch(.*)*', redirect: '/overview' },
  ],
})
