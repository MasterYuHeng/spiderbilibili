import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppLayout,
    children: [
      {
        path: '',
        redirect: '/tasks/create',
      },
      {
        path: 'tasks/create',
        name: 'task-create',
        component: () => import('@/views/TaskCreateView.vue'),
        meta: { title: '创建任务' },
      },
      {
        path: 'tasks',
        name: 'task-list',
        component: () => import('@/views/TaskListView.vue'),
        meta: { title: '任务列表' },
      },
      {
        path: 'tasks/trash',
        name: 'task-trash',
        component: () => import('@/views/TaskTrashView.vue'),
        meta: { title: '回收站' },
      },
      {
        path: 'settings/ai',
        name: 'ai-settings',
        component: () => import('@/views/AiSettingsView.vue'),
        meta: { title: '系统设置' },
      },
      {
        path: 'tasks/:taskId',
        name: 'task-detail',
        component: () => import('@/views/TaskDetailView.vue'),
        meta: { title: '任务详情' },
      },
      {
        path: 'tasks/:taskId/videos',
        name: 'task-videos',
        component: () => import('@/views/VideoListView.vue'),
        meta: { title: '视频结果' },
      },
      {
        path: 'tasks/:taskId/topics',
        name: 'task-topics',
        component: () => import('@/views/TopicAnalysisView.vue'),
        meta: { title: '主题分析' },
      },
      {
        path: 'tasks/:taskId/authors',
        name: 'task-authors',
        component: () => import('@/views/AuthorAnalysisView.vue'),
        meta: { title: 'UP 主分析' },
      },
      {
        path: 'tasks/:taskId/report',
        name: 'task-report',
        component: () => import('@/views/TaskReportView.vue'),
        meta: { title: '任务报告' },
      },
      {
        path: 'tasks/:taskId/acceptance',
        name: 'task-acceptance',
        component: () => import('@/views/TaskAcceptanceView.vue'),
        meta: { title: '上线验收' },
      },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})
