import { useState, useRef, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload as UploadIcon, FolderOpen, File, CheckCircle, XCircle, Loader2, AlertCircle, Clock } from 'lucide-react'
import clsx from 'clsx'
import { uploadResumeBatch, getPools, addCandidateToPool, UploadProgress } from '../services/api'

type FileStatus = 'pending' | 'uploading' | 'parsing' | 'done' | 'error'

interface FileWithStatus {
  file: File
  status: FileStatus
  error?: string
  candidateId?: number
}

export default function Upload() {
  const [filesWithStatus, setFilesWithStatus] = useState<FileWithStatus[]>([])
  const [progress, setProgress] = useState<UploadProgress | null>(null)
  const [selectedPool, setSelectedPool] = useState<number | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const { data: pools } = useQuery({
    queryKey: ['pools'],
    queryFn: () => getPools()
  })

  const updateFileStatus = useCallback((filename: string, status: FileStatus, error?: string, candidateId?: number) => {
    setFilesWithStatus(prev => prev.map(f =>
      f.file.name === filename
        ? { ...f, status, error, candidateId }
        : f
    ))
  }, [])

  const uploadMutation = useMutation({
    mutationFn: async (files: File[]) => {
      const uploadResults = await uploadResumeBatch(files, (prog) => {
        setProgress(prog)

        // 更新单个文件状态
        if (prog.currentStatus === 'uploading') {
          updateFileStatus(prog.current, 'uploading')
        } else if (prog.currentStatus === 'parsing') {
          updateFileStatus(prog.current, 'parsing')
        } else if (prog.currentStatus === 'done') {
          const result = prog.results.find(r => r.filename === prog.current)
          updateFileStatus(prog.current, 'done', undefined, result?.candidate_id)
        } else if (prog.currentStatus === 'error') {
          const result = prog.results.find(r => r.filename === prog.current)
          updateFileStatus(prog.current, 'error', result?.error)
        }
      })

      // Add to pool if selected
      if (selectedPool) {
        for (const r of uploadResults) {
          if (r.success && r.candidate_id) {
            try {
              await addCandidateToPool(selectedPool, r.candidate_id)
            } catch (e) {
              console.error('Failed to add to pool:', e)
            }
          }
        }
      }

      return uploadResults
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['pools'] })
    }
  })

  const handleFiles = useCallback((newFiles: FileList | File[]) => {
    const validFiles = Array.from(newFiles).filter(f =>
      f.type === 'application/pdf' ||
      f.name.toLowerCase().endsWith('.pdf') ||
      f.name.toLowerCase().endsWith('.docx') ||
      f.name.toLowerCase().endsWith('.doc')
    )
    const filesWithPendingStatus: FileWithStatus[] = validFiles.map(file => ({
      file,
      status: 'pending' as FileStatus
    }))
    setFilesWithStatus(prev => [...prev, ...filesWithPendingStatus])
    setProgress(null)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const items = e.dataTransfer.items
    const filePromises: Promise<File>[] = []

    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      if (item.kind === 'file') {
        const entry = item.webkitGetAsEntry?.()
        if (entry) {
          if (entry.isDirectory) {
            filePromises.push(...traverseDirectory(entry as FileSystemDirectoryEntry))
          } else {
            const file = item.getAsFile()
            if (file) filePromises.push(Promise.resolve(file))
          }
        }
      }
    }

    Promise.all(filePromises).then(files => handleFiles(files))
  }, [handleFiles])

  const traverseDirectory = (dir: FileSystemDirectoryEntry): Promise<File>[] => {
    const promises: Promise<File>[] = []
    const reader = dir.createReader()

    const readEntries = (): Promise<File[]> => {
      return new Promise((resolve) => {
        reader.readEntries(async (entries) => {
          const files: File[] = []
          for (const entry of entries) {
            if (entry.isFile) {
              const file = await new Promise<File>((res) => {
                (entry as FileSystemFileEntry).file(res)
              })
              if (file.name.toLowerCase().endsWith('.pdf') ||
                  file.name.toLowerCase().endsWith('.docx') ||
                  file.name.toLowerCase().endsWith('.doc')) {
                files.push(file)
              }
            } else if (entry.isDirectory) {
              const subFiles = await Promise.all(traverseDirectory(entry as FileSystemDirectoryEntry))
              files.push(...subFiles)
            }
          }
          if (entries.length > 0) {
            const moreFiles = await readEntries()
            resolve([...files, ...moreFiles])
          } else {
            resolve(files)
          }
        })
      })
    }

    promises.push(readEntries().then(files => files).then(f => f[0] || new File([], '')))
    return promises
  }

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      handleFiles(e.target.files)
    }
  }

  const startUpload = () => {
    if (filesWithStatus.length === 0) return
    const files = filesWithStatus.map(f => f.file)
    uploadMutation.mutate(files)
  }

  const clearFiles = () => {
    setFilesWithStatus([])
    setProgress(null)
  }

  const successCount = filesWithStatus.filter(f => f.status === 'done').length
  const failCount = filesWithStatus.filter(f => f.status === 'error').length
  const pendingCount = filesWithStatus.filter(f => f.status === 'pending').length
  const processingCount = filesWithStatus.filter(f => f.status === 'uploading' || f.status === 'parsing').length

  const getStatusIcon = (status: FileStatus) => {
    switch (status) {
      case 'pending':
        return <Clock className="w-4 h-4 text-gray-400" />
      case 'uploading':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
      case 'parsing':
        return <Loader2 className="w-4 h-4 text-purple-500 animate-spin" />
      case 'done':
        return <CheckCircle className="w-4 h-4 text-green-500" />
      case 'error':
        return <XCircle className="w-4 h-4 text-red-500" />
    }
  }

  const getStatusText = (status: FileStatus) => {
    switch (status) {
      case 'pending': return '等待中'
      case 'uploading': return '上传中...'
      case 'parsing': return 'AI 解析中...'
      case 'done': return '完成'
      case 'error': return '失败'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">批量导入简历</h1>
          <p className="text-gray-500 mt-1">支持 PDF、Word 格式，可一次性上传大量文件或整个文件夹</p>
        </div>
      </div>

      {/* Pool Selection */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-3">导入到人才库（可选）</h2>
        <select
          value={selectedPool || ''}
          onChange={(e) => setSelectedPool(e.target.value ? Number(e.target.value) : null)}
          className="w-full max-w-md px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option value="">不指定人才库（仅建档）</option>
          {pools?.map(pool => (
            <option key={pool.id} value={pool.id}>
              {pool.share_scope === 'org' ? '🏢' : pool.share_scope === 'custom' ? '👥' : '🔒'} {pool.name} ({pool.candidate_count} 人)
            </option>
          ))}
        </select>
      </div>

      {/* Upload Area */}
      <div
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={clsx(
          'border-2 border-dashed rounded-xl p-12 text-center transition-colors',
          isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-white',
          uploadMutation.isPending && 'pointer-events-none opacity-50'
        )}
      >
        <UploadIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
        <p className="text-lg font-medium text-gray-900 mb-2">
          拖拽文件或文件夹到此处
        </p>
        <p className="text-gray-500 mb-6">支持 PDF、Word 格式，可批量上传数万份简历</p>
        <div className="flex items-center justify-center gap-4">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx"
            multiple
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
            className="hidden"
          />
          <input
            ref={folderInputRef}
            type="file"
            // @ts-ignore
            webkitdirectory=""
            directory=""
            multiple
            onChange={handleFolderSelect}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            <File className="w-5 h-5" />
            选择文件
          </button>
          <button
            onClick={() => folderInputRef.current?.click()}
            className="flex items-center gap-2 px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <FolderOpen className="w-5 h-5" />
            选择文件夹
          </button>
        </div>
      </div>

      {/* File List */}
      {filesWithStatus.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-900">
              文件列表 ({filesWithStatus.length} 个)
            </h2>
            <div className="flex gap-3">
              <button
                onClick={clearFiles}
                disabled={uploadMutation.isPending}
                className="px-4 py-2 text-gray-600 hover:text-gray-900 transition-colors disabled:opacity-50"
              >
                清空
              </button>
              <button
                onClick={startUpload}
                disabled={uploadMutation.isPending || pendingCount === 0}
                className="flex items-center gap-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {uploadMutation.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    处理中...
                  </>
                ) : (
                  <>
                    <UploadIcon className="w-4 h-4" />
                    开始上传
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Progress Summary */}
          {(uploadMutation.isPending || successCount > 0 || failCount > 0) && (
            <div className="mb-4 p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-4 text-sm">
                  {processingCount > 0 && (
                    <span className="flex items-center gap-1 text-blue-600">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      处理中: {processingCount}
                    </span>
                  )}
                  <span className="text-green-600">✓ 成功: {successCount}</span>
                  <span className="text-red-600">✗ 失败: {failCount}</span>
                  <span className="text-gray-500">待处理: {pendingCount}</span>
                </div>
                <span className="text-sm text-gray-600">
                  {successCount + failCount} / {filesWithStatus.length}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div className="flex h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-green-500 transition-all"
                    style={{ width: `${(successCount / filesWithStatus.length) * 100}%` }}
                  />
                  <div
                    className="bg-red-500 transition-all"
                    style={{ width: `${(failCount / filesWithStatus.length) * 100}%` }}
                  />
                  <div
                    className="bg-blue-500 transition-all animate-pulse"
                    style={{ width: `${(processingCount / filesWithStatus.length) * 100}%` }}
                  />
                </div>
              </div>
              {progress?.current && (
                <div className="mt-2 text-sm text-gray-600">
                  当前: <span className="font-medium">{progress.current}</span>
                  {progress.currentStatus === 'parsing' && (
                    <span className="ml-2 text-purple-600">AI 正在解析简历...</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* File List */}
          <div className="max-h-96 overflow-y-auto space-y-2">
            {filesWithStatus.slice(0, 100).map((item, i) => (
              <div
                key={i}
                className={clsx(
                  'flex items-center justify-between p-3 rounded-lg transition-colors',
                  item.status === 'done' && 'bg-green-50',
                  item.status === 'error' && 'bg-red-50',
                  (item.status === 'uploading' || item.status === 'parsing') && 'bg-blue-50',
                  item.status === 'pending' && 'bg-gray-50'
                )}
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  {getStatusIcon(item.status)}
                  <span className="text-sm text-gray-900 truncate">{item.file.name}</span>
                  <span className="text-xs text-gray-500 flex-shrink-0">
                    {(item.file.size / 1024).toFixed(1)} KB
                  </span>
                </div>
                <div className="flex items-center gap-2 ml-2">
                  <span className={clsx(
                    'text-xs px-2 py-1 rounded',
                    item.status === 'done' && 'bg-green-100 text-green-700',
                    item.status === 'error' && 'bg-red-100 text-red-700',
                    item.status === 'uploading' && 'bg-blue-100 text-blue-700',
                    item.status === 'parsing' && 'bg-purple-100 text-purple-700',
                    item.status === 'pending' && 'bg-gray-100 text-gray-600'
                  )}>
                    {getStatusText(item.status)}
                  </span>
                  {item.error && (
                    <span className="text-xs text-red-600 max-w-xs truncate" title={item.error}>
                      {item.error}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {filesWithStatus.length > 100 && (
              <div className="text-center text-gray-500 text-sm py-2">
                ... 还有 {filesWithStatus.length - 100} 个文件
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tips */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <div className="flex gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-amber-800">
            <p className="font-medium mb-1">批量上传提示</p>
            <ul className="list-disc list-inside space-y-1 text-amber-700">
              <li>支持一次性上传数万份简历，系统会自动分批处理</li>
              <li>可直接拖拽整个文件夹，系统会自动识别其中的 PDF/Word 文件</li>
              <li>图片版 PDF 会自动使用 AI 视觉识别提取文本</li>
              <li>上传过程中请勿关闭页面，大量文件可能需要较长时间</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
