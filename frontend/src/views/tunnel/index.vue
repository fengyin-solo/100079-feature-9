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
        <strong class="stat-value" :class="{ 'stat-warn': item.warn }">{{ item.value }}</strong>
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

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-incomplete': isIncomplete(row) }">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '隧道长度'">
              <template v-if="isIncomplete(row)">
                <span v-if="hasLengthValue(row)" class="text-warn">{{ row[column] }}</span>
                <span v-else class="text-warn">缺失</span>
                <span class="badge warn" :title="lengthIssue(row)">待完善</span>
              </template>
              <template v-else>{{ row[column] }}</template>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">修改</button>
            <button v-if="isIncomplete(row)" class="link warn-link" type="button" @click="openComplete(row)">
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

    <div v-if="dialogVisible" class="modal-mask" @click.self="closeDialog">
      <div class="modal" role="dialog" aria-modal="true">
        <header class="modal-head">
          <h3>{{ dialogTitle }}</h3>
          <button class="btn ghost" type="button" @click="closeDialog">关闭</button>
        </header>
        <div v-if="completing" class="modal-banner">
          该记录为历史异常数据：{{ completingIssue }}。补齐合法长度后才会恢复为可关联的正常记录。
        </div>
        <form class="modal-body" @submit.prevent="submitForm">
          <label v-for="field in formFields" :key="field" class="form-field">
            <span>{{ field }}<em v-if="requiredFields.includes(field)" class="required-mark">*</em></span>
            <input
              v-model="form[field]"
              :data-field="field"
              :placeholder="field === '隧道长度' ? lengthHint : `请输入${field}`"
              :class="{ 'input-error': fieldErrors[field] }"
            />
            <small v-if="field === '隧道长度'" class="field-hint">{{ lengthHint }}</small>
            <small v-if="fieldErrors[field]" class="field-error">{{ fieldErrors[field] }}</small>
          </label>
        </form>
        <footer class="modal-foot">
          <span v-if="formGlobalError" class="error-text">{{ formGlobalError }}</span>
          <span v-else-if="saving" class="field-hint">正在保存…</span>
          <div class="modal-actions">
            <button class="btn ghost" type="button" @click="closeDialog">取消</button>
            <button class="btn primary" type="button" :disabled="saving" @click="submitForm">保存</button>
          </div>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/tunnel'
const columns = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式", "管养单位", "隧道状态"]
const formFields = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式", "管养单位"]
const requiredFields = ["隧道编码", "隧道名称", "隧道长度"]
const actions = ["办理移交", "安排检修", "停用隧道"]

// 隧道长度合法区间（米），需与后端 app/services/tunnel.py 的 LENGTH_MIN_M/LENGTH_MAX_M 保持一致。
const LENGTH_MIN = 0.1
const LENGTH_MAX = 50000
const lengthHint = `单位：米，允许区间 ${LENGTH_MIN}～${LENGTH_MAX}，且必须为数字`

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const stats = ref([
  { label: "在养隧道", value: 0, warn: false },
  { label: "检修中隧道", value: 0, warn: false },
  { label: "长度待完善", value: 0, warn: true },
  { label: "隧道总长(米)", value: 0, warn: false },
])

const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const editingId = ref<number | null>(null)
// 标记本次弹窗是否由「补齐长度」入口打开，仅用于提示文案，不影响保存口径。
const completing = ref(false)
const completingIssue = ref('')
const saving = ref(false)
const formGlobalError = ref('')
const form = reactive<Record<string, string>>(Object.fromEntries(formFields.map((field) => [field, ''])))
const fieldErrors = reactive<Record<string, string>>(Object.fromEntries(formFields.map((field) => [field, ''])))
const lengthInputRef = ref<HTMLInputElement | null>(null)

const dialogTitle = computed(() => {
  if (dialogMode.value === 'create') return '登记隧道设施'
  return completing.value ? '补齐隧道长度' : '修改隧道设施'
})

function isIncomplete(row: Row): boolean {
  return row.lengthComplete === false
}

function hasLengthValue(row: Row): boolean {
  return String(row['隧道长度'] ?? '').trim() !== ''
}

