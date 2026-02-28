import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Globe, Lock, Users, Mail, Phone, MapPin, Building, Briefcase, Trash2 } from 'lucide-react'
import clsx from 'clsx'
import { getPool, getPoolCandidates, removeCandidateFromPool, Candidate } from '../services/api'

export default function PoolDetail() {
  const { id } = useParams<{ id: string }>()
  const poolId = Number(id)
  const [page, setPage] = useState(1)
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)

  const { data: pool } = useQuery({
    queryKey: ['pool', poolId],
    queryFn: () => getPool(poolId)
  })

  const { data: candidatesData, refetch } = useQuery({
    queryKey: ['pool-candidates', poolId, page],
    queryFn: () => getPoolCandidates(poolId, page, 20)
  })

  const handleRemove = async (candidateId: number) => {
    if (confirm('确定从人才库中移除此候选人吗？')) {
      await removeCandidateFromPool(poolId, candidateId)
      refetch()
    }
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
            <span className={clsx(
              'flex items-center gap-1 text-xs px-2 py-1 rounded-full',
              pool.is_public ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'
            )}>
              {pool.is_public ? <Globe className="w-3 h-3" /> : <Lock className="w-3 h-3" />}
              {pool.is_public ? '公有库' : '私有库'}
            </span>
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
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* List */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <h2 className="font-semibold text-gray-900">候选人列表</h2>
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
              <div className="divide-y divide-gray-100">
                {candidatesData.items.map(candidate => (
                  <div
                    key={candidate.id}
                    onClick={() => setSelectedCandidate(candidate)}
                    className={clsx(
                      'p-4 cursor-pointer transition-colors',
                      selectedCandidate?.id === candidate.id ? 'bg-blue-50' : 'hover:bg-gray-50'
                    )}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="font-medium text-gray-900">{candidate.name}</div>
                        <div className="text-sm text-gray-500 mt-1">
                          {candidate.current_title && <span>{candidate.current_title}</span>}
                          {candidate.current_company && <span> @ {candidate.current_company}</span>}
                        </div>
                        <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                          {candidate.city && (
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3 h-3" />
                              {candidate.city}
                            </span>
                          )}
                          {candidate.years_of_experience && (
                            <span>{candidate.years_of_experience}年经验</span>
                          )}
                          {candidate.expected_salary && (
                            <span>{candidate.expected_salary}万/年</span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleRemove(candidate.id) }}
                        className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
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

        {/* Detail Panel */}
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="p-4 border-b border-gray-200">
            <h2 className="font-semibold text-gray-900">候选人详情</h2>
          </div>
          {selectedCandidate ? (
            <div className="p-4 space-y-4">
              <div>
                <div className="text-xl font-bold text-gray-900">{selectedCandidate.name}</div>
                {selectedCandidate.current_title && (
                  <div className="text-gray-600 mt-1">{selectedCandidate.current_title}</div>
                )}
              </div>

              <div className="space-y-3">
                {selectedCandidate.phone && (
                  <div className="flex items-center gap-3 text-sm">
                    <Phone className="w-4 h-4 text-gray-400" />
                    <span>{selectedCandidate.phone}</span>
                  </div>
                )}
                {selectedCandidate.email && (
                  <div className="flex items-center gap-3 text-sm">
                    <Mail className="w-4 h-4 text-gray-400" />
                    <span>{selectedCandidate.email}</span>
                  </div>
                )}
                {selectedCandidate.city && (
                  <div className="flex items-center gap-3 text-sm">
                    <MapPin className="w-4 h-4 text-gray-400" />
                    <span>{selectedCandidate.city}</span>
                  </div>
                )}
                {selectedCandidate.current_company && (
                  <div className="flex items-center gap-3 text-sm">
                    <Building className="w-4 h-4 text-gray-400" />
                    <span>{selectedCandidate.current_company}</span>
                  </div>
                )}
                {selectedCandidate.years_of_experience && (
                  <div className="flex items-center gap-3 text-sm">
                    <Briefcase className="w-4 h-4 text-gray-400" />
                    <span>{selectedCandidate.years_of_experience} 年工作经验</span>
                  </div>
                )}
              </div>

              {selectedCandidate.expected_salary && (
                <div className="p-3 bg-green-50 rounded-lg">
                  <div className="text-xs text-green-600 mb-1">期望薪资</div>
                  <div className="text-lg font-bold text-green-700">
                    {selectedCandidate.expected_salary} 万/年
                  </div>
                </div>
              )}

              {selectedCandidate.skills && (
                <div>
                  <div className="text-xs text-gray-500 mb-2">技能标签</div>
                  <div className="flex flex-wrap gap-2">
                    {(() => {
                      try {
                        const skills = JSON.parse(selectedCandidate.skills)
                        return skills.map((s: string, i: number) => (
                          <span key={i} className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded">
                            {s}
                          </span>
                        ))
                      } catch {
                        return selectedCandidate.skills.split(',').map((s, i) => (
                          <span key={i} className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded">
                            {s.trim()}
                          </span>
                        ))
                      }
                    })()}
                  </div>
                </div>
              )}

              {selectedCandidate.summary && (
                <div>
                  <div className="text-xs text-gray-500 mb-2">个人简介</div>
                  <p className="text-sm text-gray-700">{selectedCandidate.summary}</p>
                </div>
              )}

              {selectedCandidate.tags.length > 0 && (
                <div>
                  <div className="text-xs text-gray-500 mb-2">标签</div>
                  <div className="flex flex-wrap gap-2">
                    {selectedCandidate.tags.map(tag => (
                      <span key={tag.id} className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded">
                        {tag.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-12 text-center text-gray-500">
              <Users className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm">点击左侧候选人查看详情</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
