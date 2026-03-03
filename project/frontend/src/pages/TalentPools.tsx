import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Lock, Users, ChevronRight, Share2, Building2, UserPlus, Trash2, Settings } from 'lucide-react'
import clsx from 'clsx'
import { getPools, updatePool, addPoolShare, removePoolShare, TalentPool, ShareScope, SharePermission } from '../services/api'

// Simulated current user ID (in real app, this would come from auth context)
const CURRENT_USER_ID = 'default_user'

const SCOPE_CONFIG: Record<ShareScope, { icon: typeof Lock; label: string; color: string; bgColor: string; desc: string }> = {
  private: { icon: Lock, label: '仅自己', color: 'text-gray-600', bgColor: 'bg-gray-100', desc: '仅您自己可以访问' },
  team: { icon: Users, label: '团队', color: 'text-blue-600', bgColor: 'bg-blue-100', desc: '团队成员可以访问' },
  org: { icon: Building2, label: '全组织', color: 'text-green-600', bgColor: 'bg-green-100', desc: '组织内所有人可以访问' },
  custom: { icon: Share2, label: '指定成员', color: 'text-purple-600', bgColor: 'bg-purple-100', desc: '共享给指定的人' },
}

export default function TalentPools() {
  const [showSettings, setShowSettings] = useState(false)

  const { data: pools, isLoading } = useQuery({
    queryKey: ['pools'],
    queryFn: () => getPools()
  })

  // 我的人才库（第一个属于我的库）
  const myPool = pools?.find(p => p.owner_id === CURRENT_USER_ID)
  // 共享给我的人才库
  const sharedPools = pools?.filter(p => p.owner_id !== CURRENT_USER_ID) || []

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">加载中...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">人才库</h1>
      </div>

      {/* My Pool - Main Card */}
      {myPool ? (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-xl font-bold text-gray-900">{myPool.name}</h2>
                {myPool.description && (
                  <p className="text-gray-500 mt-1">{myPool.description}</p>
                )}
              </div>
              <button
                onClick={() => setShowSettings(true)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
                title="共享设置"
              >
                <Settings className="w-5 h-5" />
              </button>
            </div>

            {/* Share Status */}
            <div className="flex items-center gap-3 mb-6">
              {(() => {
                const config = SCOPE_CONFIG[myPool.share_scope]
                const Icon = config.icon
                return (
                  <div className={clsx('flex items-center gap-2 px-3 py-1.5 rounded-full', config.bgColor)}>
                    <Icon className={clsx('w-4 h-4', config.color)} />
                    <span className={clsx('text-sm font-medium', config.color)}>{config.label}</span>
                  </div>
                )
              })()}
              {myPool.share_scope === 'custom' && myPool.shared_with.length > 0 && (
                <span className="text-sm text-gray-500">
                  已共享给 {myPool.shared_with.length} 人
                </span>
              )}
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-4 p-4 bg-gray-50 rounded-lg">
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">{myPool.candidate_count}</div>
                <div className="text-sm text-gray-500">候选人</div>
              </div>
              <div className="text-center border-x border-gray-200">
                <div className="text-2xl font-bold text-gray-900">{myPool.shared_with.length}</div>
                <div className="text-sm text-gray-500">共享成员</div>
              </div>
              <div className="text-center">
                <div className="text-2xl font-bold text-gray-900">
                  {new Date(myPool.updated_at).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })}
                </div>
                <div className="text-sm text-gray-500">最近更新</div>
              </div>
            </div>
          </div>

          {/* Action */}
          <Link
            to={`/pools/${myPool.id}`}
            className="flex items-center justify-between p-4 bg-blue-50 hover:bg-blue-100 transition-colors border-t border-blue-100"
          >
            <span className="font-medium text-blue-700">查看候选人</span>
            <ChevronRight className="w-5 h-5 text-blue-700" />
          </Link>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Users className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h2 className="text-xl font-medium text-gray-900 mb-2">暂无人才库</h2>
          <p className="text-gray-500">上传简历后将自动创建您的人才库</p>
          <Link
            to="/upload"
            className="inline-block mt-4 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            上传简历
          </Link>
        </div>
      )}

      {/* Shared With Me */}
      {sharedPools.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">共享给我的</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {sharedPools.map(pool => (
              <SharedPoolCard key={pool.id} pool={pool} />
            ))}
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettings && myPool && (
        <PoolSettingsModal
          pool={myPool}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  )
}

