package ar.flowlite

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

/** Lo mínimo de Groq para el teclado: transcribir (Whisper) y pulir o aplicar un comando. Mismos prompts que la PC. */
object Groq {
    private const val BASE = "https://api.groq.com/openai/v1"

    fun prefs(ctx: Context) = ctx.getSharedPreferences("flowlite", Context.MODE_PRIVATE)
    fun key(ctx: Context) = prefs(ctx).getString("groq", "") ?: ""

    private var prompts: JSONObject? = null
    fun prompt(ctx: Context, name: String): String {
        val p = prompts ?: JSONObject(ctx.assets.open("prompts.json").bufferedReader(Charsets.UTF_8).readText()).also { prompts = it }
        return p.getString(name)
    }

    private fun open(path: String, key: String): HttpURLConnection =
        (URL(BASE + path).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15000
            readTimeout = 60000
            doOutput = true
            setRequestProperty("Authorization", "Bearer $key")
        }

    private fun read(c: HttpURLConnection): String {
        val code = c.responseCode
        val body = (if (code in 200..299) c.inputStream else c.errorStream)?.bufferedReader(Charsets.UTF_8)?.readText() ?: ""
        if (code !in 200..299) throw RuntimeException(if (code == 401) "La clave de Groq no funciona" else "Groq $code: ${body.take(120)}")
        return body
    }

    fun transcribe(ctx: Context, wav: ByteArray): String {
        val b = "----flowlite${System.nanoTime()}"
        val out = ByteArrayOutputStream()
        fun field(name: String, value: String) =
            out.write("--$b\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n".toByteArray())
        field("model", "whisper-large-v3-turbo")
        field("response_format", "json")
        field("temperature", "0")
        val lang = prefs(ctx).getString("language", "es") ?: "es"
        if (lang != "auto") field("language", lang)
        field("prompt", whisperHelp(ctx))
        out.write("--$b\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n".toByteArray())
        out.write(wav)
        out.write("\r\n--$b--\r\n".toByteArray())
        val c = open("/audio/transcriptions", key(ctx))
        c.setRequestProperty("Content-Type", "multipart/form-data; boundary=$b")
        c.outputStream.use { it.write(out.toByteArray()) }
        return fixTech(ctx, JSONObject(read(c)).optString("text").trim())
    }

    fun chat(ctx: Context, system: String, user: String, model: String = "openai/gpt-oss-20b"): String {
        val body = JSONObject()
            .put("model", model).put("temperature", 0.2).put("reasoning_effort", "low").put("include_reasoning", false)
            .put("messages", JSONArray()
                .put(JSONObject().put("role", "system").put("content", system))
                .put(JSONObject().put("role", "user").put("content", user)))
        val c = open("/chat/completions", key(ctx))
        c.setRequestProperty("Content-Type", "application/json")
        c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
        return JSONObject(read(c)).getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content").trim()
    }

    private fun list(ctx: Context, name: String): List<String> {
        prompt(ctx, "polish") // carga prompts.json
        val a = prompts!!.optJSONArray(name) ?: return emptyList()
        return (0 until a.length()).map { a.getString(it) }
    }

    private fun own(ctx: Context) = (prefs(ctx).getString("vocab", "") ?: "").split(",").map { it.trim() }.filter { it.isNotEmpty() }

    /** Ayuda para Whisper: primero IA y tecnología; si no entra todo, queda lo propio al final. */
    fun whisperHelp(ctx: Context) = (list(ctx, "tech_vocab") + own(ctx).takeLast(40)).joinToString(", ").takeLast(800)

    private var fixes: List<Pair<Regex, String>>? = null

    /** Errores típicos de Whisper con nombres de IA y tecnología ("Cloud Code" → "Claude Code"). Lista en prompts.json. */
    fun fixTech(ctx: Context, text: String): String {
        val f = fixes ?: run {
            prompt(ctx, "polish")
            val a = prompts!!.optJSONArray("tech_fixes")
            (0 until (a?.length() ?: 0)).map {
                val pair = a!!.getJSONArray(it)
                Regex("(?iu)(?<![\\p{L}\\p{N}_])(?:${pair.getString(0)})(?![\\p{L}\\p{N}_])") to pair.getString(1)
            }.also { fixes = it }
        }
        var out = text
        for ((rx, rep) in f) out = rx.replace(out, Regex.escapeReplacement(rep))
        return out
    }

    /** Whisper con casi silencio a veces devuelve la lista de la ayuda. */
    fun promptEcho(ctx: Context, text: String): Boolean {
        fun words(s: String) = java.text.Normalizer.normalize(s.lowercase(), java.text.Normalizer.Form.NFD)
            .replace(Regex("[^a-z0-9 ]"), " ").split(" ").filter { it.isNotEmpty() }
        val w = words(text)
        val known = words(whisperHelp(ctx)).toSet()
        return w.size >= 3 && known.containsAll(w)
    }

    fun polish(ctx: Context, text: String, app: String): String {
        val mine = own(ctx)
        val have = mine.map { it.lowercase() }.toSet()
        val vocab = (mine + list(ctx, "tech_vocab").filter { it.lowercase() !in have }).joinToString(", ")
        return fixTech(ctx, chat(ctx, prompt(ctx, "polish").replace("{vocab}", vocab).replace("{app}", app.ifEmpty { "celular" }), text))
    }

    /** Igual que groq_command de la PC. */
    fun command(ctx: Context, instruction: String, selected: String, app: String): String =
        chat(ctx, prompt(ctx, "command"),
            "Instrucción: $instruction\nApp: ${app.ifEmpty { "desconocida" }}\nTexto seleccionado:\n${selected.ifEmpty { "(nada)" }}",
            model = "openai/gpt-oss-120b")

    /** PCM 16 bits mono → WAV. */
    fun wav(pcm: ByteArray, rate: Int = 16000): ByteArray {
        val out = ByteArrayOutputStream(pcm.size + 44)
        fun i32(v: Int) = out.write(byteArrayOf(v.toByte(), (v shr 8).toByte(), (v shr 16).toByte(), (v shr 24).toByte()))
        fun i16(v: Int) = out.write(byteArrayOf(v.toByte(), (v shr 8).toByte()))
        out.write("RIFF".toByteArray()); i32(36 + pcm.size); out.write("WAVEfmt ".toByteArray())
        i32(16); i16(1); i16(1); i32(rate); i32(rate * 2); i16(2); i16(16)
        out.write("data".toByteArray()); i32(pcm.size); out.write(pcm)
        return out.toByteArray()
    }

    /** Volumen medio (0 = silencio total). */
    fun rms(pcm: ByteArray, len: Int = pcm.size): Double {
        var sum = 0.0
        var n = 0
        var i = 0
        while (i + 1 < len) {
            val s = ((pcm[i + 1].toInt() shl 8) or (pcm[i].toInt() and 0xff)).toShort().toDouble()
            sum += s * s; n++; i += 2
        }
        return if (n == 0) 0.0 else Math.sqrt(sum / n)
    }
}
