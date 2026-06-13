import { useEffect, useMemo, useRef, useState } from 'react'

const targetSampleRate = 16000

const defaultCommandsHint = [
  '动作：画 / 撤销 / 清空 / 保存',
  '形状：圆、矩形、三角形、直线、文字',
  '位置：左上 / 上 / 右上 / 左 / 中 / 右 / 左下 / 下 / 右下',
  '尺寸：小 / 中 / 大，或百分比（例：“宽20%高10%”）',
  '示例：“在中间画红色大圆”“撤销上一步”“清空画布”',
]

const guidance = [
  '尽量一句话说清：位置 + 形状 + 颜色 + 大小，例如“在左上角画一个红色小圆”。',
  '复杂物体分步说：先画轮廓，再补细节，例如“先画一只猫的头”“再画耳朵两侧”。',
  '如果需要文字，直接说出文字内容：如“在中间写四个字：你好世界”。',
  '撤销/清空/保存就是口令：“撤销上一步”“清空画布”“保存图片”。',
  '色彩可说常见中文色词：红色、蓝色、绿色、黄色、紫色、黑色、白色。',
]

const StatusChip = ({ status }) => {
  const tone = useMemo(() => {
    if (!status) return { text: '待机', color: 'bg-slate-100 text-slate-700 border border-slate-200' }
    if (status.includes('错误') || status.toLowerCase().includes('error')) {
      return { text: '错误', color: 'bg-red-100 text-red-700 border border-red-200' }
    }
    if (status.includes('录音') || status.includes('识别') || status.includes('上传')) {
      return { text: '处理', color: 'bg-amber-100 text-amber-800 border border-amber-200' }
    }
    return { text: '待机', color: 'bg-slate-100 text-slate-700 border border-slate-200' }
  }, [status])

  return (
    <span className={`px-3 py-1 rounded-full text-xs ${tone.color}`} title={status}>
      {tone.text}
    </span>
  )
}

