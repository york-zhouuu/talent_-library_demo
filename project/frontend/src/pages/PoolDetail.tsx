import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Lock, Users, Trash2, Share2, Building2, AlertTriangle, Clock, XCircle, Loader2, GraduationCap, Briefcase, CheckCircle } from 'lucide-react'
import clsx from 'clsx'
import { getPool, getPoolCandidates, removeCandidateFromPool, Candidate, ShareScope } from '../services/api'
import ResumePreview from '../components/ResumePreview'

const SCOPE_CONFIG: Record<ShareScope, { icon: typeof Lock; label: string; color: string }> = {
  private: { icon: Lock, label: '仅自己', color: 'text-gray-600' },
  team: { icon: Users, label: '团队共享', color: 'text-blue-600' },
  org: { icon: Building2, label: '全组织', color: 'text-green-600' },
  custom: { icon: Share2, label: '指定成员', color: 'text-purple-600' },
}

// Parse Status Icon
function ParseStatusIcon({ status }: { status?: string }) {
  if (status === 'completed') return null

  const config = {
    pending: { icon: Clock, color: 'text-yellow-500', title: '待解析' },
    parsing: { icon: Loader2, color: 'text-blue-500', title: '解析中', animate: true },
    failed: { icon: XCircle, color: 'text-red-500', title: '解析失败' },
  }[status || 'pending']

  if (!config) return null

  const Icon = config.icon
  return (
    <span title={config.title}>
      <Icon className={clsx('w-3.5 h-3.5', config.color, 'animate' in config && config.animate && 'animate-spin')} />
    </span>
  )
}

export default function PoolDetail() {
  const { id } = useParams<{ id: string }>()
  const poolId = Number(id)
  const [page, setPage] = useState(1)
  const [previewCandidate, setPreviewCandidate] = useState<Candidate | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; candidateId: number | null }>({
    open: false,
    candidateId: null
  })

  const { data: pool } = useQuery({
    queryKey: ['pool', poolId],
    queryFn: () => getPool(poolId)
  })

  const { data: candidatesData, refetch } = useQuery({
    queryKey: ['pool-candidates', poolId, page],
    queryFn: () => getPoolCandidates(poolId, page, 20)
  })

  const handleRemove = async (candidateId: number) => {
    await removeCandidateFromPool(poolId, candidateId)
    setDeleteConfirm({ open: false, candidateId: null })
    refetch()
  }

  if (!pool) {
    return <div className="text-center py-12 text-gray-500">加载中...</div>
  }

  const totalPages = Math.ceil((candidatesData?.total || 0) / 20)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link to="/pools" className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
          <ArrowLeft className="w-5 h-5 text-gray-600" />
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{pool.name}</h1>
            {(() => {
              const config = SCOPE_CONFIG[pool.share_scope]
              const Icon = config.icon
              return (
                <span className={clsx(
                  'flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-gray-100',
                  config.color
                )}>
                  <Icon className="w-3 h-3" />
                  {config.label}
                </span>
              )
            })()}
          </div>
          {pool.description && (
            <p className="text-gray-500 mt-1">{pool.description}</p>
          )}
        </div>
        <div className="flex items-center gap-2 text-gray-500">
          <Users className="w-5 h-5" />
          <span className="text-lg font-medium">{candidatesData?.total || 0} 人</span>
        </div>
      </div>

      {/* Candidates Grid */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="p-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">候选人列表</h2>
          <p className="text-sm text-gray-500 mt-1">点击卡片查看完整简历</p>
        </div>
        {!candidatesData?.items.length ? (
          <div className="p-12 text-center text-gray-500">
            <Users className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p>暂无候选人</p>
            <Link to="/upload" className="text-blue-600 hover:underline mt-2 inline-block">
              去导入简历
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
              {candidatesData.items.map(candidate => (
                <div
                  key={candidate.id}
                  onClick={() => setPreviewCandidate(candidate)}
                  className="p-4 border border-gray-200 rounded-lg cursor-pointer hover:border-blue-300 hover:shadow-md transition-all"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-900 text-lg">{candidate.name}</span>
                      <ParseStatusIcon status={candidate.parse_status} />
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteConfirm({ open: true, candidateId: candidate.id }) }}
                      className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {/* 学校 */}
                  {candidate.school && (
                    <div className="flex items-center gap-2 text-sm text-gray-600 mb-2">
                      <GraduationCap className="w-4 h-4 text-blue-500" />
                      <span>{candidate.school}</span>
                    </div>
                  )}

                  {/* 最近工作经历 */}
                  <div className="text-sm text-gray-600 mb-3">
                    {(candidate.latest_work?.title || candidate.current_title) && (
                      <div className="flex items-center gap-2">
                        <Briefcase className="w-4 h-4 text-gray-400" />
                        <span className="font-medium">{candidate.latest_work?.title || candidate.current_title}</span>
                      </div>
                    )}
                    {(candidate.latest_work?.company || candidate.current_company) && (
                      <div className="text-gray-500 ml-6">
                        @ {candidate.latest_work?.company || candidate.current_company}
                      </div>
                    )}
                  </div>

                  {/* 活跃度 */}
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1">
                      {candidate.activity === 'active' ? (
                        <>
                          <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                          <span className="text-green-600">已解析</span>
                        </>
                      ) : (
                        <>
                          <Clock className="w-3.5 h-3.5 text-yellow-500" />
                          <span className="text-yellow-600">待解析</span>
                        </>
                      )}
                    </div>
                    {candidate.years_of_experience && (
                      <span className="text-gray-500">{candidate.years_of_experience}年经验</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {/* Pagination */}
            {totalPages > 1 && (
              <div className="p-4 border-t border-gray-200 flex items-center justify-center gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
                >
                  上一页
                </button>
                <span className="text-sm text-gray-500">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <h3 className="font-semibold text-gray-900">确认移除</h3>
                <p className="text-sm text-gray-500">此操作将从人才库中移除该候选人</p>
              </div>
            </div>
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setDeleteConfirm({ open: false, candidateId: null })}
                className="flex-1 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={() => deleteConfirm.candidateId && handleRemove(deleteConfirm.candidateId)}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                确认移除
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Resume Preview Modal */}
      {previewCandidate && (
        <ResumePreview
          candidateId={previewCandidate.id}
          candidateName={previewCandidate.name}
          parseStatus={previewCandidate.parse_status}
          onClose={() => setPreviewCandidate(null)}
        />
      )}
    </div>
  )
}
