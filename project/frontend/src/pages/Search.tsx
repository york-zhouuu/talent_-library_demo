import { useState, useCallback } from 'react'
import { Search as SearchIcon, Users, MapPin, Briefcase, Loader2, Sparkles, ChevronDown, ChevronUp, CheckCircle2 } from 'lucide-react'
import clsx from 'clsx'
import { intelligentSearch, streamingSearch, SearchResult, SearchStage, StreamingEvent } from '../services/api'

interface SearchHistory {
  terms: string[]
  found: number
}

// Stage display config
const stageConfig: Record<SearchStage, { label: string; icon: string }> = {
  parsing: { label: '解析搜索意图', icon: '🔍' },
  expanding: { label: '扩展搜索关键词', icon: '💡' },
  searching: { label: '搜索候选人', icon: '📊' },
  ranking: { label: 'AI 智能排序', icon: '🎯' },
  explaining: { label: '生成匹配解释', icon: '✨' }
}

export default function Search() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchSummary, setSearchSummary] = useState('')
  const [searchHistory, setSearchHistory] = useState<SearchHistory[]>([])
  const [showHistory, setShowHistory] = useState(false)

  // Streaming states
  const [useStreaming, setUseStreaming] = useState(true)
  const [currentStage, setCurrentStage] = useState<SearchStage | null>(null)
  const [stageMessage, setStageMessage] = useState('')
  const [completedStages, setCompletedStages] = useState<SearchStage[]>([])
  const [isRanked, setIsRanked] = useState(false)

  const handleStreamingSearch = useCallback(async () => {
    if (!query.trim()) return
    setIsSearching(true)
    setResults([])
    setSearchSummary('')
    setSearchHistory([])
    setCurrentStage(null)
    setStageMessage('')
    setCompletedStages([])
    setIsRanked(false)

    try {
      await streamingSearch(
        query,
        20,
        (event: StreamingEvent) => {
          switch (event.type) {
            case 'status':
              // Mark previous stage as completed
              if (currentStage && currentStage !== event.stage) {
                setCompletedStages(prev => [...prev, currentStage])
              }
              setCurrentStage(event.stage)
              setStageMessage(event.message)
              break
            case 'partial_result':
              setResults(event.candidates)
              setIsRanked(event.is_ranked)
              break
            case 'final_result':
              setResults(event.candidates)
              setSearchHistory(event.search_process || [])
              setSearchSummary(event.reasoning || '')
              setIsRanked(true)
              setCurrentStage(null)
              setCompletedStages(['parsing', 'expanding', 'searching', 'ranking', 'explaining'])
              break
          }
        },
        (error) => {
          console.error('Streaming search failed:', error)
          // Fallback to regular search
          handleRegularSearch()
        }
      )
    } catch {
      // Fallback to regular search
      await handleRegularSearch()
    } finally {
      setIsSearching(false)
    }
  }, [query])

  const handleRegularSearch = async () => {
    if (!query.trim()) return
    setIsSearching(true)
    setResults([])
    setSearchSummary('')
    setSearchHistory([])

    try {
      const data = await intelligentSearch(query, 20)
      setResults(data.candidates || [])
      setSearchSummary(data.search_summary || '')
      setSearchHistory(data.search_history || [])
      setIsRanked(true)
    } catch (e) {
      console.error('Search failed:', e)
    } finally {
      setIsSearching(false)
    }
  }

  const handleSearch = useCallback(() => {
    if (useStreaming) {
      handleStreamingSearch()
    } else {
      handleRegularSearch()
    }
  }, [useStreaming, handleStreamingSearch])

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <Sparkles className="w-6 h-6 text-purple-600" />
          <h1 className="text-2xl font-bold text-gray-900">AI 智能搜索</h1>
        </div>
        <p className="text-gray-500 mt-1">
          AI 会自动理解你的意图，推理相关概念，多角度搜索以找到最匹配的候选人
        </p>
      </div>

      {/* Search Box */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="用自然语言描述你要找的人，如：有大模型经验的产品经理"
              className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={isSearching || !query.trim()}
            className="flex items-center gap-2 px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
          >
            {isSearching ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Sparkles className="w-5 h-5" />
            )}
            智能搜索
          </button>
        </div>

        {/* Streaming Toggle */}
        <div className="mt-3 flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={useStreaming}
              onChange={(e) => setUseStreaming(e.target.checked)}
              className="rounded text-purple-600 focus:ring-purple-500"
            />
            流式搜索（实时显示搜索进度）
          </label>
        </div>

        {/* Streaming Progress */}
        {isSearching && useStreaming && (
          <div className="mt-4 p-4 bg-purple-50 rounded-lg">
            <div className="space-y-2">
              {(['parsing', 'expanding', 'searching', 'ranking', 'explaining'] as SearchStage[]).map((stage) => {
                const isCompleted = completedStages.includes(stage)
                const isCurrent = currentStage === stage
                const config = stageConfig[stage]

                return (
                  <div
                    key={stage}
                    className={clsx(
                      'flex items-center gap-2 text-sm transition-all',
                      isCompleted ? 'text-green-600' : isCurrent ? 'text-purple-700' : 'text-gray-400'
                    )}
                  >
                    {isCompleted ? (
                      <CheckCircle2 className="w-4 h-4" />
                    ) : isCurrent ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <span className="w-4 h-4 flex items-center justify-center text-xs">{config.icon}</span>
                    )}
                    <span>{config.label}</span>
                    {isCurrent && stageMessage && (
                      <span className="text-xs text-gray-500 ml-2">- {stageMessage}</span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Legacy Search Progress */}
        {isSearching && !useStreaming && (
          <div className="mt-4 p-4 bg-purple-50 rounded-lg">
            <div className="flex items-center gap-2 text-purple-700">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">AI 正在分析你的需求，推理相关概念，执行多轮搜索...</span>
            </div>
          </div>
        )}

        {/* Search History (AI's thought process) */}
        {searchHistory.length > 0 && (
          <div className="mt-4">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
            >
              {showHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              AI 搜索过程 ({searchHistory.length} 轮)
            </button>
            {showHistory && (
              <div className="mt-2 p-3 bg-gray-50 rounded-lg space-y-2">
                {searchHistory.map((h, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className="text-gray-400">第{i + 1}轮:</span>
                    <span className="text-gray-700">搜索 [{h.terms.join(', ')}]</span>
                    <span className="text-gray-500">- 找到 {h.found} 人</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* AI Summary */}
        {searchSummary && (
          <div className="mt-4 p-4 bg-blue-50 rounded-lg">
            <div className="text-sm text-blue-800 whitespace-pre-wrap">{searchSummary}</div>
          </div>
        )}
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">搜索结果</h2>
            <div className="flex items-center gap-3">
              {!isRanked && (
                <span className="text-xs text-yellow-600 bg-yellow-50 px-2 py-1 rounded">
                  排序中...
                </span>
              )}
              <span className="text-sm text-gray-500">{results.length} 人</span>
            </div>
          </div>
          <div className="divide-y divide-gray-100">
            {results.map((candidate, index) => (
              <div
                key={candidate.id}
                className={clsx(
                  "p-4 hover:bg-gray-50 transition-all",
                  !isRanked && "opacity-80"
                )}
                style={{
                  // Animate reordering when ranking completes
                  transition: isRanked ? 'all 0.3s ease-out' : 'none'
                }}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3">
                      <span className="font-medium text-gray-900">{candidate.name}</span>
                      {/* Fit Summary Badge - replaces match score */}
                      {candidate.fit_summary && (
                        <span className="text-sm text-gray-600 italic">
                          {candidate.fit_summary}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-gray-600 mt-1">
                      {candidate.current_title}
                      {candidate.current_company && ` @ ${candidate.current_company}`}
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
                          {candidate.years_of_experience}年经验
                        </span>
                      )}
                      {candidate.expected_salary && (
                        <span>{candidate.expected_salary}万/年</span>
                      )}
                    </div>
                    {/* Match Reasons */}
                    {candidate.match_reasons.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {candidate.match_reasons.map((r, i) => (
                          <span key={i} className="text-xs text-purple-600 bg-purple-50 px-2 py-0.5 rounded">
                            {r.reason}
                          </span>
                        ))}
                      </div>
                    )}
                    {/* Skills */}
                    {candidate.skills && (
                      <div className="mt-2 text-xs text-gray-500">
                        技能: {(() => {
                          try {
                            const skills = JSON.parse(candidate.skills)
                            return Array.isArray(skills) ? skills.slice(0, 5).join(', ') + (skills.length > 5 ? '...' : '') : candidate.skills
                          } catch {
                            return candidate.skills.slice(0, 100)
                          }
                        })()}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isSearching && results.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Users className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 mb-4">输入搜索条件，AI 会帮你智能匹配候选人</p>
          <div className="text-sm text-gray-400">
            <p className="mb-2">示例搜索：</p>
            <div className="space-y-1">
              <p>"有大模型经验的产品经理"</p>
              <p>"做过 AI Agent 的工程师"</p>
              <p>"智谱或百度背景的算法专家"</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
