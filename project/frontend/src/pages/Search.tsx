import { useState, useCallback, useEffect, useRef } from 'react'
import { Search as SearchIcon, MapPin, Briefcase, Loader2, Sparkles, X, Building, Clock, Filter, Zap, Brain, ChevronDown, ChevronUp } from 'lucide-react'
import clsx from 'clsx'
import {
  unifiedSearch,
  SearchResult,
  SearchAggregations,
  SearchFilters,
  AggregationBucket,
  streamingSearch,
  StreamingEvent,
  getErrorMessage
} from '../services/api'
import { useToast } from '../components/Toast'

// 解析技能字符串的辅助函数
function parseSkills(skills: string | null): string[] {
  if (!skills) return []
  try {
    const parsed = JSON.parse(skills)
    return Array.isArray(parsed) ? parsed : [skills]
  } catch {
    return skills.split(',').map(s => s.trim()).filter(Boolean)
  }
}

// 高亮文本渲染组件
function HighlightedText({ text, className }: { text: string; className?: string }) {
  // 将 <mark>...</mark> 转换为高亮 span
  const parts = text.split(/(<mark>.*?<\/mark>)/g)
  return (
    <span className={className}>
      {parts.map((part, i) => {
        if (part.startsWith('<mark>') && part.endsWith('</mark>')) {
          const content = part.slice(6, -7)
          return (
            <span key={i} className="bg-yellow-200 text-yellow-900 px-0.5 rounded">
              {content}
            </span>
          )
        }
        return part
      })}
    </span>
  )
}

