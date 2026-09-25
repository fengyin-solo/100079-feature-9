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

    <div v-if="formVisible" class="modal-mask" @click.self="closeForm">
      <div class="modal">
        <h3 class="modal-title">登记养护计划</h3>
        <form @submit.prevent="submitForm">
          <label class="form-item required">
            <span>计划编号</span>
            <input v-model="formValues.计划编号" placeholder="请输入计划编号" @input="formError.common = ''" />
          </label>
          <label class="form-item required">
            <span>养护类型</span>
            <input v-model="formValues.养护类型" placeholder="如：日常养护、专项养护" @input="formError.common = ''" />
          </label>
          <label class="form-item required">
            <span>养护对象（隧道）</span>
            <select v-model="formValues.养护对象" @change="formError.common = ''">
              <option value="" disabled>请选择隧道设施</option>
              <option
                v-for="option in tunnelOptions"
                :key="String(option.id)"
                :value="optionLabel(option)"
                :disabled="option.长度待完善"
              >
                {{ optionLabel(option) }}{{ option.长度待完善 ? '（长度待完善，请先补齐）' : '' }}
              </option>
            </select>
            <small v-if="incompleteOptionCount > 0" class="option-hint">
              有 {{ incompleteOptionCount }} 条隧道长度待完善，仍在下拉中保留但暂不可选为养护对象，请先到隧道设施页补齐。
            </small>
          </label>
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

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type TunnelOption = {
  id: number
  隧道编码: string
  隧道名称: string
  隧道长度: number | null
  长度待完善: boolean
  长度问题: string | null
}

const ENDPOINT = '/api/plan'
const TUNNEL_ENDPOINT = '/api/tunnel'
const columns = ["计划编号", "养护类型", "养护对象", "计划工期", "预算金额", "编制人员", "审批人员", "计划状态"]
const actions = ["提交审批", "确认批复", "作废计划"]
const statuses = ["待编制", "待审批", "已批复", "已作废"]
const stats = [{"label": "待审批计划", "value": 0}, {"label": "已批复计划", "value": 0}, {"label": "本月计划金额", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const formVisible = ref(false)
const submitting = ref(false)
const tunnelOptions = ref<TunnelOption[]>([])
const formValues = reactive<Record<string, string>>({ 计划编号: '', 养护类型: '', 养护对象: '' })
const formError = reactive({ common: '' })
const incompleteOptionCount = computed(
  () => tunnelOptions.value.filter(option => option.长度待完善).length,
)

function optionLabel(option: TunnelOption): string {
  return `${option.隧道编码} ${option.隧道名称}`
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

async function openCreate() {
  formValues.计划编号 = ''
  formValues.养护类型 = ''
  formValues.养护对象 = ''
  formError.common = ''
  formVisible.value = true
  // 每次打开都拉最新选项，补齐后的隧道即时恢复可选；待完善记录不过滤，靠标注体现。
  try {
    const response = await request(`${TUNNEL_ENDPOINT}/options`)
    if (response.ok) {
      const payload = await response.json()
      tunnelOptions.value = payload.items ?? []
    }
  } catch {
    // 选项加载失败不阻断表单，保存时仍有必填校验兜底。
    tunnelOptions.value = []
  }
}

function closeForm() {
  formVisible.value = false
}

async function submitForm() {
  errorMessage.value = ''
  const missing = ['计划编号', '养护类型', '养护对象'].filter(field => !formValues[field].trim())
  if (missing.length) {
    formError.common = `缺少必填字段：${missing.join('、')}`
    return
  }
  submitting.value = true
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...formValues } }),
    })
    if (!response.ok) {
      throw new Error('养护计划登记未生效，请稍后重试')
    }
    const payload = await response.json()
    if (payload && payload.ok === false) {
      formError.common = String(payload.message || '养护计划登记失败')
      return
    }
    closeForm()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '养护计划登记失败'
  } finally {
    submitting.value = false
  }
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