function App() {
  const canvasRef = useRef(null)
  const backgroundRef = useRef(null)
  const [backgroundData, setBackgroundData] = useState('')
  const audioCtxRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const processorRef = useRef(null)
  const sourceRef = useRef(null)
  const pcmChunksRef = useRef([])
  const stackRef = useRef([])

  const [status, setStatus] = useState('待机')
  const [isRecording, setIsRecording] = useState(false)
  const [asrText, setAsrText] = useState('')
  const [replyText, setReplyText] = useState('')
  const [commandJson, setCommandJson] = useState('[]')
  const [history, setHistory] = useState([])
  const [activeTab, setActiveTab] = useState('draw')
  const synthRef = useRef(window.speechSynthesis || null)
  const [saveTitle, setSaveTitle] = useState('')
  const [drawings, setDrawings] = useState([])
  const [loadingDrawings, setLoadingDrawings] = useState(false)
  const [saving, setSaving] = useState(false)
  const LOCAL_KEY = 'voice2canvas_stack_v1'
  const [showGrid, setShowGrid] = useState(true)
  const [gridCols, setGridCols] = useState(12)
  const [gridRows, setGridRows] = useState(8)
  const [lineFromCell, setLineFromCell] = useState('')
  const [lineToCell, setLineToCell] = useState('')
  const [lineWidthSetting, setLineWidthSetting] = useState(2)
  const [lineDashed, setLineDashed] = useState(false)
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiGenerating, setAiGenerating] = useState(false)
  const [autoAiPending, setAutoAiPending] = useState(false)
  const [aiFromVoiceMode, setAiFromVoiceMode] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    // 恢复本地存储的命令
    try {
      const cached = localStorage.getItem(LOCAL_KEY)
      if (cached) {
        const commands = JSON.parse(cached)
        replaceStack(commands)
        setCommandJson(JSON.stringify(commands, null, 2))
        setStatus('已恢复上次画板')
      }
    } catch (e) {
      // ignore
    }
  }, [])

  useEffect(() => {
    return () => {
      cleanupAudio()
    }
  }, [])

  useEffect(() => {
    redraw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showGrid, gridCols, gridRows])

  const cleanupAudio = (opts = { resetPcm: true }) => {
    processorRef.current?.disconnect()
    sourceRef.current?.disconnect()
    mediaStreamRef.current?.getTracks()?.forEach((t) => t.stop())
    audioCtxRef.current?.close()
    processorRef.current = null
    sourceRef.current = null
    mediaStreamRef.current = null
    audioCtxRef.current = null
    if (opts.resetPcm) {
      pcmChunksRef.current = []
    }
    setIsRecording(false)
  }

  const startRecording = async () => {
    if (isRecording) return
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('浏览器不支持录音')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: targetSampleRate,
      })
      audioCtxRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)
      sourceRef.current = source
      const processor = audioCtx.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor
      pcmChunksRef.current = []
      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0)
        pcmChunksRef.current.push(new Float32Array(input))
      }
      source.connect(processor)
      processor.connect(audioCtx.destination)
      setIsRecording(true)
      setStatus('录音中… 再次点击停止')
    } catch (err) {
      setStatus(`错误：${err?.message || '录音失败'}`)
      cleanupAudio()
    }
  }

  const captureBackgroundDataUrl = (img) => {
    const canvas = canvasRef.current
    if (!canvas || !img) return ''
    const off = document.createElement('canvas')
    off.width = canvas.width
    off.height = canvas.height
    const ctx = off.getContext('2d')
    ctx.drawImage(img, 0, 0, off.width, off.height)
    try {
      return off.toDataURL('image/png')
    } catch (e) {
      return ''
    }
  }

  const stopRecording = () => {
    if (!isRecording) return
    try {
      const chunks = pcmChunksRef.current.slice()
      cleanupAudio({ resetPcm: false })
      const wavBlob = exportWav(chunks, targetSampleRate)
      pcmChunksRef.current = []
      setStatus('上传识别中…')
      sendAudio(wavBlob)
    } catch (err) {
      setStatus(`错误：${err?.message || '停止录音失败'}`)
    }
  }

  const interleave = (buffers, length) => {
    const result = new Float32Array(length)
    let offset = 0
    buffers.forEach((buf) => {
      result.set(buf, offset)
      offset += buf.length
    })
    return result
  }

  const floatTo16BitPCM = (float32Array) => {
    const buffer = new ArrayBuffer(float32Array.length * 2)
    const view = new DataView(buffer)
    let offset = 0
    for (let i = 0; i < float32Array.length; i += 1, offset += 2) {
      const s = Math.max(-1, Math.min(1, float32Array[i]))
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    }
    return buffer
  }

  const writeWavHeader = (view, sampleRate, numSamples) => {
    const blockAlign = 2
    const byteRate = sampleRate * blockAlign
    view.setUint32(0, 0x52494646, false)
    view.setUint32(4, 36 + numSamples * 2, true)
    view.setUint32(8, 0x57415645, false)
    view.setUint32(12, 0x666d7420, false)
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, 1, true)
    view.setUint32(24, sampleRate, true)
    view.setUint32(28, byteRate, true)
    view.setUint16(32, blockAlign, true)
    view.setUint16(34, 16, true)
    view.setUint32(36, 0x64617461, false)
    view.setUint32(40, numSamples * 2, true)
  }

  const exportWav = (chunks, sampleRate) => {
    const length = chunks.reduce((sum, b) => sum + b.length, 0)
    const pcm = interleave(chunks, length)
    const pcm16 = floatTo16BitPCM(pcm)
    const wavBuffer = new ArrayBuffer(44 + pcm16.byteLength)
    const view = new DataView(wavBuffer)
    writeWavHeader(view, sampleRate, pcm.length)
    new Uint8Array(wavBuffer, 44).set(new Uint8Array(pcm16))
    return new Blob([wavBuffer], { type: 'audio/wav' })
  }

  const sendAudio = async (blob) => {
    const form = new FormData()
    form.append('file', blob, 'speech.wav')
    try {
      setAsrText('识别中…')
      setReplyText('')
      const res = await fetch(`${apiBase}/api/asr-nlu`, { method: 'POST', body: form })
      const text = await res.text()

      if (!text) {
        throw new Error(res.ok ? '后端未返回数据' : res.statusText)
      }

      let data
      try {
        data = JSON.parse(text)
      } catch (parseErr) {
        throw new Error(`返回非 JSON：${text.slice(0, 120)}`)
      }

      if (!res.ok) throw new Error(data.detail || res.statusText)

      setAsrText(data.asr_text || '')
      setReplyText(data.reply_text || '')
      if (data.reply_text && synthRef.current) {
        const utter = new SpeechSynthesisUtterance(data.reply_text)
        utter.lang = 'zh-CN'
        synthRef.current.cancel()
        synthRef.current.speak(utter)
      }
      const cmds = (data.commands || []).map((cmd) => {
        if (cmd.shape === 'line') {
          // 若缺坐标，尝试从语音文本提取
          if (!cmd.from_cell || !cmd.to_cell) {
            const cells = extractCellsFromText(data.asr_text || '')
            if (cells.length >= 2) {
              return { ...cmd, from_cell: cells[0], to_cell: cells[1] }
            }
          }
          // 确保有 stroke
          const stroke = cmd.stroke || { color: '#000000', width: lineWidthSetting, dash: lineDashed ? [6, 4] : [] }
          return { ...cmd, stroke }
        }
        return cmd
      })
      setCommandJson(JSON.stringify(cmds, null, 2))
      const isNewBoard = (data.asr_text || '').includes('新建画板')
      if (isNewBoard && !aiFromVoiceMode) {
        await saveCurrentAndReset(`画板-${new Date().toLocaleTimeString()}`)
        return
      }
      if (aiFromVoiceMode) {
        // 不画命令，直接用 ASR 文本调用 AI 生图
        handleGenImage(data.asr_text || '')
        setAiFromVoiceMode(false)
        setStatus('AI 生图处理中…')
      } else {
        // 语音命令不清空历史，叠加绘制
        applyCommands(cmds, false)
        addHistory({
          asr: data.asr_text || '',
          reply: data.reply_text || '',
          commands: data.commands || [],
        })
        setStatus('完成')
      }
    } catch (err) {
      setStatus(`错误：${err?.message || '识别失败'}`)
    }
  }

  const applyCommands = (commands, reset = false) => {
    const shouldReset = reset && (commands?.length || 0) > 0
    const stack = shouldReset ? [] : [...stackRef.current]
    for (const cmd of commands) {
      if (cmd.action === 'undo') {
        stack.pop()
      } else if (cmd.action === 'clear') {
        stack.length = 0
      } else if (cmd.action === 'save') {
        saveCanvas()
      } else if (cmd.action === 'draw') {
        stack.push(cmd)
      }
    }
    stackRef.current = stack
    try {
      localStorage.setItem(LOCAL_KEY, JSON.stringify(stackRef.current))
    } catch (e) {
      // ignore
    }
    redraw()
  }

  const replaceStack = (commands) => {
    stackRef.current = [...(commands || [])]
    try {
      localStorage.setItem(LOCAL_KEY, JSON.stringify(stackRef.current))
    } catch (e) {
      // ignore
    }
    redraw()
  }

  const colLabel = (idx) => {
    let n = idx
    let label = ''
    while (n >= 0) {
      label = String.fromCharCode((n % 26) + 65) + label
      n = Math.floor(n / 26) - 1
    }
    return label
  }

  const parseCell = (cell) => {
    if (!cell || typeof cell !== 'string') return null
    const trimmed = cell.trim().toUpperCase()
    let match = trimmed.match(/^([A-Z]+)(\d+)$/)
    // 容错：无数字但以 I/L 结尾时，当作 1（处理 ASR 把 A1 听成 AI / AL）
    if (!match && /^[A-Z]+[IL]$/.test(trimmed)) {
      match = trimmed.replace(/([IL])$/, '1').match(/^([A-Z]+)(\d+)$/)
    }
    if (!match) return null
    const [, letters, numStr] = match
    let col = 0
    for (let i = 0; i < letters.length; i += 1) {
      col = col * 26 + (letters.charCodeAt(i) - 64)
    }
    col -= 1
    const row = parseInt(numStr, 10) - 1
    if (Number.isNaN(row) || row < 0 || col < 0) return null
    return { col, row }
  }

  const extractCellsFromText = (text) => {
    if (!text) return []
    const found = []
    const re = /([A-Za-z]+[0-9]+)/g
    let m
    while ((m = re.exec(text)) && found.length < 4) {
      found.push(m[1])
    }
    return found
  }

  const cellToCenterPx = (cell) => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const parsed = typeof cell === 'string' ? parseCell(cell) : cell
    if (!parsed) return null
    const { col, row } = parsed
    if (col >= gridCols || row >= gridRows) return null
    const cellW = canvas.width / gridCols
    const cellH = canvas.height / gridRows
    return { x: (col + 0.5) * cellW, y: (row + 0.5) * cellH }
  }

  const toPx = (val, axis) => {
    const canvas = canvasRef.current
    if (!canvas) return 0
    return (val || 0.5) * (axis === 'x' ? canvas.width : canvas.height)
  }

  const drawShape = (ctx, cmd) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pos = cmd.position || {}
    const size = cmd.size || {}
    const x = toPx(pos.x, 'x')
    const y = toPx(pos.y, 'y')
    const w = size.relative === false ? size.width || 100 : (size.width || 0.2) * canvas.width
    const h = size.relative === false ? size.height || 100 : (size.height || 0.2) * canvas.height

    ctx.save()
    ctx.fillStyle = typeof cmd.fill === 'string' ? cmd.fill : typeof cmd.color === 'string' ? cmd.color : '#ff0000'
    const strokeObj = cmd.stroke || (cmd.color && typeof cmd.color === 'object' ? cmd.color : null)
    if (strokeObj) {
      ctx.strokeStyle = strokeObj.color || '#000000'
      ctx.lineWidth = strokeObj.width || 2
    }

    switch (cmd.shape) {
      case 'circle': {
        const r = Math.min(w, h) / 2
        ctx.beginPath()
        ctx.arc(x, y, r, 0, Math.PI * 2)
        ctx.fill()
        if (cmd.stroke) ctx.stroke()
        break
      }
      case 'rect': {
        const ax = x - w / 2
        const ay = y - h / 2
        ctx.beginPath()
        ctx.rect(ax, ay, w, h)
        ctx.fill()
        if (cmd.stroke) ctx.stroke()
        break
      }
      case 'triangle': {
        const ax = x
        const ay = y - h / 2
        const bx = x - w / 2
        const by = y + h / 2
        const cx = x + w / 2
        const cy = y + h / 2
        ctx.beginPath()
        ctx.moveTo(ax, ay)
        ctx.lineTo(bx, by)
        ctx.lineTo(cx, cy)
        ctx.closePath()
        ctx.fill()
        if (cmd.stroke) ctx.stroke()
        break
      }
      case 'line': {
        let start = null
        let end = null
        if (cmd.from_cell && cmd.to_cell) {
          start = cellToCenterPx(cmd.from_cell)
          end = cellToCenterPx(cmd.to_cell)
        }
        if (!start || !end) {
          start = { x: x - w / 2, y: y - h / 2 }
          end = { x: x + w / 2, y: y + h / 2 }
        }
        // 对齐到 0.5 像素避免模糊
        const sx = Math.round(start.x) + 0.5
        const sy = Math.round(start.y) + 0.5
        const ex = Math.round(end.x) + 0.5
        const ey = Math.round(end.y) + 0.5
        ctx.beginPath()
        ctx.moveTo(sx, sy)
        ctx.lineTo(ex, ey)
        ctx.strokeStyle = strokeObj?.color || '#000000'
        ctx.lineWidth = strokeObj?.width || 2
        if (strokeObj?.dash && Array.isArray(strokeObj.dash) && strokeObj.dash.length > 0) {
          ctx.setLineDash(strokeObj.dash)
        } else {
          ctx.setLineDash([])
        }
        ctx.lineCap = 'round'
        ctx.stroke()
        break
      }
      case 'text': {
        ctx.fillStyle = cmd.color || '#000000'
        ctx.font = `${Math.max(16, Math.floor(h))}px sans-serif`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(cmd.text || '', x, y)
        break
      }
      default:
        break
    }
    ctx.restore()
  }

  const redraw = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    // 背景层
    if (backgroundRef.current) {
      ctx.drawImage(backgroundRef.current, 0, 0, canvas.width, canvas.height)
    } else {
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, canvas.width, canvas.height)
    }
    drawGrid(ctx, canvas)
    for (const cmd of stackRef.current) {
      if (cmd.action !== 'draw') continue
      drawShape(ctx, cmd)
    }
  }

  const drawGrid = (ctx, canvas) => {
    if (!showGrid) return
    const cellW = canvas.width / gridCols
    const cellH = canvas.height / gridRows
    ctx.save()
    ctx.strokeStyle = 'rgba(100,116,139,0.35)'
    ctx.lineWidth = 1
    for (let i = 0; i <= gridCols; i += 1) {
      const x = Math.round(i * cellW) + 0.5
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, canvas.height)
      ctx.stroke()
    }
    for (let j = 0; j <= gridRows; j += 1) {
      const y = Math.round(j * cellH) + 0.5
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(canvas.width, y)
      ctx.stroke()
    }
    ctx.fillStyle = 'rgba(51,65,85,0.9)'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    for (let i = 0; i < gridCols; i += 1) {
      ctx.fillText(colLabel(i), (i + 0.5) * cellW, 2)
    }
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    for (let j = 0; j < gridRows; j += 1) {
      ctx.fillText(`${j + 1}`, 4, (j + 0.5) * cellH)
    }
    ctx.restore()
  }

  const saveCanvas = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    const url = canvas.toDataURL('image/png')
    const a = document.createElement('a')
    a.href = url
    a.download = 'voice-drawing.png'
    a.click()
  }

  const addHistory = (entry) => {
    setHistory((prev) => [
      {
        ts: new Date().toLocaleTimeString(),
        ...entry,
      },
      ...prev,
    ])
  }

  const apiBase = import.meta.env.VITE_API_BASE || ''

  const fetchDrawings = async () => {
    setLoadingDrawings(true)
    try {
      const res = await fetch(`${apiBase}/api/drawings?limit=20`)
      const text = await res.text()
      if (!text) throw new Error(res.statusText || '后端无返回')
      const data = JSON.parse(text)
      if (!Array.isArray(data)) throw new Error('返回格式异常')
      setDrawings(data)
    } catch (err) {
      setStatus(`错误：获取画板失败 ${err?.message || ''}`)
    } finally {
      setLoadingDrawings(false)
    }
  }

  const loadDrawing = async (id) => {
    if (!id) return
    setLoadingDrawings(true)
    try {
      const res = await fetch(`${apiBase}/api/drawings/${id}`)
      const text = await res.text()
      if (!text) throw new Error(res.statusText || '后端无返回')
      const data = JSON.parse(text)
      if (!data?.commands) throw new Error('画板无命令')
      replaceStack(data.commands)
      if (data.background_base64) {
        const img = new Image()
        img.onload = () => {
          backgroundRef.current = img
          setBackgroundData(data.background_base64)
          redraw()
        }
        img.src = data.background_base64
      } else {
        backgroundRef.current = null
        setBackgroundData('')
        redraw()
      }
      setAsrText(data.asr_text || '')
      setReplyText(data.reply_text || '')
      setCommandJson(JSON.stringify(data.commands || [], null, 2))
      setStatus('已加载画板')
    } catch (err) {
      setStatus(`错误：加载失败 ${err?.message || ''}`)
    } finally {
      setLoadingDrawings(false)
    }
  }

  const saveDrawing = async () => {
    if (!stackRef.current.length && !backgroundData) {
      setStatus('当前没有内容可保存')
      return
    }
    setSaving(true)
    try {
      const payload = {
        title: saveTitle || '未命名',
        commands: stackRef.current,
        asr_text: asrText || '',
        reply_text: replyText || '',
        width: canvasRef.current?.width,
        height: canvasRef.current?.height,
        background_base64: backgroundData || undefined,
      }
      const res = await fetch(`${apiBase}/api/drawings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const text = await res.text()
      if (!text) throw new Error(res.statusText || '后端无返回')
      const data = JSON.parse(text)
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setStatus(`已保存：${data.title || data.id}`)
      setSaveTitle('')
      fetchDrawings()
    } catch (err) {
      setStatus(`错误：保存失败 ${err?.message || ''}`)
    } finally {
      setSaving(false)
    }
  }

  const loadBackground = async (theme) => {
    const canvas = canvasRef.current
    if (!canvas) return
    try {
      setStatus('背景生成中…')
      const res = await fetch(`/api/background?width=${canvas.width}&height=${canvas.height}&theme=${theme}`)
      if (!res.ok) throw new Error(res.statusText)
      const blob = await res.blob()
      const img = new Image()
      img.onload = () => {
        backgroundRef.current = img
        const dataUrl = captureBackgroundDataUrl(img)
        if (dataUrl) setBackgroundData(dataUrl)
        redraw()
        setStatus('背景已更新')
      }
      img.onerror = () => {
        setStatus('错误：背景加载失败')
      }
      img.src = URL.createObjectURL(blob)
    } catch (err) {
      setStatus(`错误：${err?.message || '背景失败'}`)
    }
  }

  const handleGenImage = async (promptOverride) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const promptToUse = (promptOverride && promptOverride.trim()) || aiPrompt.trim()
    if (!promptToUse) {
      setStatus('请先输入生成提示词')
      return
    }
    if (!promptOverride) {
      setAiPrompt(promptToUse)
    }
    setAiGenerating(true)
    try {
      setStatus('AI 生成中…')
      const res = await fetch(`${apiBase}/api/gen-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: promptToUse, size: '768x768' }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      const img = new Image()
      img.onload = () => {
        backgroundRef.current = img
        const dataUrl = captureBackgroundDataUrl(img)
        if (dataUrl) setBackgroundData(dataUrl)
        redraw()
        setStatus('背景已更新（AI 生成）')
      }
      img.onerror = () => setStatus('错误：AI 背景加载失败')
      img.src = `data:image/png;base64,${data.image_base64}`
    } catch (err) {
      setStatus(`错误：${err?.message || 'AI 生成失败'}`)
    } finally {
      setAiGenerating(false)
    }
  }

  const overwriteDrawing = async (drawing) => {
    if (!stackRef.current.length && !backgroundData) {
      setStatus('当前没有内容可覆盖')
      return
    }
    try {
      const payload = {
        title: saveTitle || drawing.title || `画板#${drawing.id}`,
        commands: stackRef.current,
        asr_text: asrText || '',
        reply_text: replyText || '',
        width: canvasRef.current?.width,
        height: canvasRef.current?.height,
        background_base64: backgroundData || null,
      }
      const res = await fetch(`${apiBase}/api/drawings/${drawing.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const text = await res.text()
      if (!text) throw new Error(res.statusText || '后端无返回')
      const data = JSON.parse(text)
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setStatus(`已覆盖画板：${data.title || data.id}`)
      fetchDrawings()
    } catch (err) {
      setStatus(`错误：覆盖失败 ${err?.message || ''}`)
    }
  }

  const deleteDrawing = async (id) => {
    try {
      const res = await fetch(`${apiBase}/api/drawings/${id}`, { method: 'DELETE' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || res.statusText)
      }
      setStatus('已删除画板')
      fetchDrawings()
    } catch (err) {
      setStatus(`错误：删除失败 ${err?.message || ''}`)
    }
  }

  const clearBoard = () => {
    stackRef.current = []
    backgroundRef.current = null
    setBackgroundData('')
    try {
      localStorage.removeItem(LOCAL_KEY)
    } catch (e) {
      // ignore
    }
    redraw()
  }

  const saveCurrentAndReset = async (autoTitle) => {
    if (!stackRef.current.length && !backgroundData) {
      clearBoard()
      setStatus('已新建空画板')
      return
    }
    try {
      const payload = {
        title: autoTitle || saveTitle || '未命名',
        commands: stackRef.current,
        asr_text: asrText || '',
        reply_text: replyText || '',
        width: canvasRef.current?.width,
        height: canvasRef.current?.height,
        background_base64: backgroundData || undefined,
      }
      const res = await fetch(`${apiBase}/api/drawings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const text = await res.text()
      if (!text) throw new Error(res.statusText || '后端无返回')
      const data = JSON.parse(text)
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setStatus(`已保存并新建：${data.title || data.id}`)
      clearBoard()
      fetchDrawings()
    } catch (err) {
      setStatus(`错误：保存失败 ${err?.message || ''}`)
    }
  }

  const maybeAutoGenBgFromVoice = (text) => {
    if (!text) return
    const t = text.trim()
    // 关键词检测：生成背景 / AI生图 / 生成图片 / 用AI
    const hit = /(生成背景|背景|生图|生成图片|用AI)/i.test(t)
    if (!hit) return
    setAiPrompt(t)
    setAutoAiPending(true)
    handleGenImage(t)
  }

  const handleAddLine = () => {
    if (!lineFromCell || !lineToCell) {
      setStatus('请输入起点和终点坐标，例如 A1 和 F5')
      return
    }
    const start = cellToCenterPx(lineFromCell)
    const end = cellToCenterPx(lineToCell)
    if (!start || !end) {
      setStatus('坐标无效或超出网格范围')
      return
    }
    const cmd = {
      action: 'draw',
      shape: 'line',
      from_cell: lineFromCell,
      to_cell: lineToCell,
      stroke: { color: '#000000', width: lineWidthSetting, dash: lineDashed ? [6, 4] : [] },
    }
    applyCommands([cmd])
    setCommandJson(JSON.stringify(stackRef.current, null, 2))
    setLineFromCell('')
    setLineToCell('')
    setStatus('已添加直线')
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-[1320px] px-6 py-8 lg:px-10">
        <header className="relative overflow-hidden rounded-3xl border border-slate-200/70 bg-white/95 p-6 shadow-[0_16px_40px_rgba(15,23,42,0.08)]">
          <div className="pointer-events-none absolute -top-24 -right-16 h-56 w-56 rounded-full bg-indigo-100/70 blur-2xl" />
          <div className="pointer-events-none absolute -bottom-24 -left-12 h-56 w-56 rounded-full bg-emerald-100/70 blur-2xl" />
          <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center">
            <div>
              <p className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
                Voice-First Canvas · Product UI
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 lg:text-4xl">Voice2Canvas Studio</h1>
              <p className="mt-2 text-sm text-slate-600 lg:text-base">
                语音驱动绘制与 AI 生图工作台。强调画布主舞台与专业控件体验，适合展示级 Demo。
              </p>
            </div>
            <div className="lg:ml-auto flex items-center gap-2">
              <StatusChip status={status} />
              <a
                href="/docs"
                target="_blank"
                className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
              >
                API 文档
              </a>
            </div>
          </div>
        </header>

        <main className="mt-6 grid gap-5 lg:grid-cols-12">
          <aside className="space-y-4 lg:col-span-4">
            <section className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">语音控制</h2>
              <p className="mt-1 text-xs text-slate-500">主控录音与识别入口</p>
              <div className="mt-3 flex gap-2">
                <button
                  onClick={startRecording}
                  disabled={isRecording}
                  className={`voice-btn flex-1 rounded-xl bg-slate-900 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300 disabled:text-slate-100 ${isRecording ? 'recording' : ''}`}
                >
                  {isRecording ? '录音中…' : '开始录音'}
                </button>
                <button
                  onClick={stopRecording}
                  disabled={!isRecording}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:bg-slate-50 disabled:text-slate-400"
                >
                  停止
                </button>
              </div>
              <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600">
                <p className="font-semibold text-slate-700">示例</p>
                <p className="mt-1">“在左上角画一个蓝色三角形”</p>
                <p>“撤销上一步” “清空画布” “保存图片”</p>
                <p>“在中间写四个字：你好世界”</p>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">网格与直线</h2>
              <div className="mt-3 space-y-3">
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} />
                  显示网格
                </label>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-slate-600">列</span>
                  <input
                    type="number"
                    min="2"
                    max="52"
                    value={gridCols}
                    onChange={(e) => setGridCols(Math.min(52, Math.max(2, parseInt(e.target.value, 10) || 12)))}
                    className="w-16 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                  />
                  <span className="text-slate-600">行</span>
                  <input
                    type="number"
                    min="2"
                    max="52"
                    value={gridRows}
                    onChange={(e) => setGridRows(Math.min(52, Math.max(2, parseInt(e.target.value, 10) || 8)))}
                    className="w-16 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                  />
                </div>
                <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
                  <input
                    value={lineFromCell}
                    onChange={(e) => setLineFromCell(e.target.value)}
                    placeholder="起点 A1"
                    className="rounded-lg border border-slate-200 px-2.5 py-2 text-sm"
                  />
                  <span className="text-sm text-slate-400">→</span>
                  <input
                    value={lineToCell}
                    onChange={(e) => setLineToCell(e.target.value)}
                    placeholder="终点 F5"
                    className="rounded-lg border border-slate-200 px-2.5 py-2 text-sm"
                  />
                </div>
                <div className="flex items-center gap-3 text-sm">
                  <span className="text-slate-600">线宽</span>
                  <input
                    type="number"
                    min="1"
                    max="12"
                    value={lineWidthSetting}
                    onChange={(e) => setLineWidthSetting(Math.min(12, Math.max(1, parseInt(e.target.value, 10) || 2)))}
                    className="w-16 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                  />
                  <label className="flex items-center gap-2 text-slate-700">
                    <input type="checkbox" checked={lineDashed} onChange={(e) => setLineDashed(e.target.checked)} />
                    虚线
                  </label>
                </div>
                <button
                  onClick={handleAddLine}
                  className="w-full rounded-xl bg-emerald-600 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-500"
                >
                  添加直线
                </button>
              </div>
            </section>

            <section className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm">
              <h2 className="text-sm font-semibold text-slate-900">AI 生图</h2>
              <p className="mt-1 text-xs text-slate-500">点击后录音，识别文本直接作为生图提示词</p>
              <button
                onClick={() => {
                  setAiFromVoiceMode(true)
                  startRecording()
                  setStatus('语音采集中（AI 生图）…')
                }}
                disabled={isRecording || aiGenerating}
                className="mt-3 w-full rounded-xl bg-indigo-600 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:bg-indigo-200 disabled:text-indigo-700"
              >
                {isRecording ? '录音中…' : '语音生成图片'}
              </button>
            </section>
          </aside>

          <section className="space-y-4 lg:col-span-8">
            <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-[0_12px_32px_rgba(15,23,42,0.08)]">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Canvas Stage</p>
                  <h2 className="text-lg font-semibold text-slate-900">绘图工作台</h2>
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span>当前状态</span>
                  <StatusChip status={status} />
                </div>
              </div>
              <div className="rounded-2xl border border-slate-100 bg-slate-50 p-2">
                <canvas
                  ref={canvasRef}
                  className="w-full rounded-xl border border-slate-200 bg-white shadow-inner"
                  width="1120"
                  height="680"
                />
              </div>
              <div className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500">
                <p>仅语音下达指令，画布不接受鼠标/键盘操作。</p>
                <button
                  onClick={() => saveCurrentAndReset(`画板-${new Date().toLocaleTimeString()}`)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700 transition hover:bg-slate-100"
                >
                  保存并新建画板
                </button>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-slate-900">识别与回复</h3>
                <p className="mt-3 text-xs text-slate-500">ASR 文本</p>
                <div className="mt-1 min-h-[44px] rounded-lg border border-slate-100 bg-slate-50 p-2 text-sm text-slate-800">
                  {asrText}
                </div>
                <p className="mt-3 text-xs text-slate-500">回复文本</p>
                <div className="mt-1 min-h-[44px] rounded-lg border border-emerald-100 bg-emerald-50/60 p-2 text-sm text-emerald-700">
                  {replyText}
                </div>
                <h3 className="mt-4 text-sm font-semibold text-slate-900">解析命令</h3>
                <pre className="mt-2 min-h-[150px] whitespace-pre-wrap rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs text-slate-700">
                  {commandJson}
                </pre>
              </div>

              <div className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm">
                <h3 className="text-sm font-semibold text-slate-900">历史记录</h3>
                <div className="mt-3 max-h-56 space-y-2 overflow-y-auto text-xs text-slate-700">
                  {history.slice(0, 20).map((h, idx) => (
                    <div key={`${h.ts}-${idx}`} className="rounded-lg border border-slate-100 bg-slate-50 p-2.5">
                      <div className="text-[11px] text-slate-500">{h.ts}</div>
                      <div className="text-[12px] text-slate-800">ASR: {h.asr || ''}</div>
                      <div className="text-[12px] text-emerald-700">Reply: {h.reply || ''}</div>
                      <div className="text-[11px] text-slate-600">Cmds: {JSON.stringify(h.commands || [])}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 border-t border-slate-100 pt-3">
                  <p className="text-sm font-semibold text-slate-900">提示词规范</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-600">
                    {guidance.map((g) => (
                      <li key={g}>{g}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            <section className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={saveTitle}
                  onChange={(e) => setSaveTitle(e.target.value)}
                  placeholder="保存名称（可选）"
                  className="rounded-xl border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400"
                />
                <button
                  onClick={saveDrawing}
                  disabled={saving}
                  className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:bg-emerald-200 disabled:text-emerald-700"
                >
                  {saving ? '保存中…' : '保存当前画板'}
                </button>
                <button
                  onClick={fetchDrawings}
                  disabled={loadingDrawings}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100 disabled:bg-slate-50 disabled:text-slate-400"
                >
                  {loadingDrawings ? '刷新中…' : '刷新列表'}
                </button>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {drawings.map((d) => (
                  <div
                    key={d.id}
                    className="rounded-xl border border-slate-200 bg-white p-3 transition hover:-translate-y-0.5 hover:border-emerald-300 hover:shadow-sm"
                  >
                    <div className="truncate text-sm font-semibold text-slate-900">{d.title || `画板 #${d.id}`}</div>
                    <div className="mt-1 text-xs text-slate-500">ID: {d.id}</div>
                    <div className="text-xs text-slate-500">命令数：{d.commands?.length || 0}</div>
                    <div className="text-xs text-slate-500">{d.created_at}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        onClick={() => loadDrawing(d.id)}
                        disabled={loadingDrawings}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
                      >
                        加载
                      </button>
                      <button
                        onClick={() => overwriteDrawing(d)}
                        disabled={loadingDrawings}
                        className="rounded-lg border border-emerald-200 px-2.5 py-1 text-xs font-medium text-emerald-700 transition hover:bg-emerald-50"
                      >
                        覆盖
                      </button>
                      <button
                        onClick={() => deleteDrawing(d.id)}
                        disabled={loadingDrawings}
                        className="rounded-lg border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-700 transition hover:bg-rose-50"
                      >
                        删除
                      </button>
                    </div>
                  </div>
                ))}
                {!drawings.length && !loadingDrawings && (
                  <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">
                    暂无保存画板，先创作一张并保存。
                  </div>
                )}
              </div>

              <div className="mt-4 border-t border-slate-100 pt-3">
                <p className="text-xs font-semibold text-slate-700">标准指令白名单</p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {defaultCommandsHint.map((line) => (
                    <span key={line} className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-600">
                      {line}
                    </span>
                  ))}
                </div>
              </div>
            </section>
          </section>
        </main>
      </div>
    </div>
  )
}

export default App
