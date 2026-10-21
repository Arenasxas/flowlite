package ar.flowlite

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.provider.Settings
import android.util.Base64
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.core.content.FileProvider
import com.google.android.gms.auth.api.identity.AuthorizationRequest
import com.google.android.gms.auth.api.identity.AuthorizationResult
import com.google.android.gms.auth.api.identity.Identity
import com.google.android.gms.common.api.Scope
import org.json.JSONObject
import java.io.File

/** La app web de FlowLite adentro de Android, con lo que el navegador no puede: audio del celular, teclado y Drive nativo. */
class MainActivity : Activity() {
    companion object {
        const val URL = "https://arenasxas.github.io/flowlite/"
        const val REQ_PERMS = 1
        const val REQ_CAPTURE = 2
        const val REQ_FILE = 3
        const val REQ_AUTH = 4
    }

    private lateinit var web: WebView
    private var pendingWeb: PermissionRequest? = null
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var photoUri: Uri? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        web = WebView(this)
        setContentView(web)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false
        }
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, req: android.webkit.WebResourceRequest): Boolean {
                val u = req.url
                if (u.host == "arenasxas.github.io" || u.scheme == "blob" || u.scheme == "data") return false
                startActivity(Intent(Intent.ACTION_VIEW, u)) // links de afuera (Groq, Google) en el navegador
                return true
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                runOnUiThread {
                    val need = mutableListOf<String>()
                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE in request.resources) need += Manifest.permission.RECORD_AUDIO
                    if (PermissionRequest.RESOURCE_VIDEO_CAPTURE in request.resources) need += Manifest.permission.CAMERA
                    val missing = need.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
                    if (missing.isEmpty()) request.grant(request.resources)
                    else { pendingWeb = request; requestPermissions(missing.toTypedArray(), REQ_PERMS) }
                }
            }

            override fun onShowFileChooser(view: WebView, cb: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = cb
                val pick = params.createIntent()
                val intent = if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    val f = File(cacheDir, "fotos").apply { mkdirs() }.let { File(it, "foto.jpg") }
                    photoUri = FileProvider.getUriForFile(this@MainActivity, "$packageName.fotos", f)
                    val cam = Intent(MediaStore.ACTION_IMAGE_CAPTURE).putExtra(MediaStore.EXTRA_OUTPUT, photoUri)
                        .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                    if (params.isCaptureEnabled) cam
                    else Intent.createChooser(pick, "Foto").putExtra(Intent.EXTRA_INITIAL_INTENTS, arrayOf(cam))
                } else { photoUri = null; pick }
                return try { startActivityForResult(intent, REQ_FILE); true } catch (e: Exception) { fileCallback = null; false }
            }
        }
        web.addJavascriptInterface(Bridge(), "FlowLiteAndroid")
        CaptureService.onChunk = { wav, start ->
            js("window.flowliteOnDeviceChunk && flowliteOnDeviceChunk('${Base64.encodeToString(wav, Base64.NO_WRAP)}', $start)")
        }
        CaptureService.onStatus = { text -> js("window.flowliteOnDeviceStatus && flowliteOnDeviceStatus(${JSONObject.quote(text)})") }
        // el teclado necesita el permiso del micrófono, y solo se puede pedir desde acá
        val ask = listOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.POST_NOTIFICATIONS)
            .filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (ask.isNotEmpty()) requestPermissions(ask.toTypedArray(), REQ_PERMS)
        if (saved == null) web.loadUrl(URL) else web.restoreState(saved)
    }

    private fun js(code: String) = runOnUiThread { web.evaluateJavascript(code, null) }

    override fun onSaveInstanceState(out: Bundle) { super.onSaveInstanceState(out); web.saveState(out) }

    @Deprecated("Activity sin AndroidX")
    override fun onBackPressed() { if (web.canGoBack()) web.goBack() else @Suppress("DEPRECATION") super.onBackPressed() }

    override fun onRequestPermissionsResult(code: Int, perms: Array<String>, results: IntArray) {
        super.onRequestPermissionsResult(code, perms, results)
        val req = pendingWeb ?: return
        pendingWeb = null
        val ok = req.resources.filter {
            val p = if (it == PermissionRequest.RESOURCE_VIDEO_CAPTURE) Manifest.permission.CAMERA else Manifest.permission.RECORD_AUDIO
            checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED
        }
        if (ok.isEmpty()) req.deny() else req.grant(ok.toTypedArray())
    }

    @Deprecated("Activity sin AndroidX")
    override fun onActivityResult(code: Int, result: Int, data: Intent?) {
        @Suppress("DEPRECATION") super.onActivityResult(code, result, data)
        when (code) {
            REQ_CAPTURE ->
                if (result == RESULT_OK && data != null)
                    startForegroundService(Intent(this, CaptureService::class.java).putExtra("code", result).putExtra("data", data))
                else js("window.flowliteOnDeviceStatus && flowliteOnDeviceStatus('No diste permiso para grabar el audio del celular')")
            REQ_FILE -> {
                val picked = data?.data
                val uris = when {
                    result != RESULT_OK -> null
                    picked != null -> arrayOf(picked)
                    photoUri != null -> arrayOf(photoUri!!)
                    else -> null
                }
                fileCallback?.onReceiveValue(uris)
                fileCallback = null
            }
            REQ_AUTH -> try {
                val r = Identity.getAuthorizationClient(this).getAuthorizationResultFromIntent(data)
                driveToken(r)
            } catch (e: Exception) { driveError(e.message ?: "Cancelado") }
        }
    }

    private fun driveToken(r: AuthorizationResult) =
        js("window.flowliteOnDriveToken && flowliteOnDriveToken(${JSONObject.quote(r.accessToken ?: "")}, null)")

    private fun driveError(msg: String) = js("window.flowliteOnDriveToken && flowliteOnDriveToken(null, ${JSONObject.quote(msg)})")

    inner class Bridge {
        @JavascriptInterface fun isAvailable() = true

        @JavascriptInterface fun saveKeys(groq: String, gemini: String) {
            Groq.prefs(this@MainActivity).edit().putString("groq", groq).putString("gemini", gemini).apply()
        }

        @JavascriptInterface fun saveSettings(language: String, vocab: String) {
            Groq.prefs(this@MainActivity).edit().putString("language", language).putString("vocab", vocab).apply()
        }

        @JavascriptInterface fun startDeviceAudio() = runOnUiThread {
            val mpm = getSystemService(MediaProjectionManager::class.java)
            @Suppress("DEPRECATION") startActivityForResult(mpm.createScreenCaptureIntent(), REQ_CAPTURE)
        }

        @JavascriptInterface fun stopDeviceAudio() { CaptureService.running = false }

        @JavascriptInterface fun openKeyboardSettings() = runOnUiThread {
            startActivity(Intent(Settings.ACTION_INPUT_METHOD_SETTINGS))
        }

        /** Permiso de Google Drive con la cuenta del celular (en un WebView Google no deja iniciar sesión). */
        @JavascriptInterface fun requestDriveToken() = runOnUiThread {
            val req = AuthorizationRequest.builder()
                .setRequestedScopes(listOf(Scope("https://www.googleapis.com/auth/drive"))).build()
            Identity.getAuthorizationClient(this@MainActivity).authorize(req)
                .addOnSuccessListener { r ->
                    val pi = r.pendingIntent
                    if (r.hasResolution() && pi != null) {
                        try { @Suppress("DEPRECATION") startIntentSenderForResult(pi.intentSender, REQ_AUTH, null, 0, 0, 0) }
                        catch (e: Exception) { driveError(e.message ?: "No pude pedir el permiso") }
                    } else driveToken(r)
                }
                .addOnFailureListener { e -> driveError(e.message ?: "No pude conectar Drive") }
        }
    }
}