function SharedPoolCard({ pool }: { pool: TalentPool }) {
  const config = SCOPE_CONFIG[pool.share_scope]
  const Icon = config.icon

  return (
    <Link
      to={`/pools/${pool.id}`}
      className="block bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow"
    >
      <div className="flex items-center gap-2 mb-3">
        <Icon className={clsx('w-4 h-4', config.color)} />
        <span className="text-sm text-gray-500">来自 {pool.owner_id}</span>
      </div>
      <h3 className="font-semibold text-gray-900 mb-1">{pool.name}</h3>
      {pool.description && (
        <p className="text-sm text-gray-500 line-clamp-2">{pool.description}</p>
      )}
      <div className="flex items-center justify-between mt-4 pt-4 border-t border-gray-100">
        <div className="flex items-center gap-1 text-sm text-gray-500">
          <Users className="w-4 h-4" />
          {pool.candidate_count} 人
        </div>
        <ChevronRight className="w-4 h-4 text-gray-400" />
      </div>
    </Link>
  )
}

function PoolSettingsModal({ pool, onClose }: { pool: TalentPool; onClose: () => void }) {
  const [name, setName] = useState(pool.name)
  const [description, setDescription] = useState(pool.description || '')
  const [scope, setScope] = useState<ShareScope>(pool.share_scope)
  const [newUserId, setNewUserId] = useState('')
  const [newPermission, setNewPermission] = useState<SharePermission>('view')
  const queryClient = useQueryClient()

  const updateMutation = useMutation({
    mutationFn: (data: { name?: string; description?: string; share_scope?: ShareScope }) =>
      updatePool(pool.id, data),
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

  const handleSave = () => {
    updateMutation.mutate({
      name: name.trim(),
      description: description.trim() || undefined,
      share_scope: scope
    })
  }

  const handleAddShare = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUserId.trim()) return
    addShareMutation.mutate({ userId: newUserId.trim(), permission: newPermission })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b">
          <h2 className="text-xl font-bold text-gray-900">人才库设置</h2>
        </div>

        <div className="p-6 space-y-6">
          {/* Basic Info */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">名称</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                rows={2}
                placeholder="可选"
              />
            </div>
          </div>

          {/* Share Scope */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">共享范围</label>
            <div className="grid grid-cols-2 gap-2">
              {(Object.entries(SCOPE_CONFIG) as [ShareScope, typeof SCOPE_CONFIG['private']][]).map(([s, config]) => {
                const Icon = config.icon
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setScope(s)}
                    className={clsx(
                      'flex flex-col items-start p-3 rounded-lg border-2 transition-colors text-left',
                      scope === s
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    )}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Icon className={clsx('w-4 h-4', config.color)} />
                      <span className="text-sm font-medium">{config.label}</span>
                    </div>
                    <span className="text-xs text-gray-500">{config.desc}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Custom Sharing */}
          {scope === 'custom' && (
            <div className="border-t pt-6">
              <h3 className="text-sm font-medium text-gray-700 mb-3">共享成员</h3>

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
                  className="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  <UserPlus className="w-4 h-4" />
                </button>
              </form>

              {pool.shared_with.length > 0 ? (
                <div className="space-y-2">
                  {pool.shared_with.map(share => (
                    <div key={share.user_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center text-sm font-medium">
                          {share.user_id.charAt(0).toUpperCase()}
                        </div>
                        <span className="text-sm">{share.user_id}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={clsx(
                          'text-xs px-2 py-1 rounded',
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
                <p className="text-sm text-gray-500 text-center py-4 bg-gray-50 rounded-lg">
                  暂无共享成员，添加成员后他们可以访问您的人才库
                </p>
              )}
            </div>
          )}
        </div>

        <div className="p-6 border-t flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
          >
            取消
          </button>
          <button
            onClick={() => { handleSave(); onClose() }}
            disabled={updateMutation.isPending}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  )
}
