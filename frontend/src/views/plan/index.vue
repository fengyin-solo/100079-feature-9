<template>
  <section class="page" data-module="plan">
    <header class="page-head">
      <div>
        <h2>养护计划管理</h2>
        <p class="page-desc">维护养护计划，围绕计划编号、养护类型、养护对象、计划工期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记养护计划</button>
        <button class="btn" type="button" @click="exportRows">导出养护计划清单</button>
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

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
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
          <td :colspan="columns.length + 1" class="empty-state">暂无养护计划数据，可先登记养护计划</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条养护计划记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="dialogVisible" class="modal-mask" @click.self="closeDialog">
      <div class="modal" role="dialog" aria-modal="true">
        <header class="modal-head">
          <h3>登记养护计划</h3>
          <button class="btn ghost" type="button" @click="closeDialog">关闭</button>
        </header>
        <div class="modal-body">
          <label class="form-field">
            <span>计划编号<em class="required-mark">*</em></span>
            <input
              v-model="form['计划编号']"
              placeholder="请输入计划编号"
              :class="{ 'input-error': fieldErrors['计划编号'] }"
            />
            <small v-if="fieldErrors['计划编号']" class="field-error">{{ fieldErrors['计划编号'] }}</small>
          </label>
          <label class="form-field">
            <span>养护类型<em class="required-mark">*</em></span>
            <input
              v-model="form['养护类型']"
              placeholder="请输入养护类型"
              :class="{ 'input-error': fieldErrors['养护类型'] }"
            />
            <small v-if="fieldErrors['养护类型']" class="field-error">{{ fieldErrors['养护类型'] }}</small>
          </label>
          <label class="form-field">
            <span>养护对象（隧道设施）<em class="required-mark">*</em></span>
            <select
              v-model="form['养护对象']"
              class="form-select"
              :class="{ 'input-error': fieldErrors['养护对象'] }"
            >
              <option value="" disabled>请选择隧道设施</option>
              <option
                v-for="tunnel in tunnelOptions"
                :key="String(tunnel.id)"
                :value="tunnelOptionValue(tunnel)"
                :disabled="isTunnelIncomplete(tunnel)"
              >
                {{ tunnelOptionLabel(tunnel) }}
              </option>
            </select>
            <small class="field-hint">
              长度待完善的隧道仍在列表中标为「待完善」，补齐前不可选为养护对象
            </small>
            <small v-if="fieldErrors['养护对象']" class="field-error">{{ fieldErrors['养护对象'] }}</small>
          </label>
          <label class="form-field">
            <span>计划工期</span>
            <input v-model="form['计划工期']" placeholder="如：2026-10-01～2026-12-31" />
          </label>
        </div>
        <footer class="modal-foot">
          <span v-if="formGlobalError" class="error-text">{{ formGlobalError }}</span>
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
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type TunnelOption = Row

const ENDPOINT = '/api/plan'
const TUNNEL_ENDPOINT = '/api/tunnel'
const columns = ["计划编号", "养护类型", "养护对象", "计划工期", "预算金额", "编制人员", "审批人员", "计划状态"]
const actions = ["提交审批", "确认批复", "作废计划"]
const statuses = ["待编制", "待审批", "已批复", "已作废"]
const stats = [{"label": "待审批计划", "value": 0}, {"label": "已批复计划", "value": 0}, {"label": "本月计划金额", "value": 0}]
const formFields = ["计划编号", "养护类型", "养护对象", "计划工期"]
const requiredFields = ["计划编号", "养护类型", "养护对象"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const tunnelOptions = ref<TunnelOption[]>([])

const dialogVisible = ref(false)
const saving = ref(false)
const formGlobalError = ref('')
const form = reactive<Record<string, string>>(Object.fromEntries(formFields.map((field) => [field, ''])))
const fieldErrors = reactive<Record<string, string>>(Object.fromEntries(formFields.map((field) => [field, ''])))

function isTunnelIncomplete(tunnel: TunnelOption): boolean {
  return tunnel.lengthComplete === false
}

// 待完善隧道不消失：仍然出现在下拉里，只是置灰禁用并在文本上标明原因。
function tunnelOptionLabel(tunnel: TunnelOption): string {
  const code = String(tunnel['隧道编码'] ?? '')
  const name = String(tunnel['隧道名称'] ?? '')
  const base = `${code} ${name}`
  return isTunnelIncomplete(tunnel) ? `${base}（长度待完善）` : base
}

function tunnelOptionValue(tunnel: TunnelOption): string {
  return String(tunnel['隧道编码'] ?? '')
}

function resetForm() {
  for (const field of formFields) {
    form[field] = ''
    fieldErrors[field] = ''
  }
  formGlobalError.value = ''
}

function openCreate() {
  resetForm()
  void loadTunnels()
  dialogVisible.value = true
}

function closeDialog() {
  if (saving.value) return
  dialogVisible.value = false
}

async function loadTunnels() {
  try {
    const response = await request(`${TUNNEL_ENDPOINT}/options`)
    if (!response.ok) return
    const payload = await response.json()
    tunnelOptions.value = payload.items ?? []
  } catch {
    // 下拉失败时保留已有选项，不打断登记操作。
  }
}

async function submitForm() {
  formGlobalError.value = ''
  let ok = true
  for (const field of requiredFields) {
    fieldErrors[field] = form[field].trim() ? '' : `${field}为必填项`
    if (fieldErrors[field]) ok = false
  }
  if (!ok) {
    formGlobalError.value = '表单存在不合法内容，请按提示修改后再保存'
    return
  }
  saving.value = true
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      formGlobalError.value = payload?.message ? String(payload.message) : '养护计划登记失败，请稍后重试'
      return
    }
    dialogVisible.value = false
    await reload()
  } catch (error) {
    formGlobalError.value = error instanceof Error ? error.message : '养护计划登记失败'
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
      throw new Error('养护计划动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护计划操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('养护计划列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护计划列表读取失败'
  }
}

onMounted(reload)
</script>
