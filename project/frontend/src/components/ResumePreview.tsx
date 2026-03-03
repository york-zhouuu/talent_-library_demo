import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Loader2, RefreshCw, Mail, Phone, MapPin, Briefcase, GraduationCap, Award, Calendar, Building, ChevronRight, FileText, LayoutGrid, Download } from 'lucide-react'
import clsx from 'clsx'
import { getStructuredProfile, generateStructuredProfile, StructuredProfileResponse, getResumeDownloadUrl } from '../services/api'

interface ResumePreviewProps {
  candidateId: number
  candidateName: string
  parseStatus?: string
  onClose: () => void
}

type TabType = 'structured' | 'raw'

export default function ResumePreview({ candidateId, candidateName, parseStatus, onClose }: ResumePreviewProps) {
  const [isGenerating, setIsGenerating] = useState(false)
  const [activeTab, setActiveTab] = useState<TabType>('structured')
  const queryClient = useQueryClient()

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['structured-profile', candidateId],
    queryFn: () => getStructuredProfile(candidateId),
    retry: false,
    // 如果正在解析中，每 3 秒轮询一次
    refetchInterval: parseStatus === 'parsing' ? 3000 : false
  })

  // 当解析完成时停止轮询并刷新
  useEffect(() => {
    if (parseStatus === 'completed' && !data) {
      refetch()
    }
  }, [parseStatus, data, refetch])

  const generateMutation = useMutation({
    mutationFn: () => generateStructuredProfile(candidateId, true),
    onMutate: () => setIsGenerating(true),
    onSettled: () => setIsGenerating(false),
    onSuccess: () => {
      refetch()
      queryClient.invalidateQueries({ queryKey: ['pool-candidates'] })
    }
  })

  const handleGenerate = () => {
    generateMutation.mutate()
  }

  // 正在解析中
  const isParsing = parseStatus === 'parsing' || parseStatus === 'pending'

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-bold text-gray-900">{candidateName} - 简历预览</h2>
          <div className="flex items-center gap-2">
            <a
              href={getResumeDownloadUrl(candidateId)}
              download
              className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
              title="下载原始简历"
            >
              <Download className="w-5 h-5" />
            </a>
            {data && (
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
                title="重新解析"
              >
                <RefreshCw className={clsx("w-5 h-5", isGenerating && "animate-spin")} />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tabs */}
        {data && (
          <div className="flex border-b border-gray-200 px-6">
            <button
              onClick={() => setActiveTab('structured')}
              className={clsx(
                'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'structured'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}
            >
              <LayoutGrid className="w-4 h-4" />
              结构化简历
            </button>
            <button
              onClick={() => setActiveTab('raw')}
              className={clsx(
                'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'raw'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}
            >
              <FileText className="w-4 h-4" />
              原始简历
            </button>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
              <span className="ml-3 text-gray-500">加载中...</span>
            </div>
          ) : isParsing && !data ? (
            // 正在解析中
            <div className="flex flex-col items-center justify-center py-20">
              <Loader2 className="w-16 h-16 text-blue-500 animate-spin mb-6" />
              <p className="text-lg font-medium text-gray-700 mb-2">正在解析简历...</p>
              <p className="text-sm text-gray-500">AI 正在提取结构化信息，请稍候</p>
            </div>
          ) : error || !data ? (
            // 解析失败或未解析
            <div className="flex flex-col items-center justify-center py-20">
              <div className="text-gray-400 mb-4">
                <Briefcase className="w-16 h-16" />
              </div>
              <p className="text-gray-500 mb-6">
                {parseStatus === 'failed' ? '简历解析失败' : '尚未生成结构化简历预览'}
              </p>
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
              >
                {isGenerating ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    正在解析简历...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-5 h-5" />
                    {parseStatus === 'failed' ? '重新解析' : '解析简历'}
                  </>
                )}
              </button>
            </div>
          ) : activeTab === 'structured' ? (
            <ResumeContent profile={data.profile} />
          ) : (
            <RawResumeContent rawText={data.raw_text || ''} />
          )}
        </div>
      </div>
    </div>
  )
}

function RawResumeContent({ rawText }: { rawText: string }) {
  if (!rawText) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <FileText className="w-16 h-16 text-gray-300 mb-4" />
        <p className="text-gray-500">原始简历文本不可用</p>
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="bg-gray-50 rounded-lg p-6 font-mono text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
        {rawText}
      </div>
    </div>
  )
}

function ResumeContent({ profile }: { profile: StructuredProfileResponse['profile'] }) {
  const basic = profile.basic_info
  const career = profile.career_summary

  return (
    <div className="p-8">
      {/* Header Section - Personal Info */}
      <div className="mb-8 pb-6 border-b-2 border-gray-200">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {basic?.name || '未知姓名'}
        </h1>
        {career?.one_liner && (
          <p className="text-lg text-gray-600 mb-4">{career.one_liner}</p>
        )}
        <div className="flex flex-wrap gap-4 text-sm text-gray-600">
          {basic?.phone && (
            <span className="flex items-center gap-1.5">
              <Phone className="w-4 h-4 text-gray-400" />
              {basic.phone}
            </span>
          )}
          {basic?.email && (
            <span className="flex items-center gap-1.5">
              <Mail className="w-4 h-4 text-gray-400" />
              {basic.email}
            </span>
          )}
          {basic?.city && (
            <span className="flex items-center gap-1.5">
              <MapPin className="w-4 h-4 text-gray-400" />
              {basic.city}
            </span>
          )}
          {career?.years_of_experience && (
            <span className="flex items-center gap-1.5">
              <Briefcase className="w-4 h-4 text-gray-400" />
              {career.years_of_experience} 年经验
            </span>
          )}
          {(career?.expected_salary || career?.expected_salary_range) && (
            <span className="flex items-center gap-1.5 text-green-600 font-medium">
              期望: {career.expected_salary ? `${career.expected_salary}万/年` : career.expected_salary_range}
            </span>
          )}
        </div>
      </div>

      {/* Highlights */}
      {profile.highlights && profile.highlights.length > 0 && (
        <ResumeSection title="核心优势" icon={<Award className="w-5 h-5" />}>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {profile.highlights.map((h, i) => (
              <li key={i} className="flex items-start gap-2">
                <ChevronRight className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" />
                <span className="text-gray-700">{h}</span>
              </li>
            ))}
          </ul>
        </ResumeSection>
      )}

      {/* Work Experience */}
      {profile.work_experience && profile.work_experience.length > 0 && (
        <ResumeSection title="工作经历" icon={<Briefcase className="w-5 h-5" />}>
          <div className="space-y-6">
            {profile.work_experience.map((exp, i) => (
              <div key={i} className="relative pl-4 border-l-2 border-blue-200">
                <div className="absolute -left-[9px] top-0 w-4 h-4 bg-blue-500 rounded-full border-2 border-white" />
                <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                  <div>
                    <h4 className="text-lg font-semibold text-gray-900">{exp.title}</h4>
                    <div className="flex items-center gap-2 text-gray-600">
                      <Building className="w-4 h-4" />
                      <span>{exp.company}</span>
                      {exp.department && <span className="text-gray-400">· {exp.department}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    <Calendar className="w-3.5 h-3.5" />
                    {exp.start_date} - {exp.is_current ? '至今' : exp.end_date}
                  </div>
                </div>

                {exp.responsibilities && exp.responsibilities.length > 0 && (
                  <ul className="mt-3 space-y-1.5">
                    {exp.responsibilities.map((r, j) => (
                      <li key={j} className="flex items-start gap-2 text-gray-600">
                        <span className="text-gray-400 mt-1">•</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                )}

                {exp.achievements && exp.achievements.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {exp.achievements.map((a, j) => (
                      <span key={j} className="px-2 py-1 bg-green-50 text-green-700 text-sm rounded border border-green-200">
                        {a}
                      </span>
                    ))}
                  </div>
                )}

                {exp.tech_stack && exp.tech_stack.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {exp.tech_stack.map((t, j) => (
                      <span key={j} className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </ResumeSection>
      )}

      {/* Education */}
      {profile.education && profile.education.length > 0 && (
        <ResumeSection title="教育背景" icon={<GraduationCap className="w-5 h-5" />}>
          <div className="space-y-4">
            {profile.education.map((edu, i) => (
              <div key={i} className="flex items-start justify-between">
                <div>
                  <h4 className="font-semibold text-gray-900">{edu.school}</h4>
                  <div className="text-gray-600">
                    {edu.degree && <span>{edu.degree}</span>}
                    {edu.major && <span> · {edu.major}</span>}
                  </div>
                  {edu.honors && edu.honors.length > 0 && (
                    <div className="mt-1 text-sm text-yellow-600">
                      {edu.honors.join(' / ')}
                    </div>
                  )}
                </div>
                <div className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">
                  {edu.start_date} - {edu.end_date}
                </div>
              </div>
            ))}
          </div>
        </ResumeSection>
      )}

      {/* Projects */}
      {profile.projects && profile.projects.length > 0 && (
        <ResumeSection title="项目经历" icon={<Briefcase className="w-5 h-5" />}>
          <div className="space-y-4">
            {profile.projects.map((proj, i) => (
              <div key={i} className="p-4 bg-gray-50 rounded-lg">
                <div className="flex items-start justify-between mb-2">
                  <h4 className="font-semibold text-gray-900">{proj.name}</h4>
                  {proj.period && (
                    <span className="text-sm text-gray-500">{proj.period}</span>
                  )}
                </div>
                {proj.role && (
                  <div className="text-sm text-blue-600 mb-2">{proj.role}</div>
                )}
                {proj.description && (
                  <p className="text-gray-600 text-sm">{proj.description}</p>
                )}
                {proj.highlights && proj.highlights.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {proj.highlights.map((h, j) => (
                      <li key={j} className="flex items-start gap-2 text-sm text-gray-600">
                        <span className="text-green-500">✓</span>
                        <span>{h}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {proj.tech_stack && proj.tech_stack.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {proj.tech_stack.map((t, j) => (
                      <span key={j} className="px-1.5 py-0.5 bg-white text-gray-600 text-xs rounded border">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </ResumeSection>
      )}

      {/* Skills */}
      {profile.skills && (
        <ResumeSection title="专业技能" icon={<Award className="w-5 h-5" />}>
          <div className="space-y-4">
            {profile.skills.technical && profile.skills.technical.length > 0 && (
              <SkillGroup label="技术技能" skills={profile.skills.technical} color="blue" />
            )}
            {profile.skills.tools && profile.skills.tools.length > 0 && (
              <SkillGroup label="工具软件" skills={profile.skills.tools} color="gray" />
            )}
            {profile.skills.industries && profile.skills.industries.length > 0 && (
              <SkillGroup label="行业经验" skills={profile.skills.industries} color="purple" />
            )}
            {profile.skills.languages && profile.skills.languages.length > 0 && (
              <div>
                <span className="text-sm text-gray-500 mr-3">语言能力:</span>
                <span className="text-gray-700">
                  {profile.skills.languages.map(l => `${l.language}${l.level ? `(${l.level})` : ''}`).join(' / ')}
                </span>
              </div>
            )}
            {profile.skills.soft_skills && profile.skills.soft_skills.length > 0 && (
              <SkillGroup label="软技能" skills={profile.skills.soft_skills} color="green" />
            )}
          </div>
        </ResumeSection>
      )}

      {/* Certifications */}
      {profile.certifications && profile.certifications.length > 0 && (
        <ResumeSection title="证书资质" icon={<Award className="w-5 h-5" />}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {profile.certifications.map((cert, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div>
                  <div className="font-medium text-gray-900">{cert.name}</div>
                  {cert.issuer && <div className="text-sm text-gray-500">{cert.issuer}</div>}
                </div>
                {cert.date && <div className="text-sm text-gray-400">{cert.date}</div>}
              </div>
            ))}
          </div>
        </ResumeSection>
      )}

      {/* Tags */}
      {profile.tags && profile.tags.length > 0 && (
        <div className="mt-8 pt-6 border-t border-gray-200">
          <div className="flex flex-wrap gap-2">
            {profile.tags.map((tag, i) => (
              <span key={i} className="px-3 py-1 bg-blue-50 text-blue-600 text-sm rounded-full">
                #{tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ResumeSection({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-blue-600">{icon}</span>
        <h3 className="text-lg font-bold text-gray-900">{title}</h3>
        <div className="flex-1 h-px bg-gray-200 ml-2" />
      </div>
      {children}
    </div>
  )
}

function SkillGroup({ label, skills, color }: { label: string; skills: string[]; color: 'blue' | 'gray' | 'purple' | 'green' }) {
  const colorClasses = {
    blue: 'bg-blue-100 text-blue-700',
    gray: 'bg-gray-100 text-gray-700',
    purple: 'bg-purple-100 text-purple-700',
    green: 'bg-green-100 text-green-700'
  }

  return (
    <div>
      <span className="text-sm text-gray-500 mr-3">{label}:</span>
      <div className="inline-flex flex-wrap gap-1.5 mt-1">
        {skills.map((s, i) => (
          <span key={i} className={clsx('px-2 py-0.5 text-sm rounded', colorClasses[color])}>
            {s}
          </span>
        ))}
      </div>
    </div>
  )
}
