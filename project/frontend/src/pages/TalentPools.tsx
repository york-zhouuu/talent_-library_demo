import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Plus, Lock, Trash2, Users, ChevronRight, Share2, Building2, Globe2, UserPlus } from 'lucide-react'
import clsx from 'clsx'
import { getPools, createPool, deletePool, updatePool, addPoolShare, removePoolShare, TalentPool, ShareScope, SharePermission } from '../services/api'

// Simulated current user ID (in real app, this would come from auth context)
const CURRENT_USER_ID = 'default_user'

const SCOPE_CONFIG: Record<ShareScope, { icon: typeof Lock; label: string; color: string; bgColor: string }> = {
  private: { icon: Lock, label: '仅自己', color: 'text-gray-600', bgColor: 'bg-gray-100' },
  team: { icon: Users, label: '团队', color: 'text-blue-600', bgColor: 'bg-blue-100' },
  org: { icon: Building2, label: '全组织', color: 'text-green-600', bgColor: 'bg-green-100' },
  custom: { icon: Share2, label: '自定义', color: 'text-purple-600', bgColor: 'bg-purple-100' },
}

export default function TalentPools() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [showCreate, setShowCreate] = useState(false)
  const [editingPool, setEditingPool] = useState<TalentPool | null>(null)
  const queryClient = useQueryClient()

  const scopeFilter = searchParams.get('scope') as ShareScope | null

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
    if (scopeFilter) return p.share_scope === scopeFilter
    return true
  }) || []

  const myPools = pools?.filter(p => p.owner_id === CURRENT_USER_ID) || []
  const sharedWithMe = pools?.filter(p => p.owner_id !== CURRENT_USER_ID) || []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">人才库管理</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          创建人才库
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-gray-200">
        <FilterTab
          active={!scopeFilter}
          onClick={() => setSearchParams({})}
          icon={Users}
          label="全部"
          count={pools?.length || 0}
        />
        <FilterTab
          active={scopeFilter === 'private'}
          onClick={() => setSearchParams({ scope: 'private' })}
          icon={Lock}
          label="仅自己"
          count={pools?.filter(p => p.share_scope === 'private').length || 0}
          color="gray"
        />
        <FilterTab
          active={scopeFilter === 'org'}
          onClick={() => setSearchParams({ scope: 'org' })}
          icon={Building2}
          label="全组织"
          count={pools?.filter(p => p.share_scope === 'org').length || 0}
          color="green"
        />
        <FilterTab
          active={scopeFilter === 'custom'}
          onClick={() => setSearchParams({ scope: 'custom' })}
          icon={Share2}
          label="自定义共享"
          count={pools?.filter(p => p.share_scope === 'custom').length || 0}
          color="purple"
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
            创建第一个人才库
          </button>
        </div>
      ) : (
        <>
          {/* My Pools */}
          {myPools.length > 0 && !scopeFilter && (
            <div>
              <h2 className="text-sm font-medium text-gray-500 mb-3">我的人才库</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {myPools.map(pool => (
                  <PoolCard
                    key={pool.id}
                    pool={pool}
                    isOwner={true}
                    onDelete={() => {
                      if (confirm(`确定删除人才库「${pool.name}」吗？`)) {
                        deleteMutation.mutate(pool.id)
                      }
                    }}
                    onShare={() => setEditingPool(pool)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Shared With Me */}
          {sharedWithMe.length > 0 && !scopeFilter && (
            <div className="mt-8">
              <h2 className="text-sm font-medium text-gray-500 mb-3">共享给我的</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {sharedWithMe.map(pool => (
                  <PoolCard
                    key={pool.id}
                    pool={pool}
                    isOwner={false}
                    onDelete={() => {}}
                    onShare={() => {}}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Filtered View */}
          {scopeFilter && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredPools.map(pool => (
                <PoolCard
                  key={pool.id}
                  pool={pool}
                  isOwner={pool.owner_id === CURRENT_USER_ID}
                  onDelete={() => {
                    if (pool.owner_id !== CURRENT_USER_ID) return
                    if (confirm(`确定删除人才库「${pool.name}」吗？`)) {
                      deleteMutation.mutate(pool.id)
                    }
                  }}
                  onShare={() => setEditingPool(pool)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Create Modal */}
      {showCreate && (
        <CreatePoolModal
          onClose={() => setShowCreate(false)}
          onCreate={(data) => createMutation.mutate({
            ...data,
            owner_id: CURRENT_USER_ID
          })}
          isLoading={createMutation.isPending}
        />
      )}

      {/* Share Modal */}
      {editingPool && (
        <SharePoolModal
          pool={editingPool}
          onClose={() => setEditingPool(null)}
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
  color?: 'gray' | 'green' | 'purple'
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
      <Icon className={clsx(
        'w-4 h-4',
        color === 'gray' && 'text-gray-600',
        color === 'green' && 'text-green-600',
        color === 'purple' && 'text-purple-600'
      )} />
      {label}
      <span className="text-xs bg-gray-100 px-2 py-0.5 rounded-full">{count}</span>
    </button>
  )
}

function PoolCard({ pool, isOwner, onDelete, onShare }: {
  pool: TalentPool
  isOwner: boolean
  onDelete: () => void
  onShare: () => void
}) {
  const config = SCOPE_CONFIG[pool.share_scope]
  const Icon = config.icon

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon className={clsx('w-5 h-5', config.color)} />
          <span className={clsx('text-xs px-2 py-0.5 rounded-full', config.bgColor, config.color)}>
            {config.label}
          </span>
          {pool.shared_with.length > 0 && (
            <span className="text-xs text-gray-500">
              · {pool.shared_with.length} 人
            </span>
          )}
        </div>
        {isOwner && (
          <div className="flex items-center gap-1">
            <button
              onClick={(e) => { e.preventDefault(); onShare() }}
              className="p-1 text-gray-400 hover:text-blue-500 transition-colors"
              title="共享设置"
            >
              <Share2 className="w-4 h-4" />
            </button>
            <button
              onClick={(e) => { e.preventDefault(); onDelete() }}
              className="p-1 text-gray-400 hover:text-red-500 transition-colors"
              title="删除"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
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
  onCreate: (data: { name: string; description?: string; share_scope: ShareScope }) => void
  isLoading: boolean
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [shareScope, setShareScope] = useState<ShareScope>('private')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    onCreate({
      name: name.trim(),
      description: description.trim() || undefined,
      share_scope: shareScope
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md">
        <h2 className="text-xl font-bold text-gray-900 mb-4">创建人才库</h2>
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
              rows={2}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">共享范围</label>
            <div className="grid grid-cols-2 gap-2">
              {(Object.entries(SCOPE_CONFIG) as [ShareScope, typeof SCOPE_CONFIG['private']][]).map(([scope, config]) => {
                const Icon = config.icon
                return (
                  <button
                    key={scope}
                    type="button"
                    onClick={() => setShareScope(scope)}
                    className={clsx(
                      'flex items-center gap-2 p-3 rounded-lg border-2 transition-colors',
                      shareScope === scope
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    )}
                  >
                    <Icon className={clsx('w-4 h-4', config.color)} />
                    <span className="text-sm">{config.label}</span>
                  </button>
                )
              })}
            </div>
            <p className="text-xs text-gray-500 mt-2">
              {shareScope === 'private' && '仅您自己可以访问此人才库'}
              {shareScope === 'team' && '您的团队成员可以访问此人才库'}
              {shareScope === 'org' && '组织内所有人可以访问此人才库'}
              {shareScope === 'custom' && '您可以选择共享给特定的人'}
            </p>
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

function SharePoolModal({ pool, onClose }: {
  pool: TalentPool
  onClose: () => void
}) {
  const [newUserId, setNewUserId] = useState('')
  const [newPermission, setNewPermission] = useState<SharePermission>('view')
  const [scope, setScope] = useState<ShareScope>(pool.share_scope)
  const queryClient = useQueryClient()

  const updateMutation = useMutation({
    mutationFn: (data: { share_scope: ShareScope }) => updatePool(pool.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
    }
  })

  const addShareMutation = useMutation({
    mutationFn: ({ userId, permission }: { userId: string; permission: SharePermission }) =>
      addPoolShare(pool.id, userId, permission),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
      setNewUserId('')
    }
  })

  const removeShareMutation = useMutation({
    mutationFn: (userId: string) => removePoolShare(pool.id, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pools'] })
    }
  })

  const handleScopeChange = (newScope: ShareScope) => {
    setScope(newScope)
    updateMutation.mutate({ share_scope: newScope })
  }

  const handleAddShare = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUserId.trim()) return
    addShareMutation.mutate({ userId: newUserId.trim(), permission: newPermission })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-lg">
        <h2 className="text-xl font-bold text-gray-900 mb-4">共享设置 - {pool.name}</h2>

        {/* Scope Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">共享范围</label>
          <div className="grid grid-cols-2 gap-2">
            {(Object.entries(SCOPE_CONFIG) as [ShareScope, typeof SCOPE_CONFIG['private']][]).map(([s, config]) => {
              const Icon = config.icon
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => handleScopeChange(s)}
                  className={clsx(
                    'flex items-center gap-2 p-3 rounded-lg border-2 transition-colors',
                    scope === s
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  )}
                >
                  <Icon className={clsx('w-4 h-4', config.color)} />
                  <span className="text-sm">{config.label}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Custom Sharing */}
        {scope === 'custom' && (
          <div className="border-t pt-4">
            <h3 className="text-sm font-medium text-gray-700 mb-3">共享给特定用户</h3>

            {/* Add new share */}
            <form onSubmit={handleAddShare} className="flex gap-2 mb-4">
              <input
                type="text"
                value={newUserId}
                onChange={(e) => setNewUserId(e.target.value)}
                placeholder="输入用户ID或邮箱"
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
              <select
                value={newPermission}
                onChange={(e) => setNewPermission(e.target.value as SharePermission)}
                className="px-3 py-2 border border-gray-300 rounded-lg text-sm"
              >
                <option value="view">只读</option>
                <option value="edit">可编辑</option>
                <option value="admin">管理员</option>
              </select>
              <button
                type="submit"
                disabled={!newUserId.trim() || addShareMutation.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm"
              >
                <UserPlus className="w-4 h-4" />
              </button>
            </form>

            {/* Share list */}
            {pool.shared_with.length > 0 ? (
              <div className="space-y-2">
                {pool.shared_with.map(share => (
                  <div key={share.user_id} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center text-sm font-medium">
                        {share.user_id.charAt(0).toUpperCase()}
                      </div>
                      <span className="text-sm">{share.user_id}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={clsx(
                        'text-xs px-2 py-0.5 rounded',
                        share.permission === 'admin' && 'bg-red-100 text-red-700',
                        share.permission === 'edit' && 'bg-yellow-100 text-yellow-700',
                        share.permission === 'view' && 'bg-gray-100 text-gray-700'
                      )}>
                        {share.permission === 'admin' ? '管理员' : share.permission === 'edit' ? '可编辑' : '只读'}
                      </span>
                      <button
                        onClick={() => removeShareMutation.mutate(share.user_id)}
                        className="p-1 text-gray-400 hover:text-red-500"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500 text-center py-4">暂无共享用户</p>
            )}
          </div>
        )}

        <div className="flex justify-end mt-6 pt-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  )
}
