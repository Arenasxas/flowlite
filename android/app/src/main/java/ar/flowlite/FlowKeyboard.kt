package ar.flowlite

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.inputmethodservice.InputMethodService
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.io.ByteArrayOutputStream
import kotlin.concurrent.thread

/**
 * Teclado de dictado para cualquier app: mantener el botón, hablar, soltar → texto pulido escrito donde está el cursor.
 * Si hay texto seleccionado, lo que se dice es una instrucción sobre ese texto (modo comando, como Shift en la PC).
 */
class FlowKeyboard : InputMethodService() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private lateinit var mic: Button
    @Volatile private var recording = false
    private var worker: Thread? = null
    private val pcm = ByteArrayOutputStream()

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun button(text: String, color: Int, weight: Float) = Button(this).apply {
        this.text = text
        textSize = 18f
        isAllCaps = false
        setTextColor(Color.WHITE)
        background = GradientDrawable().apply { cornerRadius = dp(14).toFloat(); setColor(color) }
        layoutParams = LinearLayout.LayoutParams(0, dp(64), weight).apply { setMargins(dp(4), dp(4), dp(4), dp(4)) }
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreateInputView(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#1f2430"))
            setPadding(dp(6), dp(6), dp(6), dp(10))
        }
        status = TextView(this).apply {
            setTextColor(Color.parseColor("#c9d1e0"))
            textSize = 14f
            gravity = Gravity.CENTER
            setPadding(0, dp(4), 0, dp(4))
        }
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val change = button("🌐", Color.parseColor("#3a4152"), 1f).apply {
            setOnClickListener { if (!switchToPreviousInputMethod()) picker() }
            setOnLongClickListener { picker(); true }
        }
        mic = button("🎙 Mantené y hablá", Color.parseColor("#3b6fd8"), 3.2f)
        mic.setOnTouchListener { _, e ->
            when (e.action) {
                MotionEvent.ACTION_DOWN -> start()
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> stop()
            }
            true
        }
        val back = button("⌫", Color.parseColor("#3a4152"), 1f).apply {
            setOnClickListener { sendDownUpKeyEvents(KeyEvent.KEYCODE_DEL) }
        }
        val enter = button("↵", Color.parseColor("#3a4152"), 1f).apply {
            setOnClickListener { sendDownUpKeyEvents(KeyEvent.KEYCODE_ENTER) }
        }
        row.addView(change); row.addView(mic); row.addView(back); row.addView(enter)
        root.addView(status); root.addView(row)
        idle()
        return root
    }

    private fun picker() = (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).showInputMethodPicker()

    private fun idle() {
        status.text = when {
            Groq.key(this).isEmpty() -> "Abrí la app FlowLite y pegá tu clave de Groq en Ajustes"
            checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED ->
                "Abrí la app FlowLite una vez para dar permiso al micrófono"
            selected().isNotEmpty() -> "Texto seleccionado: decí qué hacer con él (ej. «hacelo más formal»)"
            else -> "Mantené el botón azul mientras hablás"
        }
    }

    private fun selected(): String = currentInputConnection?.getSelectedText(0)?.toString() ?: ""

    @SuppressLint("MissingPermission")
    private fun start() {
        if (recording) return
        if (Groq.key(this).isEmpty() || checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            idle(); return
        }
        val rate = 16000
        val min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, rate, AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT, maxOf(min, rate))
        if (rec.state != AudioRecord.STATE_INITIALIZED) { status.text = "No pude abrir el micrófono"; rec.release(); return }
        pcm.reset()
        recording = true
        mic.text = "🔴 Escuchando… soltá para terminar"
        status.text = if (selected().isNotEmpty()) "Modo comando sobre el texto seleccionado" else "Hablá…"
        rec.startRecording()
        worker = thread {
            val buf = ByteArray(3200)
            while (recording) {
                val n = rec.read(buf, 0, buf.size)
                if (n > 0) synchronized(pcm) { pcm.write(buf, 0, n) }
            }
            rec.stop(); rec.release()
        }
    }

    private fun stop() {
        if (!recording) return
        recording = false
        worker?.join(1000)
        mic.text = "🎙 Mantené y hablá"
        val audio = synchronized(pcm) { pcm.toByteArray() }
        if (audio.size < 16000 * 2 / 2) { status.text = "Muy corto: mantené apretado mientras hablás"; return } // < 0,5 s
        val sel = selected()
        val app = currentInputEditorInfo?.packageName ?: ""
        status.text = "Escribiendo…"
        thread {
            try {
                val raw = Groq.transcribe(this, Groq.wav(audio))
                if (raw.isBlank() || Groq.promptEcho(this, raw)) { main.post { status.text = "No se escuchó nada" }; return@thread }
                val out = if (sel.isNotEmpty()) Groq.command(this, raw, sel, app) else Groq.polish(this, raw, app)
                main.post {
                    currentInputConnection?.commitText(if (sel.isEmpty()) "$out " else out, 1)
                    idle()
                }
            } catch (e: Exception) {
                main.post { status.text = "❌ ${e.message ?: "Sin internet"}" }
            }
        }
    }

    override fun onStartInputView(info: android.view.inputmethod.EditorInfo?, restarting: Boolean) {
        super.onStartInputView(info, restarting)
        if (::status.isInitialized) idle()
    }

    override fun onUpdateSelection(oss: Int, ose: Int, nss: Int, nse: Int, cs: Int, ce: Int) {
        super.onUpdateSelection(oss, ose, nss, nse, cs, ce)
        if (::status.isInitialized && !recording && status.text != "Escribiendo…") idle()
    }
}