function lengthIssue(row: Row): string {
  return typeof row.lengthIssue === 'string' ? row.lengthIssue : '隧道长度待完善'
}

function resetForm(source?: Row) {
  for (const field of formFields) {
    const value = source?.[field]
    form[field] = value === null || value === undefined ? '' : String(value)
    fieldErrors[field] = ''
  }
  formGlobalError.value = ''
}

function openCreate() {
  dialogMode.value = 'create'
  editingId.value = null
  completing.value = false
  completingIssue.value = ''
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: Row) {
  dialogMode.value = 'edit'
  editingId.value = Number(row.id)
  completing.value = false
  completingIssue.value = ''
  resetForm(row)
  dialogVisible.value = true
}

function openComplete(row: Row) {
  openEdit(row)
  completing.value = true
  completingIssue.value = lengthIssue(row)
  // 入口恒定：每次打开都把光标准备到长度输入框，提示用户只需补这一项。
  window.setTimeout(() => {
    lengthInputRef.value = document.querySelector<HTMLInputElement>('.modal input[data-field="隧道长度"]')
    lengthInputRef.value?.focus()
  }, 0)
}

function closeDialog() {
  if (saving.value) return
  dialogVisible.value = false
}

// 与后端同一套口径：空、非数字、超区间分别给出不同原因，校验不过不发请求。
function validateLength(raw: string): string {
  const text = raw.trim()
  if (!text) return '隧道长度缺失，请填写长度'
  const number = Number(text)
  if (!Number.isFinite(number)) {
    return `隧道长度必须是数字（米），当前填写「${text}」无法识别`
  }
  if (number < LENGTH_MIN || number > LENGTH_MAX) {
    return `隧道长度超出允许区间：${LENGTH_MIN}～${LENGTH_MAX} 米，当前填写 ${number} 米`
  }
  return ''
}

function validateForm(): boolean {
  let ok = true
  for (const field of requiredFields) {
    fieldErrors[field] = form[field].trim() ? '' : `${field}为必填项`
    if (fieldErrors[field]) ok = false
  }
  const lengthError = validateLength(form['隧道长度'])
  fieldErrors['隧道长度'] = lengthError || fieldErrors['隧道长度']
  if (lengthError) ok = false
  return ok
}

async function submitForm() {
  formGlobalError.value = ''
  if (!validateForm()) {
    formGlobalError.value = '表单存在不合法内容，请按提示修改后再保存'
    return
  }
  saving.value = true
  try {
    const url = dialogMode.value === 'create'
      ? ENDPOINT
      : `${ENDPOINT}/${editingId.value}`
    const response = await request(url, {
      method: dialogMode.value === 'create' ? 'POST' : 'PUT',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      // 后端复核未过时，把原因直接展示出来，不允许静默保存。
      formGlobalError.value = payload?.message ? String(payload.message) : '保存失败，请稍后重试'
      return
    }
    dialogVisible.value = false
    await Promise.all([reload(), loadOptions()])
  } catch (error) {
    formGlobalError.value = error instanceof Error ? error.message : '隧道设施保存失败'
  } finally {
    saving.value = false
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
    await Promise.all([reload(), loadOptions()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隧道设施操作失败'
  }
}

// 全量隧道（含待完善）只用于统计卡片；表格仍走原来的筛选分页查询。
async function loadOptions() {
  try {
    const response = await request(`${ENDPOINT}/options`)
    if (!response.ok) return
    const payload = await response.json()
    const items: Row[] = payload.items ?? []
    let inCare = 0
    let repairing = 0
    let incomplete = 0
    let totalLength = 0
    for (const item of items) {
      if (item.status === '正常养护') inCare += 1
      if (item.status === '检修封闭') repairing += 1
      if (isIncomplete(item)) {
        incomplete += 1
      } else {
        const number = Number(item['隧道长度'])
        if (Number.isFinite(number)) totalLength += number
      }
    }
    stats.value[0].value = inCare
    stats.value[1].value = repairing
    stats.value[2].value = incomplete
    stats.value[3].value = Math.round(totalLength * 100) / 100
  } catch {
    // 统计不影响主列表，静默保留原值即可。
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('隧道设施列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '隧道设施列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadOptions()
})
</script>
