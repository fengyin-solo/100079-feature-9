<template>
  <section class="page" data-module="tunnel">
    <header class="page-head">
      <div>
        <h2>隧道设施管理</h2>
        <p class="page-desc">维护隧道设施，围绕隧道编码、隧道名称、隧道长度、断面形式做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记隧道设施</button>
        <button class="btn" type="button" @click="exportRows">导出隧道设施清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="incompleteCount > 0" class="notice-bar">
      检测到 <strong>{{ incompleteCount }}</strong> 条隧道长度缺失或不可用的异常记录（行内标「长度待完善」），补齐前可在养护对象下拉中选择但会标注待完善。
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-incomplete': row.长度待完善 }">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '隧道长度'">
              <span v-if="!row.长度待完善">{{ row[column] }}</span>
              <span v-else class="incomplete-cell">
                <em>待完善</em>
                <small>{{ row.长度问题 }}</small>
              </span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">编辑</button>
            <button
              v-if="row.长度待完善"
              class="link warning"
              type="button"
              @click="openFillLength(row)"
            >
              补齐长度
            </button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无隧道设施数据，可先登记隧道设施</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条隧道设施记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <div class="modal">
        <h3 class="modal-title">{{ formTitle }}</h3>
        <form @submit.prevent="submitForm">
          <label v-for="field in formFields" :key="field" class="form-item" :class="{ required: formRequired.includes(field) }">
            <span>{{ field }}</span>
            <input
              v-model="formValues[field]"
              :ref="field === '隧道长度' && lengthFocus ? setLengthInput : undefined"
              :placeholder="field === '隧道长度' ? lengthHint : `请输入${field}`"
              @input="field === '隧道长度' ? clearError('length') : clearError('common')"
            />          </label>
          <p v-if="formError.length" class="form-error error-text">{{ formError.length }}</p>
          <p v-if="formError.common" class="form-error error-text">{{ formError.common }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="closeForm">取消</button>
            <button class="btn primary" type="submit" :disabled="submitting">
              {{ submitting ? '保存中…' : '保存' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { ComponentPublicInstance } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

interface LengthRange { min: number; max: number; unit: string }

const ENDPOINT = '/api/tunnel'
const columns = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式", "管养单位", "隧道状态"]
const formFields = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式", "管养单位"]
const formRequired = ["隧道编码", "隧道名称", "隧道长度"]
const actions = ["办理移交", "安排检修", "停用隧道"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const lengthRange = ref<LengthRange>({ min: 0.1, max: 50000, unit: '米' })

const stats = computed(() => {
  const normal = rows.value.filter(row => row.status === '正常养护').length
  const inspecting = rows.value.filter(row => row.status === '检修封闭').length
  const totalLength = rows.value.reduce(
    (sum, row) => (row.长度待完善 ? sum : sum + Number(row.隧道长度 || 0)),
    0,
  )
  return [
    { label: "在养隧道", value: normal },
    { label: "检修中隧道", value: inspecting },
    { label: "隧道总长（米）", value: Math.round(totalLength * 100) / 100 },
  ]
})
const incompleteCount = computed(() => rows.value.filter(row => row.长度待完善).length)

const lengthHint = computed(
  () => `请输入数字，允许区间 ${lengthRange.value.min}～${lengthRange.value.max} ${lengthRange.value.unit}`,
)

const formVisible = ref(false)
const formTitle = ref('登记隧道设施')
const submitting = ref(false)
const lengthFocus = ref(false)
const editingId = ref<number | null>(null)
const formValues = reactive<Record<string, string>>({})
const formError = reactive<{ length: string; common: string }>({ length: '', common: '' })

function resetForm() {
  for (const field of formFields) {
    formValues[field] = ''
  }
  formError.length = ''
  formError.common = ''
  lengthFocus.value = false
}

function setLengthInput(el: Element | ComponentPublicInstance | null) {
  const input = el instanceof Element ? el : (el?.$el ?? null)
  if (input instanceof HTMLInputElement) {
    input.focus()
  }
}

function openCreate() {
  editingId.value = null
  formTitle.value = '登记隧道设施'
  resetForm()
  formVisible.value = true
}

function openEdit(row: Row) {
  editingId.value = Number(row.id)
  formTitle.value = '修改隧道设施'
  resetForm()
  for (const field of formFields) {
    formValues[field] = row.长度待完善 && field === '隧道长度' ? '' : String(row[field] ?? '')
  }
  formVisible.value = true
}

function openFillLength(row: Row) {
  openEdit(row)
  formTitle.value = '补齐隧道长度'
  lengthFocus.value = true
}

function closeForm() {
  formVisible.value = false
  editingId.value = null
}

function clearError(key: 'length' | 'common') {
  formError[key] = ''
}

/** 与后端同一口径：必填 + 数字 + 区间，非数字或超区间直接拦下并说明原因。 */
function validateLength(raw: string): string {
  const text = raw.trim()
  if (!text) {
    return '隧道长度为必填项，请填写数字长度（单位：米）'
  }
  if (!/^-?\d+(\.\d+)?$/.test(text)) {
    return `隧道长度「${text}」不是有效数字，需填写以米为单位的数值`
  }
  const value = Number(text)
  const { min, max, unit } = lengthRange.value
  if (value < min || value > max) {
    return `隧道长度允许区间为 ${min}～${max} ${unit}，当前填写 ${value} ${unit}，超出区间`
  }
  return ''
}

async function submitForm() {
  errorMessage.value = ''
  const missing = formRequired.filter(field => !formValues[field].trim())
  formError.common = missing.length ? `缺少必填字段：${missing.join('、')}` : ''
  formError.length = missing.includes('隧道长度') ? '' : validateLength(formValues.隧道长度)
  if (formError.common || formError.length) {
    return
  }
  submitting.value = true
  try {
    const url = editingId.value === null ? ENDPOINT : `${ENDPOINT}/${editingId.value}`
    const response = await request(url, {
      method: editingId.value === null ? 'POST' : 'PUT',
      body: JSON.stringify({ values: { ...formValues } }),
    })
    if (!response.ok) {
      throw new Error('隧道设施保存未生效，请稍后重试')
    }
    const payload = await response.json()
    if (payload && payload.ok === false) {
      const message = String(payload.message || '隧道设施保存失败')
      if (message.includes('隧道长度')) {
        formError.length = message
      } else {
        formError.common = message
      }
      return
    }
    closeForm()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隧道设施保存失败'
  } finally {
    submitting.value = false
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('隧道设施动作未生效，请稍后重试')
    }
    const payload = await response.json().catch(() => null)
    if (payload && payload.ok === false) {
      throw new Error(String(payload.message || '隧道设施操作失败'))
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隧道设施操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, optionsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/options`),
    ])
    if (!listResponse.ok) {
      throw new Error('隧道设施列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (optionsResponse.ok) {
      const optionsPayload = await optionsResponse.json()
      if (optionsPayload.lengthRange) {
        lengthRange.value = optionsPayload.lengthRange
      }
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隧道设施列表读取失败'
  }
}

onMounted(reload)
</script>