export default function Search() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [selectedCandidate, setSelectedCandidate] = useState<SearchResult | null>(null)

  // Search metadata
  const [searchPath, setSearchPath] = useState<string>('')
  const [pathDescription, setPathDescription] = useState('')
  const [latencyMs, setLatencyMs] = useState(0)
  const [totalResults, setTotalResults] = useState(0)
  const [searchSummary, setSearchSummary] = useState('')

  // Aggregations for filters
  const [aggregations, setAggregations] = useState<SearchAggregations>({})
  const [filters, setFilters] = useState<SearchFilters>({})
  const [showFilters, setShowFilters] = useState(false)

  // AI search streaming states
  const [isAISearch, setIsAISearch] = useState(false)
  const [aiProgress, setAiProgress] = useState('')

  const { showToast } = useToast()
  const searchInputRef = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<NodeJS.Timeout>()

  // 执行搜索
  const executeSearch = useCallback(async (searchQuery: string, searchFilters?: SearchFilters) => {
    if (!searchQuery.trim()) {
      setResults([])
      setAggregations({})
      return
    }

    setIsSearching(true)
    setIsAISearch(false)
    setAiProgress('')
    setSelectedCandidate(null)

    try {
      const response = await unifiedSearch(searchQuery, searchFilters, 30)

      setResults(response.candidates)
      setTotalResults(response.total)
      setAggregations(response.aggregations)
      setSearchPath(response.search_path)
      setPathDescription(response.path_description)
      setLatencyMs(response.latency_ms)
      setSearchSummary(response.search_summary || '')

      // 如果是 AI 搜索路径，显示更多信息
      if (response.search_path === 'full') {
        setIsAISearch(true)
      }
    } catch (e) {
      console.error('Search failed:', e)
      showToast({
        type: 'error',
        title: '搜索失败',
        message: getErrorMessage(e)
      })
    } finally {
      setIsSearching(false)
    }
  }, [showToast])

  // 输入防抖搜索
  const handleInputChange = (value: string) => {
    setQuery(value)

    // 清除之前的定时器
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    // 设置新的防抖定时器
    debounceRef.current = setTimeout(() => {
      executeSearch(value, filters)
    }, 300)
  }

  // 回车搜索
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
      executeSearch(query, filters)
    }
  }

  // 应用筛选
  const applyFilter = (key: keyof SearchFilters, value: string | number | undefined) => {
    const newFilters = { ...filters }
    if (value === undefined || value === '') {
      delete newFilters[key]
    } else {
      (newFilters as Record<string, unknown>)[key] = value
    }
    setFilters(newFilters)
    executeSearch(query, newFilters)
  }

  // 清除所有筛选
  const clearFilters = () => {
    setFilters({})
    executeSearch(query, {})
  }

  // 热门搜索建议
  const suggestions = ['Python', '产品经理', '大模型', 'AI工程师', '北京', '杭州']

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-gradient-to-br from-purple-500 to-blue-500 rounded-lg">
            <SearchIcon className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">智能搜索</h1>
            <p className="text-sm text-gray-500">输入关键词快速搜索，或用自然语言描述需求</p>
          </div>
        </div>

        {/* Search Input */}
        <div className="relative">
          <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            ref={searchInputRef}
            type="text"
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="搜索候选人... 如 'Python 北京' 或 '找能带团队的技术专家'"
            className="w-full pl-12 pr-12 py-3 text-lg border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-purple-500 transition-shadow"
          />
          {isSearching && (
            <Loader2 className="absolute right-4 top-1/2 -translate-y-1/2 w-5 h-5 text-purple-500 animate-spin" />
          )}
          {!isSearching && query && (
            <button
              onClick={() => { setQuery(''); setResults([]); setAggregations({}); }}
              className="absolute right-4 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Search Suggestions */}
        {!query && (
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="text-sm text-gray-500">热门:</span>
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => { setQuery(s); executeSearch(s, filters); }}
                className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded-full hover:bg-gray-200 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Search Meta Info */}
        {searchPath && (
          <div className="mt-3 flex items-center gap-4 text-sm">
            <div className="flex items-center gap-1.5">
              {searchPath === 'direct' ? (
                <Zap className="w-4 h-4 text-yellow-500" />
              ) : (
                <Brain className="w-4 h-4 text-purple-500" />
              )}
              <span className={clsx(
                "font-medium",
                searchPath === 'direct' ? 'text-yellow-600' : 'text-purple-600'
              )}>
                {pathDescription}
              </span>
            </div>
            <span className="text-gray-400">|</span>
            <span className="text-gray-500">
              找到 <span className="font-medium text-gray-900">{totalResults}</span> 人
            </span>
            <span className="text-gray-400">|</span>
            <span className="text-gray-500">
              耗时 <span className="font-medium text-gray-900">{latencyMs}ms</span>
            </span>
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Filter Sidebar */}
        {Object.keys(aggregations).length > 0 && (
          <div className="w-64 flex-shrink-0 bg-gray-50 border-r border-gray-200 overflow-y-auto">
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                  <Filter className="w-4 h-4" />
                  筛选条件
                </h3>
                {Object.keys(filters).length > 0 && (
                  <button
                    onClick={clearFilters}
                    className="text-xs text-purple-600 hover:text-purple-700"
                  >
                    清除
                  </button>
                )}
              </div>

              {/* City Filter */}
              {aggregations.cities && aggregations.cities.length > 0 && (
                <div className="mb-6">
                  <h4 className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5" />
                    城市
                  </h4>
                  <div className="space-y-1">
                    {aggregations.cities.map((bucket) => (
                      <label
                        key={bucket.value}
                        className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-100 px-2 py-1.5 rounded"
                      >
                        <input
                          type="radio"
                          name="city"
                          checked={filters.city === bucket.value}
                          onChange={() => applyFilter('city', filters.city === bucket.value ? undefined : bucket.value)}
                          className="text-purple-600 focus:ring-purple-500"
                        />
                        <span className="flex-1 text-gray-700">{bucket.value}</span>
                        <span className="text-gray-400 text-xs">{bucket.count}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Experience Filter */}
              {aggregations.experience && aggregations.experience.length > 0 && (
                <div className="mb-6">
                  <h4 className="text-sm font-medium text-gray-700 mb-2 flex items-center gap-1">
                    <Briefcase className="w-3.5 h-3.5" />
                    工作经验
                  </h4>
                  <div className="space-y-1">
                    {aggregations.experience.map((bucket) => (
                      <label
                        key={bucket.value}
                        className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-100 px-2 py-1.5 rounded"
                      >
                        <input
                          type="checkbox"
                          checked={false} // TODO: implement multi-select
                          onChange={() => {
                            // Parse experience range and apply filter
                            const match = bucket.value.match(/(\d+)/)
                            if (match) {
                              const years = parseInt(match[1])
                              applyFilter('min_experience', years)
                            }
                          }}
                          className="rounded text-purple-600 focus:ring-purple-500"
                        />
                        <span className="flex-1 text-gray-700">{bucket.value}</span>
                        <span className="text-gray-400 text-xs">{bucket.count}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Salary Filter */}
              {aggregations.salary && aggregations.salary.length > 0 && (
                <div className="mb-6">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">💰 期望薪资</h4>
                  <div className="space-y-1">
                    {aggregations.salary.map((bucket) => (
                      <label
                        key={bucket.value}
                        className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-100 px-2 py-1.5 rounded"
                      >
                        <input
                          type="checkbox"
                          checked={false}
                          onChange={() => {}}
                          className="rounded text-purple-600 focus:ring-purple-500"
                        />
                        <span className="flex-1 text-gray-700">{bucket.value}</span>
                        <span className="text-gray-400 text-xs">{bucket.count}</span>
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Results List */}
        <div className="flex-1 overflow-y-auto">
          {/* AI Summary */}
          {searchSummary && (
            <div className="m-4 p-4 bg-purple-50 rounded-lg border border-purple-100">
              <div className="flex items-start gap-2">
                <Sparkles className="w-5 h-5 text-purple-500 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-purple-800 whitespace-pre-wrap">{searchSummary}</div>
              </div>
            </div>
          )}

          {/* Results */}
          {results.length > 0 ? (
            <div className="divide-y divide-gray-100">
              {results.map((candidate) => (
                <div
                  key={candidate.id}
                  onClick={() => setSelectedCandidate(candidate)}
                  className={clsx(
                    "px-6 py-4 cursor-pointer transition-all",
                    selectedCandidate?.id === candidate.id
                      ? "bg-purple-50 border-l-4 border-purple-500"
                      : "hover:bg-gray-50 border-l-4 border-transparent"
                  )}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3">
                        <span className="font-semibold text-gray-900">{candidate.name}</span>
                        {candidate.fit_summary && (
                          <span className="text-sm text-purple-600 italic truncate">
                            {candidate.fit_summary}
                          </span>
                        )}
                      </div>

                      <div className="text-sm text-gray-600 mt-1">
                        {candidate.current_title}
                        {candidate.current_company && (
                          <span className="text-gray-400"> @ {candidate.current_company}</span>
                        )}
                      </div>

                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        {candidate.city && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3 h-3" />
                            {candidate.city}
                          </span>
                        )}
                        {candidate.years_of_experience && (
                          <span className="flex items-center gap-1">
                            <Briefcase className="w-3 h-3" />
                            {candidate.years_of_experience}年
                          </span>
                        )}
                        {candidate.expected_salary && (
                          <span>{candidate.expected_salary}万/年</span>
                        )}
                      </div>

                      {/* Highlights from ES */}
                      {candidate.highlights && Object.keys(candidate.highlights).length > 0 && (
                        <div className="mt-2 space-y-1">
                          {Object.entries(candidate.highlights).slice(0, 2).map(([field, snippets]) => (
                            <div key={field} className="text-xs">
                              {snippets.slice(0, 1).map((snippet, i) => (
                                <HighlightedText
                                  key={i}
                                  text={snippet}
                                  className="text-gray-600 line-clamp-1"
                                />
                              ))}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Match Reasons */}
                      {candidate.match_reasons.length > 0 && !candidate.highlights && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {candidate.match_reasons.slice(0, 3).map((r, i) => (
                            <span
                              key={i}
                              className="text-xs text-purple-600 bg-purple-50 px-2 py-0.5 rounded"
                            >
                              {r.reason}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : query && !isSearching ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <SearchIcon className="w-12 h-12 text-gray-300 mb-4" />
              <p>没有找到匹配的候选人</p>
              <p className="text-sm mt-1">尝试其他关键词或放宽筛选条件</p>
            </div>
          ) : !query ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500 px-8">
              <div className="max-w-md text-center">
                <div className="w-16 h-16 mx-auto mb-4 bg-gradient-to-br from-purple-100 to-blue-100 rounded-2xl flex items-center justify-center">
                  <SearchIcon className="w-8 h-8 text-purple-500" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">开始搜索</h3>
                <p className="text-sm text-gray-500 mb-6">
                  输入关键词快速搜索，或用自然语言描述你想找的人
                </p>
                <div className="space-y-3 text-left bg-gray-50 rounded-lg p-4">
                  <div className="text-xs text-gray-400 uppercase tracking-wide">示例搜索</div>
                  <div className="space-y-2 text-sm">
                    <p className="flex items-center gap-2">
                      <Zap className="w-4 h-4 text-yellow-500" />
                      <span className="text-gray-600">"Python 北京" → 快速搜索</span>
                    </p>
                    <p className="flex items-center gap-2">
                      <Brain className="w-4 h-4 text-purple-500" />
                      <span className="text-gray-600">"找能带团队的大模型专家" → AI智能搜索</span>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* Detail Panel */}
        {selectedCandidate && (
          <div className="w-96 flex-shrink-0 bg-white border-l border-gray-200 overflow-y-auto">
            <div className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">候选人详情</h3>
              <button
                onClick={() => setSelectedCandidate(null)}
                className="p-1 text-gray-400 hover:text-gray-600 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 space-y-6">
              {/* Basic Info */}
              <div>
                <h4 className="text-xl font-bold text-gray-900">{selectedCandidate.name}</h4>
                {selectedCandidate.current_title && (
                  <p className="text-gray-600 mt-1">{selectedCandidate.current_title}</p>
                )}
                {selectedCandidate.current_company && (
                  <p className="text-sm text-gray-500 flex items-center gap-1 mt-1">
                    <Building className="w-4 h-4" />
                    {selectedCandidate.current_company}
                  </p>
                )}
              </div>

              {/* Quick Stats */}
              <div className="grid grid-cols-2 gap-3">
                {selectedCandidate.city && (
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">城市</div>
                    <div className="font-medium text-gray-900 flex items-center gap-1">
                      <MapPin className="w-4 h-4 text-gray-400" />
                      {selectedCandidate.city}
                    </div>
                  </div>
                )}
                {selectedCandidate.years_of_experience && (
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-xs text-gray-500 mb-1">经验</div>
                    <div className="font-medium text-gray-900 flex items-center gap-1">
                      <Briefcase className="w-4 h-4 text-gray-400" />
                      {selectedCandidate.years_of_experience} 年
                    </div>
                  </div>
                )}
                {selectedCandidate.expected_salary && (
                  <div className="bg-green-50 rounded-lg p-3 col-span-2">
                    <div className="text-xs text-green-600 mb-1">期望薪资</div>
                    <div className="text-lg font-bold text-green-700">
                      {selectedCandidate.expected_salary} 万/年
                    </div>
                  </div>
                )}
              </div>

              {/* Fit Summary */}
              {selectedCandidate.fit_summary && (
                <div className="bg-purple-50 rounded-lg p-4">
                  <div className="text-xs text-purple-600 mb-2 flex items-center gap-1">
                    <Sparkles className="w-3.5 h-3.5" />
                    AI 匹配评价
                  </div>
                  <p className="text-sm text-purple-800">{selectedCandidate.fit_summary}</p>
                </div>
              )}

              {/* Match Reasons */}
              {selectedCandidate.match_reasons.length > 0 && (
                <div>
                  <h5 className="text-sm font-medium text-gray-700 mb-2">匹配原因</h5>
                  <div className="space-y-2">
                    {selectedCandidate.match_reasons.map((r, i) => (
                      <div
                        key={i}
                        className="text-sm bg-gray-50 rounded px-3 py-2 flex items-start gap-2"
                      >
                        <span className="text-purple-500 mt-0.5">•</span>
                        <span className="text-gray-700">{r.reason}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Skills */}
              {selectedCandidate.skills && (
                <div>
                  <h5 className="text-sm font-medium text-gray-700 mb-2">技能</h5>
                  <div className="flex flex-wrap gap-2">
                    {parseSkills(selectedCandidate.skills).map((skill, i) => (
                      <span
                        key={i}
                        className="px-2 py-1 bg-blue-100 text-blue-700 text-xs rounded"
                      >
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="pt-4 border-t border-gray-200">
                <button
                  onClick={() => window.open(`/pools?candidate=${selectedCandidate.id}`, '_blank')}
                  className="w-full py-2 px-4 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors text-sm font-medium"
                >
                  查看完整简历
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
