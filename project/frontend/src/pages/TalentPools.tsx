import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, Globe, Lock, Trash2, Users, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { getPools, createPool, deletePool, TalentPool } from '../services/api'

// Simulated current user ID (in real app, this would come from auth context)
const CURRENT_USER_ID = 'user-1'

export default function TalentPools() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [showCreate, setShowCreate] = useState(false)
  const queryClient = useQueryClient()

  const typeFilter = searchParams.get('type') as 'public' | 'private' | null

  const { data: pools, isLoading } = useQuery({
    queryKey: ['pools'],
    queryFn: () => getPools()
  })

  const createMutation = useMutation({
    mutationFn: createPool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
      setShowCreate(false)
    }
  })

  const deleteMutation = useMutation({
    mutationFn: deletePool,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
    }
  })

  const filteredPools = pools?.filter(p => {
    if (typeFilter === 'public') return p.is_public
    if (typeFilter === 'private') return !p.is_public
    return true
  }) || []

  const publicPools = pools?.filter(p => p.is_public) || []
  const privatePools = pools?.filter(p => !p.is_public) || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">人才库管理</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          创建私有库
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-gray-200">
        <FilterTab
          active={!typeFilter}
          onClick={() => setSearchParams({})}
          icon={Users}
          label="全部"
          count={pools?.length || 0}
        />
        <FilterTab
          active={typeFilter === 'public'}
          onClick={() => setSearchParams({ type: 'public' })}
          icon={Globe}
          label="公有库"
          count={publicPools.length}
          color="green"
        />
        <FilterTab
          active={typeFilter === 'private'}
          onClick={() => setSearchParams({ type: 'private' })}
          icon={Lock}
          label="私有库"
          count={privatePools.length}
          color="orange"
        />
      </div>

      {/* Pool List */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">加载中...</div>
      ) : filteredPools.length === 0 ? (
        <div className="text-center py-12">
          <Users className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500">暂无人才库</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-4 text-blue-600 hover:underline"
          >
            创建第一个私有库
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredPools.map(pool => (
            <PoolCard
              key={pool.id}
              pool={pool}
              onDelete={() => {
                if (pool.is_public) {
                  alert('公有库不可删除')
                  return
                }
                if (confirm(`确定删除人才库「${pool.name}」吗？`)) {
                  deleteMutation.mutate(pool.id)
                }
              }}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
        <CreatePoolModal
          onClose={() => setShowCreate(false)}
          onCreate={(data) => createMutation.mutate({
            ...data,
            is_public: false,
            owner_id: CURRENT_USER_ID
          })}
          isLoading={createMutation.isPending}
        />
      )}
    </div>
  )
}

function FilterTab({ active, onClick, icon: Icon, label, count, color }: {
  active: boolean
  onClick: () => void
  icon: typeof Users
  label: string
  count: number
  color?: 'green' | 'orange'
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex items-center gap-2 px-4 py-3 border-b-2 -mb-px transition-colors',
        active
          ? 'border-blue-600 text-blue-600'
          : 'border-transparent text-gray-500 hover:text-gray-700'
      )}
    >
      <Icon className={clsx('w-4 h-4', color === 'green' && 'text-green-600', color === 'orange' && 'text-orange-600')} />
      {label}
      <span className="text-xs bg-gray-100 px-2 py-0.5 rounded-full">{count}</span>
    </button>
  )
}

function PoolCard({ pool, onDelete }: { pool: TalentPool; onDelete: () => void }) {
  const isPublic = pool.is_public

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {isPublic ? (
            <Globe className="w-5 h-5 text-green-600" />
          ) : (
            <Lock className="w-5 h-5 text-orange-600" />
          )}
          <span className={clsx(
            'text-xs px-2 py-0.5 rounded-full',
            isPublic ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'
          )}>
            {isPublic ? '公有库' : '私有库'}
          </span>
        </div>
        {/* Public pool cannot be deleted */}
        {!isPublic && (
          <button
            onClick={(e) => { e.preventDefault(); onDelete() }}
            className="p-1 text-gray-400 hover:text-red-500 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
      <Link to={`/pools/${pool.id}`} className="block group">
        <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
          {pool.name}
        </h3>
        {pool.description && (
          <p className="text-sm text-gray-500 mt-1 line-clamp-2">{pool.description}</p>
        )}
        <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
          <div className="flex items-center gap-1 text-sm text-gray-500">
            <Users className="w-4 h-4" />
            {pool.candidate_count} 人
          </div>
          <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-blue-600 transition-colors" />
        </div>
      </Link>
    </div>
  )
}

function CreatePoolModal({ onClose, onCreate, isLoading }: {
  onClose: () => void
  onCreate: (data: { name: string; description?: string }) => void
  isLoading: boolean
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    onCreate({ name: name.trim(), description: description.trim() || undefined })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md">
        <h2 className="text-xl font-bold text-gray-900 mb-4">创建私有人才库</h2>
        <p className="text-sm text-gray-500 mb-4">
          私有库仅您自己可见，可用于管理专属候选人
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">名称</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="输入人才库名称"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="输入描述（可选）"
              rows={3}
            />
          </div>
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isLoading || !name.trim()}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {isLoading ? '创建中...' : '创建'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
