package ar.flowlite

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import java.io.ByteArrayOutputStream
import kotlin.concurrent.thread

/**
 * Graba lo que suena en el celular (videos, YouTube, clases grabadas del campus) y lo entrega en tramos de 60 s.
 * Android no deja grabar llamadas ni videollamadas: con una llamada activa llega silencio, y se avisa.
 */
class CaptureService : Service() {
    companion object {
        const val RATE = 16000
        const val CHUNK_SEC = 60
        var onChunk: ((ByteArray, Double) -> Unit)? = null
        var onStatus: ((String) -> Unit)? = null
        @Volatile var running = false
    }

    private var projection: MediaProjection? = null
    private val main = Handler(Looper.getMainLooper())

    override fun onBind(intent: Intent?): IBinder? = null

    @SuppressLint("MissingPermission")
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null || running) return START_NOT_STICKY
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("rec", "Grabación", NotificationManager.IMPORTANCE_LOW))
        val n = Notification.Builder(this, "rec")
            .setContentTitle("FlowLite está grabando el audio del celular")
            .setContentText("Volvé a FlowLite y tocá Terminar para armar los apuntes")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .build()
        startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION)

        val mpm = getSystemService(MediaProjectionManager::class.java)
        @Suppress("DEPRECATION")
        val data = intent.getParcelableExtra<Intent>("data") ?: return START_NOT_STICKY
        val p = mpm.getMediaProjection(intent.getIntExtra("code", 0), data) ?: return START_NOT_STICKY
        projection = p
        p.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() { running = false }
        }, main)

        val config = AudioPlaybackCaptureConfiguration.Builder(p)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
            .addMatchingUsage(AudioAttributes.USAGE_GAME)
            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
            .build()
        val format = AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(RATE).setChannelMask(AudioFormat.CHANNEL_IN_MONO).build()
        val rec = AudioRecord.Builder().setAudioFormat(format).setAudioPlaybackCaptureConfig(config)
            .setBufferSizeInBytes(RATE * 2).build()
        running = true
        rec.startRecording()
        thread {
            val buf = ByteArray(3200)
            val chunk = ByteArrayOutputStream()
            var start = 0.0
            var quiet = 0
            fun flush() {
                val pcm = chunk.toByteArray()
                chunk.reset()
                if (pcm.size < RATE) return
                val loud = Groq.rms(pcm) > 30
                quiet = if (loud) 0 else quiet + 1
                if (quiet == 2) main.post {
                    onStatus?.invoke("🔇 No llega sonido del celular. ¿Está en pausa el video? Si hay una llamada, Android no deja grabarla.")
                }
                val at = start
                start += pcm.size / (RATE * 2.0)
                val wav = Groq.wav(pcm, RATE)
                main.post { onChunk?.invoke(wav, at) }
            }
            while (running) {
                val n = rec.read(buf, 0, buf.size)
                if (n > 0) chunk.write(buf, 0, n)
                if (chunk.size() >= RATE * 2 * CHUNK_SEC) flush()
            }
            flush()
            rec.stop(); rec.release()
            main.post { projection?.stop(); stopForeground(STOP_FOREGROUND_REMOVE); stopSelf() }
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = false
        super.onDestroy()
    }
}
